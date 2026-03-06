import os
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, execute_ngql
from app.schemas.edge import EdgeSearchRequest
from app.services.common import esc, vw

EDGE_SUGGEST_SCAN_LIMIT = int(os.getenv("EDGE_SUGGEST_SCAN_LIMIT", "1500"))
EDGE_SEARCH_SCAN_LIMIT = int(os.getenv("EDGE_SEARCH_SCAN_LIMIT", "8000"))
EDGE_PROP_VALUE_MAX_LEN = int(os.getenv("EDGE_PROP_VALUE_MAX_LEN", "300"))
EDGE_PROP_MAX_FIELDS = int(os.getenv("EDGE_PROP_MAX_FIELDS", "24"))
EDGE_SNIPPET_MAX_LEN = int(os.getenv("EDGE_SNIPPET_MAX_LEN", "90"))
EDGE_PROP_FIELD_WHITELIST = {
    x.strip().lower()
    for x in os.getenv(
        "EDGE_PROP_FIELD_WHITELIST",
        "evidence,description,sentence,text,pmid,title,label,name,alias,mesh_id,umls_id,drug,disease,symptom,target,pathway",
    ).split(",")
    if x.strip()
}


def relation_display(raw_relation: str) -> str:
    raw = (raw_relation or "").strip()
    if "|" in raw:
        raw = raw.split("|", 1)[0]
    return raw.replace("_", " ").strip()


def _fetch_edge_rows(
    scan_limit: int,
    relation_filter: Optional[str] = None,
    source_db_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    where_parts: List[str] = []
    if relation_filter and relation_filter.strip():
        rel_esc = esc(relation_filter.strip().lower())
        where_parts.append(f'lower(coalesce(properties(e).relation, "")) CONTAINS "{rel_esc}"')
    if source_db_filter and source_db_filter.strip():
        src_esc = esc(source_db_filter.strip().lower())
        where_parts.append(f'lower(coalesce(properties(e).source, "")) == "{src_esc}"')

    where_clause = ""
    if where_parts:
        where_clause = "WHERE " + " AND ".join(f"({p})" for p in where_parts)

    ngql = f"""
    MATCH (src:`Entity`)-[e:{EDGE_TAG}]->(dst:`Entity`)
    {where_clause}
    RETURN id(src) AS src,
           id(dst) AS dst,
           rank(e) AS rank,
           coalesce(properties(e).relation, "") AS relation,
           coalesce(properties(e).source, "") AS source_db,
           properties(e) AS props
LIMIT {int(scan_limit)};
    """
    res = execute_ngql(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    srcs = res.column_values("src")
    dsts = res.column_values("dst")
    ranks = res.column_values("rank")
    relations = res.column_values("relation")
    source_dbs = res.column_values("source_db")
    propss = res.column_values("props")

    seen = set()
    rows: List[Dict[str, Any]] = []
    for i in range(len(srcs)):
        src = int(vw(srcs[i]))
        dst = int(vw(dsts[i]))
        rank = int(vw(ranks[i]) or 0)
        relation = str(vw(relations[i]) or "")
        source_db = str(vw(source_dbs[i]) or "")
        key = (src, dst, rank)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "src": src,
                "dst": dst,
                "rank": rank,
                "relation": relation,
                "source_db": source_db,
                "props": vw(propss[i]) or {},
            }
        )
    return rows


def _safe_prop_pairs(props: Any) -> List[Tuple[str, str]]:
    if not isinstance(props, dict):
        return []

    out: List[Tuple[str, str]] = []
    scanned = 0
    for k, v in props.items():
        if scanned >= EDGE_PROP_MAX_FIELDS:
            break
        scanned += 1

        key = str(k).strip()
        key_lower = key.lower()
        if EDGE_PROP_FIELD_WHITELIST and key_lower not in EDGE_PROP_FIELD_WHITELIST:
            continue

        vv = vw(v)
        if vv is None:
            continue

        if isinstance(vv, str):
            text = vv.strip()
        elif isinstance(vv, (int, float, bool)):
            text = str(vv)
        else:
            continue

        if not text or len(text) > EDGE_PROP_VALUE_MAX_LEN:
            continue

        out.append((key, text))
    return out


def _truncate(s: str, n: int) -> str:
    return s if len(s) <= n else (s[:n] + "...")


def _score_edge(
    q_norm: str,
    relation: str,
    props: Any,
    search_in_relation: bool,
    search_in_props: bool,
) -> Tuple[float, bool, List[Tuple[str, str]], str]:
    relation_raw = str(relation or "")
    relation_norm = relation_raw.lower()
    relation_disp = relation_display(relation_raw)
    relation_disp_norm = relation_disp.lower()

    score = 0.0
    relation_hit = False
    matched_props: List[Tuple[str, str]] = []
    snippet = ""

    if search_in_relation and q_norm:
        if relation_disp_norm.startswith(q_norm):
            score += 0.72
            relation_hit = True
            snippet = "matched: relation(prefix)"
        elif q_norm in relation_disp_norm:
            score += 0.50
            relation_hit = True
            snippet = "matched: relation(contains)"
        elif q_norm in relation_norm:
            score += 0.40
            relation_hit = True
            snippet = "matched: relation(raw)"

    if search_in_props and q_norm:
        for k, text in _safe_prop_pairs(props):
            if q_norm in text.lower():
                matched_props.append((k, text))

        if matched_props:
            score += min(0.28, 0.10 + 0.06 * len(matched_props))
            if not snippet:
                k, text = matched_props[0]
                snippet = f"matched: {k}={_truncate(text, EDGE_SNIPPET_MAX_LEN)}"

    return score, relation_hit, matched_props, snippet


def _fetch_entity_labels(vids: List[int]) -> Dict[int, str]:
    uniq = sorted(set(int(v) for v in vids))
    if not uniq:
        return {}

    id_list = ",".join(str(v) for v in uniq)
    ngql = f"""
    MATCH (v:`Entity`)
    WHERE id(v) IN [{id_list}]
    RETURN id(v) AS vid,
           coalesce(v.`Entity`.`entity_name`, "") AS name
LIMIT {len(uniq)};
    """

    res = execute_ngql(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    vids_col = res.column_values("vid")
    names_col = res.column_values("name")
    out: Dict[int, str] = {}
    for i in range(len(vids_col)):
        out[int(vw(vids_col[i]))] = str(vw(names_col[i]) or "")
    return out


def _search_core(
    q: str,
    limit: int,
    search_in_relation: bool,
    search_in_props: bool,
    relation_filter: Optional[str],
    source_db_filter: Optional[str],
    scan_limit: int,
) -> Dict[str, Any]:
    q_clean = (q or "").strip()
    if not q_clean:
        return {"edges": [], "total_candidates": 0}

    if not search_in_relation and not search_in_props:
        search_in_relation = True

    q_norm = q_clean.lower()
    rows = _fetch_edge_rows(
        scan_limit=scan_limit,
        relation_filter=relation_filter,
        source_db_filter=source_db_filter,
    )

    scored: List[Dict[str, Any]] = []
    for row in rows:
        score, relation_hit, matched_props, snippet = _score_edge(
            q_norm=q_norm,
            relation=row["relation"],
            props=row["props"],
            search_in_relation=search_in_relation,
            search_in_props=search_in_props,
        )

        matched = False
        if search_in_relation and relation_hit:
            matched = True
        if search_in_props and matched_props:
            matched = True
        if not matched:
            continue

        scored.append(
            {
                "edge_type": config.EDGE_TYPE,
                "src": row["src"],
                "dst": row["dst"],
                "rank": str(row["rank"]),
                "relation": row["relation"],
                "source_db": row["source_db"],
                "score": round(float(score), 6),
                "snippet": snippet or "matched: relation",
            }
        )

    scored.sort(
        key=lambda x: (
            -x["score"],
            len(x["relation"] or ""),
            x["src"],
            x["dst"],
            int(x["rank"]),
            x["relation"],
            x["source_db"],
        )
    )

    total_candidates = len(scored)
    top_edges = scored[:limit]

    label_vids: List[int] = []
    for e in top_edges:
        label_vids.append(int(e["src"]))
        label_vids.append(int(e["dst"]))
    label_map = _fetch_entity_labels(label_vids)

    for e in top_edges:
        e["src_label"] = label_map.get(int(e["src"]), "")
        e["dst_label"] = label_map.get(int(e["dst"]), "")

    return {"edges": top_edges, "total_candidates": total_candidates}


def edge_suggest(
    q: str,
    limit: int = 12,
    relation: Optional[str] = None,
    source_db: Optional[str] = None,
) -> Dict[str, Any]:
    safe_limit = max(1, min(int(limit), 50))
    result = _search_core(
        q=q,
        limit=safe_limit + 1,
        search_in_relation=True,
        search_in_props=True,
        relation_filter=relation,
        source_db_filter=source_db,
        scan_limit=EDGE_SUGGEST_SCAN_LIMIT,
    )

    edges = result["edges"]
    truncated = len(edges) > safe_limit
    items = []
    for e in edges[:safe_limit]:
        items.append(
            {
                "edge_type": config.EDGE_TYPE,
                "src": e["src"],
                "dst": e["dst"],
                "rank": e["rank"],
                "relation": e["relation"],
                "source_db": e["source_db"],
                "score": e["score"],
                "src_label": e["src_label"],
                "dst_label": e["dst_label"],
            }
        )

    return {"q": (q or "").strip(), "items": items, "truncated": truncated}


def edge_search(req: EdgeSearchRequest) -> Dict[str, Any]:
    safe_limit = max(1, min(int(req.limit), 100))
    result = _search_core(
        q=req.q,
        limit=safe_limit,
        search_in_relation=bool(req.search_in_relation),
        search_in_props=bool(req.search_in_props),
        relation_filter=req.relation,
        source_db_filter=req.source_db,
        scan_limit=EDGE_SEARCH_SCAN_LIMIT,
    )
    return {"edges": result["edges"], "total_candidates": result["total_candidates"]}
