from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, execute_ngql
from app.services.common import uniq_edges, vw

_PAIR_PARENT_FANIN_LIMIT = 12


def _edge_key(edge: Dict[str, Any]) -> Tuple[int, int, int]:
    return (
        int(edge["source"]),
        int(edge["target"]),
        int(edge.get("rank") or 0),
    )


def _fetch_entity_nodes(
    node_ids: Iterable[int],
    *,
    execute_ngql_fn: Callable[[str], Any] = execute_ngql,
    value_wrapper: Callable[[Any], Any] = vw,
) -> Dict[int, Dict[str, Any]]:
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
    fres = execute_ngql_fn(fetch_ngql)
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
        vid = int(value_wrapper(vids[i]))
        name = str(value_wrapper(names[i]) or "")
        typ = str(value_wrapper(types[i]) or "")
        raw_id = str(value_wrapper(raw_ids[i]) or "")
        source = str(value_wrapper(sources[i]) or "")
        descr = str(value_wrapper(descs[i]) or "")
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
    ignore_direction: bool = True,
    *,
    execute_ngql_fn: Callable[[str], Any] = execute_ngql,
    edge_tag: str = EDGE_TAG,
    edge_type: str = config.EDGE_TYPE,
    value_wrapper: Callable[[Any], Any] = vw,
    uniq_edges_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]] = uniq_edges,
    relation_key_fn: Optional[Callable[[str], str]] = None,
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
    direction_kw = " BIDIRECT" if ignore_direction else ""
    ngql = f"""
    GO FROM {id_list} OVER {edge_tag}{direction_kw}
    YIELD src(edge) AS src, dst(edge) AS dst,
          rank(edge) AS rank,
          properties(edge).relation AS relation,
          properties(edge).source AS esource
    | LIMIT {int(query_scan_limit)};
    """
    res = execute_ngql_fn(ngql)
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
        src = int(value_wrapper(srcs[i]))
        dst = int(value_wrapper(dsts[i]))
        rank = int(value_wrapper(ranks[i]) or 0)
        relation = str(value_wrapper(rels[i]) or "")
        source_db = str(value_wrapper(esources[i]) or "")
        relation_key = relation_key_fn(relation) if relation_key_fn else relation

        if rel_filter and relation_key not in rel_filter:
            dropped_by_relation += 1
            continue

        anchors: List[int] = []
        if src in frontier_set:
            anchors.append(src)
        if ignore_direction and dst in frontier_set and dst != src:
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
                "edge_type": edge_type,
                "relation": relation,
                "source_db": source_db,
            }
        )

    return uniq_edges_fn(out), {
        "scanned_rows": len(srcs),
        "dropped_by_relation": dropped_by_relation,
        "dropped_by_neighbor_cap": dropped_by_neighbor_cap,
    }


def _find_shortest_path_candidates_bfs(
    src: int,
    dst: int,
    max_hop: int,
    rel_filter: Set[str],
    query_scan_limit: int,
    per_root_neighbor_cap: int,
    ignore_direction: bool,
    candidate_limit: int,
    *,
    go_edges_from_fn: Optional[Callable[..., Tuple[List[Dict[str, Any]], Dict[str, int]]]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    if int(src) == int(dst):
        return [{"nodes": [int(src)], "edges": []}], {
            "scanned_rows": 0,
            "dropped_by_relation": 0,
            "dropped_by_neighbor_cap": 0,
        }

    source = int(src)
    target = int(dst)
    visited_depth: Dict[int, int] = {source: 0}
    frontier = [source]
    parents: Dict[int, List[Tuple[int, Dict[str, Any]]]] = {}
    shortest_depth: Optional[int] = None
    meta = {
        "scanned_rows": 0,
        "dropped_by_relation": 0,
        "dropped_by_neighbor_cap": 0,
    }
    go_edges = go_edges_from_fn or _go_edges_from

    for depth in range(1, int(max_hop) + 1):
        if not frontier:
            break

        frontier_set = set(frontier)
        batch_edges, batch_meta = go_edges(
            frontier,
            rel_filter=rel_filter,
            query_scan_limit=query_scan_limit,
            per_root_neighbor_cap=per_root_neighbor_cap,
            ignore_direction=ignore_direction,
        )
        meta["scanned_rows"] += int(batch_meta["scanned_rows"])
        meta["dropped_by_relation"] += int(batch_meta["dropped_by_relation"])
        meta["dropped_by_neighbor_cap"] += int(batch_meta["dropped_by_neighbor_cap"])
        next_frontier: Set[int] = set()

        for edge in batch_edges:
            u = int(edge["source"])
            v = int(edge["target"])

            steps: List[Tuple[int, int]] = []
            if u in frontier_set:
                steps.append((u, v))
            if ignore_direction and v in frontier_set:
                steps.append((v, u))

            for parent, child in steps:
                prev_depth = visited_depth.get(child)
                if prev_depth is None:
                    visited_depth[child] = depth
                    parents[child] = [(parent, edge)]
                    next_frontier.add(child)
                elif prev_depth == depth:
                    parent_items = parents.setdefault(child, [])
                    already = False
                    for existing_parent, existing_edge in parent_items:
                        if existing_parent == parent and _edge_key(existing_edge) == _edge_key(edge):
                            already = True
                            break
                    if not already and len(parent_items) < _PAIR_PARENT_FANIN_LIMIT:
                        parent_items.append((parent, edge))

        if visited_depth.get(target) == depth:
            shortest_depth = depth
            break
        frontier = list(next_frontier)

    if shortest_depth is None:
        return [], meta

    paths: List[Dict[str, Any]] = []
    seen_path_keys: Set[Tuple[Tuple[int, ...], Tuple[Tuple[int, int, int], ...]]] = set()
    stack: List[Tuple[int, List[int], List[Dict[str, Any]]]] = [(target, [target], [])]

    while stack and len(paths) < int(candidate_limit):
        cur, nodes_rev, edges_rev = stack.pop()
        if cur == source:
            nodes = list(reversed(nodes_rev))
            edges = list(reversed(edges_rev))
            edge_seq = tuple(_edge_key(e) for e in edges)
            uniq_key = (tuple(nodes), edge_seq)
            if uniq_key not in seen_path_keys:
                seen_path_keys.add(uniq_key)
                paths.append({"nodes": nodes, "edges": edges})
            continue

        for parent, edge in parents.get(cur, []):
            if visited_depth.get(parent) != visited_depth.get(cur, 0) - 1:
                continue
            stack.append((parent, nodes_rev + [parent], edges_rev + [edge]))

    paths.sort(
        key=lambda p: (
            len(p.get("edges") or []),
            tuple(int(x) for x in (p.get("nodes") or [])),
            tuple(_edge_key(e) for e in (p.get("edges") or [])),
        )
    )
    return paths[: int(candidate_limit)], meta
