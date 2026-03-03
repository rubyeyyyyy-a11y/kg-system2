from typing import List, Literal, Optional

from pydantic import BaseModel

from .common import GraphEdge, GraphNode


class SearchRequest(BaseModel):
    q: str
    search_in_name: bool = True
    search_in_description: bool = True
    search_in_type: bool = False
    search_in_raw_id: bool = False
    entity_type: Optional[str] = None
    source: Optional[str] = None
    entity_raw_id: Optional[str] = None
    entity_raw_id_mode: Literal["contains", "prefix", "exact"] = "contains"


class SearchResp(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_candidates: int


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
