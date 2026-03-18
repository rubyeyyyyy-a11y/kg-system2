import hashlib
import json
import time

from app.core.escape import validate_updated_by
from app.core.space_context import get_current_space
from app.services.imports import audit_service, cleanup_planning_service, file_store
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import CleanupJobPhaseRecord, CleanupJobRecord, ImportBatchItemRecord, ImportBatchRecord
from app.services.imports.state_repository import cleanup_jobs as cleanup_jobs_repo
from app.services.imports.state_repository import import_batches


def _cleanup_request_key(*, space_id: str, batch_ids: list[str], scope: str, created_by: str) -> str:
    payload = {
        "space_id": space_id,
        "batch_ids": sorted(batch_ids),
        "scope": scope,
        "created_by": created_by,
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _require_batch(batch_id: str) -> ImportBatchRecord:
    try:
        return import_batches.load(batch_id)
    except Exception:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_BATCH_NOT_FOUND",
            message=f"batch `{batch_id}` not found",
            field="batch_id",
        )


def _require_cleanup_job(cleanup_job_id: str) -> CleanupJobRecord:
    try:
        return cleanup_jobs_repo.load(cleanup_job_id)
    except Exception:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_CLEANUP_JOB_NOT_FOUND",
            message=f"cleanup job `{cleanup_job_id}` not found",
            field="cleanup_job_id",
        )


def _validate_batch_access(batch: ImportBatchRecord) -> ImportBatchRecord:
    current_space = get_current_space()
    if str(batch.space_id or "") != current_space:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_BATCH_NOT_FOUND",
            message=f"batch `{batch.batch_id}` not found",
            field="batch_id",
        )
    return batch


def _validate_cleanup_job_access(record: CleanupJobRecord) -> CleanupJobRecord:
    current_space = get_current_space()
    if str(record.space_id or "") != current_space:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_CLEANUP_JOB_NOT_FOUND",
            message=f"cleanup job `{record.cleanup_job_id}` not found",
            field="cleanup_job_id",
        )
    return record


def list_batches() -> list[ImportBatchRecord]:
    current_space = get_current_space()
    return [item for item in import_batches.list() if str(item.space_id or "") == current_space]


def get_batch(batch_id: str) -> ImportBatchRecord:
    return _validate_batch_access(_require_batch(batch_id))


def get_batch_items(batch_id: str) -> list[ImportBatchItemRecord]:
    batch = get_batch(batch_id)
    return import_batches.load_items(batch.batch_id)


def list_cleanup_jobs() -> list[CleanupJobRecord]:
    current_space = get_current_space()
    return [item for item in cleanup_jobs_repo.list() if str(item.space_id or "") == current_space]


def get_cleanup_job(cleanup_job_id: str) -> CleanupJobRecord:
    return _validate_cleanup_job_access(_require_cleanup_job(cleanup_job_id))


def create_cleanup_job(*, batch_ids: list[str], scope: str, created_by: str) -> CleanupJobRecord:
    unique_batch_ids: list[str] = []
    for batch_id in batch_ids:
        normalized = str(batch_id or "").strip()
        if normalized and normalized not in unique_batch_ids:
            unique_batch_ids.append(normalized)
    if not unique_batch_ids:
        raise_import_http_error(
            status_code=422,
            error_code="IMPORT_CLEANUP_BATCH_IDS_REQUIRED",
            message="at least one batch_id is required",
            field="batch_ids",
        )
    if scope not in {"full_batch", "relations_only"}:
        raise_import_http_error(
            status_code=422,
            error_code="IMPORT_CLEANUP_SCOPE_INVALID",
            message=f"unsupported cleanup scope `{scope}`",
            field="scope",
        )
    actor = validate_updated_by(created_by)
    request_key = _cleanup_request_key(
        space_id=get_current_space(),
        batch_ids=unique_batch_ids,
        scope=scope,
        created_by=actor,
    )
    existing_active = next(
        (
            item
            for item in list_cleanup_jobs()
            if item.request_key == request_key and item.status in {"queued", "running"}
        ),
        None,
    )
    if existing_active is not None:
        return existing_active
    context = cleanup_planning_service.validate_cleanup_request(batch_ids=unique_batch_ids, scope=scope, created_by=actor)

    cleanup_job = CleanupJobRecord(
        cleanup_job_id=file_store.new_id("cleanup"),
        space_id=context.space_id,
        batch_ids=context.batch_ids,
        scope=context.scope,
        created_by=context.created_by,
        request_key=request_key,
        requested_relation_count=context.requested_relation_count,
        requested_entity_count=context.requested_entity_count if context.scope == "full_batch" else 0,
    )
    cleanup_jobs_repo.save(cleanup_job)
    for batch in context.batches:
        import_batches.update(batch.batch_id, cleanup_status="queued")
    audit_service.write_import_audit(
        "cleanup_job_submit",
        {
            "cleanup_job_id": cleanup_job.cleanup_job_id,
            "batch_ids": context.batch_ids,
            "scope": context.scope,
            "actor": context.created_by,
        },
    )
    return cleanup_job


def preview_cleanup_plan(
    *,
    batch_ids: list[str],
    scope: str,
    created_by: str,
) -> tuple[cleanup_planning_service.CleanupRequestContext, cleanup_planning_service.CleanupPlanningResult]:
    context = cleanup_planning_service.validate_cleanup_request(batch_ids=batch_ids, scope=scope, created_by=created_by)
    try:
        plan = cleanup_planning_service.plan_cleanup(space_id=context.space_id, batch_ids=context.batch_ids, scope=context.scope)
        return context, plan
    except cleanup_planning_service.CleanupPlanningError as exc:
        raise_import_http_error(
            status_code=500,
            error_code="IMPORT_CLEANUP_PLAN_FAILED",
            message=str(exc),
            extra={"kind": exc.kind, "detail": exc.detail},
        )


def mark_interrupted_cleanup_jobs() -> list[CleanupJobRecord]:
    repaired: list[CleanupJobRecord] = []
    for record in cleanup_jobs_repo.list():
        if record.status not in {"queued", "running"}:
            continue
        record.status = "failed"
        record.phase = "failed"
        record.final_phase = "failed"
        record.failure_phase = "interrupted"
        record.failure_kind = "process_interrupted"
        record.failure_detail = {"reason": "cleanup worker interrupted before completion"}
        record.error_message = "interrupted: cleanup worker was interrupted before completion"
        record.finished_at = int(time.time())
        if record.started_at:
            record.duration_ms = max(0, (record.finished_at - record.started_at) * 1000)
        record.phase_history.append(CleanupJobPhaseRecord(phase="failed", at=record.finished_at))
        record.updated_at = record.finished_at
        cleanup_jobs_repo.save(record)
        for batch_id in record.batch_ids:
            try:
                import_batches.update(batch_id, cleanup_status="failed")
            except Exception:
                continue
        repaired.append(record)
    return repaired
