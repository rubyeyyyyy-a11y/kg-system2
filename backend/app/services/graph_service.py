import time
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import HTTPException

from app.core import config
from app.db.nebula import EDGE_TAG, get_session
from app.schemas.graph import (
    ExpandRequest,
    MultiEntityGraphApplyPathsRequest,
    MultiEntityGraphRequest,
    SubgraphRequest,
)
from app.services.common import truncate_by_degree, uniq_edges, vw

_relation_cache = {"ts": 0.0, "data": []}
_MAX_MULTI_VIDS = 8
_MAX_MULTI_HOP = 3
_PAIR_CAND_LIMIT = 5
_MAX_MULTI_QUERY_EDGES = 50000
_MAX_MULTI_NODE_LIMIT = 2000


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


def _normalize_rel_filter(relations: List[str]) -> Set[str]:
    out = set()
    for r in relations or []:
        rr = str(r or "").strip()
        if rr:
            out.add(rr)
    return out


def _fetch_entity_nodes(node_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    ids = sorted(set(int(v) for v in node_ids))
    if not ids:
        return {}

    s = get_session()
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
    fres = s.execute(fetch_ngql)
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
    return node_map


def _go_edges_from(
    frontier: List[int],
    rel_filter: Set[str],
    max_edges: int,
    ignore_direction: bool = True,
) -> List[Dict[str, Any]]:
    if not frontier:
        return []

    id_list = ",".join(str(int(x)) for x in sorted(set(frontier)))
    direction_kw = " BIDIRECT" if ignore_direction else ""
    ngql = f"""
    GO FROM {id_list} OVER {EDGE_TAG}{direction_kw}
    YIELD src(edge) AS src, dst(edge) AS dst,
          rank(edge) AS rank,
          properties(edge).relation AS relation,
          properties(edge).source AS esource
    | LIMIT {int(max_edges)};
    """
    s = get_session()
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    srcs = res.column_values("src")
    dsts = res.column_values("dst")
    ranks = res.column_values("rank")
    rels = res.column_values("relation")
    esources = res.column_values("esource")

    out: List[Dict[str, Any]] = []
    for i in range(len(srcs)):
        src = int(vw(srcs[i]))
        dst = int(vw(dsts[i]))
        rank = int(vw(ranks[i]) or 0)
        rel = str(vw(rels[i]) or "")
        esrc = str(vw(esources[i]) or "")
        if rel_filter and rel not in rel_filter:
            continue
        out.append(
            {
                "source": src,
                "target": dst,
                "rank": str(rank),
                "edge_type": config.EDGE_TYPE,
                "relation": rel,
                "source_db": esrc,
            }
        )
    return uniq_edges(out)


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
    max_edges: int,
    ignore_direction: bool,
    candidate_limit: int,
) -> List[Dict[str, Any]]:
    if int(src) == int(dst):
        return [{"nodes": [int(src)], "edges": []}]

    source = int(src)
    target = int(dst)
    visited_depth: Dict[int, int] = {source: 0}
    frontier = [source]
    parents: Dict[int, List[Tuple[int, Dict[str, Any]]]] = {}
    shortest_depth: Optional[int] = None

    for depth in range(1, int(max_hop) + 1):
        if not frontier:
            break

        frontier_set = set(frontier)
        batch_edges = _go_edges_from(
            frontier,
            rel_filter=rel_filter,
            max_edges=max_edges,
            ignore_direction=ignore_direction,
        )
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
                    if not already and len(parent_items) < 12:
                        parent_items.append((parent, edge))

        if visited_depth.get(target) == depth:
            shortest_depth = depth
            break
        frontier = list(next_frontier)

    if shortest_depth is None:
        return []

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
    return paths[: int(candidate_limit)]


def relation_types() -> List[str]:
    now = time.time()
    if _relation_cache["data"] and (now - _relation_cache["ts"] < 600):
        return _relation_cache["data"]

    s = get_session()
    ngql = f"""
    MATCH ()-[e:{EDGE_TAG}]-()
    RETURN DISTINCT properties(e).relation AS relation
LIMIT 5000;
    """
    res = s.execute(ngql)
    if not res.is_succeeded():
        raise HTTPException(status_code=500, detail=res.error_msg())

    rels = []
    vals = res.column_values("relation")
    for v in vals:
        r = str(vw(v) or "").strip()
        if r:
            rels.append(r)

    rels = sorted(list(set(rels)))
    _relation_cache["ts"] = now
    _relation_cache["data"] = rels
    return rels


def subgraph(req: SubgraphRequest) -> Dict[str, Any]:
    s = get_session()

    root = int(req.root_vid)
    hop = max(1, min(int(req.hop or 1), 6))
    rel_filter = set([r for r in (req.relations or []) if r])

    max_nodes = int(req.max_nodes or 300)
    max_edges = int(req.max_edges or 20000)

    visited = set([root])
    frontier = [root]

    edges_all: List[Dict[str, Any]] = []
    nodes_all: List[int] = [root]

    for _ in range(hop):
        if not frontier:
            break

        id_list = ",".join(str(x) for x in frontier)
        go_ngql = f"""
        GO FROM {id_list} OVER {EDGE_TAG} BIDIRECT
        YIELD src(edge) AS src, dst(edge) AS dst,
              rank(edge) AS rank,
              properties(edge).relation AS relation,
              properties(edge).source AS esource
        | LIMIT {max_edges};
        """
        go_res = s.execute(go_ngql)
        if not go_res.is_succeeded():
            raise HTTPException(status_code=500, detail=go_res.error_msg())

        srcs = go_res.column_values("src")
        dsts = go_res.column_values("dst")
        ranks = go_res.column_values("rank")
        rels = go_res.column_values("relation")
        esources = go_res.column_values("esource")

        next_frontier = []
        for i in range(len(srcs)):
            src = int(vw(srcs[i]))
            dst = int(vw(dsts[i]))
            rank = int(vw(ranks[i]) or 0)
            rel = str(vw(rels[i]) or "")
            esrc = str(vw(esources[i]) or "")

            if rel_filter and rel not in rel_filter:
                continue

            edges_all.append(
                {
                    "source": src,
                    "target": dst,
                    "rank": str(rank),
                    "edge_type": config.EDGE_TYPE,
                    "relation": rel,
                    "source_db": esrc,
                }
            )

            if dst not in visited:
                visited.add(dst)
                next_frontier.append(dst)
                nodes_all.append(dst)

            if src not in visited:
                visited.add(src)
                next_frontier.append(src)
                nodes_all.append(src)

            if len(visited) >= max_nodes:
                pass

        frontier = list(set(next_frontier))
        if len(visited) >= max_nodes:
            break

    edges_all = uniq_edges(edges_all)

    nodes_unique = sorted(set(nodes_all))
    dropped_nodes = 0
    if len(nodes_unique) > max_nodes:
        kept_nodes, kept_edges, dropped_nodes = truncate_by_degree(
            root_vid=root,
            keep_forced=[root],
            nodes_all=nodes_unique,
            edges_all=edges_all,
            max_nodes=max_nodes,
        )
        nodes_unique = kept_nodes
        edges_all = kept_edges

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

    fres = s.execute(fetch_ngql)
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

    return {
        "root_vid": root,
        "nodes": nodes_out,
        "edges": edges_out,
        "stats": {
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
            "truncated": (dropped_nodes > 0),
            "dropped_nodes": dropped_nodes,
        },
    }


def expand(req: ExpandRequest) -> Dict[str, Any]:
    s = get_session()

    from_vid = int(req.from_vid)
    rel_filter = set([r for r in (req.relations or []) if r])
    existing = set(int(x) for x in (req.existing_node_ids or []))

    max_nodes = int(req.max_nodes or 300)
    max_edges = int(req.max_edges or 20000)

    go_ngql = f"""
    GO FROM {from_vid} OVER {EDGE_TAG} BIDIRECT
    YIELD src(edge) AS src, dst(edge) AS dst,
          rank(edge) AS rank,
          properties(edge).relation AS relation,
          properties(edge).source AS esource
    | LIMIT {max_edges};
    """
    go_res = s.execute(go_ngql)
    if not go_res.is_succeeded():
        raise HTTPException(status_code=500, detail=go_res.error_msg())

    srcs = go_res.column_values("src")
    dsts = go_res.column_values("dst")
    ranks = go_res.column_values("rank")
    rels = go_res.column_values("relation")
    esources = go_res.column_values("esource")

    edges_all = []
    cand_nodes = set(existing)
    cand_nodes.add(from_vid)

    for i in range(len(srcs)):
        src = int(vw(srcs[i]))
        dst = int(vw(dsts[i]))
        rank = int(vw(ranks[i]) or 0)
        rel = str(vw(rels[i]) or "")
        esrc = str(vw(esources[i]) or "")

        if rel_filter and rel not in rel_filter:
            continue

        edges_all.append(
            {
                "source": src,
                "target": dst,
                "rank": str(rank),
                "edge_type": config.EDGE_TYPE,
                "relation": rel,
                "source_db": esrc,
            }
        )
        cand_nodes.add(src)
        cand_nodes.add(dst)

    edges_all = uniq_edges(edges_all)

    dropped_nodes = 0
    kept_nodes = sorted(cand_nodes)
    kept_edges = edges_all

    if len(cand_nodes) > max_nodes:
        keep_forced = list(existing) + [from_vid]
        kept_nodes, kept_edges, dropped_nodes = truncate_by_degree(
            root_vid=from_vid,
            keep_forced=keep_forced,
            nodes_all=sorted(cand_nodes),
            edges_all=edges_all,
            max_nodes=max_nodes,
        )

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
        fres = s.execute(fetch_ngql)
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

    kept_edges = [e for e in kept_edges if int(e["source"]) in kept_set and int(e["target"]) in kept_set]
    new_set = set(new_node_ids)
    added_edges = [e for e in kept_edges if int(e["source"]) in new_set or int(e["target"]) in new_set]

    return {
        "added_nodes": added_nodes,
        "added_edges": added_edges,
        "stats": {
            "node_count_after": len(kept_set),
            "dropped_nodes": dropped_nodes,
            "policy": "degree",
        },
    }


def _build_multi_entity_graph(
    req: MultiEntityGraphRequest,
    choice_overrides: Optional[Dict[Tuple[int, int], int]] = None,
) -> Dict[str, Any]:
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
        raise HTTPException(status_code=400, detail="vids must contain at least 2 entities")
    if len(selected_vids) > _MAX_MULTI_VIDS:
        raise HTTPException(status_code=400, detail=f"vids exceeds max slots {_MAX_MULTI_VIDS}")

    max_nodes = max(2, min(int(req.max_nodes or 300), _MAX_MULTI_NODE_LIMIT))
    max_edges = max(1, min(int(req.max_edges or 20000), _MAX_MULTI_QUERY_EDGES))
    if len(selected_vids) > max_nodes:
        raise HTTPException(status_code=400, detail="max_nodes is smaller than selected vids count")

    raw_k = int(req.k or 2)
    if raw_k > _MAX_MULTI_HOP:
        raise HTTPException(status_code=400, detail=f"k exceeds max {_MAX_MULTI_HOP}")
    if raw_k < 1:
        raise HTTPException(status_code=400, detail="k must be >= 1")
    k = raw_k
    rel_filter = _normalize_rel_filter(req.relations or [])
    ignore_direction = bool(req.ignore_direction)
    explain_enabled = bool(req.explain_paths) and (not bool(req.direct_only))
    auto_apply_limit = 1 if int(req.per_pair_path_limit or 1) >= 1 else 0

    edge_map: Dict[Tuple[int, int, int, str, str], Dict[str, Any]] = {}
    node_ids: Set[int] = set(selected_vids)
    selected_set = set(selected_vids)
    truncated = False
    explained_pairs = 0
    path_candidates: List[Dict[str, Any]] = []
    unconnected_pairs: List[str] = []

    # direct edges among selected entities
    query_limit = min(max(max_edges, 20000), _MAX_MULTI_QUERY_EDGES)
    direct_candidates = _go_edges_from(
        selected_vids,
        rel_filter=rel_filter,
        max_edges=query_limit,
        ignore_direction=ignore_direction,
    )
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

                raw_paths = _find_shortest_path_candidates_bfs(
                    src=src,
                    dst=dst,
                    max_hop=k,
                    rel_filter=rel_filter,
                    max_edges=query_limit,
                    ignore_direction=ignore_direction,
                    candidate_limit=_PAIR_CAND_LIMIT,
                )
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
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
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
