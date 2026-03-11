import time

from app.core.escape import validate_updated_by
from app.services.imports import audit_service, draft_service, file_store
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import ImportJobState, JobEvent


INTERRUPTED_IMPORT_STATUSES = {"queued", "running"}
INTERRUPTED_POSTPROCESS_STATUSES = {"post_metadata_refresh", "post_es_sync"}


def create_job(*, draft_id: str, created_by: str) -> ImportJobState:
    draft = draft_service.get_draft(draft_id)
    draft = draft_service.validate_and_persist(draft_id)
    if not draft.validation or not draft.validation.passed or not draft.validation.compiled_plan:
        raise_import_http_error(
            status_code=422,
            error_code="IMPORT_DRAFT_VALIDATION_FAILED",
            message="draft validation failed; inspect validation errors before submitting a job",
            field="draft_id",
        )
    actor = validate_updated_by(created_by)
    job_id = file_store.new_id("job")
    file_store.copy_inputs_to_job(
        job_id,
        list(draft.file_ids),
        draft.model_dump(),
        draft.validation.compiled_plan.model_dump(),
    )
    state = ImportJobState(
        job_id=job_id,
        draft_id=draft_id,
        status="queued",
        created_by=actor,
        mode=draft.mode,
        plan_id=draft.validation.compiled_plan.plan_id,
        file_ids=list(draft.file_ids),
        compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
        failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
        normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
        warnings=list(draft.validation.warnings),
        integration_warnings=list(draft.validation.integration_warnings),
        integration_level=draft.validation.compiled_plan.integration_level,
        affected_schema_objects=[plan.object_name for plan in draft.validation.compiled_plan.schema_create_plan],
    )
    file_store.save_job_state(state)
    file_store.append_job_event(job_id, JobEvent(event_type="job_queued", message="job queued", context={"draft_id": draft_id}))
    file_store.append_job_log(job_id, "job queued")
    audit_service.write_import_audit("job_submit", {"job_id": job_id, "draft_id": draft_id, "actor": actor})
    return state


def get_job(job_id: str) -> ImportJobState:
    try:
        return file_store.load_job_state(job_id)
    except Exception:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_JOB_NOT_FOUND",
            message=f"job `{job_id}` not found",
            field="job_id",
        )


def list_jobs() -> list[ImportJobState]:
    return file_store.list_job_states()


def cancel_job(job_id: str) -> ImportJobState:
    state = get_job(job_id)
    if state.status in {"succeeded", "failed_import", "failed_postprocess", "cancelled"}:
        return state
    if state.status == "queued":
        state.status = "cancelled"
        state.finished_at = int(time.time())
        state.updated_at = state.finished_at
        file_store.save_job_state(state)
        file_store.append_job_event(job_id, JobEvent(event_type="job_cancelled", level="warn", message="job cancelled before start"))
        file_store.append_job_log(job_id, "job cancelled before start")
        return state
    if state.status in {"post_metadata_refresh", "post_es_sync"}:
        file_store.append_job_event(job_id, JobEvent(event_type="cancel_ignored", level="warn", message="cancel ignored during postprocess"))
        file_store.append_job_log(job_id, "cancel ignored during postprocess")
        return state
    state.cancel_requested = True
    state.updated_at = int(time.time())
    file_store.save_job_state(state)
    file_store.append_job_event(
        job_id,
        JobEvent(
            event_type="cancel_requested",
            level="warn",
            message="cancel requested; will take effect at next batch boundary",
        ),
    )
    file_store.append_job_log(job_id, "cancel requested; will take effect at next batch boundary")
    return state


def mark_interrupted_jobs() -> list[ImportJobState]:
    repaired: list[ImportJobState] = []
    for state in file_store.list_job_states():
        if state.status in INTERRUPTED_IMPORT_STATUSES:
            state.status = "failed_import"
            state.error_message = "interrupted"
            state.interrupted = True
            state.updated_at = int(time.time())
            state.finished_at = state.updated_at
            file_store.save_job_state(state)
            repaired.append(state)
        elif state.status in INTERRUPTED_POSTPROCESS_STATUSES:
            state.status = "failed_postprocess"
            state.error_message = "interrupted"
            state.interrupted = True
            state.updated_at = int(time.time())
            state.finished_at = state.updated_at
            file_store.save_job_state(state)
            repaired.append(state)
    return repaired
