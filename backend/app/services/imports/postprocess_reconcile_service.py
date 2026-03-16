from __future__ import annotations

import time
from typing import Any

from app.clients.es_client import ElasticsearchClient
from app.core.space_context import get_current_space
from app.services.imports import es_postprocess_service, file_store, metadata_postprocess_service
from app.services.imports.models import ImportCompletionSummary, ImportJobState, JobEvent
from app.services.search_v2 import indexing_service
from app.services.spaces.models import SpaceIndexStatus


def _update_job_state(state: ImportJobState, **changes) -> ImportJobState:
    for key, value in changes.items():
        setattr(state, key, value)
    state.updated_at = int(time.time())
    file_store.save_job_state(state)
    return state


def _resolve_job_state(job_id: str | None) -> ImportJobState | None:
    if not job_id:
        return None
    return file_store.load_job_state(job_id)


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


def reconcile_postprocess(
    *,
    space_name: str | None = None,
    job_id: str | None = None,
    actor: str = "postprocess_reconcile",
    refresh_metadata: bool | None = None,
    sync_scope: str = "auto",
) -> dict[str, Any]:
    job_state = _resolve_job_state(job_id)
    resolved_space = str(space_name or (job_state.space_name if job_state is not None else get_current_space())).strip()
    if not resolved_space:
        raise ValueError("space_name is required")

    resolved_refresh_metadata = _resolve_refresh_metadata(job_state, refresh_metadata)
    resolved_sync_scope = _resolve_sync_scope(job_state, sync_scope)
    affected_vids = [] if job_state is None else sorted({int(vid) for vid in job_state.affected_entity_vids if int(vid) > 0})

    if job_state is not None:
        file_store.append_job_event(
            job_state.job_id,
            JobEvent(
                event_type="job_reconcile_started",
                message="reconciling import postprocess",
                context={
                    "space_name": resolved_space,
                    "refresh_metadata": resolved_refresh_metadata,
                    "sync_scope": resolved_sync_scope,
                },
            ),
        )
        file_store.append_job_log(
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
            metadata_summary = metadata_postprocess_service.refresh_from_db(actor=actor, space_name=resolved_space)
        if resolved_sync_scope == "job":
            sync_summary = (
                {"skipped": True, "reason": "no_affected_entity_vids", "space_name": resolved_space}
                if not affected_vids
                else es_postprocess_service.sync_entities(affected_vids, space_name=resolved_space)
            )
            if int(sync_summary.get("fail_count") or 0) > 0:
                raise RuntimeError(f"es_sync_failed: fail_count={sync_summary['fail_count']}")
        elif resolved_sync_scope == "space":
            sync_summary = _sync_full_space(resolved_space)
            if int(sync_summary.get("fail_count") or 0) > 0:
                raise RuntimeError(f"es_sync_failed: fail_count={sync_summary['fail_count']}")

        verify_vids = affected_vids if resolved_sync_scope == "job" else []
        verify_summary = es_postprocess_service.post_verify_index(verify_vids, space_name=resolved_space)
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
            next_status = "succeeded" if completion_summary.searchable else "failed_postprocess"
            _update_job_state(
                job_state,
                status=next_status,
                metadata_refreshed=job_state.metadata_refreshed or resolved_refresh_metadata,
                completion_summary=completion_summary,
                index_status_snapshot=index_status_snapshot,
                error_message=None if completion_summary.searchable else completion_summary.note,
                failure_stage=completion_summary.failure_stage,
                finished_at=int(time.time()),
            )
            file_store.append_job_event(
                job_state.job_id,
                JobEvent(
                    event_type="job_reconciled" if completion_summary.searchable else "job_reconcile_failed",
                    message="postprocess reconcile finished",
                    context={
                        "space_name": resolved_space,
                        "searchable": completion_summary.searchable,
                        "failure_stage": completion_summary.failure_stage,
                    },
                ),
            )
            file_store.append_job_log(
                job_state.job_id,
                f"postprocess_reconcile done space={resolved_space} searchable={completion_summary.searchable} failure_stage={completion_summary.failure_stage or '-'}",
            )
        return result
    except Exception as exc:
        if job_state is not None:
            failure_stage = None
            message = str(exc)
            for candidate in ("metadata_failed", "es_sync_failed", "verify_failed", "registry_write_failed"):
                if message.startswith(f"{candidate}:"):
                    failure_stage = candidate
                    break
            _update_job_state(
                job_state,
                status="failed_postprocess",
                error_message=message,
                failure_stage=failure_stage,
                finished_at=int(time.time()),
            )
            file_store.append_job_event(
                job_state.job_id,
                JobEvent(
                    event_type="job_reconcile_failed",
                    level="error",
                    message="postprocess reconcile failed",
                    context={"space_name": resolved_space, "error": message, "failure_stage": failure_stage},
                ),
            )
            file_store.append_job_log(
                job_state.job_id,
                f"postprocess_reconcile failed space={resolved_space} failure_stage={failure_stage or '-'} error={message}",
            )
        raise
