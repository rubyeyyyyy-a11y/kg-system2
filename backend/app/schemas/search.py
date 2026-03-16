from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from .spaces import SpaceMetaResp

from .common import GraphEdge, GraphNode


class SearchRequest(BaseModel):
    q: str
    search_in_name: bool = True
    search_in_description: bool = False
    search_in_type: bool = False
    search_in_raw_id: bool = False
    include_edges: bool = False
    entity_type: Optional[str] = None
    source: Optional[str] = None
    entity_raw_id: Optional[str] = None
    entity_raw_id_mode: Literal["contains", "prefix", "exact"] = "contains"


class SearchResp(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_candidates: int
    truncated: bool = False
    meta: Dict[str, Any] = Field(default_factory=dict)
    space_meta: SpaceMetaResp


class SuggestItem(BaseModel):
    vid: int
    label: str
    entity_type: str = ""
    source: str = ""
    score: Optional[float] = None


class SuggestResp(BaseModel):
    q: str
    items: List[SuggestItem]
    truncated: bool
    space_meta: SpaceMetaResp


class EntityTypeItem(BaseModel):
    entity_type: str
    count: int


class RawIdSuggestItem(BaseModel):
    vid: int
    entity_raw_id: str
    label: str = ""
    entity_type: str = ""
    source: str = ""


class RawIdSuggestResp(BaseModel):
    q: str
    items: List[RawIdSuggestItem]
    truncated: bool
    space_meta: SpaceMetaResp
