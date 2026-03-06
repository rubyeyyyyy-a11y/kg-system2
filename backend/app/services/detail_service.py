from typing import Any, Dict

from fastapi import HTTPException

from app.core import config
from app.core.escape import raise_validation_error
from app.db.nebula_client import NebulaExecutionError, execute_ngql_safe
from app.schemas.detail import EdgeDetailRequest
from app.services.common import vw


def node_detail(vid: int) -> Dict[str, Any]:
    ngql = f"""
    MATCH (v:`Entity`)
    WHERE id(v) == {int(vid)}
    RETURN id(v) AS vid,
           coalesce(v.`Entity`.`entity_name`, "") AS entity_name,
           coalesce(v.`Entity`.`entity_type`, "") AS entity_type,
           coalesce(v.`Entity`.`source`, "") AS source,
           coalesce(v.`Entity`.`description`, "") AS description,
           coalesce(v.`Entity`.`entity_raw_id`, "") AS entity_raw_id,
           coalesce(v.`Entity`.`version`, 0) AS version,
           coalesce(v.`Entity`.`updated_at`, 0) AS updated_at,
           coalesce(v.`Entity`.`updated_by`, "") AS updated_by,
           properties(v) AS props
    LIMIT 1;
    """
    try:
        res = execute_ngql_safe(ngql)
    except NebulaExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="node not found")

    def col(name: str):
        return res.column_values(name)[0]

    props = vw(col("props")) or {}
    props_out: Dict[str, Any] = {}
    if isinstance(props, dict):
        for k, v in props.items():
            props_out[str(k)] = vw(v)

    return {
        "vid": int(vw(col("vid"))),
        "entity_name": str(vw(col("entity_name")) or ""),
        "entity_type": str(vw(col("entity_type")) or ""),
        "source": str(vw(col("source")) or ""),
        "description": str(vw(col("description")) or ""),
        "entity_raw_id": str(vw(col("entity_raw_id")) or ""),
        "version": int(vw(col("version")) or 0),
        "updated_at": int(vw(col("updated_at")) or 0),
        "updated_by": str(vw(col("updated_by")) or ""),
        "props": props_out,
    }


def edge_detail(req: EdgeDetailRequest) -> Dict[str, Any]:
    if (req.edge_type or "").strip() != config.EDGE_TYPE:
        raise_validation_error(f"edge_type must be '{config.EDGE_TYPE}'", field="edge_type")

    try:
        rank_int = int(str(req.rank).strip())
    except ValueError as exc:
        raise_validation_error("'rank' must be int64 string", field="rank")

    ngql = f"""
    MATCH (a:`Entity`)-[e:`{config.EDGE_TYPE}`]->(b:`Entity`)
    WHERE id(a) == {int(req.src)} AND id(b) == {int(req.dst)} AND rank(e) == {rank_int}
    RETURN id(a) AS src,
           id(b) AS dst,
           rank(e) AS rank,
           coalesce(properties(e).relation, "") AS relation,
           coalesce(properties(e).source, "") AS source_db,
           coalesce(properties(e).evidence, "") AS evidence,
           coalesce(properties(e).version, 0) AS version,
           coalesce(properties(e).updated_at, 0) AS updated_at,
           coalesce(properties(e).updated_by, "") AS updated_by,
           properties(e) AS props
    LIMIT 1;
    """
    try:
        res = execute_ngql_safe(ngql)
    except NebulaExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if len(res.rows()) == 0:
        raise HTTPException(status_code=404, detail="edge not found")

    def col(name: str):
        return res.column_values(name)[0]

    props = vw(col("props")) or {}
    props_out: Dict[str, Any] = {}
    if isinstance(props, dict):
        for k, v in props.items():
            props_out[str(k)] = vw(v)

    return {
        "edge_type": config.EDGE_TYPE,
        "src": int(vw(col("src"))),
        "dst": int(vw(col("dst"))),
        "rank": str(int(vw(col("rank")) or 0)),
        "relation": str(vw(col("relation")) or ""),
        "source_db": str(vw(col("source_db")) or ""),
        "evidence": str(vw(col("evidence")) or ""),
        "version": int(vw(col("version")) or 0),
        "updated_at": int(vw(col("updated_at")) or 0),
        "updated_by": str(vw(col("updated_by")) or ""),
        "updated": False,
        "props": props_out,
    }
