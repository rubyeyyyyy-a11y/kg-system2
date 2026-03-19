import time
from pathlib import Path

from app.core.escape import validate_updated_by
from app.core.space_context import get_current_space
from app.services.imports import audit_service, draft_service, file_store, source_service
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import (
    CompiledImportPlan,
    DraftSource,
    ImportBatchRecord,
    ImportJobState,
    JobEvent,
)
from app.services.imports.state_repository import import_batches, import_job_states


INTERRUPTED_IMPORT_STATUSES = {"queued", "running"}
INTERRUPTED_POSTPROCESS_STATUSES = {"post_metadata_refresh", "post_es_sync", "post_verify_index"}


def _effective_sources(*, draft, fallback_draft) -> list[DraftSource]:
    sources = list(draft.sources or fallback_draft.sources)
    if sources:
        return sources
    file_ids = list(draft.file_ids or fallback_draft.file_ids)
    if not file_ids:
        return []
    return source_service.build_sources(file_ids, sample_rows=20)


def _hydrate_compiled_plan(
    compiled_plan: CompiledImportPlan,
    *,
    sources: list[DraftSource],
    space_name: str,
) -> CompiledImportPlan:
    hydrated_sources = list(compiled_plan.sources or sources)
    source_by_id = {source.source_id: source for source in hydrated_sources}
    default_source = hydrated_sources[0] if len(hydrated_sources) == 1 else None
    hydrated_targets = []
    for target in compiled_plan.targets:
        source = source_by_id.get(target.source_id) or default_source
        if source is None:
            hydrated_targets.append(target)
            continue
        hydrated_targets.append(
            target.model_copy(
                update={
                    "source_id": target.source_id or source.source_id,
                    "source_file_id": target.source_file_id or source.file_id,
                    "source_filename": target.source_filename or source.filename,
                    "source_columns": target.source_columns or list(source.columns),
                    "inferred_source_kind": (
                        target.inferred_source_kind
                        if str(target.inferred_source_kind or "").strip() and target.inferred_source_kind != "unknown"
                        else source.inferred_kind
                    ),
                }
            )
        )
    return compiled_plan.model_copy(
        update={
            "space_name": compiled_plan.space_name or space_name,
            "file_ids": compiled_plan.file_ids or [source.file_id for source in hydrated_sources],
            "sources": hydrated_sources,
            "targets": hydrated_targets,
        }
    )


def create_job(
    *,
    draft_id: str,
    created_by: str,
    source_type: str = "import_ui",
    is_test_data: bool = True,
    submission_id: str | None = None,
) -> ImportJobState:
    frozen_draft = draft_service.get_draft(draft_id)
    draft = draft_service.validate_and_persist(draft_id)
    if not draft.validation or not draft.validation.passed or not draft.validation.compiled_plan:
        raise_import_http_error(
            status_code=422,
            error_code="IMPORT_DRAFT_VALIDATION_FAILED",
            message="draft validation failed; inspect validation errors before submitting a job",
            field="draft_id",
        )
    actor = validate_updated_by(created_by)
    sources = _effective_sources(draft=draft, fallback_draft=frozen_draft)
    effective_space_name = draft.space_name or frozen_draft.space_name or get_current_space()
    compiled_plan = _hydrate_compiled_plan(draft.validation.compiled_plan, sources=sources, space_name=effective_space_name)
    draft_snapshot = draft.model_dump()
    if sources:
        draft_snapshot["sources"] = [source.model_dump() for source in sources]
        draft_snapshot["file_ids"] = [source.file_id for source in sources]
    draft_snapshot["space_name"] = effective_space_name
    job_id = import_job_states.next_job_id()
    batch_id = import_job_states.next_batch_id()
    import_job_states.write_execution_snapshot(
        job_id,
        file_ids=[source.file_id for source in sources] or list(draft.file_ids or frozen_draft.file_ids),
        draft_payload=draft_snapshot,
        compiled_plan=compiled_plan.model_dump(),
    )
    artifacts = import_job_states.build_job_artifacts(job_id, compiled_plan.targets)
    first_failed = next((item for item in artifacts if item.kind == "failed_rows"), None)
    first_normalized = next((item for item in artifacts if item.kind == "normalized_rows"), None)
    state = ImportJobState(
        job_id=job_id,
        draft_id=draft_id,
        batch_id=batch_id,
        space_name=effective_space_name,
        template_type=compiled_plan.template_type,
        status="queued",
        created_by=actor,
        workspace_mode=draft.workspace_mode,
        plan_id=compiled_plan.plan_id,
        file_ids=[source.file_id for source in sources] or list(draft.file_ids or frozen_draft.file_ids),
        sources=sources,
        targets=compiled_plan.targets,
        compiled_plan_path=import_job_states.compiled_plan_path(job_id),
        artifacts=artifacts,
        failed_rows_path=first_failed.path if first_failed else None,
        normalized_rows_path=first_normalized.path if first_normalized else None,
        warnings=list(draft.validation.warnings),
        integration_warnings=list(draft.validation.integration_warnings),
        integration_level=compiled_plan.integration_level,
        affected_schema_objects=[plan.object_name for plan in compiled_plan.schema_create_plan],
    )
    import_job_states.save(state)
    import_batches.save(
        ImportBatchRecord(
            batch_id=batch_id,
            space_id=effective_space_name,
            source_type="team_ingestion" if source_type == "team_ingestion" else "import_ui",
            is_test_data=bool(is_test_data),
            draft_id=draft_id,
            job_id=job_id,
            submission_id=submission_id,
            status="queued",
            cleanup_status="not_requested" if is_test_data else "not_supported",
        )
    )
    import_job_states.append_event(job_id, JobEvent(event_type="job_queued", message="job queued", context={"draft_id": draft_id}))
    import_job_states.append_log(job_id, "job queued")
    audit_service.write_import_audit(
        "job_submit",
        {
            "job_id": job_id,
            "batch_id": batch_id,
            "draft_id": draft_id,
            "actor": actor,
            "source_type": source_type,
            "submission_id": submission_id,
        },
    )
    return state


def get_job(job_id: str) -> ImportJobState:
    try:
        state = import_job_states.load(job_id)
    except Exception:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_JOB_NOT_FOUND",
            message=f"job `{job_id}` not found",
            field="job_id",
        )
    if str(state.space_name or get_current_space()) != get_current_space():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_JOB_NOT_FOUND",
            message=f"job `{job_id}` not found",
            field="job_id",
        )
    if not state.space_name:
        state.space_name = get_current_space()
    return state


def list_jobs() -> list[ImportJobState]:
    current_space = get_current_space()
    states = []
    for state in import_job_states.list():
        state_space = str(state.space_name or "")
        if not state_space:
            state.space_name = current_space
            state_space = current_space
        if state_space == current_space:
            states.append(state)
    return states


def cancel_job(job_id: str) -> ImportJobState:
    state = get_job(job_id)
    if state.status in {"succeeded", "failed_import", "failed_postprocess", "cancelled"}:
        return state
    if state.status == "queued":
        finished_at = int(time.time())
        state = import_job_states.update(
            job_id,
            status="cancelled",
            failure_stage="cancelled",
            finished_at=finished_at,
        )
        if state.batch_id:
            import_batches.update(state.batch_id, status="cancelled")
        import_job_states.append_event(job_id, JobEvent(event_type="job_cancelled", level="warn", message="job cancelled before start"))
        import_job_states.append_log(job_id, "job cancelled before start")
        return state
    if state.status in {"post_metadata_refresh", "post_es_sync"}:
        import_job_states.append_event(job_id, JobEvent(event_type="cancel_ignored", level="warn", message="cancel ignored during postprocess"))
        import_job_states.append_log(job_id, "cancel ignored during postprocess")
        return state
    state = import_job_states.update(job_id, cancel_requested=True)
    import_job_states.append_event(
        job_id,
        JobEvent(
            event_type="cancel_requested",
            level="warn",
            message="cancel requested; will take effect at next batch boundary",
        ),
    )
    import_job_states.append_log(job_id, "cancel requested; will take effect at next batch boundary")
    return state


def list_job_logs(job_id: str, *, limit: int = 200) -> list[str]:
    get_job(job_id)
    return file_store.load_job_log_lines(job_id, limit=limit)


def resolve_failed_rows_download(job_id: str) -> tuple[Path, str, str]:
    state = get_job(job_id)
    path = Path(state.failed_rows_path or "")
    if not path.exists():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_FAILED_ROWS_NOT_FOUND",
            message="failed_rows artifact not found for this job",
            field="job_id",
        )
    return path, path.name, "text/csv"


def resolve_job_artifact_download(job_id: str, artifact_name: str) -> tuple[Path, str, str]:
    state = get_job(job_id)
    artifact = next((item for item in state.artifacts if item.filename == artifact_name), None)
    if artifact is None:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_ARTIFACT_NOT_FOUND",
            message=f"artifact `{artifact_name}` not found for job `{job_id}`",
            field="artifact_name",
        )
    path = Path(artifact.path)
    if not path.exists():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_ARTIFACT_NOT_FOUND",
            message=f"artifact `{artifact_name}` not found for job `{job_id}`",
            field="artifact_name",
        )
    media_type = "application/json" if artifact.kind == "summary" else "text/csv"
    return path, artifact.filename, media_type


def mark_interrupted_jobs() -> list[ImportJobState]:
    repaired: list[ImportJobState] = []
    for state in import_job_states.list():
        if state.status in INTERRUPTED_IMPORT_STATUSES:
            finished_at = int(time.time())
            state = import_job_states.update(
                state.job_id,
                status="failed_import",
                error_message="interrupted",
                failure_stage="interrupted",
                interrupted=True,
                finished_at=finished_at,
            )
            if state.batch_id:
                import_batches.update(state.batch_id, status="failed_import")
            repaired.append(state)
        elif state.status in INTERRUPTED_POSTPROCESS_STATUSES:
            finished_at = int(time.time())
            state = import_job_states.update(
                state.job_id,
                status="failed_postprocess",
                error_message="interrupted",
                failure_stage="interrupted",
                interrupted=True,
                finished_at=finished_at,
            )
            if state.batch_id:
                import_batches.update(state.batch_id, status="failed_postprocess")
            repaired.append(state)
    return repaired
