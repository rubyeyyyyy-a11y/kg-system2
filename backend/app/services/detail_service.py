from typing import Any, Dict

from fastapi import HTTPException

from app.db.nebula import get_session
from app.schemas.detail import EdgeDetailRequest
from app.services.common import vw


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


def edge_detail(req: EdgeDetailRequest) -> Dict[str, Any]:
    s = get_session()

    src = int(req.src)
    dst = int(req.dst)
    relation = (req.relation or "").strip()
    source_db = (req.source_db or "").strip()

    go_ngql = f"""
    GO FROM {src} OVER `REL` BIDIRECT
    YIELD src(edge) AS src, dst(edge) AS dst,
          properties(edge) AS props
    | LIMIT 20000;
    """
    res = s.execute(go_ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    srcs = res.column_values("src")
    dsts = res.column_values("dst")
    propss = res.column_values("props")

    for i in range(len(srcs)):
        ssrc = int(vw(srcs[i]))
        ddst = int(vw(dsts[i]))
        props = vw(propss[i]) or {}

        if ssrc != src or ddst != dst:
            continue

        pr = ""
        ps = ""
        if isinstance(props, dict):
            pr = str(vw(props.get("relation")) or "")
            ps = str(vw(props.get("source")) or "")

        if pr != relation:
            continue
        if source_db and ps != source_db:
            continue

        out = {}
        if isinstance(props, dict):
            for k, v in props.items():
                out[str(k)] = vw(v)

        return {"src": src, "dst": dst, "props": out}

    raise HTTPException(status_code=404, detail="edge not found")
