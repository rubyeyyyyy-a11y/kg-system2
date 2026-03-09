from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from .common import GraphEdge, GraphNode


class DiscoveryEntityCandidatesRequest(BaseModel):
    q: str = ""
    page: int = 1
    page_size: int = 100
    search_in_name: bool = True
    search_in_description: bool = True
    search_in_type: bool = False
    search_in_raw_id: bool = False
    entity_type: Optional[str] = None
    source: Optional[str] = None
    entity_raw_id: Optional[str] = None
    entity_raw_id_mode: Literal["contains", "prefix", "exact"] = "contains"


class DiscoveryEntityCandidateItem(GraphNode):
    vid: int
    raw_id: str = ""
    snippet: str = ""
    description: str = ""


class DiscoveryEntityCandidatesResp(BaseModel):
    items: List[DiscoveryEntityCandidateItem]
    page: int
    page_size: int
    returned: int
    has_more: bool
    next_page: Optional[int] = None
    meta: Dict[str, Any] = {}


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
    ranking_mode: Literal["v1", "layered_multiseed"] = "v1"


class GraphDiscoveryNode(GraphNode):
    role: str = "candidate"
    layer: str = ""
    priority_score: float = 0.0
    min_seed_distance: int = 0
    bridge_seed_count: int = 0
    local_anchor_seed: Optional[int] = None
    matched_seed_pairs: List[str] = []
    seed_support_count: int = 0
    seed_support_vids: List[int] = []
    score_breakdown: Dict[str, Any] = {}


class GraphDiscoveryEdge(GraphEdge):
    role: str = "seed_candidate"
    layer: str = ""
    priority_score: float = 0.0
    seed_support_vids: List[int] = []
    path_pair: str = ""
    is_backbone: bool = False


class GraphDiscoveryEntityFacetItem(BaseModel):
    entity_type: str
    count: int
    seed_count: int = 0
    candidate_count: int = 0
    core_count: int = 0
    shared_count: int = 0
    local_count: int = 0
    supplement_count: int = 0


class GraphDiscoveryRelationFacetItem(BaseModel):
    relation_type: str
    count: int
    seed_candidate_count: int = 0
    candidate_candidate_count: int = 0
    seed_seed_count: int = 0
    core_count: int = 0
    shared_count: int = 0
    local_count: int = 0
    supplement_count: int = 0


class GraphDiscoveryQuerySummary(BaseModel):
    search_type: str = "graph_discovery"
    selected_seed_count: int = 0
    selected_seeds: List[Dict[str, Any]] = []
    total_entities: int = 0
    total_relationships: int = 0


class GraphDiscoveryLayerFacetItem(BaseModel):
    layer: str
    node_count: int = 0
    edge_count: int = 0


class GraphDiscoverySeedFacetItem(BaseModel):
    seed_vid: int
    label: str = ""
    entity_type: str = ""
    local_count: int = 0
    shared_touch_count: int = 0
    core_path_count: int = 0


class GraphDiscoveryFacets(BaseModel):
    entity_types: List[GraphDiscoveryEntityFacetItem] = []
    relation_types: List[GraphDiscoveryRelationFacetItem] = []
    query_summary: GraphDiscoveryQuerySummary = GraphDiscoveryQuerySummary()
    layers: List[GraphDiscoveryLayerFacetItem] = []
    seeds: List[GraphDiscoverySeedFacetItem] = []


class GraphDiscoveryStats(BaseModel):
    ranking_mode: str = "v1"
    seed_count: int
    seeds_count: int = 0
    candidate_count: int
    node_count: int
    edge_count: int
    final_nodes: int = 0
    final_edges: int = 0
    truncated: bool
    core_count: int = 0
    shared_count: int = 0
    local_count: int = 0
    supplement_count: int = 0
    dropped_nodes: int = 0
    dropped_edges: int = 0
    dropped_neighbors: int = 0
    dropped_by_budget: int = 0
    dropped_by_type_budget: int = 0
    dropped_generic_hubs: int = 0
    recall_candidate_count: int = 0
    kept_candidate_count: int = 0
    budget_applied: Dict[str, Any] = {}


class GraphDiscoveryResp(BaseModel):
    nodes: List[GraphDiscoveryNode]
    edges: List[GraphDiscoveryEdge]
    facets: GraphDiscoveryFacets
    stats: GraphDiscoveryStats
