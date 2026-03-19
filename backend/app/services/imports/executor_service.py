import logging
import os
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from app.core.space_context import use_space
from app.services.imports import (
    audit_service,
    es_postprocess_service,
    file_store,
    import_ngql_service,
    job_runtime,
    job_service,
    metadata_postprocess_service,
    postprocess_reconcile_service,
    schema_service,
)
from app.services.imports.models import (
    CompiledImportPlan,
    ImportBatchItemRecord,
    ImportJobState,
    JobEvent,
)
from app.services.imports.state_repository import import_batches, import_job_states

logger = logging.getLogger(__name__)

_BATCH_SIZE = int(os.getenv("IMPORT_EXEC_BATCH_SIZE", "500"))
_MAX_FAILED_ROWS_WRITTEN = int(os.getenv("IMPORT_MAX_FAILED_ROWS_WRITTEN", "3000"))
_POSTPROCESS_FAILURE_STAGES = {"metadata_failed", "es_sync_failed", "verify_failed", "registry_write_failed"}


def _update_state(state: ImportJobState, **changes) -> ImportJobState:
    return import_job_states.update(state.job_id, **changes)


def _append_job_event(job_id: str, event: JobEvent) -> None:
    import_job_states.append_event(job_id, event)


def _append_job_log(job_id: str, message: str) -> None:
    import_job_states.append_log(job_id, message)


def _update_batch_for_job(state: ImportJobState, **changes):
    if not state.batch_id:
        return None
    return import_batches.update(state.batch_id, **changes)


def _batch_entity_item(
    *,
    state: ImportJobState,
    success: dict,
    payload: dict[str, str],
    created_by_batch: bool,
) -> dict:
    return {
        "batch_id": state.batch_id,
        "space_id": state.space_name,
        "job_id": state.job_id,
        "item_type": "entity",
        "created_by_batch": created_by_batch,
        "vid": int(success["vid"]),
        "entity_raw_id": str(payload.get("entity_raw_id") or ""),
        "entity_name": str(payload.get("entity_name") or ""),
        "row_index": int(success["row_index"]),
    }


def _batch_relation_item(
    *,
    state: ImportJobState,
    target_object: str,
    success: dict,
    payload: dict[str, str],
    created_by_batch: bool,
) -> dict:
    return {
        "batch_id": state.batch_id,
        "space_id": state.space_name,
        "job_id": state.job_id,
        "item_type": "relation",
        "created_by_batch": created_by_batch,
        "src_vid": int(success["src"]),
        "dst_vid": int(success["dst"]),
        "relation": str(payload.get("relation") or ""),
        "rank": int(success["rank"]),
        "edge_type": target_object,
        "row_index": int(success["row_index"]),
    }


def _append_batch_ledger_item(
    *,
    state: ImportJobState,
    item_kind: str,
    item_payload: dict[str, object],
    ledger_counts: dict[str, dict[str, int]],
) -> tuple[int, int]:
    append_result = import_batches.append_item_if_absent(ImportBatchItemRecord.model_validate(item_payload))
    ledger_counts[item_kind]["requested_count"] += 1
    if append_result.appended:
        ledger_counts[item_kind]["appended_count"] += 1
    else:
        ledger_counts[item_kind]["skipped_existing_count"] += 1
    return append_result.entity_count, append_result.relation_count


def _build_ledger_summary(
    *,
    state: ImportJobState,
    ledger_counts: dict[str, dict[str, int]],
) -> tuple[dict[str, object], list[str]]:
    if not state.batch_id:
        return {}, []
    consistency = import_batches.get_ledger_consistency(state.batch_id)
    warnings = list(consistency.get("warnings") or [])
    summary = {
        "entity": dict(ledger_counts["entity"]),
        "relation": dict(ledger_counts["relation"]),
        "consistency": consistency,
    }
    return summary, warnings


def _persist_batch_ledger_summary(
    state: ImportJobState,
    *,
    batch_entity_count: int,
    batch_relation_count: int,
    ledger_summary: dict[str, object],
    ledger_warnings: list[str],
    **extra_changes,
):
    if not state.batch_id:
        return None
    return import_batches.persist_ledger_summary(
        state.batch_id,
        entity_count=batch_entity_count,
        relation_count=batch_relation_count,
        ledger_summary=ledger_summary,
        ledger_warnings=ledger_warnings,
        **extra_changes,
    )


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


def _compiled_plan(state: ImportJobState) -> CompiledImportPlan:
    plan = CompiledImportPlan.model_validate(import_job_states.load_compiled_plan_payload(state.job_id))
    sources = list(plan.sources or state.sources)
    if not sources:
        file_ids = list(plan.file_ids or state.file_ids)
        known_target_source_ids = [target.source_id for target in plan.targets if target.source_id]
        sources = [
            import_job_states.load_input_source(
                state.job_id,
                file_id,
                known_target_source_ids[index] if index < len(known_target_source_ids) else f"compat_source_{index + 1}",
            )
            for index, file_id in enumerate(file_ids)
        ]
    source_by_id = {source.source_id: source for source in sources}
    default_source = sources[0] if len(sources) == 1 else None
    targets = []
    for target in plan.targets:
        source = source_by_id.get(target.source_id) or default_source
        if source is None:
            targets.append(target)
            continue
        targets.append(
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
    return plan.model_copy(
        update={
            "space_name": plan.space_name or state.space_name,
            "file_ids": plan.file_ids or state.file_ids,
            "sources": sources,
            "targets": targets,
        }
    )


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


@dataclass
class _TargetArtifactBundle:
    normalized_path: Path
    failed_path: Path
    summary_path: Path
    normalized_headers: list[str]
    failed_headers: list[str]


class _ExecutionArtifactStore:
    def __init__(self, state: ImportJobState, *, aggregate_normalized_headers: list[str], aggregate_failed_headers: list[str]):
        self._state = state
        self._aggregate_normalized_headers = aggregate_normalized_headers
        self._aggregate_failed_headers = aggregate_failed_headers

    def initialize_job_outputs(self) -> None:
        normalized_path = Path(self._state.normalized_rows_path or import_job_states.normalized_rows_path(self._state.job_id))
        failed_path = Path(self._state.failed_rows_path or import_job_states.failed_rows_path(self._state.job_id))
        file_store.touch_job_csv(normalized_path, self._aggregate_normalized_headers)
        file_store.touch_job_csv(failed_path, self._aggregate_failed_headers)

    def prepare_target(self, *, target, source) -> _TargetArtifactBundle:
        bundle = _TargetArtifactBundle(
            normalized_path=self._artifact_path(target.target_id, "normalized_rows", file_store.job_target_normalized_rows_path(self._state.job_id, target.target_id)),
            failed_path=self._artifact_path(target.target_id, "failed_rows", file_store.job_target_failed_rows_path(self._state.job_id, target.target_id)),
            summary_path=self._artifact_path(target.target_id, "summary", file_store.job_target_summary_path(self._state.job_id, target.target_id)),
            normalized_headers=_headers_for_normalized_rows(list(source.columns)),
            failed_headers=_headers_for_failed_rows(list(source.columns)),
        )
        file_store.touch_job_csv(bundle.normalized_path, bundle.normalized_headers)
        file_store.touch_job_csv(bundle.failed_path, bundle.failed_headers)
        self.write_target_summary(
            bundle,
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
        return bundle

    def write_target_summary(self, bundle: _TargetArtifactBundle, payload: dict) -> None:
        file_store.write_json(bundle.summary_path, payload)

    def append_normalized_rows(self, bundle: _TargetArtifactBundle, rows: list[dict[str, str]]) -> None:
        file_store.append_csv_rows(bundle.normalized_path, bundle.normalized_headers, rows)
        file_store.append_csv_rows(
            Path(self._state.normalized_rows_path or import_job_states.normalized_rows_path(self._state.job_id)),
            self._aggregate_normalized_headers,
            rows,
        )

    def append_failed_rows(self, bundle: _TargetArtifactBundle, rows: list[dict[str, str]]) -> None:
        file_store.append_csv_rows(bundle.failed_path, bundle.failed_headers, rows)
        file_store.append_csv_rows(
            Path(self._state.failed_rows_path or import_job_states.failed_rows_path(self._state.job_id)),
            self._aggregate_failed_headers,
            rows,
        )

    def _artifact_path(self, target_id: str, kind: str, fallback_path: Path) -> Path:
        artifact = next(
            (
                item
                for item in self._state.artifacts
                if str(item.target_id or "") == str(target_id or "") and str(item.kind or "") == kind
            ),
            None,
        )
        if artifact is None or not str(artifact.path or "").strip():
            return fallback_path
        return Path(str(artifact.path))


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
    state = import_job_states.load(job_id)
    plan = _compiled_plan(state)
    resolved_space_name = str(state.space_name or plan.space_name or "")
    if resolved_space_name and state.space_name != resolved_space_name:
        state = _update_state(state, space_name=resolved_space_name)
    with use_space(resolved_space_name):
        if plan.space_name != resolved_space_name:
            plan = plan.model_copy(update={"space_name": resolved_space_name})
        sources_by_id = {source.source_id: source for source in plan.sources}
        if state.cancel_requested:
            _update_batch_for_job(state, status="cancelled")
            return _update_state(state, status="cancelled", failure_stage="cancelled", finished_at=int(time.time()))
        state = _update_state(state, status="running", started_at=int(time.time()))
        _update_batch_for_job(state, status="running")
        _append_job_event(job_id, JobEvent(event_type="job_started", message="job started"))
        _append_job_event(
            job_id,
            JobEvent(
                event_type="job_importing_rows",
                message="importing rows per target in batches",
                context={"batch_size": _BATCH_SIZE},
            ),
        )
        _append_job_log(job_id, f"job started space={state.space_name} plan={plan.plan_id} batch_size={_BATCH_SIZE}")
        affected_entity_vids: set[int] = set()
        batch_entity_count = 0
        batch_relation_count = 0
        ledger_counts = {
            "entity": {"requested_count": 0, "appended_count": 0, "skipped_existing_count": 0},
            "relation": {"requested_count": 0, "appended_count": 0, "skipped_existing_count": 0},
        }
        ledger_summary: dict[str, object] = {}
        ledger_warnings: list[str] = []
        total_rows = 0
        processed_rows = 0
        success_rows = 0
        failed_rows = 0
        failed_rows_truncated = False
        aggregate_source_columns: list[str] = []
        for source in plan.sources:
            for column in source.columns:
                if column not in aggregate_source_columns:
                    aggregate_source_columns.append(column)
        aggregate_normalized_headers = _headers_for_normalized_rows(aggregate_source_columns)
        aggregate_failed_headers = _headers_for_failed_rows(aggregate_source_columns)
        artifact_store = _ExecutionArtifactStore(
            state,
            aggregate_normalized_headers=aggregate_normalized_headers,
            aggregate_failed_headers=aggregate_failed_headers,
        )
        artifact_store.initialize_job_outputs()
        try:
            schema_service.apply_schema_plan(plan.schema_create_plan, space_name=state.space_name)
            for target in plan.targets:
                source = sources_by_id.get(target.source_id)
                if source is None:
                    raise RuntimeError(f"compiled target `{target.target_id}` references missing source `{target.source_id}`")
                artifact_bundle = artifact_store.prepare_target(target=target, source=source)
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

                def process_batch(batch_items: list[import_ngql_service.BatchRowItem]) -> None:
                    nonlocal total_rows, processed_rows, success_rows, failed_rows, failed_rows_truncated
                    nonlocal target_scanned, target_processed, target_success, target_failed
                    nonlocal target_failed_written, target_batches, target_successful_batches, target_failed_batches, target_fallback_batches
                    nonlocal batch_entity_count, batch_relation_count
                    if not batch_items:
                        return
                    row_ledger_meta: dict[int, dict] = {}
                    for item in batch_items:
                        if target.object_type == "tag":
                            snapshot = import_ngql_service.vertex_identity_snapshot(target, item.row, actor=state.created_by)
                            row_ledger_meta[item.row_index] = {
                                "item_type": "entity",
                                "payload": snapshot["payload"],
                                "created_by_batch": not import_ngql_service.vertex_exists(
                                    target.object_name,
                                    int(snapshot["vid"]),
                                    space_name=state.space_name,
                                ),
                            }
                        else:
                            snapshot = import_ngql_service.edge_identity_snapshot(
                                target,
                                item.row,
                                row_index=item.row_index,
                                actor=state.created_by,
                            )
                            row_ledger_meta[item.row_index] = {
                                "item_type": "relation",
                                "payload": snapshot["payload"],
                                "created_by_batch": not import_ngql_service.edge_exists(
                                    target.object_name,
                                    int(snapshot["src"]),
                                    int(snapshot["dst"]),
                                    int(snapshot["rank"]),
                                    space_name=state.space_name,
                                ),
                            }
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
                        _append_job_event(
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
                        ledger_meta = row_ledger_meta.get(int(success["row_index"])) or {}
                        if success.get("kind") == "vertex" and state.batch_id:
                            batch_entity_count, batch_relation_count = _append_batch_ledger_item(
                                state=state,
                                item_kind="entity",
                                item_payload=_batch_entity_item(
                                    state=state,
                                    success=success,
                                    payload=dict(ledger_meta.get("payload") or {}),
                                    created_by_batch=bool(ledger_meta.get("created_by_batch")),
                                ),
                                ledger_counts=ledger_counts,
                            )
                        elif success.get("kind") == "edge" and state.batch_id:
                            batch_entity_count, batch_relation_count = _append_batch_ledger_item(
                                state=state,
                                item_kind="relation",
                                item_payload=_batch_relation_item(
                                    state=state,
                                    target_object=target.object_name,
                                    success=success,
                                    payload=dict(ledger_meta.get("payload") or {}),
                                    created_by_batch=bool(ledger_meta.get("created_by_batch")),
                                ),
                                ledger_counts=ledger_counts,
                            )
                    artifact_store.append_normalized_rows(artifact_bundle, normalized_rows_payload)

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
                    artifact_store.append_failed_rows(artifact_bundle, failed_rows_payload)

                    batch_count = len(batch_items)
                    total_rows += batch_count
                    target_scanned += batch_count
                    processed_rows += batch_count
                    target_processed += batch_count
                    success_rows += len(batch_result.successes)
                    target_success += len(batch_result.successes)
                    failed_rows += len(batch_result.failures)
                    target_failed += len(batch_result.failures)
                    artifact_store.write_target_summary(
                        artifact_bundle,
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

                    current_state = import_job_states.load(job_id)
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
                for row_index, (row, _columns) in enumerate(import_job_states.iter_input_rows(job_id, source.file_id), start=1):
                    if not _row_matches_selector(row, target.row_selector):
                        continue
                    batch_items.append(import_ngql_service.BatchRowItem(row_index=row_index, row=row))
                    if len(batch_items) >= _BATCH_SIZE:
                        process_batch(batch_items)
                        batch_items = []
                if batch_items:
                    process_batch(batch_items)
                artifact_store.write_target_summary(
                    artifact_bundle,
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

            state = import_job_states.load(job_id)
            state = _update_state(
                state,
                total_rows=total_rows,
                processed_rows=processed_rows,
                success_rows=success_rows,
                failed_rows=failed_rows,
                failed_rows_truncated=failed_rows_truncated,
                affected_entity_vids=sorted(affected_entity_vids),
            )
            ledger_summary, ledger_warnings = _build_ledger_summary(state=state, ledger_counts=ledger_counts)
            if ledger_warnings:
                _append_job_event(
                    job_id,
                    JobEvent(
                        event_type="batch_ledger_consistency_warning",
                        level="warn",
                        message="batch ledger consistency warning",
                        context={"warnings": ledger_warnings, "batch_id": state.batch_id},
                    ),
                )
                _append_job_log(job_id, f"batch ledger consistency warning batch_id={state.batch_id} warnings={ledger_warnings}")
            _persist_batch_ledger_summary(
                state,
                batch_entity_count=batch_entity_count,
                batch_relation_count=batch_relation_count,
                ledger_summary=ledger_summary,
                ledger_warnings=ledger_warnings,
            )
            if failed_rows > 0:
                _append_job_event(
                    job_id,
                    JobEvent(event_type="job_failed_rows_generated", level="warn", message="job completed with failed rows"),
                )
                _persist_batch_ledger_summary(
                    state,
                    batch_entity_count=batch_entity_count,
                    batch_relation_count=batch_relation_count,
                    ledger_summary=ledger_summary,
                    ledger_warnings=ledger_warnings,
                    status="failed_import",
                )
                return _update_state(
                    state,
                    status="failed_import",
                    error_message="failed rows generated",
                    finished_at=int(time.time()),
                )

            state = postprocess_reconcile_service.run_job_postprocess(
                job_id=job_id,
                actor=state.created_by,
                refresh_metadata=plan.postprocess_options.refresh_metadata,
                sync_entity_es=plan.postprocess_options.sync_entity_es,
                metadata_service=metadata_postprocess_service,
                es_service=es_postprocess_service,
            )
            _persist_batch_ledger_summary(
                state,
                batch_entity_count=batch_entity_count,
                batch_relation_count=batch_relation_count,
                ledger_summary=ledger_summary,
                ledger_warnings=ledger_warnings,
                status=state.status,
                searchable=bool(state.completion_summary.searchable) if state.completion_summary else None,
            )
            if state.status != "succeeded":
                return state
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
            return state
        except KeyboardInterrupt:
            state = import_job_states.load(job_id)
            _persist_batch_ledger_summary(
                state,
                batch_entity_count=batch_entity_count,
                batch_relation_count=batch_relation_count,
                ledger_summary=ledger_summary,
                ledger_warnings=ledger_warnings,
                status="cancelled",
            )
            return _finalize_cancelled(
                state,
                total_rows=total_rows,
                processed_rows=processed_rows,
                success_rows=success_rows,
                failed_rows=failed_rows,
                failed_rows_truncated=failed_rows_truncated,
            )
        except Exception as exc:
            state = import_job_states.load(job_id)
            failure_stage = _failure_stage_from_error(str(exc), current_status=state.status)
            failure_status = (
                "failed_postprocess"
                if state.status in {"post_metadata_refresh", "post_es_sync", "post_verify_index"}
                else "failed_import"
            )
            _append_job_event(
                job_id,
                JobEvent(
                    event_type="job_failed" if failure_stage is None else f"job_failed_{failure_stage}",
                    level="error",
                    message="job failed",
                    context={"error": str(exc), "failure_stage": failure_stage},
                ),
            )
            _append_job_log(job_id, "".join(traceback.format_exception(exc)).rstrip())
            logger.exception(
                "import_job_step job_id=%s space=%s step=failed status=%s failure_stage=%s error=%s",
                job_id,
                state.space_name,
                failure_status,
                failure_stage,
                str(exc),
            )
            _persist_batch_ledger_summary(
                state,
                batch_entity_count=batch_entity_count,
                batch_relation_count=batch_relation_count,
                ledger_summary=ledger_summary,
                ledger_warnings=ledger_warnings,
                status=failure_status,
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


_RUNTIME = job_runtime.QueuedWorkerRuntime[ImportJobState](
    worker_name="import-job-worker",
    list_records=import_job_states.list,
    run_record=lambda record: run_job(record.job_id),
    record_id=lambda record: record.job_id,
    sort_key=lambda record: (record.created_at, record.job_id),
)


def drain_queue() -> None:
    _RUNTIME.drain_queue()


def ensure_worker_running() -> None:
    _RUNTIME.ensure_worker_running()


def startup_recover_and_start() -> None:
    removed_staging = file_store.cleanup_staging_files()
    removed_artifacts = file_store.cleanup_job_artifacts()
    repaired = _RUNTIME.startup_recover_and_start(recover_interrupted=job_service.mark_interrupted_jobs)
    if removed_staging or removed_artifacts or repaired:
        logger.info(
            "imports_startup_reconcile repaired_jobs=%d removed_staging=%d removed_job_artifacts=%d",
            len(repaired),
            len(removed_staging),
            len(removed_artifacts),
        )
