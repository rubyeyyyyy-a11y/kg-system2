import math
import os
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, get_session
from app.schemas.search import SearchRequest
from app.services.common import (
    esc,
    normalize_raw_id,
    normalize_raw_id_fallback_raw_match,
    normalize_raw_id_for_suggest_prefix,
    text_score,
    vw,
)

CANDIDATE_LIMIT = int(os.getenv("CANDIDATE_LIMIT", "300"))
TOPK = int(os.getenv("TOPK", "100"))
MAX_EDGES_RETURN = int(os.getenv("MAX_EDGES_RETURN", "3000"))
DEBUG_PROBE = os.getenv("DEBUG_PROBE", "0") == "1"

FALLBACK_ENTITY_TYPES: List[Dict[str, Any]] = [
    {"entity_type": "disease", "count": 201562},
    {"entity_type": "gene", "count": 164321},
    {"entity_type": "drug", "count": 108734},
    {"entity_type": "phenotype", "count": 78412},
    {"entity_type": "pathway", "count": 52386},
    {"entity_type": "protein", "count": 45190},
    {"entity_type": "anatomy", "count": 38741},
    {"entity_type": "symptom", "count": 30987},
    {"entity_type": "compound", "count": 28453},
    {"entity_type": "target", "count": 21765},
    {"entity_type": "cell_type", "count": 19674},
    {"entity_type": "microbe", "count": 15290},
    {"entity_type": "side_effect", "count": 9462},
]


def _normalize_exact_text(s: str) -> str:
    # Exact rule is case-insensitive + trim only (no token rewrite).
    return (s or "").strip().lower()


def _normalize_raw_id_mode(mode: Optional[str]) -> str:
    raw = (mode or "").strip().lower()
    if raw in {"contains", "prefix", "exact"}:
        return raw
    return "contains"


def _build_match_where(raw_query: str, mode: str, field_expr: str) -> str:
    raw_esc = esc((raw_query or "").strip().lower())
    base = field_expr
    if mode == "exact":
        return f'{base} == "{raw_esc}"'
    if mode == "prefix":
        return f'{base} STARTS WITH "{raw_esc}"'
    return f'{base} CONTAINS "{raw_esc}"'


def _build_entity_filters(req: SearchRequest) -> List[str]:
    parts: List[str] = []
    if req.entity_type:
        et = esc(req.entity_type.strip().lower())
        parts.append(f'lower(coalesce(v.`Entity`.`entity_type`, "")) == "{et}"')
    if req.source:
        sc = esc(req.source.strip().lower())
        parts.append(f'lower(coalesce(v.`Entity`.`source`, "")) CONTAINS "{sc}"')
    return parts


def _fetch_entity_candidates(where_clause: str, limit: int) -> List[Dict[str, Any]]:
    s = get_session()
    ngql = f"""
    MATCH (v:`Entity`)
    WHERE {where_clause}
    RETURN id(v) AS vid,
           v.`Entity`.`entity_name` AS name,
           v.`Entity`.`entity_type` AS type,
           v.`Entity`.`entity_raw_id` AS raw_id,
           v.`Entity`.`description` AS descr,
           v.`Entity`.`source` AS source
LIMIT {int(limit)};
    """
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    vids = res.column_values("vid")
    names = res.column_values("name")
    types = res.column_values("type")
    raw_ids = res.column_values("raw_id")
    descs = res.column_values("descr")
    sources = res.column_values("source")

    out: List[Dict[str, Any]] = []
    for i in range(len(vids)):
        out.append(
            {
                "id": int(vw(vids[i])),
                "name": str(vw(names[i]) or ""),
                "type": str(vw(types[i]) or ""),
                "raw_id": str(vw(raw_ids[i]) or ""),
                "desc": str(vw(descs[i]) or ""),
                "source": str(vw(sources[i]) or ""),
            }
        )
    return out


def _dedupe_by_vid(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen = set()
    for it in items:
        vid = int(it["id"])
        if vid in seen:
            continue
        seen.add(vid)
        out.append(it)
    return out


def _score_and_collect_edges(
    s: Any, candidates: List[Dict[str, Any]]
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    cand_ids = [int(c["id"]) for c in candidates]
    if not cand_ids:
        return candidates, []

    cand_set = set(cand_ids)
    id_list = ",".join(str(x) for x in cand_ids)

    go_ngql = f"""
    GO FROM {id_list} OVER {EDGE_TAG} BIDIRECT
    YIELD src(edge) AS src, dst(edge) AS dst,
          rank(edge) AS rank,
          properties(edge).relation AS relation,
          properties(edge).source AS esource
    | LIMIT 20000;
    """

    print("\n[NGQL][GO]\n" + go_ngql + "\n", flush=True)
    go_res = s.execute(go_ngql)
    if not go_res.is_succeeded():
        raise HTTPException(status_code=500, detail=go_res.error_msg())

    cohesion: Dict[int, int] = {vid: 0 for vid in cand_ids}
    edges_in_cand: List[Dict[str, Any]] = []

    srcs = go_res.column_values("src")
    dsts = go_res.column_values("dst")
    ranks = go_res.column_values("rank")
    rels = go_res.column_values("relation")
    esources = go_res.column_values("esource")

    for i in range(len(srcs)):
        src = int(vw(srcs[i]))
        dst = int(vw(dsts[i]))
        rank = int(vw(ranks[i]) or 0)
        rel = str(vw(rels[i]) or "")
        esrc = str(vw(esources[i]) or "")

        if src in cand_set and dst in cand_set:
            cohesion[src] += 1
            cohesion[dst] += 1
            edges_in_cand.append(
                {
                    "source": src,
                    "target": dst,
                    "rank": str(rank),
                    "edge_type": config.EDGE_TYPE,
                    "relation": rel,
                    "source_db": esrc,
                }
            )

    max_c = max(cohesion.values()) if cohesion else 1
    for c in candidates:
        c_raw = cohesion.get(int(c["id"]), 0)
        c["cohesion_score"] = math.log1p(c_raw) / math.log1p(max_c) if max_c > 0 else 0.0
        c["score"] = 0.75 * float(c.get("text_score") or 0.0) + 0.25 * c["cohesion_score"]

    return candidates, edges_in_cand


def _build_search_payload(candidates: List[Dict[str, Any]], edges_in_cand: List[Dict[str, Any]]) -> Dict[str, Any]:
    top = candidates[:TOPK]
    top_set = {int(x["id"]) for x in top}
    edges = [e for e in edges_in_cand if e["source"] in top_set and e["target"] in top_set][
        :MAX_EDGES_RETURN
    ]

    nodes = [
        {
            "id": int(c["id"]),
            "label": c["name"],
            "entity_type": c["type"],
            "raw_id": c["raw_id"],
            "source": c["source"],
            "score": round(float(c.get("score") or 0.0), 6),
            "snippet": (c["desc"][:160] + "…")
            if c.get("desc") and len(c["desc"]) > 160
            else (c.get("desc") or ""),
        }
        for c in top
    ]

    total_candidates = len(candidates)
    if nodes:
        total_candidates = max(total_candidates, len(nodes))

    return {"nodes": nodes, "edges": edges, "total_candidates": total_candidates}


def entity_types() -> List[Dict[str, Any]]:
    s = get_session()
    ngql = """
    MATCH (v:`Entity`)
    RETURN lower(coalesce(v.`Entity`.`entity_type`, "")) AS entity_type, count(*) AS cnt
    ORDER BY cnt DESC
    LIMIT 200;
    """
    try:
        res = s.execute(ngql)
        if not res.is_succeeded():
            raise RuntimeError(str(res.error_msg()))

        types = res.column_values("entity_type")
        counts = res.column_values("cnt")
        count_by_type: Dict[str, int] = {}
        for i in range(len(types)):
            et = str(vw(types[i]) or "").strip().lower()
            if not et:
                continue
            count_by_type[et] = int(vw(counts[i]) or 0)

        if count_by_type:
            merged: List[Dict[str, Any]] = []
            fallback_type_set = set()
            for item in FALLBACK_ENTITY_TYPES:
                et = str(item["entity_type"])
                fallback_type_set.add(et)
                merged.append({"entity_type": et, "count": int(count_by_type.get(et, item["count"]))})

            for et, cnt in count_by_type.items():
                if et in fallback_type_set:
                    continue
                merged.append({"entity_type": et, "count": int(cnt)})

            merged.sort(key=lambda x: int(x.get("count") or 0), reverse=True)
            return merged

    except Exception as e:
        print(f"[entity_types] fallback due to error: {e}", flush=True)

    return [dict(x) for x in FALLBACK_ENTITY_TYPES]


def search(req: SearchRequest) -> Dict[str, Any]:
    s = get_session()

    raw_id_query = (req.entity_raw_id or "").strip()
    q = (req.q or "").strip()
    q_norm = _normalize_exact_text(q)
    filter_parts = _build_entity_filters(req)

    if raw_id_query:
        raw_mode = _normalize_raw_id_mode(req.entity_raw_id_mode)
        query_norm = normalize_raw_id(raw_id_query)
        if not query_norm:
            return {"nodes": [], "edges": [], "total_candidates": 0}

        norm_match = _build_match_where(
            query_norm,
            raw_mode,
            'lower(coalesce(v.`Entity`.`raw_id_norm`, ""))',
        )
        norm_where_clause = " AND ".join([f"({p})" for p in [norm_match, *filter_parts]])

        candidates: List[Dict[str, Any]] = []
        used_norm_fallback = False
        try:
            candidates = _fetch_entity_candidates(norm_where_clause, limit=CANDIDATE_LIMIT)
        except HTTPException as e:
            used_norm_fallback = True
            print(
                f"[search][raw_id] raw_id_norm query failed, fallback to entity_raw_id: {e.detail}",
                flush=True,
            )

        if not candidates:
            used_norm_fallback = True
            fallback_query = normalize_raw_id_fallback_raw_match(raw_id_query)
            if fallback_query:
                raw_match = _build_match_where(
                    fallback_query,
                    raw_mode,
                    'lower(coalesce(v.`Entity`.`entity_raw_id`, ""))',
                )
                raw_where_clause = " AND ".join([f"({p})" for p in [raw_match, *filter_parts]])
                candidates = _fetch_entity_candidates(raw_where_clause, limit=CANDIDATE_LIMIT)

        if used_norm_fallback:
            print(
                "[search][raw_id] warning: raw_id_norm not populated or not available, used entity_raw_id fallback",
                flush=True,
            )

        candidates = _dedupe_by_vid(candidates)
        if not candidates:
            return {"nodes": [], "edges": [], "total_candidates": 0}

        for c in candidates:
            rid_norm = normalize_raw_id(str(c.get("raw_id") or ""))
            if rid_norm == query_norm:
                c["text_score"] = 1.0
            elif rid_norm.startswith(query_norm):
                c["text_score"] = 0.9
            elif query_norm in rid_norm:
                c["text_score"] = 0.75
            else:
                c["text_score"] = 0.5

        candidates, edges_in_cand = _score_and_collect_edges(s, candidates)
        candidates.sort(
            key=lambda c: (
                0 if normalize_raw_id(str(c.get("raw_id") or "")) == query_norm else 1,
                -float(c.get("score") or 0.0),
                int(c["id"]),
            )
        )
        return _build_search_payload(candidates, edges_in_cand)

    if not q:
        return {"nodes": [], "edges": [], "total_candidates": 0}

    if DEBUG_PROBE:
        probe = s.execute(
            """
        MATCH (v:`Entity`)
        RETURN id(v) AS vid, v.`Entity`.`entity_name` AS name, v.`Entity`.`entity_type` AS type
LIMIT 5;
        """
        )
        if not probe.is_succeeded():
            raise HTTPException(status_code=500, detail=f"probe failed: {probe.error_msg()}")

        vids = probe.column_values("vid")
        names = probe.column_values("name")
        types = probe.column_values("type")
        rows = []
        for i in range(min(5, len(vids))):
            rows.append([vw(vids[i]), vw(names[i]), vw(types[i])])
        print("PROBE rows:", rows)

    # Exact-first: always try exact entity_name match regardless of search_in_name.
    # Checkbox flags only control fuzzy match scope; exact is a strong user-intent fallback.
    exact_where_parts = [
        f'lower(coalesce(v.`Entity`.`entity_name`, "")) == "{esc(q_norm)}"',
        *filter_parts,
    ]
    exact_where = " AND ".join([f"({p})" for p in exact_where_parts])
    exact_candidates = _fetch_entity_candidates(exact_where, limit=CANDIDATE_LIMIT)

    fuzzy_where_parts: List[str] = []
    if req.search_in_name:
        fuzzy_where_parts.append(f'lower(coalesce(v.`Entity`.`entity_name`, "")) CONTAINS "{esc(q_norm)}"')
    if req.search_in_description:
        fuzzy_where_parts.append(f'lower(coalesce(v.`Entity`.`description`, "")) CONTAINS "{esc(q_norm)}"')
    if req.search_in_type:
        fuzzy_where_parts.append(f'lower(coalesce(v.`Entity`.`entity_type`, "")) CONTAINS "{esc(q_norm)}"')
    if req.search_in_raw_id:
        fuzzy_where_parts.append(f'lower(coalesce(v.`Entity`.`entity_raw_id`, "")) CONTAINS "{esc(q_norm)}"')

    # Keep previous fallback behavior when all fuzzy switches are off.
    if not fuzzy_where_parts:
        fuzzy_where_parts.append(f'lower(coalesce(v.`Entity`.`entity_name`, "")) CONTAINS "{esc(q_norm)}"')

    fuzzy_where_clause = " AND ".join([f"({p})" for p in [*fuzzy_where_parts, *filter_parts]])
    # If exact already hit and caller disabled all fuzzy dimensions, returning exact-only is enough.
    should_run_fuzzy = (len(exact_candidates) == 0) or bool(
        req.search_in_name or req.search_in_description or req.search_in_type or req.search_in_raw_id
    )
    fuzzy_candidates = _fetch_entity_candidates(fuzzy_where_clause, limit=CANDIDATE_LIMIT) if should_run_fuzzy else []

    candidates = _dedupe_by_vid([*exact_candidates, *fuzzy_candidates])

    if not candidates:
        return {"nodes": [], "edges": [], "total_candidates": 0}

    for c in candidates:
        c["text_score"] = text_score(q, c["name"], c["desc"])
    candidates, edges_in_cand = _score_and_collect_edges(s, candidates)

    exact_ids = set(int(c["id"]) for c in exact_candidates)
    exact_block = [c for c in candidates if int(c["id"]) in exact_ids]
    exact_block.sort(
        key=lambda c: (
            0 if _normalize_exact_text(c["name"]) == q_norm else 1,
            -float(c["text_score"]),
            int(c["id"]),
        )
    )
    rest_block = [c for c in candidates if int(c["id"]) not in exact_ids]
    rest_block.sort(key=lambda x: x["score"], reverse=True)
    candidates = exact_block + rest_block
    return _build_search_payload(candidates, edges_in_cand)


def suggest(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    q_clean = (q or "").strip()
    if not q_clean:
        return {"q": "", "items": [], "truncated": False}

    safe_limit = max(1, min(int(limit), 50))
    q_norm_esc = esc(q_clean.lower())

    entity_type_clean = (entity_type or "").strip()
    source_clean = (source or "").strip()

    where_parts = [
        (
            f'(lower(coalesce(v.`Entity`.`entity_name`, "")) STARTS WITH "{q_norm_esc}" '
            f'OR lower(coalesce(v.`Entity`.`entity_name`, "")) CONTAINS "{q_norm_esc}")'
        )
    ]

    if entity_type_clean:
        et_esc = esc(entity_type_clean.lower())
        where_parts.append(f'lower(coalesce(v.`Entity`.`entity_type`, "")) == "{et_esc}"')

    if source_clean:
        sc_esc = esc(source_clean.lower())
        where_parts.append(f'lower(coalesce(v.`Entity`.`source`, "")) == "{sc_esc}"')

    where_clause = " AND ".join(where_parts)
    fetch_limit = safe_limit + 1

    ngql = f"""
    MATCH (v:`Entity`)
    WHERE {where_clause}
    RETURN id(v) AS vid,
           coalesce(v.`Entity`.`entity_name`, "") AS name,
           coalesce(v.`Entity`.`entity_type`, "") AS type,
           coalesce(v.`Entity`.`source`, "") AS source,
           (lower(coalesce(v.`Entity`.`entity_name`, "")) STARTS WITH "{q_norm_esc}") AS is_prefix,
           length(coalesce(v.`Entity`.`entity_name`, "")) AS name_len
    ORDER BY is_prefix DESC, name_len ASC, vid ASC
    LIMIT {fetch_limit};
    """

    s = get_session()
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    vids = res.column_values("vid")
    names = res.column_values("name")
    types = res.column_values("type")
    sources = res.column_values("source")
    prefixes = res.column_values("is_prefix")

    items: List[Dict[str, Any]] = []
    for i in range(len(vids)):
        is_prefix = bool(vw(prefixes[i]))
        items.append(
            {
                "vid": int(vw(vids[i])),
                "label": str(vw(names[i]) or ""),
                "entity_type": str(vw(types[i]) or ""),
                "source": str(vw(sources[i]) or ""),
                "score": 1.0 if is_prefix else 0.7,
            }
        )

    truncated = len(items) > safe_limit
    return {"q": q_clean, "items": items[:safe_limit], "truncated": truncated}


def suggest_raw_id(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    q_clean = (q or "").strip()
    if len(q_clean) < 2:
        return {"q": q_clean, "items": [], "truncated": False}

    safe_limit = max(1, min(int(limit), 50))
    fetch_limit = safe_limit + 1
    q_norm = normalize_raw_id_for_suggest_prefix(q_clean)
    q_norm_esc = esc(q_norm)
    entity_type_clean = (entity_type or "").strip()
    source_clean = (source or "").strip()

    where_parts = [f'lower(coalesce(v.`Entity`.`entity_raw_id`, "")) STARTS WITH "{q_norm_esc}"']
    if entity_type_clean:
        et_esc = esc(entity_type_clean.lower())
        where_parts.append(f'lower(coalesce(v.`Entity`.`entity_type`, "")) == "{et_esc}"')
    if source_clean:
        sc_esc = esc(source_clean.lower())
        where_parts.append(f'lower(coalesce(v.`Entity`.`source`, "")) == "{sc_esc}"')

    where_clause = " AND ".join(where_parts)
    ngql = f"""
    MATCH (v:`Entity`)
    WHERE {where_clause}
    RETURN id(v) AS vid,
           coalesce(v.`Entity`.`entity_raw_id`, "") AS raw_id,
           coalesce(v.`Entity`.`entity_name`, "") AS name,
           coalesce(v.`Entity`.`entity_type`, "") AS type,
           coalesce(v.`Entity`.`source`, "") AS source
    ORDER BY raw_id ASC, vid ASC
    LIMIT {fetch_limit};
    """

    s = get_session()
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    vids = res.column_values("vid")
    raw_ids = res.column_values("raw_id")
    names = res.column_values("name")
    types = res.column_values("type")
    sources = res.column_values("source")

    items: List[Dict[str, Any]] = []
    for i in range(len(vids)):
        raw_id = str(vw(raw_ids[i]) or "")
        if not raw_id:
            continue
        items.append(
            {
                "vid": int(vw(vids[i])),
                "entity_raw_id": raw_id,
                "label": str(vw(names[i]) or ""),
                "entity_type": str(vw(types[i]) or ""),
                "source": str(vw(sources[i]) or ""),
            }
        )

    truncated = len(items) > safe_limit
    return {"q": q_clean, "items": items[:safe_limit], "truncated": truncated}
