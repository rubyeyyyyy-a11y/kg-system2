import logging
import time
from typing import Any, Dict

from fastapi import HTTPException

from app.core import config, field_policy
from app.core.audit_logger import write_audit_record
from app.core.escape import (
    escape_ngql_string,
    raise_validation_error,
    validate_text,
    validate_updated_by,
)
from app.db.nebula_client import NebulaExecutionError, execute_ngql_safe
from app.schemas.edit import EdgePatchRequest, NodePatchRequest
from app.services import metadata_service
from app.services.common import vw

logger = logging.getLogger(__name__)


def editable_fields() -> Dict[str, Any]:
    return field_policy.editable_fields_payload()


def _parse_rank(rank: str) -> int:
    text = str(rank or "").strip()
    if not text:
        raise_validation_error("'rank' is required", field="rank")
    try:
        return int(text)
    except ValueError as exc:
        raise_validation_error("'rank' must be int64 string", field="rank")


def _ensure_expected_version(v: int) -> int:
    if not isinstance(v, int):
        raise_validation_error("'expected_version' must be int", field="expected_version")
    if v < 0:
        raise_validation_error("'expected_version' must be >= 0", field="expected_version")
    return v


def _detail_text(detail: Any) -> str:
    if isinstance(detail, dict):
        msg = detail.get("message")
        if msg is not None:
            return str(msg)
    return str(detail)


def _as_text(value: Any) -> str:
    raw = vw(value)
    if raw is None:
        return ""
    return str(raw)


def _as_int(value: Any) -> int:
    raw = vw(value)
    if raw in (None, ""):
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _audit(
    *,
    actor: str,
    object_type: str,
    identity: Dict[str, Any],
    expected_version: int,
    before_version: int | None,
    after_version: int | None,
    diff: Dict[str, Any],
    result: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    write_audit_record(
        {
            "ts": int(time.time()),
            "actor": actor,
            "space": config.SPACE,
            "object_type": object_type,
            "identity": identity,
            "expected_version": expected_version,
            "before_version": before_version,
            "after_version": after_version,
            "diff": diff,
            "result": result,
            "error_code": error_code,
            "error_message": error_message,
        }
    )


def _node_snapshot(vid: int) -> Dict[str, Any]:
    ngql = f"""
    FETCH PROP ON `Entity` {int(vid)}
    YIELD id(vertex) AS vid,
          properties(vertex).entity_name AS entity_name,
          properties(vertex).entity_type AS entity_type,
          properties(vertex).source AS source,
          properties(vertex).description AS description,
          properties(vertex).entity_raw_id AS entity_raw_id,
          properties(vertex).version AS version,
          properties(vertex).updated_at AS updated_at,
          properties(vertex).updated_by AS updated_by;
    """
    res = execute_ngql_safe(ngql)
    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="node not found")
    cols = {
        "vid": res.column_values("vid"),
        "entity_name": res.column_values("entity_name"),
        "entity_type": res.column_values("entity_type"),
        "source": res.column_values("source"),
        "description": res.column_values("description"),
        "entity_raw_id": res.column_values("entity_raw_id"),
        "version": res.column_values("version"),
        "updated_at": res.column_values("updated_at"),
        "updated_by": res.column_values("updated_by"),
    }
    return {
        "vid": _as_int(cols["vid"][0]),
        "entity_name": _as_text(cols["entity_name"][0]),
        "entity_type": _as_text(cols["entity_type"][0]),
        "source": _as_text(cols["source"][0]),
        "description": _as_text(cols["description"][0]),
        "entity_raw_id": _as_text(cols["entity_raw_id"][0]),
        "version": _as_int(cols["version"][0]),
        "updated_at": _as_int(cols["updated_at"][0]),
        "updated_by": _as_text(cols["updated_by"][0]),
    }


def _edge_snapshot(src: int, dst: int, rank: int) -> Dict[str, Any]:
    ngql = f"""
    MATCH (a:`Entity`)-[e:`{config.EDGE_TYPE}`]->(b:`Entity`)
    WHERE id(a) == {int(src)} AND id(b) == {int(dst)} AND rank(e) == {int(rank)}
    RETURN id(a) AS src,
           id(b) AS dst,
           rank(e) AS rank,
           coalesce(properties(e).relation, "") AS relation,
           coalesce(properties(e).source, "") AS source,
           coalesce(properties(e).evidence, "") AS evidence,
           coalesce(properties(e).version, 0) AS version,
           coalesce(properties(e).updated_at, 0) AS updated_at,
           coalesce(properties(e).updated_by, "") AS updated_by
    LIMIT 1;
    """
    res = execute_ngql_safe(ngql)
    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="edge not found")
    cols = {
        "src": res.column_values("src"),
        "dst": res.column_values("dst"),
        "rank": res.column_values("rank"),
        "relation": res.column_values("relation"),
        "source": res.column_values("source"),
        "evidence": res.column_values("evidence"),
        "version": res.column_values("version"),
        "updated_at": res.column_values("updated_at"),
        "updated_by": res.column_values("updated_by"),
    }
    return {
        "src": int(vw(cols["src"][0])),
        "dst": int(vw(cols["dst"][0])),
        "rank": str(int(vw(cols["rank"][0]) or 0)),
        "relation": str(vw(cols["relation"][0]) or ""),
        "source": str(vw(cols["source"][0]) or ""),
        "evidence": str(vw(cols["evidence"][0]) or ""),
        "version": int(vw(cols["version"][0]) or 0),
        "updated_at": int(vw(cols["updated_at"][0]) or 0),
        "updated_by": str(vw(cols["updated_by"][0]) or ""),
        "edge_type": config.EDGE_TYPE,
    }


def patch_node(vid: int, req: NodePatchRequest) -> Dict[str, Any]:
    actor = ""
    expected_version = int(req.expected_version) if isinstance(req.expected_version, int) else -1
    identity = {"vid": int(vid)}
    phase = "validate"
    try:
        actor = validate_updated_by(req.updated_by)
        expected_version = _ensure_expected_version(req.expected_version)
        incoming_set = field_policy.validate_node_patch_set(req.set)
        phase = "snapshot_before"
        before = _node_snapshot(vid=int(vid))
        before_version = int(before.get("version") or 0)
        if before_version != expected_version:
            _audit(
                actor=actor,
                object_type="node",
                identity=identity,
                expected_version=expected_version,
                before_version=before_version,
                after_version=None,
                diff={},
                result="conflict",
                error_code="VERSION_CONFLICT",
                error_message="expected_version mismatch",
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "VERSION_CONFLICT",
                    "message": "expected_version mismatch",
                    "current_version": before_version,
                    "current_snapshot": before,
                },
            )

        diff: Dict[str, Dict[str, str]] = {}
        set_clauses = []
        updated_values: Dict[str, str] = {}
        for field_name, raw_value in incoming_set.items():
            cleaned = validate_text(
                field_name=field_name,
                value=raw_value,
                max_len=config.ENTITY_FIELD_MAX_LEN[field_name],
                multiline=(field_name in config.ALLOW_MULTILINE_FIELDS),
            )
            escaped = escape_ngql_string(
                value=cleaned,
                field_name=field_name,
                max_len=config.ENTITY_FIELD_MAX_LEN[field_name],
                multiline=(field_name in config.ALLOW_MULTILINE_FIELDS),
            )
            set_clauses.append(f'`{field_name}` = "{escaped}"')
            updated_values[field_name] = cleaned
            old_value = str(before.get(field_name) or "")
            if old_value != cleaned:
                diff[field_name] = {"from": old_value, "to": cleaned}

        now_sec = int(time.time())
        new_version = before_version + 1
        actor_escaped = escape_ngql_string(actor, "updated_by", config.SYSTEM_FIELD_MAX_LEN["updated_by"], False)
        set_clauses.extend(
            [
                f"`version` = {new_version}",
                f"`updated_at` = {now_sec}",
                f'`updated_by` = "{actor_escaped}"',
            ]
        )
        update_ngql = f"""
        UPDATE VERTEX ON `Entity` {int(vid)}
        SET {", ".join(set_clauses)}
        ;
        """
        phase = "update"
        execute_ngql_safe(update_ngql)
        phase = "snapshot_after"
        after = _node_snapshot(vid=int(vid))
        if "entity_type" in incoming_set:
            metadata_service.sync_entity_type_change(
                before_type=str(before.get("entity_type") or ""),
                after_type=str(after.get("entity_type") or ""),
                actor=actor,
            )
        _audit(
            actor=actor,
            object_type="node",
            identity=identity,
            expected_version=expected_version,
            before_version=before_version,
            after_version=new_version,
            diff=diff,
            result="success",
        )
        return {
            "vid": int(vid),
            "updated": {k: after[k] for k in incoming_set.keys()},
            "version": int(after["version"]),
            "updated_at": int(after["updated_at"]),
            "updated_by": str(after["updated_by"]),
        }
    except HTTPException as exc:
        logger.warning(
            "node patch http error phase=%s vid=%s status=%s detail=%s",
            phase,
            int(vid),
            exc.status_code,
            exc.detail,
        )
        if exc.status_code == 422:
            _audit(
                actor=actor or str(req.updated_by or ""),
                object_type="node",
                identity=identity,
                expected_version=expected_version,
                before_version=None,
                after_version=None,
                diff={},
                result="validation_error",
                error_code="VALIDATION_ERROR",
                error_message=f"{phase}: {_detail_text(exc.detail)}",
            )
        elif exc.status_code == 404:
            _audit(
                actor=actor or str(req.updated_by or ""),
                object_type="node",
                identity=identity,
                expected_version=expected_version,
                before_version=None,
                after_version=None,
                diff={},
                result="fail",
                error_code="NOT_FOUND",
                error_message=f"{phase}: {_detail_text(exc.detail)}",
            )
        elif exc.status_code not in (409,):
            _audit(
                actor=actor or str(req.updated_by or ""),
                object_type="node",
                identity=identity,
                expected_version=expected_version,
                before_version=None,
                after_version=None,
                diff={},
                result="fail",
                error_code=f"HTTP_{exc.status_code}",
                error_message=f"{phase}: {_detail_text(exc.detail)}",
            )
        raise
    except NebulaExecutionError as exc:
        logger.exception("node patch nebula error phase=%s vid=%s", phase, int(vid))
        _audit(
            actor=actor or str(req.updated_by or ""),
            object_type="node",
            identity=identity,
            expected_version=expected_version,
            before_version=None,
            after_version=None,
            diff={},
            result="fail",
            error_code=exc.code,
            error_message=f"{phase}: {exc.message}",
        )
        raise HTTPException(
            status_code=500,
            detail={"error_code": exc.code, "request_id": str(int(time.time() * 1000))},
        ) from exc


def patch_edge(req: EdgePatchRequest) -> Dict[str, Any]:
    actor = ""
    expected_version = int(req.expected_version) if isinstance(req.expected_version, int) else -1
    rank_int = 0
    try:
        if req.edge_type and req.edge_type.strip() and req.edge_type.strip() != config.EDGE_TYPE:
            raise_validation_error(f"edge_type must be '{config.EDGE_TYPE}'", field="edge_type")
        actor = validate_updated_by(req.updated_by)
        expected_version = _ensure_expected_version(req.expected_version)
        rank_int = _parse_rank(req.rank)
        incoming_set = field_policy.validate_edge_patch_set(req.set)
        identity = {
            "src": int(req.src),
            "dst": int(req.dst),
            "rank": str(rank_int),
            "edge_type": config.EDGE_TYPE,
        }

        before = _edge_snapshot(src=int(req.src), dst=int(req.dst), rank=rank_int)
        before_version = int(before.get("version") or 0)
        if before_version != expected_version:
            _audit(
                actor=actor,
                object_type="edge",
                identity=identity,
                expected_version=expected_version,
                before_version=before_version,
                after_version=None,
                diff={},
                result="conflict",
                error_code="VERSION_CONFLICT",
                error_message="expected_version mismatch",
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "VERSION_CONFLICT",
                    "message": "expected_version mismatch",
                    "current_version": before_version,
                    "current_snapshot": before,
                },
            )

        diff: Dict[str, Dict[str, str]] = {}
        set_clauses = []
        for field_name, raw_value in incoming_set.items():
            cleaned = validate_text(
                field_name=field_name,
                value=raw_value,
                max_len=config.EDGE_FIELD_MAX_LEN[field_name],
                multiline=(field_name in config.ALLOW_MULTILINE_FIELDS),
            )
            escaped = escape_ngql_string(
                value=cleaned,
                field_name=field_name,
                max_len=config.EDGE_FIELD_MAX_LEN[field_name],
                multiline=(field_name in config.ALLOW_MULTILINE_FIELDS),
            )
            set_clauses.append(f'`{field_name}` = "{escaped}"')
            old_value = str(before.get(field_name) or "")
            if old_value != cleaned:
                diff[field_name] = {"from": old_value, "to": cleaned}

        now_sec = int(time.time())
        new_version = before_version + 1
        actor_escaped = escape_ngql_string(actor, "updated_by", config.SYSTEM_FIELD_MAX_LEN["updated_by"], False)
        set_clauses.extend(
            [
                f"`version` = {new_version}",
                f"`updated_at` = {now_sec}",
                f'`updated_by` = "{actor_escaped}"',
            ]
        )
        update_ngql = f"""
        UPDATE EDGE ON `{config.EDGE_TYPE}` {int(req.src)}->{int(req.dst)}@{rank_int}
        SET {", ".join(set_clauses)}
        ;
        """
        execute_ngql_safe(update_ngql)
        after = _edge_snapshot(src=int(req.src), dst=int(req.dst), rank=rank_int)
        if "relation" in incoming_set:
            metadata_service.sync_relation_type_change(
                before_relation=str(before.get("relation") or ""),
                after_relation=str(after.get("relation") or ""),
                actor=actor,
            )
        _audit(
            actor=actor,
            object_type="edge",
            identity=identity,
            expected_version=expected_version,
            before_version=before_version,
            after_version=new_version,
            diff=diff,
            result="success",
        )
        return {
            "identity": identity,
            "updated": {k: after[k] for k in incoming_set.keys()},
            "version": int(after["version"]),
            "updated_at": int(after["updated_at"]),
            "updated_by": str(after["updated_by"]),
        }
    except HTTPException as exc:
        identity = {
            "src": int(req.src),
            "dst": int(req.dst),
            "rank": str(rank_int if rank_int else req.rank or ""),
            "edge_type": config.EDGE_TYPE,
        }
        if exc.status_code == 422:
            _audit(
                actor=actor or str(req.updated_by or ""),
                object_type="edge",
                identity=identity,
                expected_version=expected_version,
                before_version=None,
                after_version=None,
                diff={},
                result="validation_error",
                error_code="VALIDATION_ERROR",
                error_message=_detail_text(exc.detail),
            )
        elif exc.status_code == 404:
            _audit(
                actor=actor or str(req.updated_by or ""),
                object_type="edge",
                identity=identity,
                expected_version=expected_version,
                before_version=None,
                after_version=None,
                diff={},
                result="fail",
                error_code="NOT_FOUND",
                error_message=_detail_text(exc.detail),
            )
        elif exc.status_code not in (409,):
            _audit(
                actor=actor or str(req.updated_by or ""),
                object_type="edge",
                identity=identity,
                expected_version=expected_version,
                before_version=None,
                after_version=None,
                diff={},
                result="fail",
                error_code=f"HTTP_{exc.status_code}",
                error_message=_detail_text(exc.detail),
            )
        raise
    except NebulaExecutionError as exc:
        identity = {
            "src": int(req.src),
            "dst": int(req.dst),
            "rank": str(rank_int if rank_int else req.rank or ""),
            "edge_type": config.EDGE_TYPE,
        }
        _audit(
            actor=actor or str(req.updated_by or ""),
            object_type="edge",
            identity=identity,
            expected_version=expected_version,
            before_version=None,
            after_version=None,
            diff={},
            result="fail",
            error_code=exc.code,
            error_message=exc.message,
        )
        raise HTTPException(
            status_code=500,
            detail={"error_code": exc.code, "request_id": str(int(time.time() * 1000))},
        ) from exc
