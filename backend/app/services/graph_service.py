import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, execute_ngql
from app.platform.graph.traversal_service import (
    _fetch_entity_nodes as _platform_fetch_entity_nodes,
    _go_edges_from as _platform_go_edges_from,
)
from app.platform.metadata import relation_catalog_service
from app.schemas.graph import (
    ExpandRequest,
    SubgraphRequest,
)
from app.services.graph_budget import graph_budget
from app.services import metadata_service
from app.services.common import truncate_by_degree, uniq_edges, vw

logger = logging.getLogger(__name__)


def _edge_key(edge: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        int(edge["source"]),
        int(edge["target"]),
        int(edge.get("rank") or 0),
    )


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
