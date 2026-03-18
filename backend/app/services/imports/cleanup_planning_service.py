from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.escape import validate_updated_by
from app.core.space_context import get_current_space
from app.services.imports import cleanup_graph_scan_service
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import (
    CleanupBlockedEntityRecord,
    CleanupConflictRecord,
    CleanupDeletableEntityRecord,
    CleanupDeletableRelationRecord,
    CleanupPlanSummary,
    ImportBatchItemRecord,
    ImportBatchRecord,
)
from app.services.imports.state_repository import cleanup_state


class CleanupPlanningError(RuntimeError):
    def __init__(self, *, kind: str, message: str, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.kind = kind
        self.detail = dict(detail or {})


@dataclass
class CleanupRequestSpec:
    space_id: str
    batch_ids: list[str] = field(default_factory=list)
    scope: str = "full_batch"
    created_by: str = "import_workspace_cleanup"


@dataclass
class CleanupRequestContext:
    space_id: str
    batch_ids: list[str] = field(default_factory=list)
    scope: str = "full_batch"
    created_by: str = "import_workspace_cleanup"
    requested_relation_count: int = 0
    requested_entity_count: int = 0
    batches: list[ImportBatchRecord] = field(default_factory=list)
    validation_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CleanupPlanningResult:
    relation_items: list[ImportBatchItemRecord] = field(default_factory=list)
    relation_delete_keys: set[tuple[str, int, int, int]] = field(default_factory=set)
    entity_delete_candidates: list[ImportBatchItemRecord] = field(default_factory=list)
    deletable_entities: list[ImportBatchItemRecord] = field(default_factory=list)
    blocked_entities: list[ImportBatchItemRecord] = field(default_factory=list)
    skipped_entities: list[dict[str, Any]] = field(default_factory=list)
    skipped_relations: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[CleanupConflictRecord] = field(default_factory=list)
    warning_messages: list[str] = field(default_factory=list)
    deduplicated_entity_count: int = 0
    deduplicated_relation_count: int = 0
    plan_summary: CleanupPlanSummary = field(default_factory=CleanupPlanSummary)
    blocked_entity_records: list[CleanupBlockedEntityRecord] = field(default_factory=list)
    deletable_entity_records: list[CleanupDeletableEntityRecord] = field(default_factory=list)
    deletable_relation_records: list[CleanupDeletableRelationRecord] = field(default_factory=list)

    @property
    def blocked_entities_artifact(self) -> list[dict[str, Any]]:
        return [item.model_dump() for item in self.blocked_entity_records]

    @property
    def deletable_entities_artifact(self) -> list[dict[str, Any]]:
        return [item.model_dump() for item in self.deletable_entity_records]

    @property
    def deletable_relations_artifact(self) -> list[dict[str, Any]]:
        return [item.model_dump() for item in self.deletable_relation_records]


@dataclass
class CleanupPlanningSnapshot:
    space_id: str
    batch_ids: list[str] = field(default_factory=list)
    selected_items: list[ImportBatchItemRecord] = field(default_factory=list)
    relation_items_in_space: list[ImportBatchItemRecord] = field(default_factory=list)
    batch_items_by_batch_id: dict[str, list[ImportBatchItemRecord]] = field(default_factory=dict)


def _require_batch(batch_id: str) -> ImportBatchRecord:
    try:
        return cleanup_state.load_batch(batch_id)
    except Exception:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_BATCH_NOT_FOUND",
            message=f"batch `{batch_id}` not found",
            field="batch_id",
        )


def _validate_batch_access(batch: ImportBatchRecord, *, expected_space: str) -> ImportBatchRecord:
    if str(batch.space_id or "") != expected_space:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_BATCH_NOT_FOUND",
            message=f"batch `{batch.batch_id}` not found",
            field="batch_id",
        )
    return batch


def normalize_cleanup_request(*, batch_ids: list[str], scope: str, created_by: str, space_id: str | None = None) -> CleanupRequestSpec:
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
    return CleanupRequestSpec(
        space_id=str(space_id or get_current_space()),
        batch_ids=unique_batch_ids,
        scope=scope,
        created_by=validate_updated_by(created_by),
    )


def validate_cleanup_request(*, batch_ids: list[str], scope: str, created_by: str, space_id: str | None = None) -> CleanupRequestContext:
    request = normalize_cleanup_request(batch_ids=batch_ids, scope=scope, created_by=created_by, space_id=space_id)
    batches: list[ImportBatchRecord] = []
    requested_relation_count = 0
    requested_entity_count = 0
    validation_errors: list[str] = []
    validation_results: list[dict[str, Any]] = []
    batch_items_by_batch_id = cleanup_state.load_batch_items_for_batches(request.batch_ids)
    for batch_id in request.batch_ids:
        batch = _validate_batch_access(_require_batch(batch_id), expected_space=request.space_id)
        batch_error: str | None = None
        if not batch.is_test_data:
            batch_error = f"batch `{batch_id}` is not marked as test data and cannot be cleaned up"
        elif batch.cleanup_status == "succeeded":
            batch_error = f"batch `{batch_id}` already cleanup_succeeded and cannot be cleaned up again by default"
        elif batch.cleanup_status in {"queued", "running"}:
            batch_error = f"batch `{batch_id}` already has a queued or running cleanup"
        elif not cleanup_state.batch_items_exist(batch_id):
            batch_error = f"batch `{batch_id}` has no item ledger and is read-only"
        validation_results.append(
            {
                "batch_id": batch_id,
                "cleanup_status": batch.cleanup_status,
                "ok": batch_error is None,
                "error": batch_error,
            }
        )
        if batch_error is not None:
            validation_errors.append(batch_error)
            continue
        items = batch_items_by_batch_id.get(batch_id, [])
        requested_relation_count += sum(1 for item in items if item.item_type == "relation" and item.created_by_batch)
        requested_entity_count += sum(1 for item in items if item.item_type == "entity" and item.created_by_batch)
        batches.append(batch)
    if validation_errors:
        raise_import_http_error(
            status_code=409,
            error_code="IMPORT_CLEANUP_BATCH_VALIDATION_FAILED",
            message="cleanup request rejected: " + "; ".join(validation_errors),
            field="batch_ids",
            extra={"batch_results": validation_results},
        )
    return CleanupRequestContext(
        space_id=request.space_id,
        batch_ids=request.batch_ids,
        scope=request.scope,
        created_by=request.created_by,
        requested_relation_count=requested_relation_count,
        requested_entity_count=requested_entity_count,
        batches=batches,
        validation_results=validation_results,
    )


def _build_planning_snapshot(*, space_id: str, batch_ids: list[str]) -> CleanupPlanningSnapshot:
    batch_items_by_batch_id = cleanup_state.load_batch_items_for_batches(batch_ids)
    selected_items: list[ImportBatchItemRecord] = []
    for batch_id in batch_ids:
        selected_items.extend(batch_items_by_batch_id.get(batch_id, []))
    return CleanupPlanningSnapshot(
        space_id=space_id,
        batch_ids=list(batch_ids),
        selected_items=selected_items,
        relation_items_in_space=cleanup_state.list_relation_items(space_id=space_id),
        batch_items_by_batch_id=batch_items_by_batch_id,
    )


def relation_key(item: ImportBatchItemRecord) -> tuple[str, int, int, int]:
    return (str(item.edge_type or "REL2"), int(item.src_vid or 0), int(item.dst_vid or 0), int(item.rank or 0))


def _deduplicate_items(items: list[ImportBatchItemRecord]) -> tuple[list[ImportBatchItemRecord], list[ImportBatchItemRecord]]:
    seen: set[str] = set()
    unique: list[ImportBatchItemRecord] = []
    duplicates: list[ImportBatchItemRecord] = []
    for item in items:
        item_key = str(item.item_key or "")
        if item_key in seen:
            duplicates.append(item)
            continue
        seen.add(item_key)
        unique.append(item)
    return unique, duplicates


def _summarize_item(item: ImportBatchItemRecord, *, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "item_id": item.item_id,
        "item_key": item.item_key,
        "batch_id": item.batch_id,
        "item_type": item.item_type,
        "created_by_batch": item.created_by_batch,
        "reason": reason,
        "details": dict(details or {}),
    }
    if item.item_type == "entity":
        payload.update({"vid": item.vid, "entity_name": item.entity_name, "entity_raw_id": item.entity_raw_id})
    else:
        payload.update(
            {
                "edge_type": item.edge_type,
                "src_vid": item.src_vid,
                "dst_vid": item.dst_vid,
                "relation": item.relation,
                "rank": item.rank,
            }
        )
    return payload


def _build_ledger_conflicts(
    *,
    batch_ids: list[str],
    all_relation_items: list[ImportBatchItemRecord],
    relation_delete_keys: set[tuple[str, int, int, int]],
    entity_candidates: list[ImportBatchItemRecord],
) -> list[CleanupConflictRecord]:
    conflicts: list[CleanupConflictRecord] = []
    for entity_item in entity_candidates:
        vid = int(entity_item.vid or 0)
        blockers = [
            relation_item
            for relation_item in all_relation_items
            if relation_key(relation_item) not in relation_delete_keys
            and vid > 0
            and vid in {int(relation_item.src_vid or 0), int(relation_item.dst_vid or 0)}
        ]
        if blockers:
            conflicts.append(
                CleanupConflictRecord(
                    vid=vid,
                    item_type="entity",
                    source="ledger",
                    reason="referenced_by_other_batches",
                    blocking_batch_ids=sorted({item.batch_id for item in blockers if item.batch_id not in batch_ids}),
                    blocking_relations=len(blockers),
                    details={"entity_name": entity_item.entity_name, "entity_raw_id": entity_item.entity_raw_id},
                )
            )
    return conflicts


def verification_scope_note(*, scope: str, live_scan_note: str | None = None) -> str:
    if scope == "relations_only":
        return (
            "scope=relations_only: entity deletion and entity-level live graph scan are skipped; "
            "verify focuses on relation-only execution boundaries and does not claim global relation cleanup completeness"
        )
    parts = [
        "scope=full_batch: blocker detection combines ledger references + live graph incident edge scan",
        "live scan currently checks configured EDGE_TYPE incident edges and excludes relations planned for deletion",
        "verify phase checks ES + sample search/suggest visibility; relation-level global leftovers are not exhaustively audited",
    ]
    if live_scan_note:
        parts.append(str(live_scan_note))
    return "; ".join(parts)


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def plan_cleanup(
    *,
    space_id: str,
    batch_ids: list[str],
    scope: str,
    check_entity_live_references: Callable[[str, int, set[tuple[str, int, int, int]]], dict[str, Any]] | None = None,
) -> CleanupPlanningResult:
    snapshot = _build_planning_snapshot(space_id=space_id, batch_ids=batch_ids)
    return _plan_cleanup_snapshot(
        snapshot=snapshot,
        scope=scope,
        check_entity_live_references=check_entity_live_references,
    )


def _plan_cleanup_snapshot(
    *,
    snapshot: CleanupPlanningSnapshot,
    scope: str,
    check_entity_live_references: Callable[[str, int, set[tuple[str, int, int, int]]], dict[str, Any]] | None = None,
) -> CleanupPlanningResult:
    def _check_live(
        *,
        target_space_id: str,
        vid: int,
        excluding_relation_keys: set[tuple[str, int, int, int]],
    ) -> dict[str, Any]:
        if check_entity_live_references is not None:
            return check_entity_live_references(target_space_id, vid, excluding_relation_keys)
        return cleanup_graph_scan_service.check_entity_live_references(
            space_id=target_space_id,
            vid=vid,
            excluding_relation_keys=excluding_relation_keys,
        )

    items = list(snapshot.selected_items)
    relation_items_requested = [item for item in items if item.item_type == "relation" and item.created_by_batch]
    entity_items_requested = [item for item in items if item.item_type == "entity" and item.created_by_batch]
    read_only_relations = [item for item in items if item.item_type == "relation" and not item.created_by_batch]
    read_only_entities = [item for item in items if item.item_type == "entity" and not item.created_by_batch]

    skipped_relations = [_summarize_item(item, reason="existing_before_batch") for item in read_only_relations]
    skipped_entities = [_summarize_item(item, reason="existing_before_batch") for item in read_only_entities]

    relation_items, duplicate_relations = _deduplicate_items(relation_items_requested)
    entity_items, duplicate_entities = _deduplicate_items(entity_items_requested)
    deduplicated_relation_count = len(duplicate_relations)
    deduplicated_entity_count = len(duplicate_entities)
    skipped_relations.extend([_summarize_item(item, reason="duplicate_ledger_entry") for item in duplicate_relations])
    skipped_entities.extend([_summarize_item(item, reason="duplicate_ledger_entry") for item in duplicate_entities])

    warning_messages: list[str] = []
    if deduplicated_relation_count or deduplicated_entity_count:
        warning_messages.append("cleanup request contained duplicate ledger entries; duplicates were skipped before delete execution")

    relation_delete_keys = {relation_key(item) for item in relation_items}
    conflicts: list[CleanupConflictRecord] = []
    ledger_blocked_vids: set[int] = set()
    live_graph_blocked_vids: set[int] = set()
    live_scan_note = ""

    if scope == "full_batch":
        ledger_conflicts = _build_ledger_conflicts(
            batch_ids=snapshot.batch_ids,
            all_relation_items=snapshot.relation_items_in_space,
            relation_delete_keys=relation_delete_keys,
            entity_candidates=entity_items,
        )
        conflicts.extend(ledger_conflicts)
        ledger_blocked_vids = {int(conflict.vid or 0) for conflict in ledger_conflicts if int(conflict.vid or 0) > 0}
        ledger_deletable_entities = [item for item in entity_items if int(item.vid or 0) not in ledger_blocked_vids]
        for entity_item in sorted(ledger_deletable_entities, key=lambda item: int(item.vid or 0)):
            vid = int(entity_item.vid or 0)
            if vid <= 0:
                conflicts.append(
                    CleanupConflictRecord(
                        vid=vid,
                        item_type="entity",
                        source="ledger",
                        reason="invalid_entity_vid",
                        blocking_batch_ids=[],
                        blocking_relations=0,
                        details={"entity_name": entity_item.entity_name, "entity_raw_id": entity_item.entity_raw_id},
                    )
                )
                continue
            try:
                live_scan = _check_live(
                    target_space_id=snapshot.space_id,
                    vid=vid,
                    excluding_relation_keys=relation_delete_keys,
                )
            except Exception as exc:
                raise CleanupPlanningError(
                    kind="live_graph_scan_failed",
                    message=f"failed to scan live graph references for vid={vid}: {exc}",
                    detail={"vid": vid, "error": str(exc)},
                ) from exc
            live_scan_note = str(live_scan.get("scan_note") or live_scan_note)
            if live_scan.get("warning"):
                warning_messages.append(str(live_scan.get("warning")))
            if bool(live_scan.get("has_blockers")):
                live_graph_blocked_vids.add(vid)
                conflicts.append(
                    CleanupConflictRecord(
                        vid=vid,
                        item_type="entity",
                        source="live_graph",
                        reason="referenced_in_live_graph",
                        blocking_batch_ids=[],
                        blocking_relations=int(live_scan.get("live_blocking_count") or 0),
                        details={
                            "entity_name": entity_item.entity_name,
                            "entity_raw_id": entity_item.entity_raw_id,
                            "scan_edge_type": live_scan.get("scan_edge_type"),
                            "scan_note": live_scan.get("scan_note"),
                            "truncated": bool(live_scan.get("truncated")),
                            "scanned_incident_edge_count": int(live_scan.get("scanned_incident_edge_count") or 0),
                            "excluded_by_plan_count": int(live_scan.get("excluded_by_plan_count") or 0),
                            "live_blocking_edges": list(live_scan.get("live_blocking_edges") or []),
                            "took_ms": live_scan.get("took_ms"),
                        },
                    )
                )
    else:
        warning_messages.append(
            "relations_only cleanup skips entity deletion and does not perform relation-level global reference verification"
        )

    blocked_vids = {int(conflict.vid or 0) for conflict in conflicts}
    blocked_entities = [item for item in entity_items if int(item.vid or 0) in blocked_vids]
    deletable_entities = [item for item in entity_items if int(item.vid or 0) not in blocked_vids]
    for item in blocked_entities:
        vid = int(item.vid or 0)
        blocking_conflicts = [conflict.model_dump() for conflict in conflicts if int(conflict.vid or 0) == vid]
        skipped_entities.append(
            _summarize_item(
                item,
                reason="blocked_by_conflict",
                details={"blocking_conflicts": blocking_conflicts},
            )
        )

    if scope == "relations_only":
        deletable_entities = []
        skipped_entities.extend([_summarize_item(item, reason="scope_relations_only") for item in entity_items])

    if not relation_items and not deletable_entities:
        warning_messages.append(
            "cleanup planning found no deletable relations or entities; execution will continue with postprocess/verify semantics"
        )

    warning_messages = _dedupe_text(warning_messages)
    blocked_entity_records: list[CleanupBlockedEntityRecord] = []
    for item in sorted(blocked_entities, key=lambda entity_item: int(entity_item.vid or 0)):
        entity_conflicts = [conflict for conflict in conflicts if int(conflict.vid or 0) == int(item.vid or 0)]
        blocked_entity_records.append(
            CleanupBlockedEntityRecord(
                vid=int(item.vid or 0),
                entity_name=item.entity_name,
                entity_raw_id=item.entity_raw_id,
                item_key=item.item_key,
                conflict_sources=sorted({str(conflict.source) for conflict in entity_conflicts}),
                conflicts=entity_conflicts,
            )
        )
    deletable_entity_records = [
        CleanupDeletableEntityRecord(
            vid=int(item.vid or 0),
            entity_name=item.entity_name,
            entity_raw_id=item.entity_raw_id,
            item_key=item.item_key,
        )
        for item in sorted(deletable_entities, key=lambda entity_item: int(entity_item.vid or 0))
    ]
    deletable_relation_records = [
        CleanupDeletableRelationRecord(
            edge_type=str(item.edge_type or "REL2"),
            src_vid=int(item.src_vid or 0),
            dst_vid=int(item.dst_vid or 0),
            rank=int(item.rank or 0),
            relation=item.relation,
            item_key=item.item_key,
        )
        for item in sorted(relation_items, key=relation_key)
    ]

    requested_entity_count = len(entity_items_requested) if scope == "full_batch" else 0
    requested_relation_count = len(relation_items_requested)
    plan_summary = CleanupPlanSummary(
        requested_entity_count=requested_entity_count,
        requested_relation_count=requested_relation_count,
        ledger_blocked_entity_count=len({vid for vid in ledger_blocked_vids if vid > 0}),
        live_graph_blocked_entity_count=len({vid for vid in live_graph_blocked_vids if vid > 0}),
        blocked_entity_count=len({int(item.vid or 0) for item in blocked_entities if int(item.vid or 0) > 0}),
        deletable_entity_count=len(deletable_entities),
        deletable_relation_count=len(relation_items),
        conflict_count=len(conflicts),
        warnings=list(warning_messages),
        verification_scope_note=verification_scope_note(scope=scope, live_scan_note=live_scan_note),
        generated_at=int(time.time()),
    )
    return CleanupPlanningResult(
        relation_items=relation_items,
        relation_delete_keys=relation_delete_keys,
        entity_delete_candidates=list(entity_items) if scope == "full_batch" else [],
        deletable_entities=deletable_entities,
        blocked_entities=blocked_entities,
        skipped_entities=skipped_entities,
        skipped_relations=skipped_relations,
        conflicts=conflicts,
        warning_messages=warning_messages,
        deduplicated_entity_count=deduplicated_entity_count,
        deduplicated_relation_count=deduplicated_relation_count,
        plan_summary=plan_summary,
        blocked_entity_records=blocked_entity_records,
        deletable_entity_records=deletable_entity_records,
        deletable_relation_records=deletable_relation_records,
    )
