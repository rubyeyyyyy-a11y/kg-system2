from typing import Any, Dict, List

from pydantic import BaseModel

from .common import GraphEdge, GraphNode


class GraphDiscoveryRequest(BaseModel):
    seed_vids: List[int] = []
    allowed_entity_types: List[str] = []
    allowed_relation_types: List[str] = []
    max_nodes: int = 300
    max_edges: int = 1200
    top_k_per_type: int = 20
    include_candidate_candidate_edges: bool = True
    include_seed_seed_edges: bool = False
    hop: int = 1


class GraphDiscoveryNode(GraphNode):
    role: str = "candidate"
    seed_support_count: int = 0
    seed_support_vids: List[int] = []
    score_breakdown: Dict[str, Any] = {}


class GraphDiscoveryEdge(GraphEdge):
    role: str = "seed_candidate"


class GraphDiscoveryEntityFacetItem(BaseModel):
    entity_type: str
    count: int
    seed_count: int = 0
    candidate_count: int = 0


class GraphDiscoveryRelationFacetItem(BaseModel):
    relation_type: str
    count: int
    seed_candidate_count: int = 0
    candidate_candidate_count: int = 0
    seed_seed_count: int = 0


class GraphDiscoveryFacets(BaseModel):
    entity_types: List[GraphDiscoveryEntityFacetItem] = []
    relation_types: List[GraphDiscoveryRelationFacetItem] = []


class GraphDiscoveryStats(BaseModel):
    seed_count: int
    candidate_count: int
    node_count: int
    edge_count: int
    truncated: bool
    dropped_nodes: int = 0
    dropped_edges: int = 0
    dropped_neighbors: int = 0
    recall_candidate_count: int = 0
    kept_candidate_count: int = 0
    budget_applied: Dict[str, Any] = {}


class GraphDiscoveryResp(BaseModel):
    nodes: List[GraphDiscoveryNode]
    edges: List[GraphDiscoveryEdge]
    facets: GraphDiscoveryFacets
    stats: GraphDiscoveryStats
