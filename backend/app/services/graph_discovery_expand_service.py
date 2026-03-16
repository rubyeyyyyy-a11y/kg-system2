from collections import defaultdict
from typing import Any, Dict, Iterable, List, Set, Tuple

from fastapi import HTTPException

from app.platform.graph.traversal_service import _fetch_entity_nodes, _go_edges_from
from app.schemas.discovery import (
    DiscoveryDroppedReason,
    GraphDiscoveryExpandRequest,
)
from app.services.graph_budget import graph_budget
from app.services.graph_discovery_service import (
    _edge_role_for_nodes,
    _normalize_filter,
    _normalize_key,
)

_EDGE_KEY_SEP = "**"


def _expand_error(message: str, code: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": code,
            "message": message,
        },
    )


def _edge_key(edge: Dict[str, Any]) -> Tuple[int, int, str]:
    return (
        int(edge["source"]),
        int(edge["target"]),
        str(edge.get("rank") or "0"),
    )


def _is_target_incident_edge(edge: Dict[str, Any], target_node_id: int) -> bool:
    return int(edge["source"]) == int(target_node_id) or int(edge["target"]) == int(target_node_id)


def _parse_rendered_edge_ids(items: Iterable[str]) -> Set[Tuple[int, int, str]]:
    out: Set[Tuple[int, int, str]] = set()
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        parts = text.split(_EDGE_KEY_SEP)
        if len(parts) != 3:
            continue
        try:
            out.add((int(parts[0]), int(parts[1]), str(parts[2] or "0")))
        except ValueError:
            continue
    return out


def _candidate_sort_key(item: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        -int(item.get("support_edge_count") or 0),
        -int(item.get("relation_diversity") or 0),
        str(item.get("entity_type_norm") or ""),
        str(item.get("label") or ""),
        int(item.get("id") or 0),
    )


def _node_payload(node: Dict[str, Any], support_edge_count: int) -> Dict[str, Any]:
    return {
        "id": int(node["id"]),
        "label": str(node.get("label") or ""),
        "entity_type": str(node.get("entity_type") or ""),
        "raw_id": str(node.get("raw_id") or ""),
        "source": str(node.get("source") or ""),
        "snippet": str(node.get("snippet") or ""),
        "score": float(support_edge_count),
        "role": "candidate",
        "layer": "supplement",
        "priority_score": float(support_edge_count),
        "min_seed_distance": 1,
        "bridge_seed_count": 0,
        "local_anchor_seed": None,
        "matched_seed_pairs": [],
        "seed_support_count": 0,
        "seed_support_vids": [],
        "score_breakdown": {
            "support_edge_count": int(support_edge_count),
        },
    }


def _edge_payload(edge: Dict[str, Any], seed_set: Set[int]) -> Dict[str, Any]:
    role = _edge_role_for_nodes(int(edge["source"]), int(edge["target"]), seed_set)
    return {
        "source": int(edge["source"]),
        "target": int(edge["target"]),
        "rank": str(edge.get("rank") or "0"),
        "edge_type": str(edge.get("edge_type") or "REL2"),
        "relation": str(edge.get("relation") or ""),
        "source_db": str(edge.get("source_db") or ""),
        "role": role,
        "layer": "supplement",
        "priority_score": 1.0,
        "seed_support_vids": [],
        "path_pair": "",
        "is_backbone": False,
    }


def _dropped_candidate_payload(
    node: Dict[str, Any],
    *,
    reason: DiscoveryDroppedReason,
    source_node_id: int,
    support_edges: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "node_id": int(node["id"]),
        "label": str(node.get("label") or ""),
        "entity_type": str(node.get("entity_type") or ""),
        "raw_id": str(node.get("raw_id") or ""),
        "source": str(node.get("source") or ""),
        "snippet": str(node.get("snippet") or ""),
        "reason": reason,
        "source_node_id": int(source_node_id),
        "support_edges": support_edges,
    }


def expand(req: GraphDiscoveryExpandRequest) -> Dict[str, Any]:
    target_node_id = int(req.target_node_id)
    if int(req.expand_max_hop or 1) != 1:
        raise _expand_error(
            "expand_max_hop only supports 1 in this workbench phase",
            "graph_discovery_expand_hop_invalid",
        )

    rendered_node_ids = {
        int(item)
        for item in list(req.rendered_node_ids or [])[: graph_budget.expand_existing_node_cap]
    }
    rendered_edge_ids = _parse_rendered_edge_ids(req.rendered_edge_ids or [])
    allowed_entity_types, _ = _normalize_filter(
        req.allowed_entity_types or [],
        max_count=graph_budget.relation_filter_max,
    )
    allowed_relation_types, _ = _normalize_filter(
        req.allowed_relation_types or [],
        max_count=graph_budget.relation_filter_max,
    )

    max_new_nodes = max(0, min(int(req.expand_max_new_nodes or 0), graph_budget.expand_max_nodes_cap))
    max_new_edges = max(0, min(int(req.expand_max_new_edges or 0), graph_budget.expand_max_edges_cap))
    top_k_per_type = max(
        1,
        min(int(req.expand_top_k_per_type or 1), graph_budget.discovery_top_k_per_type_cap),
    )
    query_scan_limit = min(
        graph_budget.expand_query_edge_scan_cap,
        max(30, max(max_new_edges, 1) * 6),
    )

    raw_edges, raw_meta = _go_edges_from(
        frontier=[target_node_id],
        rel_filter=set(),
        query_scan_limit=query_scan_limit,
        per_root_neighbor_cap=graph_budget.expand_per_root_neighbor_cap,
        ignore_direction=True,
    )

    all_candidate_ids: Set[int] = set()
    raw_edges_by_node: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    relation_allowed_edges_by_node: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    for edge in raw_edges:
        if not _is_target_incident_edge(edge, target_node_id):
            continue
        src = int(edge["source"])
        dst = int(edge["target"])
        candidate_id = dst if src == target_node_id else src
        if candidate_id == target_node_id:
            continue
        all_candidate_ids.add(candidate_id)
        raw_edges_by_node[candidate_id].append(edge)
        relation_norm = _normalize_key(str(edge.get("relation") or ""))
        if allowed_relation_types and relation_norm not in allowed_relation_types:
            continue
        relation_allowed_edges_by_node[candidate_id].append(edge)

    candidate_node_map = _fetch_entity_nodes(all_candidate_ids)
    seed_set = {int(item) for item in rendered_node_ids if int(item) == target_node_id}

    raw_unrendered_candidate_ids = {
        int(node_id)
        for node_id in all_candidate_ids
        if int(node_id) not in rendered_node_ids and int(node_id) in candidate_node_map
    }

    relation_filtered_ids = {
        int(node_id)
        for node_id in raw_unrendered_candidate_ids
        if not relation_allowed_edges_by_node.get(int(node_id))
    }

    type_filtered_ids: Set[int] = set()
    eligible_candidates: List[Dict[str, Any]] = []
    for node_id in sorted(raw_unrendered_candidate_ids):
        if node_id in relation_filtered_ids:
            continue
        node = candidate_node_map.get(node_id)
        if not node:
            continue
        entity_type_norm = _normalize_key(str(node.get("entity_type") or ""))
        if allowed_entity_types and entity_type_norm not in allowed_entity_types:
            type_filtered_ids.add(node_id)
            continue
        support_edges = relation_allowed_edges_by_node.get(node_id) or []
        relation_set = {
            _normalize_key(str(edge.get("relation") or ""))
            for edge in support_edges
            if str(edge.get("relation") or "").strip()
        }
        eligible_candidates.append(
            {
                **node,
                "entity_type_norm": entity_type_norm,
                "support_edges": list(support_edges),
                "support_edge_count": len(support_edges),
                "relation_diversity": len(relation_set),
            }
        )

    eligible_candidates.sort(key=_candidate_sort_key)
    eligible_candidate_ids = {int(item["id"]) for item in eligible_candidates}

    selected_pool: List[Dict[str, Any]] = []
    by_type_count: Dict[str, int] = defaultdict(int)
    effective_node_cap = min(max_new_nodes, max_new_edges)
    for item in eligible_candidates:
        entity_type_norm = str(item.get("entity_type_norm") or "")
        if by_type_count[entity_type_norm] >= top_k_per_type:
            continue
        by_type_count[entity_type_norm] += 1
        selected_pool.append(item)

    selected_candidates = selected_pool[:effective_node_cap]
    selected_candidate_ids = {int(item["id"]) for item in selected_candidates}
    budget_dropped_ids = eligible_candidate_ids - selected_candidate_ids

    normalized_selected_candidates: List[Dict[str, Any]] = []
    for item in selected_candidates:
        incident_support_edges = [
            edge for edge in item.get("support_edges") or [] if _is_target_incident_edge(edge, target_node_id)
        ]
        if not incident_support_edges:
            budget_dropped_ids.add(int(item["id"]))
            continue
        normalized_selected_candidates.append(
            {
                **item,
                "support_edges": incident_support_edges,
                "support_edge_count": len(incident_support_edges),
            }
        )

    selected_candidates = normalized_selected_candidates
    selected_candidate_ids = {int(item["id"]) for item in selected_candidates}

    primary_edges: List[Dict[str, Any]] = []
    seen_new_edge_keys: Set[Tuple[int, int, str]] = set(rendered_edge_ids)
    for item in selected_candidates:
        for edge in item.get("support_edges") or []:
            key = _edge_key(edge)
            if key in seen_new_edge_keys:
                continue
            primary_edges.append(edge)
            seen_new_edge_keys.add(key)
            break

    extra_edges: List[Dict[str, Any]] = []
    if max_new_edges > len(primary_edges):
        for item in selected_candidates:
            chosen_keys = {_edge_key(edge) for edge in primary_edges}
            for edge in item.get("support_edges") or []:
                key = _edge_key(edge)
                if key in seen_new_edge_keys or key in chosen_keys:
                    continue
                extra_edges.append(edge)
                seen_new_edge_keys.add(key)
                if len(primary_edges) + len(extra_edges) >= max_new_edges:
                    break
            if len(primary_edges) + len(extra_edges) >= max_new_edges:
                break

    new_edges = primary_edges + extra_edges
    support_edges: List[Dict[str, Any]] = []
    support_edge_keys = {_edge_key(edge) for edge in new_edges}
    for item in selected_candidates:
        for edge in item.get("support_edges") or []:
            key = _edge_key(edge)
            if key in support_edge_keys:
                continue
            support_edges.append(edge)
            support_edge_keys.add(key)

    new_nodes = [
        _node_payload(item, int(item.get("support_edge_count") or 0))
        for item in selected_candidates
    ]

    dropped_candidates: List[Dict[str, Any]] = []
    for node_id in sorted(relation_filtered_ids):
        node = candidate_node_map.get(node_id)
        if not node:
            continue
        dropped_candidates.append(
            _dropped_candidate_payload(
                node,
                reason=DiscoveryDroppedReason.RELATION_FILTER,
                source_node_id=target_node_id,
                support_edges=[_edge_payload(edge, seed_set) for edge in raw_edges_by_node.get(node_id) or []],
            )
        )
    for node_id in sorted(type_filtered_ids):
        node = candidate_node_map.get(node_id)
        if not node:
            continue
        dropped_candidates.append(
            _dropped_candidate_payload(
                node,
                reason=DiscoveryDroppedReason.TYPE_FILTER,
                source_node_id=target_node_id,
                support_edges=[
                    _edge_payload(edge, seed_set)
                    for edge in relation_allowed_edges_by_node.get(node_id) or []
                ],
            )
        )
    for node_id in sorted(budget_dropped_ids):
        node = candidate_node_map.get(node_id)
        if not node:
            continue
        dropped_candidates.append(
            _dropped_candidate_payload(
                node,
                reason=DiscoveryDroppedReason.BUDGET,
                source_node_id=target_node_id,
                support_edges=[
                    _edge_payload(edge, seed_set)
                    for edge in relation_allowed_edges_by_node.get(node_id) or []
                ],
            )
        )

    has_more_candidates_before_budget = bool(raw_unrendered_candidate_ids)
    has_more_candidates_after_filters = len(eligible_candidate_ids - selected_candidate_ids) > 0

    return {
        "new_nodes": new_nodes,
        "new_edges": [_edge_payload(edge, seed_set) for edge in new_edges],
        "support_edges": [_edge_payload(edge, seed_set) for edge in support_edges],
        "dropped_candidates": dropped_candidates,
        "has_more_candidates_before_budget": bool(has_more_candidates_before_budget),
        "has_more_candidates_after_filters": bool(has_more_candidates_after_filters),
        "terminal": not bool(has_more_candidates_after_filters),
        "stats": {
            "candidate_neighbor_count": len(raw_unrendered_candidate_ids),
            "filtered_candidate_count": len(eligible_candidate_ids),
            "new_nodes_count": len(new_nodes),
            "new_edges_count": len(new_edges),
            "dropped_by_budget": len(budget_dropped_ids),
            "dropped_by_type_filter": len(type_filtered_ids),
            "dropped_by_relation_filter": len(relation_filtered_ids),
            "dropped_neighbors": int(raw_meta["dropped_by_neighbor_cap"]),
            "scanned_rows": int(raw_meta["scanned_rows"]),
            "budget_applied": {
                "api": "graph_discovery_expand",
                "requested": {
                    "target_node_id": target_node_id,
                    "rendered_node_count": len(req.rendered_node_ids or []),
                    "rendered_edge_count": len(req.rendered_edge_ids or []),
                    "allowed_entity_type_count": len(req.allowed_entity_types or []),
                    "allowed_relation_type_count": len(req.allowed_relation_types or []),
                    "expand_max_new_nodes": int(req.expand_max_new_nodes or 0),
                    "expand_max_new_edges": int(req.expand_max_new_edges or 0),
                    "expand_top_k_per_type": int(req.expand_top_k_per_type or 0),
                },
                "applied": {
                    "rendered_node_count": len(rendered_node_ids),
                    "rendered_edge_count": len(rendered_edge_ids),
                    "allowed_entity_type_count": len(allowed_entity_types),
                    "allowed_relation_type_count": len(allowed_relation_types),
                    "expand_max_new_nodes": max_new_nodes,
                    "expand_max_new_edges": max_new_edges,
                    "effective_node_cap": effective_node_cap,
                    "expand_top_k_per_type": top_k_per_type,
                    "query_edge_scan_limit": query_scan_limit,
                    "per_root_neighbor_cap": graph_budget.expand_per_root_neighbor_cap,
                },
            },
        },
    }
