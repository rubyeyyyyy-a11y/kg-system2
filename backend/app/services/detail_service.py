import json
import math
from typing import Any, Dict

from fastapi import HTTPException

from app.db.nebula import EDGE_TAG, get_session
from app.schemas.detail import EdgeDetailRequest, EdgeUpdateRequest
from app.services.common import esc, vw


def node_detail(vid: int) -> Dict[str, Any]:
    s = get_session()
    ngql = f"""
    FETCH PROP ON `Entity` {int(vid)}
    YIELD properties(vertex) AS props;
    """
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="node not found")

    props_col = res.column_values("props")
    props = vw(props_col[0]) or {}

    out = {}
    if isinstance(props, dict):
        for k, v in props.items():
            out[str(k)] = vw(v)

    return {"vid": int(vid), "props": out}


def _edge_lookup(src: int, dst: int, rank: int) -> Dict[str, Any]:
    s = get_session()
    ngql = f"""
    MATCH (a:`Entity`)-[e:{EDGE_TAG}]->(b:`Entity`)
    WHERE id(a) == {int(src)} AND id(b) == {int(dst)} AND rank(e) == {int(rank)}
    RETURN properties(e) AS props
    LIMIT 1;
    """
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())
    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="edge not found")

    props_col = res.column_values("props")
    props = vw(props_col[0]) or {}
    out: Dict[str, Any] = {}
    if isinstance(props, dict):
        for k, v in props.items():
            out[str(k)] = vw(v)

    return {
        "src": int(src),
        "dst": int(dst),
        "rank": str(int(rank)),
        "relation": str(out.get("relation") or ""),
        "source_db": str(out.get("source") or ""),
        "props": out,
    }


def _parse_rank(raw_rank: str) -> int:
    text = str(raw_rank or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="rank is required")
    try:
        return int(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="rank must be an int64 string") from exc


def _to_ngql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise HTTPException(status_code=400, detail="invalid float value in edge props")
        return repr(value)

    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    return f'"{esc(text)}"'


def edge_detail(req: EdgeDetailRequest) -> Dict[str, Any]:
    payload = _edge_lookup(src=int(req.src), dst=int(req.dst), rank=_parse_rank(req.rank))
    payload["updated"] = False
    return payload


def edge_update(req: EdgeUpdateRequest) -> Dict[str, Any]:
    if not isinstance(req.props, dict) or len(req.props) == 0:
        raise HTTPException(status_code=400, detail="props must be a non-empty object")

    src = int(req.src)
    dst = int(req.dst)
    rank = _parse_rank(req.rank)
    _edge_lookup(src=src, dst=dst, rank=rank)

    set_parts = []
    for k, v in req.props.items():
        key = str(k).strip()
        if not key:
            continue
        key = key.replace("`", "")
        set_parts.append(f"`{key}` = {_to_ngql_literal(v)}")
    if not set_parts:
        raise HTTPException(status_code=400, detail="no valid prop keys to update")

    ngql = f"""
    UPDATE EDGE ON {EDGE_TAG} {src}->{dst}@{rank}
    SET {", ".join(set_parts)};
    """
    s = get_session()
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    payload = _edge_lookup(src=src, dst=dst, rank=rank)
    payload["updated"] = True
    return payload
