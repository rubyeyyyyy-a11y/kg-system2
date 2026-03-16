import time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from app.core.escape import escape_ngql_string, validate_updated_by
from app.db.nebula_client import execute_ngql_safe
from app.services.imports.models import CompiledTargetPlan


@dataclass
class BatchRowItem:
    row_index: int
    row: dict[str, str]


@dataclass
class BatchImportResult:
    successes: list[dict[str, Any]]
    failures: list[tuple[BatchRowItem, Exception]]
    batch_statement_count: int
    used_fallback: bool = False


def _encode_value(field_name: str, field_type: str, raw_value: str) -> str:
    if field_type.lower() in {"int", "int64", "integer"}:
        return str(int(str(raw_value or "").strip()))
    if field_type.lower() in {"double", "float"}:
        return str(float(str(raw_value or "").strip()))
    return f'"{escape_ngql_string(str(raw_value or ""), field_name, 65535, True)}"'


def _generated_rank(src: int, dst: int, row_index: int) -> int:
    return abs(hash(f"{src}:{dst}:{row_index}")) % 2147483647


def _vertex_payload(target: CompiledTargetPlan, row: dict[str, str], actor: str) -> tuple[int, dict[str, str]]:
    if not target.identity_mapping.id_column:
        raise HTTPException(status_code=422, detail="vertex mapping requires identity_mapping.id_column")
    vid = int(str(row.get(target.identity_mapping.id_column, "")).strip())
    payload = {item.target_field: str(row.get(item.source_column, "") or "") for item in target.property_mappings}
    payload["updated_by"] = actor
    payload["updated_at"] = str(int(time.time()))
    return vid, payload


def _edge_payload(target: CompiledTargetPlan, row: dict[str, str], row_index: int, actor: str) -> tuple[int, int, int, dict[str, str]]:
    if not target.identity_mapping.src_column or not target.identity_mapping.dst_column:
        raise HTTPException(status_code=422, detail="edge mapping requires identity_mapping.src_column and dst_column")
    src = int(str(row.get(target.identity_mapping.src_column, "")).strip())
    dst = int(str(row.get(target.identity_mapping.dst_column, "")).strip())
    rank = (
        int(str(row.get(target.identity_mapping.rank_column, "")).strip())
        if target.identity_mapping.rank_column and str(row.get(target.identity_mapping.rank_column, "")).strip()
        else _generated_rank(src, dst, row_index)
    )
    payload = {item.target_field: str(row.get(item.source_column, "") or "") for item in target.property_mappings}
    payload["updated_by"] = actor
    payload["updated_at"] = str(int(time.time()))
    return src, dst, rank, payload


def _vertex_statement(target: CompiledTargetPlan, row: dict[str, str], *, row_index: int, actor: str) -> tuple[str, dict[str, Any]]:
    actor_text = validate_updated_by(actor)
    vid, payload = _vertex_payload(target, row, actor_text)
    property_types = target.property_types
    clauses = []
    for field_name in target.update_fields:
        if field_name not in payload:
            continue
        clauses.append(f"`{field_name}` = {_encode_value(field_name, property_types.get(field_name, 'string'), payload[field_name])}")
    if "entity_raw_id" in target.create_fields and "entity_raw_id" in payload:
        encoded = _encode_value("entity_raw_id", property_types.get("entity_raw_id", "string"), payload["entity_raw_id"])
        clauses.append(f"`entity_raw_id` = coalesce(`entity_raw_id`, {encoded})")
    clauses.append("`version` = coalesce(`version`, 0) + 1")
    clauses.append(f"`updated_at` = {int(payload['updated_at'])}")
    clauses.append(f'`updated_by` = "{escape_ngql_string(actor_text, "updated_by", 64, False)}"')
    return (
        f"UPSERT VERTEX ON `{target.object_name}` {vid} SET {', '.join(clauses)};",
        {"kind": "vertex", "vid": vid, "target": target.object_name, "row_index": row_index},
    )


def _edge_statement(target: CompiledTargetPlan, row: dict[str, str], *, row_index: int, actor: str) -> tuple[str, dict[str, Any]]:
    actor_text = validate_updated_by(actor)
    src, dst, rank, payload = _edge_payload(target, row, row_index, actor_text)
    property_types = target.property_types
    clauses = []
    for field_name in target.create_fields:
        if field_name not in payload:
            continue
        clauses.append(f"`{field_name}` = {_encode_value(field_name, property_types.get(field_name, 'string'), payload[field_name])}")
    clauses.append("`version` = coalesce(`version`, 0) + 1")
    clauses.append(f"`updated_at` = {int(payload['updated_at'])}")
    clauses.append(f'`updated_by` = "{escape_ngql_string(actor_text, "updated_by", 64, False)}"')
    return (
        f"UPSERT EDGE ON `{target.object_name}` {src}->{dst}@{rank} SET {', '.join(clauses)};",
        {"kind": "edge", "src": src, "dst": dst, "rank": rank, "target": target.object_name, "row_index": row_index},
    )


def build_row_statement(
    target: CompiledTargetPlan,
    row: dict[str, str],
    *,
    row_index: int,
    actor: str,
) -> tuple[str, dict[str, Any]]:
    if target.object_type == "tag":
        return _vertex_statement(target, row, row_index=row_index, actor=actor)
    return _edge_statement(target, row, row_index=row_index, actor=actor)


def _build_insert_batch_statement(
    target: CompiledTargetPlan,
    rows: list[BatchRowItem],
    *,
    actor: str,
) -> tuple[str, list[dict[str, Any]]]:
    actor_text = validate_updated_by(actor)
    if target.object_type == "tag":
        field_order = list(target.create_fields) + ["version", "updated_at", "updated_by"]
        values_sql: list[str] = []
        result_meta: list[dict[str, Any]] = []
        for item in rows:
            vid, payload = _vertex_payload(target, item.row, actor_text)
            encoded_values = []
            for field_name in target.create_fields:
                encoded_values.append(
                    _encode_value(field_name, target.property_types.get(field_name, "string"), payload.get(field_name, ""))
                )
            encoded_values.extend(["1", payload["updated_at"], f'"{escape_ngql_string(actor_text, "updated_by", 64, False)}"'])
            values_sql.append(f"{vid}:({', '.join(encoded_values)})")
            result_meta.append({"kind": "vertex", "vid": vid, "target": target.object_name, "row_index": item.row_index})
        statement = (
            f"INSERT VERTEX `{target.object_name}`({', '.join(f'`{field}`' for field in field_order)}) "
            f"VALUES {', '.join(values_sql)};"
        )
        return statement, result_meta

    field_order = list(target.create_fields) + ["version", "updated_at", "updated_by"]
    values_sql = []
    result_meta = []
    for item in rows:
        src, dst, rank, payload = _edge_payload(target, item.row, item.row_index, actor_text)
        encoded_values = []
        for field_name in target.create_fields:
            encoded_values.append(
                _encode_value(field_name, target.property_types.get(field_name, "string"), payload.get(field_name, ""))
            )
        encoded_values.extend(["1", payload["updated_at"], f'"{escape_ngql_string(actor_text, "updated_by", 64, False)}"'])
        values_sql.append(f"{src}->{dst}@{rank}:({', '.join(encoded_values)})")
        result_meta.append({"kind": "edge", "src": src, "dst": dst, "rank": rank, "target": target.object_name, "row_index": item.row_index})
    statement = (
        f"INSERT EDGE `{target.object_name}`({', '.join(f'`{field}`' for field in field_order)}) "
        f"VALUES {', '.join(values_sql)};"
    )
    return statement, result_meta


def import_row(
    target: CompiledTargetPlan,
    row: dict[str, str],
    *,
    row_index: int,
    actor: str,
    space_name: str | None = None,
) -> dict[str, Any]:
    statement, result_meta = build_row_statement(target, row, row_index=row_index, actor=actor)
    execute_ngql_safe(statement, space_name=space_name)
    return result_meta


def import_batch(
    target: CompiledTargetPlan,
    rows: list[BatchRowItem],
    *,
    actor: str,
    space_name: str | None = None,
) -> BatchImportResult:
    if not rows:
        return BatchImportResult(successes=[], failures=[], batch_statement_count=0, used_fallback=False)
    for item in rows:
        # Pre-validate row payloads so obviously bad rows still resolve to row-level failures.
        build_row_statement(target, item.row, row_index=item.row_index, actor=actor)
    try:
        batch_statement, result_meta = _build_insert_batch_statement(target, rows, actor=actor)
        execute_ngql_safe(batch_statement, space_name=space_name)
        return BatchImportResult(
            successes=result_meta,
            failures=[],
            batch_statement_count=1,
            used_fallback=False,
        )
    except Exception as batch_exc:
        if len(rows) == 1:
            return BatchImportResult(
                successes=[],
                failures=[(rows[0], batch_exc)],
                batch_statement_count=1,
                used_fallback=False,
            )

    successes: list[dict[str, Any]] = []
    failures: list[tuple[BatchRowItem, Exception]] = []
    for item in rows:
        try:
            successes.append(import_row(target, item.row, row_index=item.row_index, actor=actor, space_name=space_name))
        except Exception as exc:
            failures.append((item, exc))
    return BatchImportResult(
        successes=successes,
        failures=failures,
        batch_statement_count=len(rows),
        used_fallback=True,
    )
