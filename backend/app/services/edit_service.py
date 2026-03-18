import logging
import time
from typing import Any, Dict

from fastapi import HTTPException

from app.core import config, field_policy
from app.core.audit_logger import write_audit_record
from app.core.space_context import get_current_space
from app.core.escape import (
    escape_ngql_string,
    raise_validation_error,
    validate_updated_by,
)
from app.db.nebula_client import NebulaExecutionError, execute_ngql_safe
from app.object_meta import validation_service
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
            "space": get_current_space(),
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
          properties(vertex) AS props;
    """
    res = execute_ngql_safe(ngql)
    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="node not found")
    vid_value = _as_int(res.column_values("vid")[0])
    props = vw(res.column_values("props")[0]) or {}
    snapshot: Dict[str, Any] = {"vid": vid_value}
    if isinstance(props, dict):
        for key, value in props.items():
            snapshot[str(key)] = vw(value)
    snapshot["entity_name"] = _as_text(snapshot.get("entity_name"))
    snapshot["entity_type"] = _as_text(snapshot.get("entity_type"))
    snapshot["source"] = _as_text(snapshot.get("source"))
    snapshot["description"] = _as_text(snapshot.get("description"))
    snapshot["entity_raw_id"] = _as_text(snapshot.get("entity_raw_id"))
    snapshot["version"] = _as_int(snapshot.get("version"))
    snapshot["updated_at"] = _as_int(snapshot.get("updated_at"))
    snapshot["updated_by"] = _as_text(snapshot.get("updated_by"))
    return snapshot


def _edge_snapshot(src: int, dst: int, rank: int) -> Dict[str, Any]:
    ngql = f"""
    MATCH (a:`Entity`)-[e:`{config.EDGE_TYPE}`]->(b:`Entity`)
    WHERE id(a) == {int(src)} AND id(b) == {int(dst)} AND rank(e) == {int(rank)}
    RETURN id(a) AS src,
           id(b) AS dst,
           rank(e) AS rank,
           properties(e) AS props
    LIMIT 1;
    """
    res = execute_ngql_safe(ngql)
    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="edge not found")
    snapshot: Dict[str, Any] = {
        "src": int(vw(res.column_values("src")[0])),
        "dst": int(vw(res.column_values("dst")[0])),
        "rank": str(int(vw(res.column_values("rank")[0]) or 0)),
        "edge_type": config.EDGE_TYPE,
    }
    props = vw(res.column_values("props")[0]) or {}
    if isinstance(props, dict):
        for key, value in props.items():
            snapshot[validation_service.canonical_field_name("edge", str(key))] = vw(value)
    snapshot["relation"] = str(snapshot.get("relation") or "")
    snapshot["source"] = str(snapshot.get("source") or "")
    snapshot["evidence"] = str(snapshot.get("evidence") or "")
    snapshot["version"] = int(snapshot.get("version") or 0)
    snapshot["updated_at"] = int(snapshot.get("updated_at") or 0)
    snapshot["updated_by"] = str(snapshot.get("updated_by") or "")
    return snapshot


def patch_node(vid: int, req: NodePatchRequest) -> Dict[str, Any]:
    actor = ""
    expected_version = int(req.expected_version) if isinstance(req.expected_version, int) else -1
    identity = {"vid": int(vid)}
    phase = "validate"
    try:
        actor = validate_updated_by(req.updated_by)
        expected_version = _ensure_expected_version(req.expected_version)
        phase = "snapshot_before"
        before = _node_snapshot(vid=int(vid))
        incoming_set = validation_service.validate_patch_set("node", req.set, current_snapshot=before)
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
            rule = validation_service.get_field_rule("node", field_name, current_snapshot=before)
            cleaned = raw_value
            escaped = escape_ngql_string(
                value=cleaned,
                field_name=field_name,
                max_len=rule.max_len,
                multiline=rule.multiline,
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
        identity = {
            "src": int(req.src),
            "dst": int(req.dst),
            "rank": str(rank_int),
            "edge_type": config.EDGE_TYPE,
        }

        before = _edge_snapshot(src=int(req.src), dst=int(req.dst), rank=rank_int)
        incoming_set = validation_service.validate_patch_set("edge", req.set, current_snapshot=before)
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
            rule = validation_service.get_field_rule("edge", field_name, current_snapshot=before)
            cleaned = raw_value
            escaped = escape_ngql_string(
                value=cleaned,
                field_name=field_name,
                max_len=rule.max_len,
                multiline=rule.multiline,
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
