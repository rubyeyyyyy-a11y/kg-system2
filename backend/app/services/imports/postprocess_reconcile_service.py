from __future__ import annotations

import time
from typing import Any

from app.clients.es_client import ElasticsearchClient
from app.core.space_context import get_current_space
from app.services.imports import es_postprocess_service, metadata_postprocess_service
from app.services.imports.models import ImportCompletionSummary, ImportJobState, JobEvent
from app.services.imports.state_repository import import_batches, import_job_states
from app.services.search_v2 import indexing_service
from app.services.spaces.models import SpaceIndexStatus


_POSTPROCESS_FAILURE_STAGES = ("metadata_failed", "es_sync_failed", "verify_failed", "registry_write_failed")


def _update_job_state(state: ImportJobState, **changes) -> ImportJobState:
    return import_job_states.update(state.job_id, **changes)


def _resolve_job_state(job_id: str | None) -> ImportJobState | None:
    if not job_id:
        return None
    return import_job_states.load(job_id)


def _append_job_event(job_id: str, event: JobEvent) -> None:
    import_job_states.append_event(job_id, event)


def _append_job_log(job_id: str, message: str) -> None:
    import_job_states.append_log(job_id, message)


def _failure_stage_from_message(message: str) -> str | None:
    text = str(message or "")
    for candidate in _POSTPROCESS_FAILURE_STAGES:
        if text.startswith(f"{candidate}:"):
            return candidate
    return None


def _resolve_sync_scope(job_state: ImportJobState | None, requested_scope: str) -> str:
    scope = str(requested_scope or "auto").strip().lower() or "auto"
    if scope not in {"auto", "none", "job", "space"}:
        raise ValueError(f"unsupported sync_scope `{scope}`")
    if scope != "auto":
        return scope
    if job_state is None:
        return "none"
    completion_summary = job_state.completion_summary
    if completion_summary is not None and completion_summary.post_es_sync_success:
        return "none"
    if job_state.affected_entity_vids:
        return "job"
    return "none"


def _resolve_refresh_metadata(job_state: ImportJobState | None, refresh_metadata: bool | None) -> bool:
    if refresh_metadata is not None:
        return bool(refresh_metadata)
    if job_state is None:
        return False
    return not bool(job_state.metadata_refreshed)


def _sync_full_space(space_name: str) -> dict[str, Any]:
    es_client = ElasticsearchClient()
    total_docs = 0
    total_ok = 0
    total_fail = 0
    total_bulk_ms = 0.0
    batch_count = 0
    pending_batch = None

    for batch in indexing_service.iter_entity_doc_batches(
        space_name,
        after_vid=0,
        batch_size=indexing_service.DEFAULT_BULK_UPSERT_BATCH_SIZE,
    ):
        if pending_batch is None:
            pending_batch = batch
            continue
        batch_count += 1
        result = indexing_service.bulk_upsert(
            space_name,
            pending_batch["docs"],
            es_client=es_client,
            ensure_index=batch_count == 1,
            refresh="false",
        )
        total_docs += len(pending_batch["docs"])
        total_ok += int(result["ok_count"])
        total_fail += int(result["fail_count"])
        total_bulk_ms += float(result["bulk_ms"])
        pending_batch = batch

    if pending_batch is not None:
        batch_count += 1
        result = indexing_service.bulk_upsert(
            space_name,
            pending_batch["docs"],
            es_client=es_client,
            ensure_index=batch_count == 1,
            refresh="wait_for",
        )
        total_docs += len(pending_batch["docs"])
        total_ok += int(result["ok_count"])
        total_fail += int(result["fail_count"])
        total_bulk_ms += float(result["bulk_ms"])

    return {
        "skipped": pending_batch is None and batch_count == 0,
        "space_name": space_name,
        "docs": total_docs,
        "ok_count": total_ok,
        "fail_count": total_fail,
        "bulk_ms": round(total_bulk_ms, 3),
        "batch_count": batch_count,
        "mode": "space",
    }


def _finalize_job_postprocess(
    job_state: ImportJobState,
    *,
    resolved_space: str,
    resolved_refresh_metadata: bool,
    completion_summary: ImportCompletionSummary,
    index_status_snapshot: SpaceIndexStatus | None,
    event_type: str,
    message: str,
) -> ImportJobState:
    next_status = "succeeded" if completion_summary.searchable else "failed_postprocess"
    updated = _update_job_state(
        job_state,
        status=next_status,
        metadata_refreshed=job_state.metadata_refreshed or resolved_refresh_metadata,
        completion_summary=completion_summary,
        index_status_snapshot=index_status_snapshot,
        error_message=None if completion_summary.searchable else completion_summary.note,
        failure_stage=completion_summary.failure_stage,
        finished_at=int(time.time()),
    )
    if updated.batch_id:
        import_batches.update(updated.batch_id, searchable=bool(completion_summary.searchable))
    _append_job_event(
        updated.job_id,
        JobEvent(
            event_type=event_type,
            message=message,
            context={
                "space_name": resolved_space,
                "searchable": completion_summary.searchable,
                "failure_stage": completion_summary.failure_stage,
            },
        ),
    )
    _append_job_log(
        updated.job_id,
        f"postprocess_reconcile done space={resolved_space} searchable={completion_summary.searchable} failure_stage={completion_summary.failure_stage or '-'}",
    )
    return updated


def _mark_postprocess_failure(
    job_state: ImportJobState,
    *,
    resolved_space: str,
    error: Exception,
    event_type: str,
    message: str,
) -> ImportJobState:
    error_message = str(error)
    failure_stage = _failure_stage_from_message(error_message)
    updated = _update_job_state(
        job_state,
        status="failed_postprocess",
        error_message=error_message,
        failure_stage=failure_stage,
        finished_at=int(time.time()),
    )
    _append_job_event(
        updated.job_id,
        JobEvent(
            event_type=event_type,
            level="error",
            message=message,
            context={"space_name": resolved_space, "error": error_message, "failure_stage": failure_stage},
        ),
    )
    _append_job_log(
        updated.job_id,
        f"postprocess_reconcile failed space={resolved_space} failure_stage={failure_stage or '-'} error={error_message}",
    )
    return updated


def _run_postprocess(
    *,
    space_name: str | None,
    job_state: ImportJobState | None,
    actor: str,
    refresh_metadata: bool | None,
    sync_scope: str,
    metadata_service,
    es_service,
    manage_job_status: bool,
    start_event_type: str,
    start_message: str,
    success_event_type: str,
    success_message: str,
    failure_event_type: str,
    failure_message: str,
) -> dict[str, Any]:
    resolved_space = str(space_name or (job_state.space_name if job_state is not None else get_current_space())).strip()
    if not resolved_space:
        raise ValueError("space_name is required")

    resolved_refresh_metadata = _resolve_refresh_metadata(job_state, refresh_metadata)
    resolved_sync_scope = _resolve_sync_scope(job_state, sync_scope)
    affected_vids = [] if job_state is None else sorted({int(vid) for vid in job_state.affected_entity_vids if int(vid) > 0})

    if job_state is not None:
        _append_job_event(
            job_state.job_id,
            JobEvent(
                event_type=start_event_type,
                message=start_message,
                context={
                    "space_name": resolved_space,
                    "refresh_metadata": resolved_refresh_metadata,
                    "sync_scope": resolved_sync_scope,
                },
            ),
        )
        _append_job_log(
            job_state.job_id,
            f"postprocess_reconcile start space={resolved_space} refresh_metadata={resolved_refresh_metadata} sync_scope={resolved_sync_scope}",
        )

    metadata_summary = {"skipped": True, "reason": "not_requested"}
    sync_summary = {"skipped": True, "reason": "not_requested", "space_name": resolved_space}
    verify_summary = None
    completion_summary = None
    index_status_snapshot = None

    try:
        if resolved_refresh_metadata:
            if job_state is not None and manage_job_status:
                job_state = _update_job_state(job_state, status="post_metadata_refresh", failure_stage=None)
            metadata_summary = metadata_service.refresh_from_db(actor=actor, space_name=resolved_space)
            if job_state is not None:
                job_state = _update_job_state(job_state, metadata_refreshed=True)

        if resolved_sync_scope == "job":
            if job_state is not None and manage_job_status:
                job_state = _update_job_state(job_state, status="post_es_sync", failure_stage=None)
            sync_summary = (
                {"skipped": True, "reason": "no_affected_entity_vids", "space_name": resolved_space}
                if not affected_vids
                else es_service.sync_entities(affected_vids, space_name=resolved_space)
            )
            if int(sync_summary.get("fail_count") or 0) > 0:
                raise RuntimeError(f"es_sync_failed: fail_count={sync_summary['fail_count']}")
        elif resolved_sync_scope == "space":
            if job_state is not None and manage_job_status:
                job_state = _update_job_state(job_state, status="post_es_sync", failure_stage=None)
            sync_summary = _sync_full_space(resolved_space)
            if int(sync_summary.get("fail_count") or 0) > 0:
                raise RuntimeError(f"es_sync_failed: fail_count={sync_summary['fail_count']}")
        elif job_state is not None:
            job_state = _update_job_state(job_state, es_sync_skipped=True)

        if job_state is not None and manage_job_status:
            job_state = _update_job_state(job_state, status="post_verify_index", failure_stage=None)
        verify_vids = affected_vids if resolved_sync_scope == "job" else []
        verify_summary = es_service.post_verify_index(
            verify_vids,
            space_name=resolved_space,
            batch_id=None if job_state is None else (job_state.batch_id or None),
        )
        completion_summary = ImportCompletionSummary.model_validate(verify_summary["completion_summary"])
        raw_index_status_snapshot = verify_summary.get("index_status_snapshot")
        index_status_snapshot = (
            None if raw_index_status_snapshot is None else SpaceIndexStatus.model_validate(raw_index_status_snapshot)
        )

        result = {
            "space_name": resolved_space,
            "job_id": None if job_state is None else job_state.job_id,
            "refresh_metadata": resolved_refresh_metadata,
            "sync_scope": resolved_sync_scope,
            "affected_entity_count": len(affected_vids),
            "metadata_summary": metadata_summary,
            "sync_summary": sync_summary,
            "verify_summary": verify_summary,
            "completion_summary": completion_summary.model_dump(),
            "index_status_snapshot": None if index_status_snapshot is None else index_status_snapshot.model_dump(),
        }

        if job_state is not None:
            _finalize_job_postprocess(
                job_state,
                resolved_space=resolved_space,
                resolved_refresh_metadata=resolved_refresh_metadata,
                completion_summary=completion_summary,
                index_status_snapshot=index_status_snapshot,
                event_type=success_event_type,
                message=success_message,
            )
        return result
    except Exception as exc:
        if job_state is not None:
            _mark_postprocess_failure(
                job_state,
                resolved_space=resolved_space,
                error=exc,
                event_type=failure_event_type,
                message=failure_message,
            )
        raise


def run_job_postprocess(
    *,
    job_id: str,
    actor: str,
    refresh_metadata: bool,
    sync_entity_es: bool,
    metadata_service=metadata_postprocess_service,
    es_service=es_postprocess_service,
) -> ImportJobState:
    job_state = import_job_states.load(job_id)
    sync_scope = "job" if sync_entity_es and job_state.affected_entity_vids else "none"
    try:
        _run_postprocess(
            space_name=job_state.space_name,
            job_state=job_state,
            actor=actor,
            refresh_metadata=refresh_metadata,
            sync_scope=sync_scope,
            metadata_service=metadata_service,
            es_service=es_service,
            manage_job_status=True,
            start_event_type="job_postprocess_started",
            start_message="running import postprocess",
            success_event_type="job_succeeded",
            success_message="import job completed",
            failure_event_type="job_postprocess_failed",
            failure_message="import postprocess failed",
        )
    except Exception:
        return import_job_states.load(job_id)
    return import_job_states.load(job_id)


def reconcile_postprocess(
    *,
    space_name: str | None = None,
    job_id: str | None = None,
    actor: str = "postprocess_reconcile",
    refresh_metadata: bool | None = None,
    sync_scope: str = "auto",
) -> dict[str, Any]:
    job_state = _resolve_job_state(job_id)
    return _run_postprocess(
        space_name=space_name,
        job_state=job_state,
        actor=actor,
        refresh_metadata=refresh_metadata,
        sync_scope=sync_scope,
        metadata_service=metadata_postprocess_service,
        es_service=es_postprocess_service,
        manage_job_status=False,
        start_event_type="job_reconcile_started",
        start_message="reconciling import postprocess",
        success_event_type="job_reconciled",
        success_message="postprocess reconcile finished",
        failure_event_type="job_reconcile_failed",
        failure_message="postprocess reconcile failed",
    )
