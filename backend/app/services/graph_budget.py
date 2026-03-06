import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(raw)
    except ValueError:
        return int(default)


@dataclass(frozen=True)
class GraphQueryBudget:
    relation_filter_max: int

    subgraph_hop_max: int
    subgraph_max_nodes_cap: int
    subgraph_max_edges_cap: int
    subgraph_frontier_cap: int
    subgraph_per_root_neighbor_cap: int
    subgraph_query_edge_scan_cap: int

    expand_existing_node_cap: int
    expand_max_nodes_cap: int
    expand_max_edges_cap: int
    expand_per_root_neighbor_cap: int
    expand_query_edge_scan_cap: int

    multi_root_cap: int
    multi_k_max: int
    multi_max_nodes_cap: int
    multi_max_edges_cap: int
    multi_pair_candidate_cap: int
    multi_per_root_neighbor_cap: int
    multi_query_edge_scan_cap: int


graph_budget = GraphQueryBudget(
    relation_filter_max=max(1, min(_env_int("GRAPH_REL_FILTER_MAX", 120), 500)),
    subgraph_hop_max=max(1, min(_env_int("GRAPH_SUBGRAPH_HOP_MAX", 3), 6)),
    subgraph_max_nodes_cap=max(20, min(_env_int("GRAPH_SUBGRAPH_MAX_NODES_CAP", 300), 3000)),
    subgraph_max_edges_cap=max(20, min(_env_int("GRAPH_SUBGRAPH_MAX_EDGES_CAP", 1200), 10000)),
    subgraph_frontier_cap=max(1, min(_env_int("GRAPH_SUBGRAPH_FRONTIER_CAP", 200), 2000)),
    subgraph_per_root_neighbor_cap=max(1, min(_env_int("GRAPH_SUBGRAPH_PER_ROOT_NEIGHBOR_CAP", 120), 2000)),
    subgraph_query_edge_scan_cap=max(100, min(_env_int("GRAPH_SUBGRAPH_QUERY_EDGE_SCAN_CAP", 50000), 200000)),
    expand_existing_node_cap=max(1, min(_env_int("GRAPH_EXPAND_EXISTING_NODE_CAP", 2000), 20000)),
    expand_max_nodes_cap=max(20, min(_env_int("GRAPH_EXPAND_MAX_NODES_CAP", 300), 3000)),
    expand_max_edges_cap=max(20, min(_env_int("GRAPH_EXPAND_MAX_EDGES_CAP", 1200), 10000)),
    expand_per_root_neighbor_cap=max(1, min(_env_int("GRAPH_EXPAND_PER_ROOT_NEIGHBOR_CAP", 200), 5000)),
    expand_query_edge_scan_cap=max(100, min(_env_int("GRAPH_EXPAND_QUERY_EDGE_SCAN_CAP", 50000), 200000)),
    multi_root_cap=max(2, min(_env_int("GRAPH_MULTI_ROOT_CAP", 8), 16)),
    multi_k_max=max(1, min(_env_int("GRAPH_MULTI_K_MAX", 3), 4)),
    multi_max_nodes_cap=max(20, min(_env_int("GRAPH_MULTI_MAX_NODES_CAP", 600), 5000)),
    multi_max_edges_cap=max(20, min(_env_int("GRAPH_MULTI_MAX_EDGES_CAP", 2500), 20000)),
    multi_pair_candidate_cap=max(1, min(_env_int("GRAPH_MULTI_PAIR_CANDIDATE_CAP", 3), 10)),
    multi_per_root_neighbor_cap=max(1, min(_env_int("GRAPH_MULTI_PER_ROOT_NEIGHBOR_CAP", 120), 2000)),
    multi_query_edge_scan_cap=max(100, min(_env_int("GRAPH_MULTI_QUERY_EDGE_SCAN_CAP", 60000), 200000)),
)
