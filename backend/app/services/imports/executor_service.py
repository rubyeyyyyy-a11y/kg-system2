import logging
import os
import time
import traceback
from threading import Lock, Thread

from app.core.space_context import use_space
from app.services.imports import (
    audit_service,
    es_postprocess_service,
    file_store,
    import_ngql_service,
    job_service,
    metadata_postprocess_service,
    schema_service,
)
from app.services.imports.models import CompiledImportPlan, ImportCompletionSummary, ImportJobState, JobEvent
from app.services.spaces.models import SpaceIndexStatus

logger = logging.getLogger(__name__)

_WORKER_LOCK = Lock()
_WORKER_THREAD: Thread | None = None
_BATCH_SIZE = int(os.getenv("IMPORT_EXEC_BATCH_SIZE", "500"))
_MAX_FAILED_ROWS_WRITTEN = int(os.getenv("IMPORT_MAX_FAILED_ROWS_WRITTEN", "3000"))
_POSTPROCESS_FAILURE_STAGES = {"metadata_failed", "es_sync_failed", "verify_failed", "registry_write_failed"}


def _update_state(state: ImportJobState, **changes) -> ImportJobState:
    for key, value in changes.items():
        setattr(state, key, value)
    state.updated_at = int(time.time())
    file_store.save_job_state(state)
    return state


def _failure_stage_from_error(error_message: str, *, current_status: str) -> str | None:
    raw = str(error_message or "").strip()
    for stage in _POSTPROCESS_FAILURE_STAGES:
        if raw.startswith(f"{stage}:"):
            return stage
    if current_status == "post_metadata_refresh":
        return "metadata_failed"
    if current_status == "post_es_sync":
        return "es_sync_failed"
    if current_status == "post_verify_index":
        return "verify_failed"
    return None


def _compiled_plan(job_id: str) -> CompiledImportPlan:
    return CompiledImportPlan.model_validate(file_store.read_compiled_plan_copy(job_id))


def _iter_job_csv_rows(job_id: str, file_id: str):
    meta = file_store.read_json(file_store.job_input_dir(job_id) / file_id / "meta.json")
    path = file_store.job_input_dir(job_id) / file_id / "source.csv"
    import csv

    handle = path.open("r", encoding=str(meta.get("detected_encoding") or "utf-8"), errors="replace", newline="")
    reader = csv.DictReader(handle, delimiter=str(meta.get("detected_delimiter") or ","))
    try:
        for row in reader:
            yield {str(k or ""): str(v or "") for k, v in row.items()}, list(reader.fieldnames or [])
    finally:
        handle.close()


def _row_matches_selector(row: dict[str, str], selector) -> bool:
    if selector is None:
        return True
    return str(row.get(selector.column, "")).strip() == str(selector.equals or "").strip()


def _headers_for_failed_rows(base_headers: list[str]) -> list[str]:
    headers = list(base_headers)
    for extra in ["__source_id", "__file_id", "__row_number", "__error", "__target_id", "__target_object", "__target_type"]:
        if extra not in headers:
            headers.append(extra)
    return headers


def _headers_for_normalized_rows(base_headers: list[str]) -> list[str]:
    headers = list(base_headers)
    for extra in ["__source_id", "__target_id", "__target_object", "__target_type", "__status"]:
        if extra not in headers:
            headers.append(extra)
    return headers


def _write_target_summary(summary_path, summary: dict) -> None:
    file_store.write_json(summary_path, summary)


def _finalize_cancelled(
    state: ImportJobState,
    *,
    total_rows: int,
    processed_rows: int,
    success_rows: int,
    failed_rows: int,
    failed_rows_truncated: bool,
) -> ImportJobState:
    return _update_state(
        state,
        status="cancelled",
        failure_stage="cancelled",
        cancel_effective_at_batch=True,
        total_rows=total_rows,
        processed_rows=processed_rows,
        success_rows=success_rows,
        failed_rows=failed_rows,
        failed_rows_truncated=failed_rows_truncated,
        finished_at=int(time.time()),
    )


def run_job(job_id: str) -> ImportJobState:
    state = file_store.load_job_state(job_id)
    with use_space(state.space_name):
        plan = _compiled_plan(job_id)
        sources_by_id = {source.source_id: source for source in plan.sources}
        if state.cancel_requested:
            return _update_state(state, status="cancelled", failure_stage="cancelled", finished_at=int(time.time()))
        _update_state(state, status="running", started_at=int(time.time()))
        file_store.append_job_event(job_id, JobEvent(event_type="job_started", message="job started"))
        file_store.append_job_event(
            job_id,
            JobEvent(
                event_type="job_importing_rows",
                message="importing rows per target in batches",
                context={"batch_size": _BATCH_SIZE},
            ),
        )
        file_store.append_job_log(job_id, f"job started space={state.space_name} plan={plan.plan_id} batch_size={_BATCH_SIZE}")
        affected_entity_vids: set[int] = set()
        total_rows = 0
        processed_rows = 0
        success_rows = 0
        failed_rows = 0
        failed_rows_truncated = False
        try:
            schema_service.apply_schema_plan(plan.schema_create_plan, space_name=state.space_name)
            for target in plan.targets:
                source = sources_by_id.get(target.source_id)
                if source is None:
                    raise RuntimeError(f"compiled target `{target.target_id}` references missing source `{target.source_id}`")
                normalized_path = file_store.job_target_normalized_rows_path(job_id, target.target_id)
                failed_path = file_store.job_target_failed_rows_path(job_id, target.target_id)
                summary_path = file_store.job_target_summary_path(job_id, target.target_id)
                normalized_headers = _headers_for_normalized_rows(list(source.columns))
                failed_headers = _headers_for_failed_rows(list(source.columns))
                file_store.touch_job_csv(normalized_path, normalized_headers)
                file_store.touch_job_csv(failed_path, failed_headers)
                target_scanned = 0
                target_processed = 0
                target_success = 0
                target_failed = 0
                target_failed_written = 0
                target_batches = 0
                target_successful_batches = 0
                target_failed_batches = 0
                target_fallback_batches = 0
                logger.warning(
                    "import_job_step job_id=%s space=%s step=target_start target_id=%s source_id=%s object=%s batch_size=%d",
                    job_id,
                    state.space_name,
                    target.target_id,
                    target.source_id,
                    target.object_name,
                    _BATCH_SIZE,
                )
                _write_target_summary(
                    summary_path,
                    {
                        "target_id": target.target_id,
                        "source_id": source.source_id,
                        "file_id": source.file_id,
                        "filename": source.filename,
                        "object_type": target.object_type,
                        "object_name": target.object_name,
                        "batch_size": _BATCH_SIZE,
                        "batches_total": 0,
                        "batches_succeeded": 0,
                        "batches_failed": 0,
                        "fallback_batches": 0,
                        "scanned_rows": 0,
                        "processed_rows": 0,
                        "success_rows": 0,
                        "failed_rows": 0,
                        "failed_rows_truncated": False,
                        "status": "running",
                    },
                )

                def process_batch(batch_items: list[import_ngql_service.BatchRowItem]) -> None:
                    nonlocal total_rows, processed_rows, success_rows, failed_rows, failed_rows_truncated
                    nonlocal target_scanned, target_processed, target_success, target_failed
                    nonlocal target_failed_written, target_batches, target_successful_batches, target_failed_batches, target_fallback_batches
                    if not batch_items:
                        return
                    target_batches += 1
                    batch_result = import_ngql_service.import_batch(
                        target,
                        batch_items,
                        actor=state.created_by,
                        space_name=state.space_name,
                    )
                    if batch_result.used_fallback:
                        target_fallback_batches += 1
                    if batch_result.failures:
                        target_failed_batches += 1
                        file_store.append_job_event(
                            job_id,
                            JobEvent(
                                event_type="batch_failed",
                                level="warn",
                                message="batch completed with fallback failures",
                                context={
                                    "target_id": target.target_id,
                                    "source_id": source.source_id,
                                    "batch_size": len(batch_items),
                                    "failed_rows": len(batch_result.failures),
                                },
                            ),
                        )
                    else:
                        target_successful_batches += 1

                    row_lookup = {item.row_index: item for item in batch_items}
                    normalized_rows_payload: list[dict[str, str]] = []
                    for success in batch_result.successes:
                        item = row_lookup[success["row_index"]]
                        normalized = dict(item.row)
                        normalized["__source_id"] = source.source_id
                        normalized["__target_id"] = target.target_id
                        normalized["__target_object"] = target.object_name
                        normalized["__target_type"] = target.object_type
                        normalized["__status"] = "ok"
                        normalized_rows_payload.append(normalized)
                        if success.get("kind") == "vertex" and target.object_name == "Entity":
                            affected_entity_vids.add(int(success["vid"]))
                    file_store.append_csv_rows(normalized_path, normalized_headers, normalized_rows_payload)

                    failed_rows_payload: list[dict[str, str]] = []
                    for failed_item, exc in batch_result.failures:
                        if target_failed_written < _MAX_FAILED_ROWS_WRITTEN:
                            failed = dict(failed_item.row)
                            failed["__source_id"] = source.source_id
                            failed["__file_id"] = source.file_id
                            failed["__row_number"] = failed_item.row_index
                            failed["__target_id"] = target.target_id
                            failed["__target_object"] = target.object_name
                            failed["__target_type"] = target.object_type
                            failed["__error"] = str(exc)
                            failed_rows_payload.append(failed)
                            target_failed_written += 1
                        elif target_failed_written == _MAX_FAILED_ROWS_WRITTEN:
                            failed_rows_payload.append(
                                {
                                    "__source_id": source.source_id,
                                    "__file_id": source.file_id,
                                    "__row_number": failed_item.row_index,
                                    "__target_id": target.target_id,
                                    "__target_object": target.object_name,
                                    "__target_type": target.object_type,
                                    "__error": f"failed_rows truncated after {_MAX_FAILED_ROWS_WRITTEN} rows",
                                }
                            )
                            target_failed_written += 1
                            failed_rows_truncated = True
                    file_store.append_csv_rows(failed_path, failed_headers, failed_rows_payload)

                    batch_count = len(batch_items)
                    total_rows += batch_count
                    target_scanned += batch_count
                    processed_rows += batch_count
                    target_processed += batch_count
                    success_rows += len(batch_result.successes)
                    target_success += len(batch_result.successes)
                    failed_rows += len(batch_result.failures)
                    target_failed += len(batch_result.failures)
                    _write_target_summary(
                        summary_path,
                        {
                            "target_id": target.target_id,
                            "source_id": source.source_id,
                            "file_id": source.file_id,
                            "filename": source.filename,
                            "object_type": target.object_type,
                            "object_name": target.object_name,
                            "batch_size": _BATCH_SIZE,
                            "batches_total": target_batches,
                            "batches_succeeded": target_successful_batches,
                            "batches_failed": target_failed_batches,
                            "fallback_batches": target_fallback_batches,
                            "scanned_rows": target_scanned,
                            "processed_rows": target_processed,
                            "success_rows": target_success,
                            "failed_rows": target_failed,
                            "failed_rows_truncated": target_failed_written > _MAX_FAILED_ROWS_WRITTEN,
                            "status": "running",
                        },
                    )

                    current_state = file_store.load_job_state(job_id)
                    if current_state.cancel_requested:
                        raise KeyboardInterrupt("cancel requested")
                    _update_state(
                        current_state,
                        total_rows=total_rows,
                        processed_rows=processed_rows,
                        success_rows=success_rows,
                        failed_rows=failed_rows,
                        failed_rows_truncated=failed_rows_truncated,
                    )

                batch_items: list[import_ngql_service.BatchRowItem] = []
                for row_index, (row, _columns) in enumerate(_iter_job_csv_rows(job_id, source.file_id), start=1):
                    if not _row_matches_selector(row, target.row_selector):
                        continue
                    batch_items.append(import_ngql_service.BatchRowItem(row_index=row_index, row=row))
                    if len(batch_items) >= _BATCH_SIZE:
                        process_batch(batch_items)
                        batch_items = []
                if batch_items:
                    process_batch(batch_items)
                _write_target_summary(
                    summary_path,
                    {
                        "target_id": target.target_id,
                        "source_id": source.source_id,
                        "file_id": source.file_id,
                        "filename": source.filename,
                        "object_type": target.object_type,
                        "object_name": target.object_name,
                        "batch_size": _BATCH_SIZE,
                        "batches_total": target_batches,
                        "batches_succeeded": target_successful_batches,
                        "batches_failed": target_failed_batches,
                        "fallback_batches": target_fallback_batches,
                        "scanned_rows": target_scanned,
                        "processed_rows": target_processed,
                        "success_rows": target_success,
                        "failed_rows": target_failed,
                        "failed_rows_truncated": target_failed_written > _MAX_FAILED_ROWS_WRITTEN,
                        "status": "completed" if target_failed == 0 else "completed_with_failures",
                    },
                )

            state = file_store.load_job_state(job_id)
            state = _update_state(
                state,
                total_rows=total_rows,
                processed_rows=processed_rows,
                success_rows=success_rows,
                failed_rows=failed_rows,
                failed_rows_truncated=failed_rows_truncated,
                affected_entity_vids=sorted(affected_entity_vids),
            )
            if failed_rows > 0:
                file_store.append_job_event(
                    job_id,
                    JobEvent(event_type="job_failed_rows_generated", level="warn", message="job completed with failed rows"),
                )
                return _update_state(
                    state,
                    status="failed_import",
                    error_message="failed rows generated",
                    finished_at=int(time.time()),
                )

            if plan.postprocess_options.refresh_metadata:
                state = _update_state(state, status="post_metadata_refresh", failure_stage=None)
                file_store.append_job_event(job_id, JobEvent(event_type="job_refreshing_metadata", message="refreshing metadata"))
                file_store.append_job_log(job_id, f"post_metadata_refresh space={state.space_name}")
                try:
                    metadata_postprocess_service.refresh_from_db(actor=state.created_by, space_name=state.space_name)
                except Exception as exc:
                    raise RuntimeError(f"metadata_failed: {exc}") from exc
                state = _update_state(state, metadata_refreshed=True)

            if plan.postprocess_options.sync_entity_es and affected_entity_vids:
                state = _update_state(state, status="post_es_sync", failure_stage=None)
                file_store.append_job_event(job_id, JobEvent(event_type="job_syncing_search_index", message="syncing search index"))
                file_store.append_job_log(
                    job_id,
                    f"post_es_sync space={state.space_name} affected_entity_vids={len(affected_entity_vids)}",
                )
                try:
                    sync_summary = es_postprocess_service.sync_entities(sorted(affected_entity_vids), space_name=state.space_name)
                except Exception as exc:
                    raise RuntimeError(f"es_sync_failed: {exc}") from exc
                if int(sync_summary.get("fail_count") or 0) > 0:
                    raise RuntimeError(f"es_sync_failed: fail_count={sync_summary['fail_count']}")
            else:
                state = _update_state(state, es_sync_skipped=True)

            state = _update_state(state, status="post_verify_index", failure_stage=None)
            file_store.append_job_event(job_id, JobEvent(event_type="job_verifying_search_index", message="verifying search index"))
            file_store.append_job_log(job_id, f"post_verify_index space={state.space_name}")
            try:
                verify_summary = es_postprocess_service.post_verify_index(sorted(affected_entity_vids), space_name=state.space_name)
            except Exception as exc:
                raise RuntimeError(str(exc)) from exc
            completion_summary = ImportCompletionSummary.model_validate(verify_summary["completion_summary"])
            index_status_snapshot = verify_summary.get("index_status_snapshot")
            state = _update_state(
                state,
                completion_summary=completion_summary,
                index_status_snapshot=None
                if index_status_snapshot is None
                else SpaceIndexStatus.model_validate(index_status_snapshot),
            )
            if not completion_summary.searchable:
                failure_stage = completion_summary.failure_stage or "verify_failed"
                raise RuntimeError(f"{failure_stage}: {completion_summary.note or 'post_verify_index failed'}")

            state = _update_state(state, status="succeeded", finished_at=int(time.time()), failure_stage=None)
            audit_service.write_import_audit(
                "job_finish",
                {
                    "job_id": job_id,
                    "status": state.status,
                    "success_rows": success_rows,
                    "failed_rows": failed_rows,
                    "space_name": state.space_name,
                    "searchable": bool(state.completion_summary.searchable) if state.completion_summary else False,
                },
            )
            file_store.append_job_event(job_id, JobEvent(event_type="job_succeeded", message="job succeeded"))
            file_store.append_job_log(job_id, f"job succeeded space={state.space_name}")
            return state
        except KeyboardInterrupt:
            state = file_store.load_job_state(job_id)
            return _finalize_cancelled(
                state,
                total_rows=total_rows,
                processed_rows=processed_rows,
                success_rows=success_rows,
                failed_rows=failed_rows,
                failed_rows_truncated=failed_rows_truncated,
            )
        except Exception as exc:
            state = file_store.load_job_state(job_id)
            failure_stage = _failure_stage_from_error(str(exc), current_status=state.status)
            failure_status = (
                "failed_postprocess"
                if state.status in {"post_metadata_refresh", "post_es_sync", "post_verify_index"}
                else "failed_import"
            )
            file_store.append_job_event(
                job_id,
                JobEvent(
                    event_type="job_failed" if failure_stage is None else f"job_failed_{failure_stage}",
                    level="error",
                    message="job failed",
                    context={"error": str(exc), "failure_stage": failure_stage},
                ),
            )
            file_store.append_job_log(job_id, "".join(traceback.format_exception(exc)).rstrip())
            logger.exception(
                "import_job_step job_id=%s space=%s step=failed status=%s failure_stage=%s error=%s",
                job_id,
                state.space_name,
                failure_status,
                failure_stage,
                str(exc),
            )
            return _update_state(
                state,
                status=failure_status,
                error_message=str(exc),
                failure_stage=failure_stage,
                total_rows=total_rows,
                processed_rows=processed_rows,
                success_rows=success_rows,
                failed_rows=failed_rows,
                failed_rows_truncated=failed_rows_truncated,
                affected_entity_vids=sorted(affected_entity_vids),
                finished_at=int(time.time()),
            )


def _next_queued_job() -> ImportJobState | None:
    for state in sorted(file_store.list_job_states(), key=lambda item: (item.created_at, item.job_id)):
        if state.status == "queued":
            return state
    return None


def drain_queue() -> None:
    if not _WORKER_LOCK.acquire(blocking=False):
        return
    try:
        while True:
            next_job = _next_queued_job()
            if next_job is None:
                return
            run_job(next_job.job_id)
    finally:
        _WORKER_LOCK.release()


def _worker_main() -> None:
    while True:
        queued = [state for state in file_store.list_job_states() if state.status == "queued"]
        if not queued:
            return
        drain_queue()
        time.sleep(0.3)


def ensure_worker_running() -> None:
    global _WORKER_THREAD
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return
    _WORKER_THREAD = Thread(target=_worker_main, name="import-job-worker", daemon=True)
    _WORKER_THREAD.start()


def startup_recover_and_start() -> None:
    removed_staging = file_store.cleanup_staging_files()
    removed_artifacts = file_store.cleanup_job_artifacts()
    repaired = job_service.mark_interrupted_jobs()
    if removed_staging or removed_artifacts or repaired:
        logger.info(
            "imports_startup_reconcile repaired_jobs=%d removed_staging=%d removed_job_artifacts=%d",
            len(repaired),
            len(removed_staging),
            len(removed_artifacts),
        )
    if any(state.status == "queued" for state in file_store.list_job_states()):
        ensure_worker_running()
