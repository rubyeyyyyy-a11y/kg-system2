from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from .common import GraphEdge, GraphNode


class SubgraphRequest(BaseModel):
    root_vid: int
    hop: int = 1
    relations: List[str] = []
    max_nodes: int = 300
    max_edges: int = 20000


class ExpandRequest(BaseModel):
    from_vid: int
    relations: List[str] = []
    existing_node_ids: List[int] = []
    max_nodes: int = 300
    max_edges: int = 20000


class SubgraphStats(BaseModel):
    node_count: int
    edge_count: int
    truncated: bool
    dropped_nodes: int
    dropped_edges: int = 0
    dropped_neighbors: int = 0
    budget_applied: Dict[str, Any] = {}


class SubgraphResp(BaseModel):
    root_vid: int
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    stats: SubgraphStats


class ExpandStats(BaseModel):
    node_count_after: int
    edge_count_after: int = 0
    added_nodes: int = 0
    added_edges: int = 0
    truncated: bool = False
    dropped_nodes: int
    dropped_edges: int = 0
    dropped_neighbors: int = 0
    policy: str
    budget_applied: Dict[str, Any] = {}


class ExpandResp(BaseModel):
    added_nodes: List[GraphNode]
    added_edges: List[GraphEdge]
    stats: ExpandStats


class RelationTypeItem(BaseModel):
    relation_type: str
    count: int


class RelationTypesResp(BaseModel):
    items: List[RelationTypeItem]
    q: str = ""
    limit: int
    offset: int
    next_offset: Optional[int] = None
    has_more: bool = False
    matched_total: int = 0


class MultiEntityGraphRequest(BaseModel):
    vids: List[int] = []
    direct_only: bool = True
    explain_paths: bool = False
    k: int = 2
    relations: List[str] = []
    max_nodes: int = 300
    max_edges: int = 20000
    per_pair_path_limit: int = 1
    ignore_direction: bool = True


class MultiEntityEdge(GraphEdge):
    is_explain: bool = False


class MultiEntityStats(BaseModel):
    selected: int
    direct_edges: int
    explained_pairs: int
    unconnected: List[int]
    unconnected_pairs: List[str] = []
    truncated: bool
    dropped_nodes: int = 0
    dropped_edges: int = 0
    dropped_neighbors: int = 0
    node_count: int
    edge_count: int
    budget_applied: Dict[str, Any] = {}


class PathEdgeBrief(GraphEdge):
    pass


class PathCandidate(BaseModel):
    path_id: str
    length: int
    nodes: List[int]
    edges: List[PathEdgeBrief]
    score: float = 1.0
    summary: str = ""


class PairPathCandidates(BaseModel):
    u: int
    v: int
    has_direct: bool = False
    chosen_index: Optional[int] = None
    candidates: List[PathCandidate] = []


class MultiEntityGraphResp(BaseModel):
    nodes: List[GraphNode]
    edges: List[MultiEntityEdge]
    stats: MultiEntityStats
    path_candidates: List[PairPathCandidates] = []


class PairPathChoice(BaseModel):
    u: int
    v: int
    chosen_index: int


class MultiEntityGraphApplyPathsRequest(BaseModel):
    base_request: MultiEntityGraphRequest
    choices: List[PairPathChoice] = []
