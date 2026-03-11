import time
from typing import Any

from fastapi import HTTPException

from app.core.escape import escape_ngql_string, validate_updated_by
from app.db.nebula_client import execute_ngql_safe
from app.services.common import vw
from app.services.imports.models import CompiledTargetPlan


def _fetch_vertex_exists(tag_name: str, vid: int) -> bool:
    res = execute_ngql_safe(f"FETCH PROP ON `{tag_name}` {int(vid)} YIELD id(vertex) AS vid;")
    return len(res.rows()) > 0


def _fetch_edge_exists(edge_type: str, src: int, dst: int, rank: int) -> bool:
    ngql = f"""
    MATCH ()-[e:`{edge_type}`]->()
    WHERE src(e) == {int(src)} AND dst(e) == {int(dst)} AND rank(e) == {int(rank)}
    RETURN src(e) AS src
    LIMIT 1;
    """
    res = execute_ngql_safe(ngql)
    return len(res.rows()) > 0


def _encode_value(field_name: str, field_type: str, raw_value: str) -> str:
    if field_type.lower() in {"int", "int64", "integer"}:
        return str(int(str(raw_value or "").strip()))
    if field_type.lower() in {"double", "float"}:
        return str(float(str(raw_value or "").strip()))
    return f'"{escape_ngql_string(str(raw_value or ""), field_name, 65535, True)}"'


def _generated_rank(src: int, dst: int, row_index: int) -> int:
    return abs(hash(f"{src}:{dst}:{row_index}")) % 2147483647


def _vertex_payload(target: CompiledTargetPlan, row: dict[str, str], actor: str) -> tuple[int, dict[str, str]]:
    reverse = {target_field: source_column for source_column, target_field in target.field_mappings.items()}
    if "ID" not in reverse:
        raise HTTPException(status_code=422, detail="vertex mapping requires ID")
    vid = int(str(row.get(reverse["ID"], "")).strip())
    payload: dict[str, str] = {}
    for source_column, target_field in target.field_mappings.items():
        if target_field == "ID":
            continue
        payload[target_field] = str(row.get(source_column, "") or "")
    payload["updated_by"] = actor
    payload["updated_at"] = str(int(time.time()))
    return vid, payload


def _edge_payload(target: CompiledTargetPlan, row: dict[str, str], row_index: int, actor: str) -> tuple[int, int, int, dict[str, str]]:
    reverse = {target_field: source_column for source_column, target_field in target.field_mappings.items()}
    src = int(str(row.get(reverse["srcVID"], "")).strip())
    dst = int(str(row.get(reverse["dstVID"], "")).strip())
    rank = (
        int(str(row.get(reverse["rank"], "")).strip())
        if "rank" in reverse and str(row.get(reverse["rank"], "")).strip()
        else _generated_rank(src, dst, row_index)
    )
    payload: dict[str, str] = {}
    for source_column, target_field in target.field_mappings.items():
        if target_field in {"srcVID", "dstVID", "rank"}:
            continue
        payload[target_field] = str(row.get(source_column, "") or "")
    payload["updated_by"] = actor
    payload["updated_at"] = str(int(time.time()))
    return src, dst, rank, payload


def import_row(target: CompiledTargetPlan, row: dict[str, str], *, row_index: int, actor: str) -> dict[str, Any]:
    actor_text = validate_updated_by(actor)
    if target.object_type == "tag":
        vid, payload = _vertex_payload(target, row, actor_text)
        exists = _fetch_vertex_exists(target.object_name, vid)
        property_types = target.property_types
        if exists:
            clauses = []
            for field_name in target.update_fields:
                if field_name not in payload:
                    continue
                clauses.append(f"`{field_name}` = {_encode_value(field_name, property_types.get(field_name, 'string'), payload[field_name])}")
            clauses.append(f"`version` = coalesce(`version`, 0) + 1")
            clauses.append(f"`updated_at` = {int(payload['updated_at'])}")
            clauses.append(f'`updated_by` = "{escape_ngql_string(actor_text, "updated_by", 64, False)}"')
            execute_ngql_safe(f"UPDATE VERTEX ON `{target.object_name}` {vid} SET {', '.join(clauses)};")
        else:
            fields = []
            values = []
            for field_name in target.create_fields:
                if field_name == "entity_raw_id" or field_name in target.update_fields:
                    fields.append(field_name)
                    values.append(_encode_value(field_name, property_types.get(field_name, "string"), payload.get(field_name, "")))
            fields.extend(["version", "updated_at", "updated_by"])
            values.extend(["1", payload["updated_at"], f'"{escape_ngql_string(actor_text, "updated_by", 64, False)}"'])
            execute_ngql_safe(
                f"INSERT VERTEX `{target.object_name}`({', '.join(f'`{field}`' for field in fields)}) VALUES {vid}:({', '.join(values)});"
            )
        return {"kind": "vertex", "vid": vid, "target": target.object_name}

    src, dst, rank, payload = _edge_payload(target, row, row_index, actor_text)
    exists = _fetch_edge_exists(target.object_name, src, dst, rank)
    property_types = target.property_types
    if exists:
        clauses = []
        for field_name in target.update_fields:
            if field_name not in payload:
                continue
            clauses.append(f"`{field_name}` = {_encode_value(field_name, property_types.get(field_name, 'string'), payload[field_name])}")
        clauses.append("`version` = coalesce(`version`, 0) + 1")
        clauses.append(f"`updated_at` = {int(payload['updated_at'])}")
        clauses.append(f'`updated_by` = "{escape_ngql_string(actor_text, "updated_by", 64, False)}"')
        execute_ngql_safe(f"UPDATE EDGE ON `{target.object_name}` {src}->{dst}@{rank} SET {', '.join(clauses)};")
    else:
        fields = [field for field in target.create_fields if field not in {"srcVID", "dstVID", "rank"}]
        values = [
            _encode_value(field_name, property_types.get(field_name, "string"), payload.get(field_name, ""))
            for field_name in fields
        ]
        fields.extend(["version", "updated_at", "updated_by"])
        values.extend(["1", payload["updated_at"], f'"{escape_ngql_string(actor_text, "updated_by", 64, False)}"'])
        execute_ngql_safe(
            f"INSERT EDGE `{target.object_name}`({', '.join(f'`{field}`' for field in fields)}) VALUES {src}->{dst}@{rank}:({', '.join(values)});"
        )
    return {"kind": "edge", "src": src, "dst": dst, "rank": rank, "target": target.object_name}
