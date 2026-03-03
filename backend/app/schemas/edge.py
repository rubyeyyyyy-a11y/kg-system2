from typing import List, Optional

from pydantic import BaseModel


class EdgeSuggestItem(BaseModel):
    src: int
    dst: int
    rank: str = "0"
    relation: str
    source_db: str = ""
    score: Optional[float] = None
    src_label: str = ""
    dst_label: str = ""


class EdgeSuggestResp(BaseModel):
    q: str
    items: List[EdgeSuggestItem]
    truncated: bool


class EdgeSearchRequest(BaseModel):
    q: str
    search_in_relation: bool = True
    search_in_props: bool = True
    source_db: Optional[str] = None
    relation: Optional[str] = None
    limit: int = 100


class EdgeSearchItem(BaseModel):
    src: int
    dst: int
    rank: str = "0"
    relation: str
    source_db: str = ""
    score: Optional[float] = None
    src_label: str = ""
    dst_label: str = ""
    snippet: str = ""


class EdgeSearchResp(BaseModel):
    edges: List[EdgeSearchItem]
    total_candidates: int
