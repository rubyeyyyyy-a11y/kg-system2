import time
import traceback
import logging
from threading import Lock, Thread

from app.services.imports import (
    audit_service,
    es_postprocess_service,
    file_store,
    import_ngql_service,
    job_service,
    metadata_postprocess_service,
    schema_service,
)
from app.services.imports.models import CompiledImportPlan, CompiledTargetPlan, ImportJobState, JobEvent

logger = logging.getLogger(__name__)

_WORKER_LOCK = Lock()
_WORKER_THREAD: Thread | None = None
_BATCH_SIZE = 100
_MAX_FAILED_ROWS_WRITTEN = 1000


def _update_state(state: ImportJobState, **changes) -> ImportJobState:
    for key, value in changes.items():
        setattr(state, key, value)
    state.updated_at = int(time.time())
    file_store.save_job_state(state)
    return state


def _compiled_plan(job_id: str) -> CompiledImportPlan:
    return CompiledImportPlan.model_validate(file_store.read_compiled_plan_copy(job_id))


def _select_target(plan: CompiledImportPlan, row: dict[str, str]) -> CompiledTargetPlan:
    if plan.mode != "mixed":
        return plan.targets[0]
    discriminator = str(row.get(plan.discriminator_column or "", "")).strip()
    for target in plan.targets:
        if str(target.discriminator_value or "") == discriminator:
            return target
    raise ValueError(f"unmapped discriminator value `{discriminator}`")


def _job_file_ids(job_id: str) -> list[str]:
    input_dir = file_store.job_input_dir(job_id)
    if not input_dir.exists():
        return []
    return sorted([item.name for item in input_dir.iterdir() if item.is_dir()])


def _iter_job_csv_rows(job_id: str, file_id: str):
    meta = file_store.read_json(file_store.job_input_dir(job_id) / file_id / "meta.json")
    path = file_store.job_input_dir(job_id) / file_id / "source.csv"
    import csv

    handle = path.open("r", encoding=str(meta.get("detected_encoding") or "utf-8"), newline="")
    reader = csv.DictReader(handle, delimiter=str(meta.get("detected_delimiter") or ","))
    try:
        for row in reader:
            yield {str(k or ""): str(v or "") for k, v in row.items()}, list(reader.fieldnames or [])
    finally:
        handle.close()


def _headers_for_failed_rows(base_headers: list[str]) -> list[str]:
    headers = list(base_headers)
    for extra in ["__file_id", "__row_number", "__error", "__target_object", "__target_type"]:
        if extra not in headers:
            headers.append(extra)
    return headers


def _headers_for_normalized_rows(base_headers: list[str]) -> list[str]:
    headers = list(base_headers)
    for extra in ["__target_object", "__target_type", "__status"]:
        if extra not in headers:
            headers.append(extra)
    return headers


def run_job(job_id: str) -> ImportJobState:
    state = job_service.get_job(job_id)
    plan = _compiled_plan(job_id)
    base_headers: list[str] = []
    failed_headers: list[str] = ["__error"]
    normalized_headers: list[str] = ["__status"]
    if state.cancel_requested:
        return _update_state(state, status="cancelled", finished_at=int(time.time()))
    _update_state(state, status="running", started_at=int(time.time()))
    file_store.append_job_event(job_id, JobEvent(event_type="job_started", message="job started"))
    file_store.append_job_log(job_id, "job started")
    affected_entity_vids: set[int] = set()
    total_rows = 0
    processed_rows = 0
    success_rows = 0
    failed_rows = 0
    try:
        schema_service.apply_schema_plan(plan.schema_create_plan)
        failed_rows_truncated = False
        for file_id in _job_file_ids(job_id):
            for row_index, (row, columns) in enumerate(_iter_job_csv_rows(job_id, file_id), start=1):
                if not base_headers:
                    base_headers = columns
                    failed_headers = _headers_for_failed_rows(columns)
                    normalized_headers = _headers_for_normalized_rows(columns)
                    file_store.touch_job_csv(file_store.job_failed_rows_path(job_id), failed_headers)
                    file_store.touch_job_csv(file_store.job_normalized_rows_path(job_id), normalized_headers)
                total_rows += 1
                try:
                    target = _select_target(plan, row)
                    result = import_ngql_service.import_row(target, row, row_index=row_index, actor=state.created_by)
                    normalized = dict(row)
                    normalized["__target_object"] = target.object_name
                    normalized["__target_type"] = target.object_type
                    normalized["__status"] = "ok"
                    file_store.append_csv_row(file_store.job_normalized_rows_path(job_id), normalized_headers, normalized)
                    success_rows += 1
                    if result.get("kind") == "vertex" and target.object_name == "Entity":
                        affected_entity_vids.add(int(result["vid"]))
                except Exception as exc:
                    failed_rows += 1
                    if failed_rows <= _MAX_FAILED_ROWS_WRITTEN:
                        failed = dict(row)
                        try:
                            target = _select_target(plan, row)
                            failed["__target_object"] = target.object_name
                            failed["__target_type"] = target.object_type
                        except Exception:
                            failed["__target_object"] = ""
                            failed["__target_type"] = ""
                        failed["__file_id"] = file_id
                        failed["__row_number"] = row_index
                        failed["__error"] = str(exc)
                        file_store.append_csv_row(file_store.job_failed_rows_path(job_id), failed_headers, failed)
                    elif not failed_rows_truncated:
                        file_store.append_csv_row(
                            file_store.job_failed_rows_path(job_id),
                            failed_headers,
                            {
                                "__file_id": file_id,
                                "__row_number": row_index,
                                "__target_object": "",
                                "__target_type": "",
                                "__error": f"failed_rows truncated after {_MAX_FAILED_ROWS_WRITTEN} rows",
                            },
                        )
                        failed_rows_truncated = True
                        file_store.append_job_event(
                            job_id,
                            JobEvent(
                                event_type="row_failed",
                                level="error",
                                message="row failed",
                                context={"row_index": row_index, "error": str(exc)},
                            ),
                        )
                    file_store.append_job_log(job_id, f"row failed row_index={row_index} error={exc}")
                processed_rows += 1
                if processed_rows % _BATCH_SIZE == 0:
                    state = job_service.get_job(job_id)
                    if state.cancel_requested:
                        return _update_state(
                            state,
                            status="cancelled",
                            cancel_effective_at_batch=True,
                            total_rows=total_rows,
                            processed_rows=processed_rows,
                            success_rows=success_rows,
                            failed_rows=failed_rows,
                            failed_rows_truncated=failed_rows_truncated,
                            finished_at=int(time.time()),
                        )
                    _update_state(
                        state,
                        total_rows=total_rows,
                        processed_rows=processed_rows,
                        success_rows=success_rows,
                        failed_rows=failed_rows,
                    )

        state = job_service.get_job(job_id)
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
            return _update_state(state, status="failed_import", error_message="failed rows generated", finished_at=int(time.time()))

        if plan.postprocess_options.refresh_metadata:
            state = _update_state(state, status="post_metadata_refresh")
            metadata_postprocess_service.refresh_from_db(actor=state.created_by)
            state = _update_state(state, metadata_refreshed=True)

        if plan.postprocess_options.sync_entity_es and affected_entity_vids:
            state = _update_state(state, status="post_es_sync")
            es_postprocess_service.sync_entities(sorted(affected_entity_vids))
        else:
            state = _update_state(state, es_sync_skipped=True)

        state = _update_state(state, status="succeeded", finished_at=int(time.time()))
        audit_service.write_import_audit(
            "job_finish",
            {"job_id": job_id, "status": state.status, "success_rows": success_rows, "failed_rows": failed_rows},
        )
        file_store.append_job_event(job_id, JobEvent(event_type="job_succeeded", message="job succeeded"))
        file_store.append_job_log(job_id, "job succeeded")
        return state
    except Exception as exc:
        state = job_service.get_job(job_id)
        failure_status = "failed_postprocess" if state.status in {"post_metadata_refresh", "post_es_sync"} else "failed_import"
        file_store.append_job_event(
            job_id,
            JobEvent(event_type="job_failed", level="error", message="job failed", context={"error": str(exc)}),
        )
        file_store.append_job_log(job_id, "".join(traceback.format_exception(exc)).rstrip())
        return _update_state(
            state,
            status=failure_status,
            error_message=str(exc),
            total_rows=total_rows,
            processed_rows=processed_rows,
            success_rows=success_rows,
            failed_rows=failed_rows,
            failed_rows_truncated="failed_rows_truncated" in locals() and failed_rows_truncated,
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
