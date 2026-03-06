import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, execute_ngql
from app.schemas.discovery import GraphDiscoveryRequest
from app.services.common import truncate_by_degree, uniq_edges, vw
from app.services.graph_budget import graph_budget

logger = logging.getLogger(__name__)

_EDGE_ROLE_PRIORITY = {
    "seed_candidate": 0,
    "candidate_candidate": 1,
    "seed_seed": 2,
}


def _normalize_key(raw: str) -> str:
    return str(raw or "").strip().lower()


def _budget_error(message: str, code: str = "graph_discovery_budget_reject") -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": code,
            "message": message,
        },
    )


def _normalize_filter(values: Iterable[str], max_count: int) -> Tuple[Set[str], int]:
    out: Set[str] = set()
    dropped = 0
    for item in values or []:
        key = _normalize_key(item)
        if not key:
            continue
        if key in out:
            continue
        if len(out) >= int(max_count):
            dropped += 1
            continue
        out.add(key)
    return out, dropped


def _fetch_entity_nodes(node_ids: Iterable[int]) -> Dict[int, Dict[str, Any]]:
    ids = sorted(set(int(v) for v in node_ids))
    if not ids:
        return {}

    vid_list = ",".join(str(x) for x in ids)
    fetch_ngql = f"""
    MATCH (v:`Entity`)
    WHERE id(v) IN [{vid_list}]
    RETURN id(v) AS vid,
           v.`Entity`.`entity_name` AS name,
           v.`Entity`.`entity_type` AS type,
           v.`Entity`.`entity_raw_id` AS raw_id,
           v.`Entity`.`source` AS source,
           v.`Entity`.`description` AS descr
LIMIT {len(ids)};
    """
    fres = execute_ngql(fetch_ngql)
    if not fres.is_succeeded():
        raise HTTPException(status_code=500, detail=fres.error_msg())

    vids = fres.column_values("vid")
    names = fres.column_values("name")
    types = fres.column_values("type")
    raw_ids = fres.column_values("raw_id")
    sources = fres.column_values("source")
    descs = fres.column_values("descr")

    node_map: Dict[int, Dict[str, Any]] = {}
    for i in range(len(vids)):
        vid = int(vw(vids[i]))
        name = str(vw(names[i]) or "")
        typ = str(vw(types[i]) or "")
        raw_id = str(vw(raw_ids[i]) or "")
        source = str(vw(sources[i]) or "")
        descr = str(vw(descs[i]) or "")
        node_map[vid] = {
            "id": vid,
            "label": name,
            "entity_type": typ,
            "raw_id": raw_id,
            "source": source,
            "snippet": (descr[:160] + "…") if descr and len(descr) > 160 else (descr or ""),
        }
    return node_map


def _go_edges_from(
    frontier: Iterable[int],
    rel_filter: Set[str],
    query_scan_limit: int,
    per_root_neighbor_cap: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    frontier_unique = sorted(set(int(x) for x in frontier))
    if not frontier_unique:
        return [], {
            "scanned_rows": 0,
            "dropped_by_relation": 0,
            "dropped_by_neighbor_cap": 0,
        }

    frontier_set = set(frontier_unique)
    id_list = ",".join(str(x) for x in frontier_unique)
    ngql = f"""
    GO FROM {id_list} OVER {EDGE_TAG} BIDIRECT
    YIELD src(edge) AS src,
          dst(edge) AS dst,
          rank(edge) AS rank,
          properties(edge).relation AS relation,
          properties(edge).source AS esource
    | LIMIT {int(query_scan_limit)};
    """
    res = execute_ngql(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    srcs = res.column_values("src")
    dsts = res.column_values("dst")
    ranks = res.column_values("rank")
    rels = res.column_values("relation")
    esources = res.column_values("esource")

    root_neighbor_count: Dict[int, int] = {int(v): 0 for v in frontier_unique}
    dropped_by_neighbor_cap = 0
    dropped_by_relation = 0
    out: List[Dict[str, Any]] = []

    for i in range(len(srcs)):
        src = int(vw(srcs[i]))
        dst = int(vw(dsts[i]))
        rank = int(vw(ranks[i]) or 0)
        relation = str(vw(rels[i]) or "")
        source_db = str(vw(esources[i]) or "")
        relation_norm = _normalize_key(relation)

        if rel_filter and relation_norm not in rel_filter:
            dropped_by_relation += 1
            continue

        anchors: List[int] = []
        if src in frontier_set:
            anchors.append(src)
        if dst in frontier_set and dst != src:
            anchors.append(dst)
        if not anchors:
            continue

        accepted = False
        for anchor in anchors:
            if int(root_neighbor_count.get(anchor) or 0) >= int(per_root_neighbor_cap):
                continue
            root_neighbor_count[anchor] = int(root_neighbor_count.get(anchor) or 0) + 1
            accepted = True
        if not accepted:
            dropped_by_neighbor_cap += 1
            continue

        out.append(
            {
                "source": src,
                "target": dst,
                "rank": str(rank),
                "edge_type": config.EDGE_TYPE,
                "relation": relation,
                "source_db": source_db,
            }
        )

    return uniq_edges(out), {
        "scanned_rows": len(srcs),
        "dropped_by_relation": dropped_by_relation,
        "dropped_by_neighbor_cap": dropped_by_neighbor_cap,
    }


def _edge_sort_key(edge: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        int(_EDGE_ROLE_PRIORITY.get(str(edge.get("role") or ""), 99)),
        -float(edge.get("_priority_score") or 0.0),
        int(edge["source"]),
        int(edge["target"]),
        int(edge.get("rank") or 0),
        str(edge.get("relation") or ""),
        str(edge.get("source_db") or ""),
    )


def _score_candidate(candidate: Dict[str, Any]) -> float:
    matched_seed_count = int(candidate.get("matched_seed_count") or 0)
    seed_edge_count = int(candidate.get("seed_edge_count") or 0)
    relation_diversity = int(candidate.get("relation_diversity") or 0)
    return float(matched_seed_count * 1000 + seed_edge_count * 100 + relation_diversity * 10)


def _candidate_sort_key(candidate: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        -float(candidate.get("score") or 0.0),
        -int(candidate.get("matched_seed_count") or 0),
        -int(candidate.get("seed_edge_count") or 0),
        str(candidate.get("entity_type_norm") or ""),
        int(candidate.get("id") or 0),
    )


def _select_candidates(
    candidates: Iterable[Dict[str, Any]],
    *,
    top_k_per_type: int,
    candidate_cap: int,
) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        grouped[str(item.get("entity_type_norm") or "")].append(item)

    kept: List[Dict[str, Any]] = []
    for entity_type in sorted(grouped.keys()):
        bucket = sorted(grouped[entity_type], key=_candidate_sort_key)
        kept.extend(bucket[: int(top_k_per_type)])

    kept.sort(key=_candidate_sort_key)
    return kept[: int(candidate_cap)]


def _trim_edges_with_priority(edges: Iterable[Dict[str, Any]], max_edges: int) -> Tuple[List[Dict[str, Any]], int]:
    edges_list = list(edges)
    if len(edges_list) <= int(max_edges):
        return edges_list, 0
    kept = sorted(edges_list, key=_edge_sort_key)[: int(max_edges)]
    return kept, max(0, len(edges_list) - len(kept))


def _build_facets(nodes: Iterable[Dict[str, Any]], edges: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    entity_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"count": 0, "seed_count": 0, "candidate_count": 0})
    relation_counts: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "count": 0,
            "seed_candidate_count": 0,
            "candidate_candidate_count": 0,
            "seed_seed_count": 0,
        }
    )

    for node in nodes:
        entity_type = str(node.get("entity_type") or "")
        bucket = entity_counts[entity_type]
        bucket["count"] += 1
        if str(node.get("role") or "") == "seed":
            bucket["seed_count"] += 1
        else:
            bucket["candidate_count"] += 1

    for edge in edges:
        relation = str(edge.get("relation") or "")
        role = str(edge.get("role") or "")
        bucket = relation_counts[relation]
        bucket["count"] += 1
        if role == "seed_candidate":
            bucket["seed_candidate_count"] += 1
        elif role == "candidate_candidate":
            bucket["candidate_candidate_count"] += 1
        elif role == "seed_seed":
            bucket["seed_seed_count"] += 1

    entity_items = [
        {
            "entity_type": entity_type,
            "count": counts["count"],
            "seed_count": counts["seed_count"],
            "candidate_count": counts["candidate_count"],
        }
        for entity_type, counts in entity_counts.items()
    ]
    entity_items.sort(key=lambda item: (-int(item["count"]), str(item["entity_type"])))

    relation_items = [
        {
            "relation_type": relation,
            "count": counts["count"],
            "seed_candidate_count": counts["seed_candidate_count"],
            "candidate_candidate_count": counts["candidate_candidate_count"],
            "seed_seed_count": counts["seed_seed_count"],
        }
        for relation, counts in relation_counts.items()
    ]
    relation_items.sort(key=lambda item: (-int(item["count"]), str(item["relation_type"])))

    return {
        "entity_types": entity_items,
        "relation_types": relation_items,
    }


def discovery(req: GraphDiscoveryRequest) -> Dict[str, Any]:
    requested_seed_count = len(req.seed_vids or [])
    requested_max_nodes = int(req.max_nodes or 300)
    requested_max_edges = int(req.max_edges or 1200)
    requested_top_k_per_type = int(req.top_k_per_type or 0)
    requested_hop = int(req.hop or 1)

    seed_vids: List[int] = []
    seen_seed = set()
    for vid in req.seed_vids or []:
        iv = int(vid)
        if iv in seen_seed:
            continue
        seen_seed.add(iv)
        seed_vids.append(iv)

    if not seed_vids:
        raise _budget_error("seed_vids must contain at least 1 entity", code="graph_discovery_seed_missing")
    if len(seed_vids) > graph_budget.discovery_seed_cap:
        raise _budget_error(
            f"seed_vids exceeds max slots {graph_budget.discovery_seed_cap}",
            code="graph_discovery_seed_overflow",
        )
    if requested_hop != 1:
        raise _budget_error("hop currently supports only 1 in discovery v1", code="graph_discovery_hop_unsupported")
    if requested_max_nodes < len(seed_vids):
        raise _budget_error("max_nodes is smaller than seed_vids count", code="graph_discovery_max_nodes_invalid")

    max_nodes = max(len(seed_vids), min(requested_max_nodes, graph_budget.discovery_max_nodes_cap))
    max_edges = max(1, min(requested_max_edges, graph_budget.discovery_max_edges_cap))

    top_k_per_type = max(1, min(requested_top_k_per_type, graph_budget.discovery_top_k_per_type_cap))
    allowed_entity_types, dropped_entity_filter_terms = _normalize_filter(
        req.allowed_entity_types or [],
        max_count=graph_budget.relation_filter_max,
    )
    allowed_relation_types, dropped_relation_filter_terms = _normalize_filter(
        req.allowed_relation_types or [],
        max_count=graph_budget.relation_filter_max,
    )
    query_scan_limit = max(
        max_edges,
        min(graph_budget.discovery_query_edge_scan_cap, max_edges * 4),
    )
    candidate_cap = min(
        max(0, max_nodes - len(seed_vids)),
        graph_budget.discovery_candidate_cap,
    )

    logger.info(
        "graph discovery start seeds=%d requested_max_nodes=%d requested_max_edges=%d top_k_per_type=%d include_candidate_candidate_edges=%s include_seed_seed_edges=%s",
        len(seed_vids),
        requested_max_nodes,
        requested_max_edges,
        requested_top_k_per_type,
        bool(req.include_candidate_candidate_edges),
        bool(req.include_seed_seed_edges),
    )

    seed_set = set(seed_vids)
    dropped_neighbors = 0
    scanned_rows = 0
    dropped_nodes = 0
    dropped_edges = 0
    truncated = False

    try:
        seed_edges_raw, seed_meta = _go_edges_from(
            seed_vids,
            rel_filter=allowed_relation_types,
            query_scan_limit=query_scan_limit,
            per_root_neighbor_cap=graph_budget.discovery_per_seed_neighbor_cap,
        )
        scanned_rows += int(seed_meta["scanned_rows"])
        dropped_neighbors += int(seed_meta["dropped_by_neighbor_cap"])

        candidate_support: Dict[int, Dict[str, Any]] = {}
        seed_seed_edges: List[Dict[str, Any]] = []

        for edge in seed_edges_raw:
            src = int(edge["source"])
            dst = int(edge["target"])
            if src in seed_set and dst in seed_set:
                seed_seed_edges.append(
                    {
                        **edge,
                        "role": "seed_seed",
                        "_priority_score": 0.0,
                    }
                )
                continue

            anchor_seed: Optional[int] = None
            candidate_vid: Optional[int] = None
            if src in seed_set and dst not in seed_set:
                anchor_seed = src
                candidate_vid = dst
            elif dst in seed_set and src not in seed_set:
                anchor_seed = dst
                candidate_vid = src
            if anchor_seed is None or candidate_vid is None:
                continue

            support = candidate_support.setdefault(
                candidate_vid,
                {
                    "id": candidate_vid,
                    "seed_support_vids": set(),
                    "support_edges": [],
                    "support_edge_keys": set(),
                    "relation_set": set(),
                },
            )
            support["seed_support_vids"].add(anchor_seed)
            relation_norm = _normalize_key(str(edge.get("relation") or ""))
            if relation_norm:
                support["relation_set"].add(relation_norm)
            edge_key = (int(edge["source"]), int(edge["target"]), int(edge.get("rank") or 0))
            if edge_key not in support["support_edge_keys"]:
                support["support_edge_keys"].add(edge_key)
                support["support_edges"].append(
                    {
                        **edge,
                        "role": "seed_candidate",
                    }
                )

        recall_candidate_count = len(candidate_support)

        candidate_node_map = _fetch_entity_nodes(candidate_support.keys())
        scored_candidates: List[Dict[str, Any]] = []
        for vid, support in candidate_support.items():
            node = candidate_node_map.get(int(vid))
            if not node:
                continue
            entity_type_norm = _normalize_key(str(node.get("entity_type") or ""))
            if allowed_entity_types and entity_type_norm not in allowed_entity_types:
                dropped_nodes += 1
                continue

            matched_seed_count = len(support["seed_support_vids"])
            seed_edge_count = len(support["support_edges"])
            relation_diversity = len(support["relation_set"])
            score = _score_candidate(
                {
                    "matched_seed_count": matched_seed_count,
                    "seed_edge_count": seed_edge_count,
                    "relation_diversity": relation_diversity,
                }
            )
            scored_candidates.append(
                {
                    **node,
                    "entity_type_norm": entity_type_norm,
                    "seed_support_vids": sorted(int(x) for x in support["seed_support_vids"]),
                    "matched_seed_count": matched_seed_count,
                    "seed_edge_count": seed_edge_count,
                    "relation_diversity": relation_diversity,
                    "score": score,
                    "score_breakdown": {
                        "matched_seed_count": matched_seed_count,
                        "seed_edge_count": seed_edge_count,
                        "relation_diversity": relation_diversity,
                        "total_score": score,
                    },
                    "support_edges": support["support_edges"],
                }
            )

        selected_candidates = _select_candidates(
            scored_candidates,
            top_k_per_type=top_k_per_type,
            candidate_cap=candidate_cap,
        )
        kept_candidate_vids = {int(item["id"]) for item in selected_candidates}
        if len(selected_candidates) < len(scored_candidates):
            dropped_nodes += len(scored_candidates) - len(selected_candidates)
            truncated = True

        seed_node_map = _fetch_entity_nodes(seed_vids)
        nodes_out: List[Dict[str, Any]] = []
        for vid in seed_vids:
            node = seed_node_map.get(int(vid))
            if node is None:
                node = {
                    "id": int(vid),
                    "label": str(vid),
                    "entity_type": "",
                    "raw_id": "",
                    "source": "",
                    "snippet": "",
                }
            nodes_out.append(
                {
                    **node,
                    "role": "seed",
                    "score": None,
                    "seed_support_count": 0,
                    "seed_support_vids": [],
                    "score_breakdown": {},
                }
            )

        selected_candidates.sort(key=_candidate_sort_key)
        for item in selected_candidates:
            nodes_out.append(
                {
                    "id": int(item["id"]),
                    "label": str(item.get("label") or ""),
                    "entity_type": str(item.get("entity_type") or ""),
                    "raw_id": str(item.get("raw_id") or ""),
                    "source": str(item.get("source") or ""),
                    "snippet": str(item.get("snippet") or ""),
                    "score": float(item["score"]),
                    "role": "candidate",
                    "seed_support_count": int(item["matched_seed_count"]),
                    "seed_support_vids": list(item["seed_support_vids"]),
                    "score_breakdown": dict(item["score_breakdown"]),
                }
            )

        edges_out: List[Dict[str, Any]] = []
        for item in selected_candidates:
            for edge in item["support_edges"]:
                edges_out.append(
                    {
                        **edge,
                        "_priority_score": float(item["score"]),
                    }
                )

        if req.include_candidate_candidate_edges and kept_candidate_vids:
            candidate_edges_raw, candidate_meta = _go_edges_from(
                kept_candidate_vids,
                rel_filter=allowed_relation_types,
                query_scan_limit=query_scan_limit,
                per_root_neighbor_cap=graph_budget.discovery_per_seed_neighbor_cap,
            )
            scanned_rows += int(candidate_meta["scanned_rows"])
            dropped_neighbors += int(candidate_meta["dropped_by_neighbor_cap"])
            candidate_score_map = {int(item["id"]): float(item["score"]) for item in selected_candidates}
            for edge in candidate_edges_raw:
                src = int(edge["source"])
                dst = int(edge["target"])
                if src not in kept_candidate_vids or dst not in kept_candidate_vids:
                    continue
                edges_out.append(
                    {
                        **edge,
                        "role": "candidate_candidate",
                        "_priority_score": max(candidate_score_map.get(src, 0.0), candidate_score_map.get(dst, 0.0)),
                    }
                )

        if req.include_seed_seed_edges:
            edges_out.extend(seed_seed_edges)

        edges_out = uniq_edges(edges_out)
        edges_out, trimmed_edges = _trim_edges_with_priority(edges_out, max_edges=max_edges)
        dropped_edges += int(trimmed_edges)
        if trimmed_edges > 0:
            truncated = True

        node_map_out = {int(node["id"]): dict(node) for node in nodes_out}
        used_node_ids = {int(node["id"]) for node in nodes_out if str(node.get("role") or "") == "seed"}
        for edge in edges_out:
            used_node_ids.add(int(edge["source"]))
            used_node_ids.add(int(edge["target"]))

        pruned_candidate_count = sum(
            1
            for node in nodes_out
            if str(node.get("role") or "") == "candidate" and int(node["id"]) not in used_node_ids
        )
        if pruned_candidate_count > 0:
            dropped_nodes += int(pruned_candidate_count)
            truncated = True

        final_nodes = [node_map_out[vid] for vid in seed_vids if vid in node_map_out]
        candidate_nodes = [
            node_map_out[vid]
            for vid in sorted(
                [vid for vid in used_node_ids if vid in node_map_out and str(node_map_out[vid].get("role") or "") == "candidate"],
                key=lambda vid: _candidate_sort_key(node_map_out[vid]),
            )
        ]
        final_nodes.extend(candidate_nodes)

        if len(final_nodes) > max_nodes:
            before_trim_edges = len(edges_out)
            forced_vids = [int(node["id"]) for node in final_nodes if str(node.get("role") or "") == "seed"]
            kept_nodes, kept_edges, degree_dropped_nodes = truncate_by_degree(
                root_vid=forced_vids[0],
                keep_forced=forced_vids,
                nodes_all=[int(node["id"]) for node in final_nodes],
                edges_all=edges_out,
                max_nodes=max_nodes,
            )
            kept_set = set(int(x) for x in kept_nodes)
            final_nodes = [node_map_out[int(vid)] for vid in seed_vids if int(vid) in kept_set]
            final_nodes.extend(
                [
                    node_map_out[int(vid)]
                    for vid in sorted(
                        [vid for vid in kept_set if vid not in seed_set and vid in node_map_out],
                        key=lambda vid: _candidate_sort_key(node_map_out[vid]),
                    )
                ]
            )
            edges_out = kept_edges
            dropped_nodes += int(degree_dropped_nodes)
            dropped_edges += max(0, before_trim_edges - len(edges_out))
            truncated = True

        final_edges = [
            {
                "source": int(edge["source"]),
                "target": int(edge["target"]),
                "rank": str(edge.get("rank") or "0"),
                "edge_type": str(edge.get("edge_type") or config.EDGE_TYPE),
                "relation": str(edge.get("relation") or ""),
                "source_db": str(edge.get("source_db") or ""),
                "role": str(edge.get("role") or "seed_candidate"),
            }
            for edge in edges_out
        ]

        facets = _build_facets(final_nodes, final_edges)
        kept_candidate_count = sum(1 for node in final_nodes if str(node.get("role") or "") == "candidate")
        budget_applied = {
            "api": "graph_discovery",
            "requested": {
                "seed_count": requested_seed_count,
                "hop": requested_hop,
                "max_nodes": requested_max_nodes,
                "max_edges": requested_max_edges,
                "top_k_per_type": requested_top_k_per_type,
                "allowed_entity_type_count": len(req.allowed_entity_types or []),
                "allowed_relation_type_count": len(req.allowed_relation_types or []),
            },
            "applied": {
                "seed_count": len(seed_vids),
                "seed_cap": graph_budget.discovery_seed_cap,
                "hop": 1,
                "hop_cap": graph_budget.discovery_hop_max,
                "max_nodes": max_nodes,
                "max_nodes_cap": graph_budget.discovery_max_nodes_cap,
                "max_edges": max_edges,
                "max_edges_cap": graph_budget.discovery_max_edges_cap,
                "top_k_per_type": top_k_per_type,
                "top_k_per_type_cap": graph_budget.discovery_top_k_per_type_cap,
                "candidate_cap": candidate_cap,
                "candidate_cap_limit": graph_budget.discovery_candidate_cap,
                "allowed_entity_type_count": len(allowed_entity_types),
                "allowed_relation_type_count": len(allowed_relation_types),
                "query_edge_scan_limit": query_scan_limit,
                "per_seed_neighbor_cap": graph_budget.discovery_per_seed_neighbor_cap,
            },
            "dropped": {
                "entity_filter_terms": int(dropped_entity_filter_terms),
                "relation_filter_terms": int(dropped_relation_filter_terms),
                "rows_by_neighbor_cap": int(dropped_neighbors),
            },
            "scanned_rows": int(scanned_rows),
        }
        truncated = bool(
            truncated
            or dropped_nodes > 0
            or dropped_edges > 0
            or dropped_neighbors > 0
            or dropped_entity_filter_terms > 0
            or dropped_relation_filter_terms > 0
            or requested_top_k_per_type != top_k_per_type
            or requested_max_nodes != max_nodes
            or requested_max_edges != max_edges
        )

        logger.info(
            "graph discovery success seeds=%d candidates=%d nodes=%d edges=%d truncated=%s scanned_rows=%d",
            len(seed_vids),
            kept_candidate_count,
            len(final_nodes),
            len(edges_out),
            truncated,
            scanned_rows,
        )
        return {
            "nodes": final_nodes,
            "edges": final_edges,
            "facets": facets,
            "stats": {
                "seed_count": len(seed_vids),
                "candidate_count": kept_candidate_count,
                "node_count": len(final_nodes),
                "edge_count": len(final_edges),
                "truncated": bool(truncated),
                "dropped_nodes": int(dropped_nodes),
                "dropped_edges": int(dropped_edges),
                "dropped_neighbors": int(dropped_neighbors),
                "recall_candidate_count": int(recall_candidate_count),
                "kept_candidate_count": int(kept_candidate_count),
                "budget_applied": budget_applied,
            },
        }
    except HTTPException:
        logger.warning("graph discovery failed with http error seeds=%s", seed_vids, exc_info=True)
        raise
    except Exception as exc:
        logger.exception("graph discovery unexpected error seeds=%s", seed_vids)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "graph_discovery_internal_error",
                "message": str(exc),
            },
        ) from exc
