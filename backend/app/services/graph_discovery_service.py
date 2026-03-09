import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, execute_ngql
from app.schemas.discovery import GraphDiscoveryRequest
from app.services.common import truncate_by_degree, uniq_edges, vw
from app.services.graph_budget import graph_budget
from app.services.graph_service import _find_shortest_path_candidates_bfs

logger = logging.getLogger(__name__)

_EDGE_ROLE_PRIORITY = {
    "seed_candidate": 0,
    "candidate_candidate": 1,
    "seed_seed": 2,
}

_LAYER_ORDER = {
    "core": 0,
    "shared": 1,
    "local": 2,
    "supplement": 3,
}

_LAYER_BUDGET_WEIGHTS = {
    "core": 20,
    "shared": 30,
    "local": 30,
    "supplement": 10,
}

_TYPE_BUDGET_DEFAULTS = {
    "disease": 20,
    "gene": 20,
    "drug": 15,
    "protein": 10,
    "phenotype": 10,
    "symptom": 8,
    "anatomy": 7,
}

_TYPE_WEIGHT_DEFAULTS = {
    "disease": 1.0,
    "gene": 1.0,
    "drug": 0.95,
    "protein": 0.85,
    "phenotype": 0.8,
    "symptom": 0.7,
    "anatomy": 0.65,
}

_LAYER_SCORE_BONUS = {
    "core": 10000.0,
    "shared": 7000.0,
    "local": 4000.0,
    "supplement": 1000.0,
}

_GENERIC_HUB_LABELS = {
    "disease",
    "human disease",
    "metabolic disease",
}

_GENERIC_HUB_ENTITY_TYPES = {
    "disease",
}

_EDGE_LAYER_BUCKET = {
    "core_backbone": -10,
    "core_path": -9,
    "seed_seed": -8,
    "shared": -7,
    "local": -6,
    "supplement": -5,
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


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    x = int(a)
    y = int(b)
    return (x, y) if x <= y else (y, x)


def _pair_key_text(a: int, b: int) -> str:
    x, y = _pair_key(a, b)
    return f"{x}-{y}"


def _type_budget_key(entity_type_norm: str) -> str:
    key = str(entity_type_norm or "")
    if key in _TYPE_BUDGET_DEFAULTS:
        return key
    return "other"


def _label_norm(node: Dict[str, Any]) -> str:
    return _normalize_key(str(node.get("label") or ""))


def _is_valid_shared_bridge(
    *,
    matched_seed_count: int,
    direct_seed_support_count: int,
    path_pair_count: int,
) -> bool:
    if matched_seed_count < 2:
        return False
    if direct_seed_support_count >= 2:
        return True
    return path_pair_count > 0 and direct_seed_support_count >= 1


def _generic_hub_reason(
    *,
    label_norm: str,
    entity_type_norm: str,
    observed_degree: int,
    matched_seed_count: int,
) -> str:
    if label_norm in _GENERIC_HUB_LABELS:
        return "generic_label"
    if (
        entity_type_norm in _GENERIC_HUB_ENTITY_TYPES
        and "disease" in label_norm
        and observed_degree >= 6
        and matched_seed_count <= 1
    ):
        return "generic_high_degree_type"
    return ""


def _candidate_layer_counts(nodes: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts = {layer: 0 for layer in _LAYER_ORDER}
    for node in nodes:
        if str(node.get("role") or "") != "candidate":
            continue
        layer = str(node.get("layer") or "")
        if layer in counts:
            counts[layer] += 1
    return counts


def _safe_ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _scale_layer_budgets(candidate_budget: int) -> Dict[str, int]:
    if candidate_budget <= 0:
        return {layer: 0 for layer in _LAYER_BUDGET_WEIGHTS}

    total_weight = sum(_LAYER_BUDGET_WEIGHTS.values())
    budgets = {layer: 0 for layer in _LAYER_BUDGET_WEIGHTS}
    remainder: List[Tuple[int, str]] = []
    assigned = 0
    for layer, weight in _LAYER_BUDGET_WEIGHTS.items():
        raw = (int(candidate_budget) * int(weight)) / float(total_weight)
        count = int(raw)
        budgets[layer] = count
        assigned += count
        remainder.append((int(round((raw - count) * 1000000)), layer))

    remaining = max(0, int(candidate_budget) - assigned)
    for _, layer in sorted(remainder, key=lambda item: (-item[0], _LAYER_ORDER[item[1]])):
        if remaining <= 0:
            break
        budgets[layer] += 1
        remaining -= 1
    return budgets


def _layer_sort_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        int(_LAYER_ORDER.get(str(item.get("layer") or ""), 99)),
        -float(item.get("priority_score") or 0.0),
        -int(item.get("matched_seed_count") or 0),
        int(item.get("min_seed_distance") or 99),
        str(item.get("entity_type_norm") or ""),
        int(item.get("id") or 0),
    )


def _score_candidate_layered(
    *,
    layer: str,
    seed_count: int,
    matched_seed_count: int,
    path_pair_count: int,
    seed_edge_count: int,
    relation_diversity: int,
    min_seed_distance: int,
    observed_degree: int,
    entity_type_norm: str,
    generic_hub_penalty_boost: float = 0.0,
) -> Tuple[float, Dict[str, Any]]:
    coverage_score = round(_safe_ratio(matched_seed_count, max(1, seed_count)), 4)
    path_score = round(_safe_ratio(path_pair_count, max(1, seed_count - 1)), 4) if seed_count > 1 else 0.0
    bridge_score = round(_safe_ratio(max(0, matched_seed_count - 1), max(1, seed_count - 1)), 4)
    relation_weight = round(min(1.5, (seed_edge_count * 0.25) + (relation_diversity * 0.15)), 4)
    type_weight = round(float(_TYPE_WEIGHT_DEFAULTS.get(entity_type_norm, 0.55)), 4)
    distance_penalty = round(max(0.0, float(min_seed_distance) - 1.0), 4)
    hub_penalty = round(min(2.0, _safe_ratio(max(0, observed_degree - 2), 8)), 4)
    generic_hub_penalty = round(max(0.0, float(generic_hub_penalty_boost)), 4)

    priority_score = round(
        float(_LAYER_SCORE_BONUS.get(layer, 0.0))
        + (coverage_score * 1000.0)
        + (path_score * 800.0)
        + (bridge_score * 700.0)
        + (relation_weight * 220.0)
        + (type_weight * 120.0)
        - (distance_penalty * 180.0)
        - ((hub_penalty + generic_hub_penalty) * 240.0),
        4,
    )
    return priority_score, {
        "coverage_score": coverage_score,
        "path_score": path_score,
        "bridge_score": bridge_score,
        "relation_weight": relation_weight,
        "type_weight": type_weight,
        "distance_penalty": distance_penalty,
        "hub_penalty": hub_penalty,
        "generic_hub_penalty": generic_hub_penalty,
        "total_score": priority_score,
    }


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
        int(edge.get("_priority_bucket") if edge.get("_priority_bucket") is not None else 999),
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


def _build_facets(
    nodes: Iterable[Dict[str, Any]],
    edges: Iterable[Dict[str, Any]],
    *,
    query_summary: Optional[Dict[str, Any]] = None,
    seed_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    node_list = list(nodes)
    edge_list = list(edges)
    entity_counts: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "count": 0,
            "seed_count": 0,
            "candidate_count": 0,
            "core_count": 0,
            "shared_count": 0,
            "local_count": 0,
            "supplement_count": 0,
        }
    )
    relation_counts: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {
            "count": 0,
            "seed_candidate_count": 0,
            "candidate_candidate_count": 0,
            "seed_seed_count": 0,
            "core_count": 0,
            "shared_count": 0,
            "local_count": 0,
            "supplement_count": 0,
        }
    )
    layer_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"node_count": 0, "edge_count": 0})

    for node in node_list:
        entity_type = str(node.get("entity_type") or "")
        bucket = entity_counts[entity_type]
        bucket["count"] += 1
        if str(node.get("role") or "") == "seed":
            bucket["seed_count"] += 1
        else:
            bucket["candidate_count"] += 1
        layer = str(node.get("layer") or "")
        if layer in _LAYER_ORDER:
            bucket[f"{layer}_count"] += 1
            layer_counts[layer]["node_count"] += 1

    for edge in edge_list:
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
        layer = str(edge.get("layer") or "")
        if layer in _LAYER_ORDER:
            bucket[f"{layer}_count"] += 1
            layer_counts[layer]["edge_count"] += 1

    entity_items = [
        {
            "entity_type": entity_type,
            "count": counts["count"],
            "seed_count": counts["seed_count"],
            "candidate_count": counts["candidate_count"],
            "core_count": counts["core_count"],
            "shared_count": counts["shared_count"],
            "local_count": counts["local_count"],
            "supplement_count": counts["supplement_count"],
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
            "core_count": counts["core_count"],
            "shared_count": counts["shared_count"],
            "local_count": counts["local_count"],
            "supplement_count": counts["supplement_count"],
        }
        for relation, counts in relation_counts.items()
    ]
    relation_items.sort(key=lambda item: (-int(item["count"]), str(item["relation_type"])))

    layer_items = [
        {
            "layer": layer,
            "node_count": counts["node_count"],
            "edge_count": counts["edge_count"],
        }
        for layer, counts in layer_counts.items()
    ]
    layer_items.sort(key=lambda item: int(_LAYER_ORDER.get(str(item["layer"]), 99)))

    return {
        "entity_types": entity_items,
        "relation_types": relation_items,
        "query_summary": {
            "search_type": str((query_summary or {}).get("search_type") or "graph_discovery"),
            "selected_seed_count": int((query_summary or {}).get("selected_seed_count") or 0),
            "selected_seeds": list((query_summary or {}).get("selected_seeds") or []),
            "total_entities": int((query_summary or {}).get("total_entities") or len(node_list)),
            "total_relationships": int((query_summary or {}).get("total_relationships") or len(edge_list)),
        },
        "layers": layer_items,
        "seeds": list(seed_items or []),
    }


def _discovery_v1(req: GraphDiscoveryRequest) -> Dict[str, Any]:
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


def _select_with_type_budget(
    candidates: Iterable[Dict[str, Any]],
    *,
    max_count: int,
    selected_ids: Set[int],
    type_budget_remaining: Dict[str, int],
    type_budget_blocked_ids: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    if max_count <= 0:
        return []

    kept: List[Dict[str, Any]] = []
    for item in sorted(candidates, key=_layer_sort_key):
        vid = int(item["id"])
        if vid in selected_ids:
            continue
        budget_key = _type_budget_key(str(item.get("entity_type_norm") or ""))
        remaining = int(type_budget_remaining.get(budget_key, 0))
        if remaining <= 0:
            if type_budget_blocked_ids is not None:
                type_budget_blocked_ids.add(vid)
            continue
        kept.append(item)
        selected_ids.add(vid)
        if type_budget_blocked_ids is not None:
            type_budget_blocked_ids.discard(vid)
        type_budget_remaining[budget_key] = remaining - 1
        if len(kept) >= int(max_count):
            break
    return kept


def _limit_pool_per_type(candidates: Iterable[Dict[str, Any]], top_k_per_type: int) -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in candidates:
        grouped[str(item.get("entity_type_norm") or "")].append(item)

    kept: List[Dict[str, Any]] = []
    for entity_type in sorted(grouped.keys()):
        bucket = sorted(grouped[entity_type], key=_layer_sort_key)
        kept.extend(bucket[: int(top_k_per_type)])
    return sorted(kept, key=_layer_sort_key)


def _clone_candidate_for_layer(item: Dict[str, Any], layer: str, seed_count: int) -> Dict[str, Any]:
    clone = dict(item)
    priority_score, breakdown = _score_candidate_layered(
        layer=layer,
        seed_count=seed_count,
        matched_seed_count=int(clone.get("matched_seed_count") or 0),
        path_pair_count=len(clone.get("matched_seed_pairs") or []),
        seed_edge_count=len(clone.get("support_edges") or []),
        relation_diversity=int(clone.get("relation_diversity") or 0),
        min_seed_distance=int(clone.get("min_seed_distance") or 1),
        observed_degree=int(clone.get("observed_degree") or 0),
        entity_type_norm=str(clone.get("entity_type_norm") or ""),
    )
    clone["layer"] = layer
    clone["priority_score"] = priority_score
    clone["score_breakdown"] = breakdown
    return clone


def _edge_role_for_nodes(source: int, target: int, seed_set: Set[int]) -> str:
    src = int(source)
    dst = int(target)
    if src in seed_set and dst in seed_set:
        return "seed_seed"
    if src in seed_set or dst in seed_set:
        return "seed_candidate"
    return "candidate_candidate"


def _layer_bucket_for_edge(layer: str, role: str, is_backbone: bool) -> int:
    if role == "seed_seed":
        return int(_EDGE_LAYER_BUCKET["seed_seed"])
    if is_backbone and layer == "core":
        return int(_EDGE_LAYER_BUCKET["core_backbone"])
    if is_backbone:
        return int(_EDGE_LAYER_BUCKET.get(layer, _EDGE_LAYER_BUCKET["supplement"]))
    return int(_EDGE_LAYER_BUCKET.get(layer, 0))


def _candidate_edge_layer(src_layer: str, dst_layer: str) -> str:
    if src_layer == "core" and dst_layer == "core":
        return "core"
    if src_layer in {"core", "shared"} and dst_layer in {"core", "shared"}:
        return "shared"
    if src_layer == "local" and dst_layer == "local":
        return "local"
    if "supplement" in {src_layer, dst_layer}:
        return "supplement"
    if "local" in {src_layer, dst_layer}:
        return "local"
    return src_layer or dst_layer or "supplement"


def _discovery_layered(req: GraphDiscoveryRequest) -> Dict[str, Any]:
    requested_seed_count = len(req.seed_vids or [])
    requested_max_nodes = int(req.max_nodes or 90)
    requested_max_edges = int(req.max_edges or 140)
    requested_top_k_per_type = int(req.top_k_per_type or 0)
    requested_hop = int(req.hop or 3)

    seed_vids: List[int] = []
    seen_seed: Set[int] = set()
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
    if requested_max_nodes < len(seed_vids):
        raise _budget_error("max_nodes is smaller than seed_vids count", code="graph_discovery_max_nodes_invalid")

    hop = max(1, min(requested_hop, graph_budget.discovery_hop_max))
    max_nodes = max(len(seed_vids), min(requested_max_nodes, graph_budget.discovery_max_nodes_cap))
    max_edges = max(1, min(requested_max_edges, graph_budget.discovery_max_edges_cap))
    top_k_per_type = max(1, min(requested_top_k_per_type or 20, graph_budget.discovery_top_k_per_type_cap))

    allowed_entity_types, dropped_entity_filter_terms = _normalize_filter(
        req.allowed_entity_types or [],
        max_count=graph_budget.relation_filter_max,
    )
    allowed_relation_types, dropped_relation_filter_terms = _normalize_filter(
        req.allowed_relation_types or [],
        max_count=graph_budget.relation_filter_max,
    )
    raw_relation_filter = set(str(item or "").strip() for item in (req.allowed_relation_types or []) if str(item or "").strip())

    query_scan_limit = max(
        max_edges,
        min(graph_budget.discovery_query_edge_scan_cap, max_edges * 4),
    )
    candidate_budget = min(
        max(0, max_nodes - len(seed_vids)),
        graph_budget.discovery_candidate_cap,
    )
    layer_budgets = _scale_layer_budgets(candidate_budget)
    seed_set = set(seed_vids)

    logger.info(
        "graph discovery layered start seeds=%d requested_max_nodes=%d requested_max_edges=%d hop=%d",
        len(seed_vids),
        requested_max_nodes,
        requested_max_edges,
        requested_hop,
    )

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
        direct_pair_edges: Set[Tuple[int, int]] = set()
        support_edge_keys: Set[Tuple[int, int, int]] = set()

        for edge in seed_edges_raw:
            src = int(edge["source"])
            dst = int(edge["target"])
            if src in seed_set and dst in seed_set:
                direct_pair_edges.add(_pair_key(src, dst))
                seed_seed_edges.append(
                    {
                        **edge,
                        "role": "seed_seed",
                        "layer": "core",
                        "seed_support_vids": [src, dst],
                        "path_pair": _pair_key_text(src, dst),
                        "is_backbone": True,
                        "_priority_bucket": _layer_bucket_for_edge("core", "seed_seed", True),
                        "_priority_score": 99999.0,
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
                    "direct_seed_vids": set(),
                    "support_edges": [],
                    "support_edge_keys": set(),
                    "relation_set": set(),
                    "matched_seed_pairs": set(),
                    "min_seed_distance": 1,
                    "observed_degree": 0,
                    "local_anchor_scores": defaultdict(int),
                },
            )
            support["seed_support_vids"].add(anchor_seed)
            support["direct_seed_vids"].add(anchor_seed)
            support["local_anchor_scores"][anchor_seed] += 1
            support["observed_degree"] += 1
            relation_norm = _normalize_key(str(edge.get("relation") or ""))
            if relation_norm:
                support["relation_set"].add(relation_norm)
            edge_key = (int(edge["source"]), int(edge["target"]), int(edge.get("rank") or 0))
            if edge_key not in support["support_edge_keys"]:
                support["support_edge_keys"].add(edge_key)
                support["support_edges"].append({**edge})

        core_path_edges: List[Dict[str, Any]] = []
        for idx, src_seed in enumerate(seed_vids):
            for dst_seed in seed_vids[idx + 1 :]:
                pair_key = _pair_key(src_seed, dst_seed)
                pair_text = _pair_key_text(src_seed, dst_seed)
                if pair_key in direct_pair_edges:
                    continue
                raw_paths, path_meta = _find_shortest_path_candidates_bfs(
                    src=src_seed,
                    dst=dst_seed,
                    max_hop=hop,
                    rel_filter=raw_relation_filter,
                    query_scan_limit=query_scan_limit,
                    per_root_neighbor_cap=graph_budget.discovery_per_seed_neighbor_cap,
                    ignore_direction=True,
                    candidate_limit=1,
                )
                scanned_rows += int(path_meta["scanned_rows"])
                dropped_neighbors += int(path_meta["dropped_by_neighbor_cap"])
                if not raw_paths:
                    continue

                chosen_path = raw_paths[0]
                path_nodes = [int(x) for x in (chosen_path.get("nodes") or [])]
                path_edges = list(chosen_path.get("edges") or [])
                path_len = len(path_edges)
                for pos, node_id in enumerate(path_nodes):
                    if node_id in seed_set:
                        continue
                    support = candidate_support.setdefault(
                        node_id,
                        {
                            "id": node_id,
                            "seed_support_vids": set(),
                            "direct_seed_vids": set(),
                            "support_edges": [],
                            "support_edge_keys": set(),
                            "relation_set": set(),
                            "matched_seed_pairs": set(),
                            "min_seed_distance": 99,
                            "observed_degree": 0,
                            "local_anchor_scores": defaultdict(int),
                        },
                    )
                    support["seed_support_vids"].update([src_seed, dst_seed])
                    support["matched_seed_pairs"].add(pair_text)
                    support["min_seed_distance"] = min(
                        int(support["min_seed_distance"] or 99),
                        min(pos, len(path_nodes) - pos - 1),
                    )
                for edge in path_edges:
                    src = int(edge["source"])
                    dst = int(edge["target"])
                    role = _edge_role_for_nodes(src, dst, seed_set)
                    edge_key = (src, dst, int(edge.get("rank") or 0))
                    if edge_key in support_edge_keys:
                        continue
                    support_edge_keys.add(edge_key)
                    core_path_edges.append(
                        {
                            "source": src,
                            "target": dst,
                            "rank": str(edge.get("rank") or "0"),
                            "edge_type": str(edge.get("edge_type") or config.EDGE_TYPE),
                            "relation": str(edge.get("relation") or ""),
                            "source_db": str(edge.get("source_db") or ""),
                            "role": role,
                            "layer": "core",
                            "seed_support_vids": [src_seed, dst_seed],
                            "path_pair": pair_text,
                            "is_backbone": True,
                            "_priority_bucket": _layer_bucket_for_edge("core", role, True),
                            "_priority_score": 90000.0 - float(path_len * 100),
                        }
                    )
                    if src not in seed_set:
                        candidate_support[src]["observed_degree"] += 1
                    if dst not in seed_set:
                        candidate_support[dst]["observed_degree"] += 1
                    relation_norm = _normalize_key(str(edge.get("relation") or ""))
                    if relation_norm:
                        if src not in seed_set:
                            candidate_support[src]["relation_set"].add(relation_norm)
                        if dst not in seed_set:
                            candidate_support[dst]["relation_set"].add(relation_norm)

        recall_candidate_count = len(candidate_support)
        candidate_node_map = _fetch_entity_nodes(candidate_support.keys())

        scored_candidates: List[Dict[str, Any]] = []
        dropped_by_entity_filter = 0
        for vid, support in candidate_support.items():
            node = candidate_node_map.get(int(vid))
            if not node:
                continue
            entity_type_norm = _normalize_key(str(node.get("entity_type") or ""))
            if allowed_entity_types and entity_type_norm not in allowed_entity_types:
                dropped_nodes += 1
                dropped_by_entity_filter += 1
                continue

            matched_seed_count = len(support["seed_support_vids"])
            matched_seed_pairs = sorted(str(x) for x in support["matched_seed_pairs"])
            path_pair_count = len(matched_seed_pairs)
            direct_seed_support_count = len(support["direct_seed_vids"])
            observed_degree = max(
                int(support.get("observed_degree") or 0),
                len(support["support_edges"]),
            )
            label_norm = _label_norm(node)
            is_valid_shared_bridge = _is_valid_shared_bridge(
                matched_seed_count=matched_seed_count,
                direct_seed_support_count=direct_seed_support_count,
                path_pair_count=path_pair_count,
            )
            generic_hub_reason = _generic_hub_reason(
                label_norm=label_norm,
                entity_type_norm=entity_type_norm,
                observed_degree=observed_degree,
                matched_seed_count=matched_seed_count,
            )
            generic_hub_suppressed = bool(generic_hub_reason) and path_pair_count <= 0 and not is_valid_shared_bridge

            layer = "local"
            if path_pair_count > 0:
                layer = "core"
            elif is_valid_shared_bridge:
                layer = "shared"
            elif generic_hub_suppressed:
                layer = "supplement"

            anchor_scores = support["local_anchor_scores"]
            local_anchor_seed = None
            if anchor_scores:
                local_anchor_seed = sorted(
                    anchor_scores.items(),
                    key=lambda item: (-int(item[1]), int(item[0])),
                )[0][0]
            elif support["seed_support_vids"]:
                local_anchor_seed = sorted(int(x) for x in support["seed_support_vids"])[0]

            priority_score, score_breakdown = _score_candidate_layered(
                layer=layer,
                seed_count=len(seed_vids),
                matched_seed_count=matched_seed_count,
                path_pair_count=path_pair_count,
                seed_edge_count=len(support["support_edges"]),
                relation_diversity=len(support["relation_set"]),
                min_seed_distance=max(1, int(support.get("min_seed_distance") or 1)),
                observed_degree=observed_degree,
                entity_type_norm=entity_type_norm,
                generic_hub_penalty_boost=8.0 if generic_hub_suppressed else 0.0,
            )
            score_breakdown["direct_seed_support_count"] = direct_seed_support_count
            score_breakdown["path_pair_count"] = path_pair_count
            score_breakdown["is_valid_shared_bridge"] = is_valid_shared_bridge
            score_breakdown["is_generic_hub"] = bool(generic_hub_reason)
            score_breakdown["generic_hub_reason"] = generic_hub_reason
            scored_candidates.append(
                {
                    **node,
                    "entity_type_norm": entity_type_norm,
                    "layer": layer,
                    "priority_score": priority_score,
                    "seed_support_vids": sorted(int(x) for x in support["seed_support_vids"]),
                    "matched_seed_count": matched_seed_count,
                    "matched_seed_pairs": matched_seed_pairs,
                    "path_pair_count": path_pair_count,
                    "direct_seed_support_count": direct_seed_support_count,
                    "seed_edge_count": len(support["support_edges"]),
                    "relation_diversity": len(support["relation_set"]),
                    "min_seed_distance": max(1, int(support.get("min_seed_distance") or 1)),
                    "observed_degree": observed_degree,
                    "bridge_seed_count": matched_seed_count,
                    "local_anchor_seed": local_anchor_seed,
                    "score_breakdown": score_breakdown,
                    "support_edges": list(support["support_edges"]),
                    "is_valid_shared_bridge": is_valid_shared_bridge,
                    "is_generic_hub": bool(generic_hub_reason),
                    "generic_hub_reason": generic_hub_reason,
                    "generic_hub_suppressed": generic_hub_suppressed,
                }
            )

        scored_candidates.sort(key=_layer_sort_key)
        core_pool = [item for item in scored_candidates if str(item.get("layer") or "") == "core"]
        shared_pool = _limit_pool_per_type(
            [item for item in scored_candidates if str(item.get("layer") or "") == "shared"],
            top_k_per_type=top_k_per_type,
        )
        local_pool = _limit_pool_per_type(
            [item for item in scored_candidates if str(item.get("layer") or "") == "local"],
            top_k_per_type=top_k_per_type,
        )
        selected_ids: Set[int] = set()
        selected_candidates: List[Dict[str, Any]] = []
        type_budget_remaining = dict(_TYPE_BUDGET_DEFAULTS)
        type_budget_remaining["other"] = max(6, min(12, max(1, candidate_budget // 6)))
        type_budget_blocked_ids: Set[int] = set()

        carry = 0
        remaining_capacity = candidate_budget

        desired_core = min(remaining_capacity, max(layer_budgets["core"] + carry, len(core_pool)))
        core_selected = sorted(core_pool, key=_layer_sort_key)[:desired_core]
        for item in core_selected:
            selected_ids.add(int(item["id"]))
        selected_candidates.extend(core_selected)
        remaining_capacity -= len(core_selected)
        carry = max(0, desired_core - len(core_selected))

        desired_shared = min(remaining_capacity, layer_budgets["shared"] + carry)
        shared_selected = _select_with_type_budget(
            shared_pool,
            max_count=desired_shared,
            selected_ids=selected_ids,
            type_budget_remaining=type_budget_remaining,
            type_budget_blocked_ids=type_budget_blocked_ids,
        )
        selected_candidates.extend(shared_selected)
        remaining_capacity -= len(shared_selected)
        carry = max(0, desired_shared - len(shared_selected))

        desired_local = min(remaining_capacity, layer_budgets["local"] + carry)
        local_selected: List[Dict[str, Any]] = []
        seed_local_floor = 0
        if desired_local > 0 and seed_vids:
            seed_local_floor = max(1, min(4, desired_local // len(seed_vids) or 1))
            local_by_seed: Dict[int, List[Dict[str, Any]]] = {int(vid): [] for vid in seed_vids}
            for item in local_pool:
                anchor_seed = int(item.get("local_anchor_seed") or 0)
                if anchor_seed in local_by_seed:
                    local_by_seed[anchor_seed].append(item)
            local_offsets = {int(vid): 0 for vid in seed_vids}
            for _ in range(seed_local_floor):
                for seed_vid in seed_vids:
                    bucket = local_by_seed.get(int(seed_vid)) or []
                    while local_offsets[int(seed_vid)] < len(bucket):
                        candidate = bucket[local_offsets[int(seed_vid)]]
                        local_offsets[int(seed_vid)] += 1
                        if int(candidate["id"]) in selected_ids:
                            continue
                        budget_key = _type_budget_key(str(candidate.get("entity_type_norm") or ""))
                        remaining = int(type_budget_remaining.get(budget_key, 0))
                        if remaining <= 0:
                            type_budget_blocked_ids.add(int(candidate["id"]))
                            continue
                        local_selected.append(candidate)
                        selected_ids.add(int(candidate["id"]))
                        type_budget_blocked_ids.discard(int(candidate["id"]))
                        type_budget_remaining[budget_key] = remaining - 1
                        break
                    if len(local_selected) >= desired_local:
                        break
                if len(local_selected) >= desired_local:
                    break
        if len(local_selected) < desired_local:
            local_selected.extend(
                _select_with_type_budget(
                    [item for item in local_pool if int(item["id"]) not in selected_ids],
                    max_count=desired_local - len(local_selected),
                    selected_ids=selected_ids,
                    type_budget_remaining=type_budget_remaining,
                    type_budget_blocked_ids=type_budget_blocked_ids,
                )
            )
        selected_candidates.extend(local_selected)
        remaining_capacity -= len(local_selected)
        carry = max(0, desired_local - len(local_selected))

        supplement_source = [
            _clone_candidate_for_layer(item, "supplement", len(seed_vids))
            for item in local_pool
            if int(item["id"]) not in selected_ids
        ]
        supplement_pool = _limit_pool_per_type(supplement_source, top_k_per_type=max(1, min(top_k_per_type, 6)))
        desired_supplement = min(remaining_capacity, layer_budgets["supplement"] + carry)
        supplement_selected = _select_with_type_budget(
            supplement_pool,
            max_count=desired_supplement,
            selected_ids=selected_ids,
            type_budget_remaining=type_budget_remaining,
            type_budget_blocked_ids=type_budget_blocked_ids,
        )
        selected_candidates.extend(supplement_selected)

        selected_candidate_ids = {int(item["id"]) for item in selected_candidates}
        dropped_generic_hub_ids = {
            int(item["id"])
            for item in scored_candidates
            if bool(item.get("generic_hub_suppressed")) and int(item["id"]) not in selected_candidate_ids
        }
        dropped_by_type_budget_ids = {
            int(vid)
            for vid in type_budget_blocked_ids
            if int(vid) not in selected_candidate_ids and int(vid) not in dropped_generic_hub_ids
        }
        dropped_by_budget_ids = {
            int(item["id"])
            for item in scored_candidates
            if int(item["id"]) not in selected_candidate_ids
            and int(item["id"]) not in dropped_generic_hub_ids
            and int(item["id"]) not in dropped_by_type_budget_ids
        }
        eligible_candidate_count = len(scored_candidates)
        if len(selected_candidates) < eligible_candidate_count:
            dropped_nodes += eligible_candidate_count - len(selected_candidates)
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
                    "layer": "core",
                    "priority_score": 100000.0,
                    "min_seed_distance": 0,
                    "bridge_seed_count": 0,
                    "local_anchor_seed": None,
                    "matched_seed_pairs": [],
                    "seed_support_count": 0,
                    "seed_support_vids": [],
                    "score_breakdown": {},
                }
            )

        selected_candidates.sort(key=_layer_sort_key)
        for item in selected_candidates:
            nodes_out.append(
                {
                    "id": int(item["id"]),
                    "label": str(item.get("label") or ""),
                    "entity_type": str(item.get("entity_type") or ""),
                    "raw_id": str(item.get("raw_id") or ""),
                    "source": str(item.get("source") or ""),
                    "snippet": str(item.get("snippet") or ""),
                    "score": float(item["priority_score"]),
                    "role": "candidate",
                    "layer": str(item.get("layer") or ""),
                    "priority_score": float(item["priority_score"]),
                    "min_seed_distance": int(item.get("min_seed_distance") or 0),
                    "bridge_seed_count": int(item.get("bridge_seed_count") or 0),
                    "local_anchor_seed": item.get("local_anchor_seed"),
                    "matched_seed_pairs": list(item.get("matched_seed_pairs") or []),
                    "seed_support_count": int(item.get("matched_seed_count") or 0),
                    "seed_support_vids": list(item.get("seed_support_vids") or []),
                    "score_breakdown": dict(item.get("score_breakdown") or {}),
                }
            )

        node_layer_map = {int(node["id"]): str(node.get("layer") or "") for node in nodes_out}
        selected_candidate_map = {int(item["id"]): item for item in selected_candidates}
        candidate_score_map = {int(item["id"]): float(item["priority_score"]) for item in selected_candidates}

        edges_out: List[Dict[str, Any]] = []
        edges_out.extend(seed_seed_edges)
        edges_out.extend(core_path_edges)

        for item in selected_candidates:
            item_layer = str(item.get("layer") or "")
            item_score = float(item.get("priority_score") or 0.0)
            for edge in item.get("support_edges") or []:
                src = int(edge["source"])
                dst = int(edge["target"])
                if src not in seed_set and dst not in seed_set:
                    continue
                role = _edge_role_for_nodes(src, dst, seed_set)
                edges_out.append(
                    {
                        "source": src,
                        "target": dst,
                        "rank": str(edge.get("rank") or "0"),
                        "edge_type": str(edge.get("edge_type") or config.EDGE_TYPE),
                        "relation": str(edge.get("relation") or ""),
                        "source_db": str(edge.get("source_db") or ""),
                        "role": role,
                        "layer": item_layer,
                        "seed_support_vids": list(item.get("seed_support_vids") or []),
                        "path_pair": "",
                        "is_backbone": item_layer in {"core", "shared"},
                        "_priority_bucket": _layer_bucket_for_edge(item_layer, role, item_layer in {"core", "shared"}),
                        "_priority_score": item_score,
                    }
                )

        kept_candidate_vids = {int(item["id"]) for item in selected_candidates}
        if req.include_candidate_candidate_edges and kept_candidate_vids:
            candidate_edges_raw, candidate_meta = _go_edges_from(
                kept_candidate_vids,
                rel_filter=allowed_relation_types,
                query_scan_limit=query_scan_limit,
                per_root_neighbor_cap=graph_budget.discovery_per_seed_neighbor_cap,
            )
            scanned_rows += int(candidate_meta["scanned_rows"])
            dropped_neighbors += int(candidate_meta["dropped_by_neighbor_cap"])
            for edge in candidate_edges_raw:
                src = int(edge["source"])
                dst = int(edge["target"])
                if src not in kept_candidate_vids or dst not in kept_candidate_vids:
                    continue
                src_item = selected_candidate_map.get(src) or {}
                dst_item = selected_candidate_map.get(dst) or {}
                src_layer = str(node_layer_map.get(src) or "")
                dst_layer = str(node_layer_map.get(dst) or "")
                layer = _candidate_edge_layer(src_layer, dst_layer)
                shared_seed_support = set(int(x) for x in (src_item.get("seed_support_vids") or [])) & set(
                    int(x) for x in (dst_item.get("seed_support_vids") or [])
                )
                same_local_anchor = (
                    src_layer == "local"
                    and dst_layer == "local"
                    and int(src_item.get("local_anchor_seed") or 0) > 0
                    and int(src_item.get("local_anchor_seed") or 0) == int(dst_item.get("local_anchor_seed") or 0)
                )
                if layer in {"core", "shared"}:
                    pass
                elif layer == "local" and (same_local_anchor or shared_seed_support):
                    pass
                elif layer == "supplement" and shared_seed_support:
                    pass
                else:
                    continue
                role = "candidate_candidate"
                is_backbone = layer in {"core", "shared"}
                edges_out.append(
                    {
                        "source": src,
                        "target": dst,
                        "rank": str(edge.get("rank") or "0"),
                        "edge_type": str(edge.get("edge_type") or config.EDGE_TYPE),
                        "relation": str(edge.get("relation") or ""),
                        "source_db": str(edge.get("source_db") or ""),
                        "role": role,
                        "layer": layer,
                        "seed_support_vids": sorted(shared_seed_support),
                        "path_pair": "",
                        "is_backbone": is_backbone,
                        "_priority_bucket": _layer_bucket_for_edge(layer, role, is_backbone),
                        "_priority_score": max(candidate_score_map.get(src, 0.0), candidate_score_map.get(dst, 0.0)),
                    }
                )

        edges_out = uniq_edges(edges_out)
        edges_out, trimmed_edges = _trim_edges_with_priority(edges_out, max_edges=max_edges)
        dropped_edges += int(trimmed_edges)
        if trimmed_edges > 0:
            truncated = True

        node_map_out = {int(node["id"]): dict(node) for node in nodes_out}
        used_node_ids = set(seed_vids)
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
            dropped_by_budget_ids.update(
                int(node["id"])
                for node in nodes_out
                if str(node.get("role") or "") == "candidate" and int(node["id"]) not in used_node_ids
            )

        final_nodes = [node_map_out[vid] for vid in seed_vids if vid in node_map_out]
        final_nodes.extend(
            [
                node_map_out[vid]
                for vid in sorted(
                    [
                        vid
                        for vid in used_node_ids
                        if vid in node_map_out and str(node_map_out[vid].get("role") or "") == "candidate"
                    ],
                    key=lambda vid: _layer_sort_key(node_map_out[vid]),
                )
            ]
        )

        final_edges = [
            {
                "source": int(edge["source"]),
                "target": int(edge["target"]),
                "rank": str(edge.get("rank") or "0"),
                "edge_type": str(edge.get("edge_type") or config.EDGE_TYPE),
                "relation": str(edge.get("relation") or ""),
                "source_db": str(edge.get("source_db") or ""),
                "role": str(edge.get("role") or "seed_candidate"),
                "layer": str(edge.get("layer") or ""),
                "priority_score": float(edge.get("_priority_score") or 0.0),
                "seed_support_vids": list(edge.get("seed_support_vids") or []),
                "path_pair": str(edge.get("path_pair") or ""),
                "is_backbone": bool(edge.get("is_backbone")),
            }
            for edge in edges_out
        ]

        final_layer_counts = _candidate_layer_counts(final_nodes)

        seed_items = []
        for vid in seed_vids:
            seed_node = seed_node_map.get(int(vid)) or {}
            seed_items.append(
                {
                    "seed_vid": int(vid),
                    "label": str(seed_node.get("label") or ""),
                    "entity_type": str(seed_node.get("entity_type") or ""),
                    "local_count": sum(
                        1
                        for node in final_nodes
                        if str(node.get("layer") or "") == "local" and int(node.get("local_anchor_seed") or 0) == int(vid)
                    ),
                    "shared_touch_count": sum(
                        1
                        for node in final_nodes
                        if str(node.get("layer") or "") == "shared" and int(vid) in [int(x) for x in (node.get("seed_support_vids") or [])]
                    ),
                    "core_path_count": sum(
                        1
                        for node in final_nodes
                        if str(node.get("layer") or "") == "core" and int(vid) in [int(x) for x in (node.get("seed_support_vids") or [])]
                    ),
                }
            )

        facets = _build_facets(
            final_nodes,
            final_edges,
            query_summary={
                "search_type": "layered_multiseed",
                "selected_seed_count": len(seed_vids),
                "selected_seeds": [
                    {
                        "id": int(vid),
                        "label": str((seed_node_map.get(int(vid)) or {}).get("label") or ""),
                        "entity_type": str((seed_node_map.get(int(vid)) or {}).get("entity_type") or ""),
                    }
                    for vid in seed_vids
                ],
                "total_entities": len(final_nodes),
                "total_relationships": len(final_edges),
            },
            seed_items=seed_items,
        )

        kept_candidate_count = sum(1 for node in final_nodes if str(node.get("role") or "") == "candidate")
        dropped_by_type_budget = len(dropped_by_type_budget_ids)
        dropped_generic_hubs = len(dropped_generic_hub_ids)
        dropped_by_budget = len(dropped_by_budget_ids)
        budget_applied = {
            "api": "graph_discovery",
            "ranking_mode": "layered_multiseed",
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
                "hop": hop,
                "hop_cap": graph_budget.discovery_hop_max,
                "max_nodes": max_nodes,
                "max_nodes_cap": graph_budget.discovery_max_nodes_cap,
                "max_edges": max_edges,
                "max_edges_cap": graph_budget.discovery_max_edges_cap,
                "top_k_per_type": top_k_per_type,
                "top_k_per_type_cap": graph_budget.discovery_top_k_per_type_cap,
                "candidate_cap": candidate_budget,
                "candidate_cap_limit": graph_budget.discovery_candidate_cap,
                "layer_budgets": layer_budgets,
                "seed_local_floor": seed_local_floor,
                "type_budgets": dict(_TYPE_BUDGET_DEFAULTS),
                "allowed_entity_type_count": len(allowed_entity_types),
                "allowed_relation_type_count": len(allowed_relation_types),
                "query_edge_scan_limit": query_scan_limit,
                "per_seed_neighbor_cap": graph_budget.discovery_per_seed_neighbor_cap,
            },
            "dropped": {
                "entity_filter_terms": int(dropped_entity_filter_terms),
                "relation_filter_terms": int(dropped_relation_filter_terms),
                "entity_filtered_nodes": int(dropped_by_entity_filter),
                "rows_by_neighbor_cap": int(dropped_neighbors),
                "by_budget": int(dropped_by_budget),
                "by_type_budget": int(dropped_by_type_budget),
                "generic_hubs": int(dropped_generic_hubs),
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
            or requested_hop != hop
            or requested_max_nodes != max_nodes
            or requested_max_edges != max_edges
        )

        logger.info(
            "graph discovery layered success seeds=%d candidates=%d nodes=%d edges=%d truncated=%s scanned_rows=%d",
            len(seed_vids),
            kept_candidate_count,
            len(final_nodes),
            len(final_edges),
            truncated,
            scanned_rows,
        )
        return {
            "nodes": final_nodes,
            "edges": final_edges,
            "facets": facets,
            "stats": {
                "ranking_mode": "layered_multiseed",
                "seed_count": len(seed_vids),
                "seeds_count": len(seed_vids),
                "candidate_count": kept_candidate_count,
                "node_count": len(final_nodes),
                "edge_count": len(final_edges),
                "final_nodes": len(final_nodes),
                "final_edges": len(final_edges),
                "truncated": bool(truncated),
                "core_count": int(final_layer_counts["core"]),
                "shared_count": int(final_layer_counts["shared"]),
                "local_count": int(final_layer_counts["local"]),
                "supplement_count": int(final_layer_counts["supplement"]),
                "dropped_nodes": int(dropped_nodes),
                "dropped_edges": int(dropped_edges),
                "dropped_neighbors": int(dropped_neighbors),
                "dropped_by_budget": int(dropped_by_budget),
                "dropped_by_type_budget": int(dropped_by_type_budget),
                "dropped_generic_hubs": int(dropped_generic_hubs),
                "recall_candidate_count": int(recall_candidate_count),
                "kept_candidate_count": int(kept_candidate_count),
                "budget_applied": budget_applied,
            },
        }
    except HTTPException:
        logger.warning("graph discovery layered failed with http error seeds=%s", seed_vids, exc_info=True)
        raise
    except Exception as exc:
        logger.exception("graph discovery layered unexpected error seeds=%s", seed_vids)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "graph_discovery_internal_error",
                "message": str(exc),
            },
        ) from exc


def discovery(req: GraphDiscoveryRequest) -> Dict[str, Any]:
    if str(req.ranking_mode or "v1") == "layered_multiseed":
        return _discovery_layered(req)
    return _discovery_v1(req)
