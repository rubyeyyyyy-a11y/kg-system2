import logging
import time
from typing import Any

from app.clients.es_client import ElasticsearchClient
from app.core.space_context import use_space
from app.services.common import normalize_raw_id
from app.services.imports import (
    audit_service,
    cleanup_graph_scan_service,
    cleanup_planning_service,
    cleanup_service,
    es_postprocess_service,
    file_store,
    import_ngql_service,
    job_runtime,
    metadata_postprocess_service,
    postprocess_reconcile_service,
)
from app.services.imports.models import (
    CleanupConflictRecord,
    CleanupJobPhaseRecord,
    CleanupJobRecord,
    ImportBatchItemRecord,
)
from app.services.imports.state_repository import cleanup_jobs as cleanup_jobs_repo
from app.services.imports.state_repository import import_batches

logger = logging.getLogger(__name__)


class CleanupExecutionError(RuntimeError):
    def __init__(self, *, phase: str, kind: str, message: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.phase = phase
        self.kind = kind
        self.detail = dict(detail or {})


def _update_cleanup_job(record: CleanupJobRecord, **changes) -> CleanupJobRecord:
    for key, value in changes.items():
        setattr(record, key, value)
    if record.started_at and record.finished_at:
        record.duration_ms = max(0, (int(record.finished_at) - int(record.started_at)) * 1000)
    record.updated_at = int(time.time())
    cleanup_jobs_repo.save(record)
    return record


def _set_phase(record: CleanupJobRecord, phase: str, *, force_event: bool = False) -> CleanupJobRecord:
    now = int(time.time())
    if force_event or record.phase != phase:
        record.phase = phase
        record.phase_history.append(CleanupJobPhaseRecord(phase=phase, at=now))
    if phase in {"completed", "failed"}:
        record.final_phase = phase
    return _update_cleanup_job(record, phase=record.phase, phase_history=record.phase_history, final_phase=record.final_phase)


def _update_batch_cleanup_status(batch_ids: list[str], cleanup_status: str) -> None:
    for batch_id in batch_ids:
        try:
            import_batches.update(batch_id, cleanup_status=cleanup_status)
        except Exception:
            continue


def _relation_key(item: ImportBatchItemRecord) -> tuple[str, int, int, int]:
    return cleanup_planning_service.relation_key(item)


def _plan_cleanup(record: CleanupJobRecord) -> cleanup_planning_service.CleanupPlanningResult:
    try:
        return cleanup_planning_service.plan_cleanup(
            space_id=record.space_id,
            batch_ids=record.batch_ids,
            scope=record.scope,
            check_entity_live_references=lambda space_id, vid, excluding_relation_keys: cleanup_graph_scan_service.check_entity_live_references(
                space_id=space_id,
                vid=vid,
                excluding_relation_keys=excluding_relation_keys,
            ),
        )
    except cleanup_planning_service.CleanupPlanningError as exc:
        raise CleanupExecutionError(
            phase="planning",
            kind=exc.kind,
            message=str(exc),
            detail=exc.detail,
        ) from exc


def _verify_deleted_entities(space_id: str, deleted_entities: list[ImportBatchItemRecord], *, scope: str) -> dict[str, Any]:
    if scope == "relations_only":
        return {
            "ok": True,
            "deleted_entity_count": 0,
            "es_docs_removed": None,
            "leftover_doc_ids": [],
            "sample_search_ok": None,
            "sample_suggest_ok": None,
            "samples": [],
            "note": "relations_only cleanup does not verify relation-level leftovers or global graph references",
            "warning": "entity verification skipped because scope=relations_only",
        }
    if not deleted_entities:
        return {
            "ok": True,
            "deleted_entity_count": 0,
            "es_docs_removed": True,
            "leftover_doc_ids": [],
            "sample_search_ok": True,
            "sample_suggest_ok": True,
            "samples": [],
            "note": "no entity deletions were requested or all entity deletions were skipped",
            "warning": None,
        }
    client = ElasticsearchClient()
    deleted_vids = sorted({int(item.vid or 0) for item in deleted_entities if int(item.vid or 0) > 0})
    docs, fetch_ms = client.fetch_documents_by_ids(space_id, deleted_vids)
    leftover_docs = [doc for doc in docs if doc.get("found")]
    sample_entities = deleted_entities[: min(5, len(deleted_entities))]
    search_ok = True
    suggest_ok = True
    samples: list[dict[str, Any]] = []
    for item in sample_entities:
        vid = int(item.vid or 0)
        entity_name = str(item.entity_name or "").strip()
        raw_id = str(item.entity_raw_id or "").strip()
        sample: dict[str, Any] = {"vid": vid, "search_hits": [], "suggest_hits": []}
        if raw_id:
            hits, _ = client.search_entity_vids_by_raw_id_norm(
                normalize_raw_id(raw_id),
                raw_id_original=raw_id,
                mode="exact",
                limit=5,
                space_name=space_id,
                entity_type=None,
                source=None,
            )
            hit_vids = [int(hit_vid) for hit_vid, _score in hits]
            sample["search_hits"] = hit_vids
            if vid in hit_vids:
                search_ok = False
        elif entity_name:
            hits, _ = client.search_entity_vids(
                entity_name,
                limit=5,
                offset=0,
                space_name=space_id,
                search_in_name=True,
                search_in_description=False,
                search_in_type=False,
                search_in_raw_id=False,
                entity_type=None,
                source=None,
            )
            hit_vids = [int(hit_vid) for hit_vid, _score in hits]
            sample["search_hits"] = hit_vids
            if vid in hit_vids:
                search_ok = False
        if entity_name:
            suggest_hits, _ = client.suggest_entities_by_name_prefix(
                entity_name[: min(8, len(entity_name))] or entity_name,
                limit=5,
                space_name=space_id,
                entity_type=None,
                source=None,
            )
            suggest_vids = [int(hit.get("vid") or 0) for hit in suggest_hits]
            sample["suggest_hits"] = suggest_vids
            if vid in suggest_vids:
                suggest_ok = False
        samples.append(sample)
    return {
        "ok": len(leftover_docs) == 0 and search_ok and suggest_ok,
        "deleted_entity_count": len(deleted_vids),
        "es_docs_removed": len(leftover_docs) == 0,
        "leftover_doc_ids": [str(doc.get("_id") or "") for doc in leftover_docs],
        "fetch_ms": round(float(fetch_ms), 3),
        "sample_search_ok": search_ok,
        "sample_suggest_ok": suggest_ok,
        "samples": samples,
        "note": "entity verification checks ES docs plus sample search/suggest visibility",
        "warning": None,
    }


def _write_cleanup_artifacts(
    record: CleanupJobRecord,
    *,
    skipped_entities: list[dict[str, Any]],
    skipped_relations: list[dict[str, Any]],
) -> CleanupJobRecord:
    summary_payload = {
        "cleanup_job_id": record.cleanup_job_id,
        "space_id": record.space_id,
        "batch_ids": record.batch_ids,
        "scope": record.scope,
        "status": record.status,
        "current_phase": record.phase,
        "final_phase": record.final_phase,
        "phase_history": [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in record.phase_history],
        "requested_entity_count": record.requested_entity_count,
        "requested_relation_count": record.requested_relation_count,
        "deleted_entity_count": record.deleted_entity_count,
        "deleted_relation_count": record.deleted_relation_count,
        "skipped_entity_count": record.skipped_entity_count,
        "skipped_relation_count": record.skipped_relation_count,
        "deduplicated_entity_count": record.deduplicated_entity_count,
        "deduplicated_relation_count": record.deduplicated_relation_count,
        "conflict_count": record.conflict_count,
        "plan_summary": record.plan_summary.model_dump() if hasattr(record.plan_summary, "model_dump") else dict(record.plan_summary),
        "has_plan_artifacts": bool(record.has_plan_artifacts),
        "warning_messages": record.warning_messages,
        "error_message": record.error_message,
        "failure_phase": record.failure_phase,
        "failure_kind": record.failure_kind,
        "failure_detail": record.failure_detail,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "duration_ms": record.duration_ms,
        "metadata_summary": record.metadata_summary,
        "reconcile_summary": record.reconcile_summary,
        "verify_summary": record.verify_summary,
    }
    artifacts = _merge_cleanup_artifacts(
        record.artifacts,
        [
            file_store.write_cleanup_job_artifact(record.cleanup_job_id, "summary.json", summary_payload),
            file_store.write_cleanup_job_artifact(
                record.cleanup_job_id,
                "conflicts.json",
                [item.model_dump() if hasattr(item, "model_dump") else dict(item) for item in record.conflicts],
            ),
            file_store.write_cleanup_job_artifact(record.cleanup_job_id, "skipped_entities.json", skipped_entities),
            file_store.write_cleanup_job_artifact(record.cleanup_job_id, "skipped_relations.json", skipped_relations),
            file_store.write_cleanup_job_artifact(record.cleanup_job_id, "verify_summary.json", record.verify_summary),
        ],
    )
    return _update_cleanup_job(record, artifacts=artifacts)


def _merge_cleanup_artifacts(existing: list[Any], updates: list[Any]) -> list[Any]:
    merged: dict[str, Any] = {}
    for artifact in existing:
        filename = str(getattr(artifact, "filename", "") or "")
        if filename:
            merged[filename] = artifact
    for artifact in updates:
        filename = str(getattr(artifact, "filename", "") or "")
        if filename:
            merged[filename] = artifact
    return [merged[key] for key in sorted(merged.keys())]


def _write_cleanup_plan_artifacts(
    record: CleanupJobRecord,
    plan: cleanup_planning_service.CleanupPlanningResult,
) -> CleanupJobRecord:
    plan_artifacts = [
        file_store.write_cleanup_job_artifact(record.cleanup_job_id, "plan_summary.json", plan.plan_summary.model_dump()),
        file_store.write_cleanup_job_artifact(record.cleanup_job_id, "blocked_entities.json", plan.blocked_entities_artifact),
        file_store.write_cleanup_job_artifact(record.cleanup_job_id, "deletable_entities.json", plan.deletable_entities_artifact),
        file_store.write_cleanup_job_artifact(record.cleanup_job_id, "deletable_relations.json", plan.deletable_relations_artifact),
    ]
    merged = _merge_cleanup_artifacts(record.artifacts, plan_artifacts)
    return _update_cleanup_job(record, has_plan_artifacts=True, artifacts=merged)


def run_cleanup_job(cleanup_job_id: str) -> CleanupJobRecord:
    record = cleanup_jobs_repo.load(cleanup_job_id)
    with use_space(record.space_id):
        now = int(time.time())
        record = _update_cleanup_job(
            record,
            status="running",
            started_at=record.started_at or now,
            error_message=None,
            failure_phase=None,
            failure_kind=None,
            failure_detail={},
            warning_messages=[],
        )
        record = _set_phase(record, "planning", force_event=True)
        _update_batch_cleanup_status(record.batch_ids, "running")

        deleted_relations = 0
        deleted_entities = 0
        skipped_entities: list[dict[str, Any]] = []
        skipped_relations: list[dict[str, Any]] = []
        metadata_summary: dict[str, Any] = {"skipped": True, "reason": "not_started"}
        reconcile_summary: dict[str, Any] = {"skipped": True, "reason": "not_started"}
        verify_summary: dict[str, Any] = {}
        conflicts: list[CleanupConflictRecord] = []
        warning_messages: list[str] = []
        deduplicated_entity_count = 0
        deduplicated_relation_count = 0
        planning_result: cleanup_planning_service.CleanupPlanningResult | None = None
        try:
            try:
                planning_result = _plan_cleanup(record)
            except CleanupExecutionError:
                raise
            except Exception as exc:
                raise CleanupExecutionError(
                    phase="planning",
                    kind="planning_failed",
                    message=f"cleanup planning failed: {exc}",
                    detail={"error": str(exc)},
                ) from exc

            skipped_entities = list(planning_result.skipped_entities)
            skipped_relations = list(planning_result.skipped_relations)
            conflicts = list(planning_result.conflicts)
            warning_messages = list(planning_result.warning_messages)
            deduplicated_entity_count = int(planning_result.deduplicated_entity_count)
            deduplicated_relation_count = int(planning_result.deduplicated_relation_count)
            record = _update_cleanup_job(
                record,
                requested_entity_count=planning_result.plan_summary.requested_entity_count,
                requested_relation_count=planning_result.plan_summary.requested_relation_count,
                deduplicated_entity_count=deduplicated_entity_count,
                deduplicated_relation_count=deduplicated_relation_count,
                conflict_count=len(conflicts),
                conflicts=conflicts,
                warning_messages=warning_messages,
                plan_summary=planning_result.plan_summary,
            )
            record = _write_cleanup_plan_artifacts(record, planning_result)

            record = _set_phase(record, "deleting_relations")
            for relation_item in sorted(planning_result.relation_items, key=_relation_key):
                try:
                    import_ngql_service.delete_edge(
                        str(relation_item.edge_type or "REL2"),
                        int(relation_item.src_vid or 0),
                        int(relation_item.dst_vid or 0),
                        int(relation_item.rank or 0),
                        space_name=record.space_id,
                    )
                except Exception as exc:
                    raise CleanupExecutionError(
                        phase="deleting_relations",
                        kind="delete_failed",
                        message=f"failed to delete relation {relation_item.item_key}: {exc}",
                        detail={"item_key": relation_item.item_key, "src_vid": relation_item.src_vid, "dst_vid": relation_item.dst_vid},
                    ) from exc
                deleted_relations += 1

            record = _set_phase(record, "deleting_entities")
            for entity_item in sorted(planning_result.deletable_entities, key=lambda item: int(item.vid or 0)):
                try:
                    import_ngql_service.delete_vertex(int(entity_item.vid or 0), space_name=record.space_id)
                except Exception as exc:
                    raise CleanupExecutionError(
                        phase="deleting_entities",
                        kind="delete_failed",
                        message=f"failed to delete entity {entity_item.item_key}: {exc}",
                        detail={"item_key": entity_item.item_key, "vid": entity_item.vid},
                    ) from exc
                deleted_entities += 1

            record = _set_phase(record, "deleting_es_docs")
            if planning_result.deletable_entities:
                try:
                    delete_summary = es_postprocess_service.delete_entities_from_index(
                        [int(item.vid or 0) for item in planning_result.deletable_entities],
                        space_name=record.space_id,
                    )
                except Exception as exc:
                    raise CleanupExecutionError(
                        phase="deleting_es_docs",
                        kind="es_delete_failed",
                        message=f"failed to delete ES docs: {exc}",
                    ) from exc
                if int(delete_summary.get("fail_count") or 0) > 0:
                    raise CleanupExecutionError(
                        phase="deleting_es_docs",
                        kind="es_delete_failed",
                        message=f"es_delete_failed: fail_count={delete_summary['fail_count']}",
                        detail=delete_summary,
                    )
            else:
                warning_messages = list(record.warning_messages)
                if record.scope == "relations_only":
                    warning_messages.append("entity ES cleanup skipped because scope=relations_only")
                else:
                    warning_messages.append("entity ES cleanup skipped because no deletable entities remained")
                record = _update_cleanup_job(record, warning_messages=warning_messages)

            record = _set_phase(record, "refreshing_metadata")
            try:
                metadata_summary = metadata_postprocess_service.refresh_from_db(
                    actor=record.created_by,
                    space_name=record.space_id,
                )
            except Exception as exc:
                raise CleanupExecutionError(
                    phase="refreshing_metadata",
                    kind="metadata_refresh_failed",
                    message=f"failed to refresh metadata: {exc}",
                ) from exc

            record = _set_phase(record, "reconciling")
            try:
                reconcile_summary = postprocess_reconcile_service.reconcile_postprocess(
                    space_name=record.space_id,
                    actor=record.created_by,
                    refresh_metadata=False,
                    sync_scope="none",
                )
            except Exception as exc:
                raise CleanupExecutionError(
                    phase="reconciling",
                    kind="reconcile_failed",
                    message=f"failed to reconcile postprocess: {exc}",
                ) from exc

            record = _set_phase(record, "verifying")
            verify_summary = _verify_deleted_entities(record.space_id, planning_result.deletable_entities, scope=record.scope)
            if not bool(verify_summary.get("ok")):
                raise CleanupExecutionError(
                    phase="verifying",
                    kind="verify_failed",
                    message=str(verify_summary.get("warning") or verify_summary.get("note") or "cleanup verify failed"),
                    detail=verify_summary,
                )

            status = "partial_succeeded" if conflicts else "succeeded"
            warning_messages = list(record.warning_messages)
            record = _update_cleanup_job(
                record,
                status=status,
                deleted_relation_count=deleted_relations,
                deleted_entity_count=deleted_entities,
                skipped_relation_count=len(skipped_relations),
                skipped_entity_count=len(skipped_entities),
                deduplicated_relation_count=deduplicated_relation_count,
                deduplicated_entity_count=deduplicated_entity_count,
                conflict_count=len(conflicts),
                conflicts=conflicts,
                verify_summary=verify_summary,
                metadata_summary=metadata_summary,
                reconcile_summary=reconcile_summary,
                warning_messages=warning_messages,
                plan_summary=(planning_result.plan_summary if planning_result is not None else record.plan_summary),
                finished_at=int(time.time()),
            )
            record = _set_phase(record, "completed")
            _update_batch_cleanup_status(record.batch_ids, status)
            record = _write_cleanup_artifacts(record, skipped_entities=skipped_entities, skipped_relations=skipped_relations)
            audit_service.write_import_audit(
                "cleanup_job_finish",
                {
                    "cleanup_job_id": cleanup_job_id,
                    "status": status,
                    "batch_ids": record.batch_ids,
                    "deleted_relation_count": deleted_relations,
                    "deleted_entity_count": deleted_entities,
                    "conflict_count": len(conflicts),
                    "phase": record.phase,
                },
            )
            return record
        except CleanupExecutionError as exc:
            logger.exception("cleanup_job_failed cleanup_job_id=%s phase=%s kind=%s error=%s", cleanup_job_id, exc.phase, exc.kind, str(exc))
            record = cleanup_jobs_repo.load(cleanup_job_id)
            record = _update_cleanup_job(
                record,
                status="failed",
                deleted_relation_count=deleted_relations,
                deleted_entity_count=deleted_entities,
                skipped_relation_count=len(skipped_relations),
                skipped_entity_count=len(skipped_entities),
                deduplicated_relation_count=deduplicated_relation_count,
                deduplicated_entity_count=deduplicated_entity_count,
                conflict_count=len(conflicts),
                conflicts=conflicts,
                verify_summary=verify_summary,
                metadata_summary=metadata_summary,
                reconcile_summary=reconcile_summary,
                warning_messages=warning_messages,
                error_message=str(exc),
                failure_phase=exc.phase,
                failure_kind=exc.kind,
                failure_detail=exc.detail,
                plan_summary=(planning_result.plan_summary if planning_result is not None else record.plan_summary),
                finished_at=int(time.time()),
            )
            record = _set_phase(record, "failed")
            _update_batch_cleanup_status(record.batch_ids, "failed")
            record = _write_cleanup_artifacts(record, skipped_entities=skipped_entities, skipped_relations=skipped_relations)
            audit_service.write_import_audit(
                "cleanup_job_finish",
                {
                    "cleanup_job_id": cleanup_job_id,
                    "status": "failed",
                    "batch_ids": record.batch_ids,
                    "deleted_relation_count": deleted_relations,
                    "deleted_entity_count": deleted_entities,
                    "conflict_count": len(conflicts),
                    "failure_phase": exc.phase,
                    "failure_kind": exc.kind,
                },
            )
            return record
        except Exception as exc:
            logger.exception("cleanup_job_failed cleanup_job_id=%s error=%s", cleanup_job_id, str(exc))
            record = cleanup_jobs_repo.load(cleanup_job_id)
            failure_phase = record.phase or "planning"
            record = _update_cleanup_job(
                record,
                status="failed",
                deleted_relation_count=deleted_relations,
                deleted_entity_count=deleted_entities,
                skipped_relation_count=len(skipped_relations),
                skipped_entity_count=len(skipped_entities),
                deduplicated_relation_count=deduplicated_relation_count,
                deduplicated_entity_count=deduplicated_entity_count,
                conflict_count=len(conflicts),
                conflicts=conflicts,
                verify_summary=verify_summary,
                metadata_summary=metadata_summary,
                reconcile_summary=reconcile_summary,
                warning_messages=warning_messages,
                error_message=str(exc),
                failure_phase=failure_phase,
                failure_kind="unexpected_failed",
                failure_detail={"error": str(exc)},
                plan_summary=(planning_result.plan_summary if planning_result is not None else record.plan_summary),
                finished_at=int(time.time()),
            )
            record = _set_phase(record, "failed")
            _update_batch_cleanup_status(record.batch_ids, "failed")
            record = _write_cleanup_artifacts(record, skipped_entities=skipped_entities, skipped_relations=skipped_relations)
            audit_service.write_import_audit(
                "cleanup_job_finish",
                {
                    "cleanup_job_id": cleanup_job_id,
                    "status": "failed",
                    "batch_ids": record.batch_ids,
                    "deleted_relation_count": deleted_relations,
                    "deleted_entity_count": deleted_entities,
                    "conflict_count": len(conflicts),
                    "failure_phase": failure_phase,
                    "failure_kind": "unexpected_failed",
                },
            )
            return record


_RUNTIME = job_runtime.QueuedWorkerRuntime[CleanupJobRecord](
    worker_name="import-cleanup-job-worker",
    list_records=cleanup_jobs_repo.list,
    run_record=lambda record: run_cleanup_job(record.cleanup_job_id),
    record_id=lambda record: record.cleanup_job_id,
    sort_key=lambda record: (record.created_at, record.cleanup_job_id),
)


def drain_queue() -> None:
    _RUNTIME.drain_queue()


def ensure_worker_running() -> None:
    _RUNTIME.ensure_worker_running()


def startup_recover_and_start() -> None:
    repaired = _RUNTIME.startup_recover_and_start(recover_interrupted=cleanup_service.mark_interrupted_cleanup_jobs)
    if repaired:
        logger.info("imports_cleanup_startup repaired_cleanup_jobs=%d", len(repaired))
