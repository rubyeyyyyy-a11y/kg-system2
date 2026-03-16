import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, execute_ngql
from app.platform.graph.traversal_service import (
    _fetch_entity_nodes as _platform_fetch_entity_nodes,
    _find_shortest_path_candidates_bfs as _platform_find_shortest_path_candidates_bfs,
    _go_edges_from as _platform_go_edges_from,
)
from app.platform.metadata import relation_catalog_service
from app.schemas.graph import (
    ExpandRequest,
    MultiEntityGraphApplyPathsRequest,
    MultiEntityGraphRequest,
    SubgraphRequest,
)
from app.services.graph_budget import graph_budget
from app.services import metadata_service
from app.services.common import truncate_by_degree, uniq_edges, vw

logger = logging.getLogger(__name__)

_PAIR_PARENT_FANIN_LIMIT = 12


def _edge_key(edge: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        int(edge["source"]),
        int(edge["target"]),
        int(edge.get("rank") or 0),
    )


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    x = int(a)
    y = int(b)
    return (x, y) if x <= y else (y, x)


def _pair_key_with_direction(a: int, b: int, ignore_direction: bool) -> Tuple[int, int]:
    if ignore_direction:
        return _pair_key(a, b)
    return (int(a), int(b))


def _budget_error(message: str, code: str = "graph_budget_reject") -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": code,
            "message": message,
        },
    )


def _normalize_rel_filter(relations: List[str], max_count: int) -> Tuple[Set[str], int]:
    out = set()
    dropped = 0
    for r in relations or []:
        rr = str(r or "").strip()
        if not rr:
            continue
        if rr in out:
            continue
        if len(out) >= int(max_count):
            dropped += 1
            continue
        out.add(rr)
    return out, dropped


def _fetch_entity_nodes(node_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    return _platform_fetch_entity_nodes(
        node_ids,
        execute_ngql_fn=execute_ngql,
        value_wrapper=vw,
    )


def _go_edges_from(
    frontier: List[int],
    rel_filter: Set[str],
    query_scan_limit: int,
    per_root_neighbor_cap: int,
    ignore_direction: bool = True,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    return _platform_go_edges_from(
        frontier,
        rel_filter=rel_filter,
        query_scan_limit=query_scan_limit,
        per_root_neighbor_cap=per_root_neighbor_cap,
        ignore_direction=ignore_direction,
        execute_ngql_fn=execute_ngql,
        edge_tag=EDGE_TAG,
        edge_type=config.EDGE_TYPE,
        value_wrapper=vw,
        uniq_edges_fn=uniq_edges,
    )


def _apply_edge_hard_cap(edges: List[Dict[str, Any]], max_edges: int) -> Tuple[List[Dict[str, Any]], int]:
    if len(edges) <= int(max_edges):
        return edges, 0
    sorted_edges = sorted(
        edges,
        key=lambda e: (
            int(e["source"]),
            int(e["target"]),
            int(e.get("rank") or 0),
            str(e.get("relation") or ""),
            str(e.get("source_db") or ""),
        ),
    )
    kept = sorted_edges[: int(max_edges)]
    return kept, max(0, len(sorted_edges) - len(kept))


def _build_path_summary(path: Dict[str, Any]) -> str:
    nodes = [int(x) for x in (path.get("nodes") or [])]
    edges = path.get("edges") or []
    if not nodes:
        return ""
    if len(nodes) == 1:
        return str(nodes[0])

    parts: List[str] = [str(nodes[0])]
    for idx, edge in enumerate(edges):
        rel = str(edge.get("relation") or "")
        nxt = nodes[idx + 1] if idx + 1 < len(nodes) else "?"
        parts.append(f"-({rel})->")
        parts.append(str(nxt))
    return " ".join(parts)


def _find_shortest_path_candidates_bfs(
    src: int,
    dst: int,
    max_hop: int,
    rel_filter: Set[str],
    query_scan_limit: int,
    per_root_neighbor_cap: int,
    ignore_direction: bool,
    candidate_limit: int,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    return _platform_find_shortest_path_candidates_bfs(
        src=src,
        dst=dst,
        max_hop=max_hop,
        rel_filter=rel_filter,
        query_scan_limit=query_scan_limit,
        per_root_neighbor_cap=per_root_neighbor_cap,
        ignore_direction=ignore_direction,
        candidate_limit=candidate_limit,
        go_edges_from_fn=_go_edges_from,
    )


def relation_types(*, q: str = "", limit: int = 100, offset: int = 0) -> Dict[str, Any]:
    return relation_catalog_service.query_relation_types(
        q=q,
        limit=limit,
        offset=offset,
        query_relation_types_fn=metadata_service.query_relation_types,
        logger_instance=logger,
    )


def subgraph(req: SubgraphRequest) -> Dict[str, Any]:
    root = int(req.root_vid)
    requested_hop = int(req.hop or 1)
    requested_max_nodes = int(req.max_nodes or 300)
    requested_max_edges = int(req.max_edges or 20000)

    hop = max(1, min(requested_hop, graph_budget.subgraph_hop_max))
    max_nodes = max(2, min(requested_max_nodes, graph_budget.subgraph_max_nodes_cap))
    max_edges = max(1, min(requested_max_edges, graph_budget.subgraph_max_edges_cap))
    rel_filter, dropped_relation_filter_terms = _normalize_rel_filter(
        req.relations or [],
        max_count=graph_budget.relation_filter_max,
    )
    query_scan_limit = max(
        max_edges,
        min(graph_budget.subgraph_query_edge_scan_cap, max_edges * 4),
    )

    visited = set([root])
    frontier = [root]

    edges_all: List[Dict[str, Any]] = []
    nodes_all: List[int] = [root]
    dropped_neighbors = 0
    dropped_edges = 0
    dropped_frontier = 0
    scanned_rows = 0
    dropped_rows_by_relation = 0
    truncated = False

    for _hop_idx in range(hop):
        if not frontier:
            break

        if len(frontier) > graph_budget.subgraph_frontier_cap:
            dropped_frontier += len(frontier) - graph_budget.subgraph_frontier_cap
            frontier = sorted(frontier)[: graph_budget.subgraph_frontier_cap]
            truncated = True

        batch_edges, batch_meta = _go_edges_from(
            frontier=frontier,
            rel_filter=rel_filter,
            query_scan_limit=query_scan_limit,
            per_root_neighbor_cap=graph_budget.subgraph_per_root_neighbor_cap,
            ignore_direction=True,
        )
        scanned_rows += int(batch_meta["scanned_rows"])
        dropped_rows_by_relation += int(batch_meta["dropped_by_relation"])
        dropped_neighbors += int(batch_meta["dropped_by_neighbor_cap"])

        next_frontier: List[int] = []
        frontier_set = set(frontier)
        for edge in batch_edges:
            edges_all.append(edge)

            src = int(edge["source"])
            dst = int(edge["target"])
            for nid in (src, dst):
                if nid in visited:
                    continue
                visited.add(nid)
                nodes_all.append(nid)
                if nid not in frontier_set:
                    next_frontier.append(nid)

        frontier = sorted(set(next_frontier))
        if len(edges_all) >= max_edges:
            truncated = True
            break
        if len(visited) >= max_nodes:
            truncated = True
            break

    edges_all = uniq_edges(edges_all)
    edges_all, dropped_by_edge_cap = _apply_edge_hard_cap(edges_all, max_edges=max_edges)
    dropped_edges += int(dropped_by_edge_cap)
    if dropped_by_edge_cap > 0:
        truncated = True

    nodes_unique = sorted(set(nodes_all))
    dropped_nodes = 0
    if len(nodes_unique) > max_nodes:
        before_trim = len(edges_all)
        kept_nodes, kept_edges, dropped_nodes = truncate_by_degree(
            root_vid=root,
            keep_forced=[root],
            nodes_all=nodes_unique,
            edges_all=edges_all,
            max_nodes=max_nodes,
        )
        nodes_unique = kept_nodes
        edges_all = kept_edges
        dropped_edges += max(0, before_trim - len(kept_edges))
        truncated = True

    vid_list = ",".join(str(x) for x in nodes_unique)
    fetch_ngql = f"""
    MATCH (v:`Entity`)
    WHERE id(v) IN [{vid_list}]
    RETURN id(v) AS vid,
           v.`Entity`.`entity_name` AS name,
           v.`Entity`.`entity_type` AS type,
           v.`Entity`.`entity_raw_id` AS raw_id,
           v.`Entity`.`source` AS source,
           v.`Entity`.`description` AS descr
LIMIT {len(nodes_unique)};
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
        rid = str(vw(raw_ids[i]) or "")
        src = str(vw(sources[i]) or "")
        dsc = str(vw(descs[i]) or "")
        node_map[vid] = {
            "id": vid,
            "label": name,
            "entity_type": typ,
            "raw_id": rid,
            "source": src,
            "snippet": (dsc[:160] + "…") if dsc and len(dsc) > 160 else (dsc or ""),
        }

    nodes_out = [node_map[v] for v in nodes_unique if v in node_map]
    kept_nodes_set = set(n["id"] for n in nodes_out)
    edges_out = [
        e for e in edges_all if int(e["source"]) in kept_nodes_set and int(e["target"]) in kept_nodes_set
    ]
    if len(edges_out) < len(edges_all):
        dropped_edges += len(edges_all) - len(edges_out)
        truncated = True

    budget_applied = {
        "api": "subgraph",
        "requested": {
            "hop": requested_hop,
            "max_nodes": requested_max_nodes,
            "max_edges": requested_max_edges,
            "relation_filter_count": len(req.relations or []),
        },
        "applied": {
            "hop": hop,
            "max_nodes": max_nodes,
            "max_edges": max_edges,
            "relation_filter_count": len(rel_filter),
            "relation_filter_max": graph_budget.relation_filter_max,
            "frontier_cap": graph_budget.subgraph_frontier_cap,
            "per_root_neighbor_cap": graph_budget.subgraph_per_root_neighbor_cap,
            "query_edge_scan_limit": query_scan_limit,
        },
        "dropped": {
            "relation_filter_terms": int(dropped_relation_filter_terms),
            "frontier_nodes": int(dropped_frontier),
            "rows_by_relation": int(dropped_rows_by_relation),
            "rows_by_neighbor_cap": int(dropped_neighbors),
        },
        "scanned_rows": int(scanned_rows),
    }
    truncated = bool(
        truncated
        or dropped_nodes > 0
        or dropped_edges > 0
        or dropped_neighbors > 0
        or dropped_relation_filter_terms > 0
    )

    return {
        "root_vid": root,
        "nodes": nodes_out,
        "edges": edges_out,
        "stats": {
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
            "truncated": bool(truncated),
            "dropped_nodes": int(dropped_nodes),
            "dropped_edges": int(dropped_edges),
            "dropped_neighbors": int(dropped_neighbors),
            "budget_applied": budget_applied,
        },
    }


def expand(req: ExpandRequest) -> Dict[str, Any]:
    from_vid = int(req.from_vid)
    requested_max_nodes = int(req.max_nodes or 300)
    requested_max_edges = int(req.max_edges or 20000)
    requested_existing_count = len(req.existing_node_ids or [])
    rel_filter, dropped_relation_filter_terms = _normalize_rel_filter(
        req.relations or [],
        max_count=graph_budget.relation_filter_max,
    )

    existing_items = [int(x) for x in (req.existing_node_ids or [])]
    if len(existing_items) > graph_budget.expand_existing_node_cap:
        existing_items = existing_items[: graph_budget.expand_existing_node_cap]
    existing = set(existing_items)

    max_nodes = max(2, min(requested_max_nodes, graph_budget.expand_max_nodes_cap))
    max_edges = max(1, min(requested_max_edges, graph_budget.expand_max_edges_cap))
    query_scan_limit = max(
        max_edges,
        min(graph_budget.expand_query_edge_scan_cap, max_edges * 4),
    )

    batch_edges, batch_meta = _go_edges_from(
        frontier=[from_vid],
        rel_filter=rel_filter,
        query_scan_limit=query_scan_limit,
        per_root_neighbor_cap=graph_budget.expand_per_root_neighbor_cap,
        ignore_direction=True,
    )
    dropped_neighbors = int(batch_meta["dropped_by_neighbor_cap"])
    dropped_rows_by_relation = int(batch_meta["dropped_by_relation"])
    scanned_rows = int(batch_meta["scanned_rows"])

    edges_all = []
    cand_nodes = set(existing)
    cand_nodes.add(from_vid)
    dropped_edges = 0
    truncated = False

    for edge in batch_edges:
        src = int(edge["source"])
        dst = int(edge["target"])
        edges_all.append(edge)
        cand_nodes.add(src)
        cand_nodes.add(dst)

    edges_all = uniq_edges(edges_all)
    edges_all, dropped_by_edge_cap = _apply_edge_hard_cap(edges_all, max_edges=max_edges)
    dropped_edges += int(dropped_by_edge_cap)
    if dropped_by_edge_cap > 0:
        truncated = True

    dropped_nodes = 0
    kept_nodes = sorted(cand_nodes)
    kept_edges = edges_all

    if len(cand_nodes) > max_nodes:
        before_trim = len(kept_edges)
        keep_forced = list(existing) + [from_vid]
        kept_nodes, kept_edges, dropped_nodes = truncate_by_degree(
            root_vid=from_vid,
            keep_forced=keep_forced,
            nodes_all=sorted(cand_nodes),
            edges_all=edges_all,
            max_nodes=max_nodes,
        )
        dropped_edges += max(0, before_trim - len(kept_edges))
        truncated = True

    kept_set = set(kept_nodes)

    new_node_ids = [v for v in kept_nodes if v not in existing]
    added_nodes = []
    if new_node_ids:
        vid_list = ",".join(str(x) for x in new_node_ids)
        fetch_ngql = f"""
        MATCH (v:`Entity`)
        WHERE id(v) IN [{vid_list}]
        RETURN id(v) AS vid,
               v.`Entity`.`entity_name` AS name,
               v.`Entity`.`entity_type` AS type,
               v.`Entity`.`entity_raw_id` AS raw_id,
               v.`Entity`.`source` AS source,
               v.`Entity`.`description` AS descr
LIMIT {len(new_node_ids)};
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

        for i in range(len(vids)):
            vid = int(vw(vids[i]))
            name = str(vw(names[i]) or "")
            typ = str(vw(types[i]) or "")
            rid = str(vw(raw_ids[i]) or "")
            src = str(vw(sources[i]) or "")
            dsc = str(vw(descs[i]) or "")
            added_nodes.append(
                {
                    "id": vid,
                    "label": name,
                    "entity_type": typ,
                    "raw_id": rid,
                    "source": src,
                    "snippet": (dsc[:160] + "…") if dsc and len(dsc) > 160 else (dsc or ""),
                }
            )

    pre_filter_edges = len(kept_edges)
    kept_edges = [e for e in kept_edges if int(e["source"]) in kept_set and int(e["target"]) in kept_set]
    if len(kept_edges) < pre_filter_edges:
        dropped_edges += pre_filter_edges - len(kept_edges)
        truncated = True
    new_set = set(new_node_ids)
    added_edges = [e for e in kept_edges if int(e["source"]) in new_set or int(e["target"]) in new_set]

    budget_applied = {
        "api": "expand",
        "requested": {
            "max_nodes": requested_max_nodes,
            "max_edges": requested_max_edges,
            "relation_filter_count": len(req.relations or []),
            "existing_node_ids_count": requested_existing_count,
        },
        "applied": {
            "max_nodes": max_nodes,
            "max_edges": max_edges,
            "relation_filter_count": len(rel_filter),
            "relation_filter_max": graph_budget.relation_filter_max,
            "existing_node_ids_count": len(existing),
            "existing_node_ids_cap": graph_budget.expand_existing_node_cap,
            "per_root_neighbor_cap": graph_budget.expand_per_root_neighbor_cap,
            "query_edge_scan_limit": query_scan_limit,
        },
        "dropped": {
            "relation_filter_terms": int(dropped_relation_filter_terms),
            "rows_by_relation": int(dropped_rows_by_relation),
            "rows_by_neighbor_cap": int(dropped_neighbors),
            "existing_node_ids": max(0, requested_existing_count - len(existing)),
        },
        "scanned_rows": int(scanned_rows),
    }
    truncated = bool(
        truncated
        or dropped_nodes > 0
        or dropped_edges > 0
        or dropped_neighbors > 0
        or dropped_relation_filter_terms > 0
        or requested_existing_count > len(existing)
    )

    return {
        "added_nodes": added_nodes,
        "added_edges": added_edges,
        "stats": {
            "node_count_after": len(kept_set),
            "edge_count_after": len(kept_edges),
            "added_nodes": len(added_nodes),
            "added_edges": len(added_edges),
            "truncated": bool(truncated),
            "dropped_nodes": int(dropped_nodes),
            "dropped_edges": int(dropped_edges),
            "dropped_neighbors": int(dropped_neighbors),
            "policy": "degree",
            "budget_applied": budget_applied,
        },
    }


def _build_multi_entity_graph(
    req: MultiEntityGraphRequest,
    choice_overrides: Optional[Dict[Tuple[int, int], int]] = None,
) -> Dict[str, Any]:
    requested_vid_count = len(req.vids or [])
    requested_max_nodes = int(req.max_nodes or 300)
    requested_max_edges = int(req.max_edges or 20000)
    requested_k = int(req.k or 2)
    requested_rel_filter_count = len(req.relations or [])

    vids_raw = req.vids or []
    selected_vids: List[int] = []
    seen_vid = set()
    for v in vids_raw:
        iv = int(v)
        if iv in seen_vid:
            continue
        seen_vid.add(iv)
        selected_vids.append(iv)

    if len(selected_vids) < 2:
        raise _budget_error("vids must contain at least 2 entities")
    if len(selected_vids) > graph_budget.multi_root_cap:
        raise _budget_error(
            f"vids exceeds max slots {graph_budget.multi_root_cap}",
            code="graph_root_overflow",
        )

    max_nodes = max(2, min(requested_max_nodes, graph_budget.multi_max_nodes_cap))
    max_edges = max(1, min(requested_max_edges, graph_budget.multi_max_edges_cap))
    if len(selected_vids) > max_nodes:
        raise _budget_error("max_nodes is smaller than selected vids count")

    k = max(1, min(requested_k, graph_budget.multi_k_max))
    rel_filter, dropped_relation_filter_terms = _normalize_rel_filter(
        req.relations or [],
        max_count=graph_budget.relation_filter_max,
    )
    ignore_direction = bool(req.ignore_direction)
    explain_enabled = bool(req.explain_paths) and (not bool(req.direct_only))
    auto_apply_limit = 1 if int(req.per_pair_path_limit or 1) >= 1 else 0
    pair_candidate_limit = graph_budget.multi_pair_candidate_cap
    query_limit = max(
        max_edges,
        min(graph_budget.multi_query_edge_scan_cap, max_edges * 4),
    )

    edge_map: Dict[Tuple[int, int, int, str, str], Dict[str, Any]] = {}
    node_ids: Set[int] = set(selected_vids)
    selected_set = set(selected_vids)
    truncated = False
    dropped_neighbors = 0
    dropped_rows_by_relation = 0
    scanned_rows = 0
    explained_pairs = 0
    path_candidates: List[Dict[str, Any]] = []
    unconnected_pairs: List[str] = []

    # direct edges among selected entities
    direct_candidates, direct_meta = _go_edges_from(
        selected_vids,
        rel_filter=rel_filter,
        query_scan_limit=query_limit,
        per_root_neighbor_cap=graph_budget.multi_per_root_neighbor_cap,
        ignore_direction=ignore_direction,
    )
    scanned_rows += int(direct_meta["scanned_rows"])
    dropped_neighbors += int(direct_meta["dropped_by_neighbor_cap"])
    dropped_rows_by_relation += int(direct_meta["dropped_by_relation"])
    direct_edges = [
        e
        for e in direct_candidates
        if int(e["source"]) in selected_set and int(e["target"]) in selected_set
    ]
    direct_edges = uniq_edges(direct_edges)

    direct_pairs = set()
    for e in direct_edges:
        src = int(e["source"])
        dst = int(e["target"])
        ek = _edge_key(e)
        edge_map[ek] = {
            "source": src,
            "target": dst,
            "rank": str(e.get("rank") or "0"),
            "edge_type": config.EDGE_TYPE,
            "relation": str(e.get("relation") or ""),
            "source_db": str(e.get("source_db") or ""),
            "is_explain": False,
        }
        direct_pairs.add(_pair_key_with_direction(src, dst, ignore_direction))

    if explain_enabled:
        for i in range(len(selected_vids)):
            for j in range(i + 1, len(selected_vids)):
                src = int(selected_vids[i])
                dst = int(selected_vids[j])
                pair_key = _pair_key(src, dst)
                lookup_pair = _pair_key_with_direction(src, dst, ignore_direction)
                if lookup_pair in direct_pairs:
                    path_candidates.append(
                        {
                            "u": pair_key[0],
                            "v": pair_key[1],
                            "has_direct": True,
                            "chosen_index": None,
                            "candidates": [],
                        }
                    )
                    continue

                raw_paths, path_meta = _find_shortest_path_candidates_bfs(
                    src=src,
                    dst=dst,
                    max_hop=k,
                    rel_filter=rel_filter,
                    query_scan_limit=query_limit,
                    per_root_neighbor_cap=graph_budget.multi_per_root_neighbor_cap,
                    ignore_direction=ignore_direction,
                    candidate_limit=pair_candidate_limit,
                )
                scanned_rows += int(path_meta["scanned_rows"])
                dropped_neighbors += int(path_meta["dropped_by_neighbor_cap"])
                dropped_rows_by_relation += int(path_meta["dropped_by_relation"])
                if not raw_paths:
                    unconnected_pairs.append(f"{pair_key[0]}-{pair_key[1]}")
                    path_candidates.append(
                        {
                            "u": pair_key[0],
                            "v": pair_key[1],
                            "has_direct": False,
                            "chosen_index": None,
                            "candidates": [],
                        }
                    )
                    continue

                candidates: List[Dict[str, Any]] = []
                for idx, p in enumerate(raw_paths):
                    p_nodes = [int(x) for x in (p.get("nodes") or [])]
                    p_edges = [
                        {
                            "source": int(e["source"]),
                            "target": int(e["target"]),
                            "rank": str(e.get("rank") or "0"),
                            "edge_type": config.EDGE_TYPE,
                            "relation": str(e.get("relation") or ""),
                            "source_db": str(e.get("source_db") or ""),
                        }
                        for e in (p.get("edges") or [])
                    ]
                    score = round(max(0.1, 1.0 - (idx * 0.2)), 3)
                    candidate = {
                        "path_id": f"p{idx}",
                        "length": len(p_edges),
                        "nodes": p_nodes,
                        "edges": p_edges,
                        "score": score,
                        "summary": _build_path_summary({"nodes": p_nodes, "edges": p_edges}),
                    }
                    candidates.append(candidate)

                chosen_index: Optional[int] = 0 if auto_apply_limit > 0 else None
                if choice_overrides and pair_key in choice_overrides:
                    req_choice = int(choice_overrides[pair_key])
                    if 0 <= req_choice < len(candidates):
                        chosen_index = req_choice

                if chosen_index is not None:
                    explained_pairs += 1
                    chosen_path = candidates[chosen_index]
                    for nid in chosen_path["nodes"]:
                        node_ids.add(int(nid))
                    for edge in chosen_path["edges"]:
                        ek = _edge_key(edge)
                        if ek in edge_map and edge_map[ek].get("is_explain") is False:
                            continue
                        edge_map[ek] = {
                            "source": int(edge["source"]),
                            "target": int(edge["target"]),
                            "rank": str(edge.get("rank") or "0"),
                            "edge_type": config.EDGE_TYPE,
                            "relation": str(edge.get("relation") or ""),
                            "source_db": str(edge.get("source_db") or ""),
                            "is_explain": True,
                        }

                path_candidates.append(
                    {
                        "u": pair_key[0],
                        "v": pair_key[1],
                        "has_direct": False,
                        "chosen_index": chosen_index,
                        "candidates": candidates,
                    }
                )

    edges_out = list(edge_map.values())
    dropped_edges = 0
    dropped_nodes = 0
    if len(node_ids) > max_nodes:
        before_trim_edges = len(edges_out)
        kept_nodes, kept_edges, dropped_nodes = truncate_by_degree(
            root_vid=selected_vids[0],
            keep_forced=selected_vids,
            nodes_all=sorted(node_ids),
            edges_all=edges_out,
            max_nodes=max_nodes,
        )
        node_ids = set(int(x) for x in kept_nodes)
        edges_out = kept_edges
        dropped_edges += max(0, before_trim_edges - len(edges_out))
        truncated = truncated or (dropped_nodes > 0)

    # prune non-selected isolated explain nodes
    used_nodes = set(selected_vids)
    for e in edges_out:
        used_nodes.add(int(e["source"]))
        used_nodes.add(int(e["target"]))
    node_ids = node_ids.intersection(used_nodes)

    if len(edges_out) > max_edges:
        dropped_edges += len(edges_out) - max_edges
        # keep direct edges first, then explain edges
        edges_out.sort(
            key=lambda e: (
                bool(e.get("is_explain", False)),
                int(e["source"]),
                int(e["target"]),
                int(e.get("rank") or 0),
                str(e.get("relation") or ""),
                str(e.get("source_db") or ""),
            )
        )
        edges_out = edges_out[:max_edges]
        truncated = True

    used_after_trim = set(selected_vids)
    for e in edges_out:
        used_after_trim.add(int(e["source"]))
        used_after_trim.add(int(e["target"]))
    node_ids = node_ids.intersection(used_after_trim)

    node_map = _fetch_entity_nodes(sorted(node_ids))
    ordered_nodes = selected_vids + sorted([v for v in node_ids if v not in selected_set])
    nodes_out = []
    for vid in ordered_nodes:
        if vid in node_map:
            nodes_out.append(node_map[vid])
        else:
            nodes_out.append(
                {
                    "id": int(vid),
                    "label": str(vid),
                    "entity_type": "",
                    "raw_id": "",
                    "source": "",
                    "snippet": "",
                }
            )

    connected_selected = set()
    for e in edges_out:
        s = int(e["source"])
        t = int(e["target"])
        if s in selected_set:
            connected_selected.add(s)
        if t in selected_set:
            connected_selected.add(t)

    unconnected = [v for v in selected_vids if v not in connected_selected]
    direct_edge_count = sum(1 for e in edges_out if not bool(e.get("is_explain", False)))
    budget_applied = {
        "api": "multi_entity_graph",
        "requested": {
            "vids_count": requested_vid_count,
            "k": requested_k,
            "max_nodes": requested_max_nodes,
            "max_edges": requested_max_edges,
            "relation_filter_count": requested_rel_filter_count,
        },
        "applied": {
            "vids_count": len(selected_vids),
            "vids_cap": graph_budget.multi_root_cap,
            "k": k,
            "k_cap": graph_budget.multi_k_max,
            "max_nodes": max_nodes,
            "max_nodes_cap": graph_budget.multi_max_nodes_cap,
            "max_edges": max_edges,
            "max_edges_cap": graph_budget.multi_max_edges_cap,
            "relation_filter_count": len(rel_filter),
            "relation_filter_cap": graph_budget.relation_filter_max,
            "pair_candidate_cap": pair_candidate_limit,
            "per_root_neighbor_cap": graph_budget.multi_per_root_neighbor_cap,
            "query_edge_scan_limit": query_limit,
        },
        "dropped": {
            "relation_filter_terms": int(dropped_relation_filter_terms),
            "rows_by_relation": int(dropped_rows_by_relation),
            "rows_by_neighbor_cap": int(dropped_neighbors),
        },
        "scanned_rows": int(scanned_rows),
    }
    truncated = bool(
        truncated
        or dropped_nodes > 0
        or dropped_edges > 0
        or dropped_neighbors > 0
        or dropped_relation_filter_terms > 0
        or requested_k != k
    )

    return {
        "nodes": nodes_out,
        "edges": edges_out,
        "stats": {
            "selected": len(selected_vids),
            "direct_edges": direct_edge_count,
            "explained_pairs": int(explained_pairs),
            "unconnected": unconnected,
            "unconnected_pairs": unconnected_pairs,
            "truncated": bool(truncated),
            "dropped_nodes": int(dropped_nodes),
            "dropped_edges": int(dropped_edges),
            "dropped_neighbors": int(dropped_neighbors),
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
            "budget_applied": budget_applied,
        },
        "path_candidates": path_candidates,
    }


def multi_entity_graph(req: MultiEntityGraphRequest) -> Dict[str, Any]:
    return _build_multi_entity_graph(req=req, choice_overrides=None)


def multi_entity_graph_apply_paths(req: MultiEntityGraphApplyPathsRequest) -> Dict[str, Any]:
    base_data = req.base_request.dict()
    base_data["direct_only"] = False
    base_data["explain_paths"] = True
    base_req = MultiEntityGraphRequest(**base_data)

    choice_overrides: Dict[Tuple[int, int], int] = {}
    for choice in req.choices or []:
        pair_key = _pair_key(int(choice.u), int(choice.v))
        choice_overrides[pair_key] = int(choice.chosen_index)

    return _build_multi_entity_graph(req=base_req, choice_overrides=choice_overrides)
