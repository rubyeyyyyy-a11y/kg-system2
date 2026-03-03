from typing import Optional

from pydantic import BaseModel


class GraphEdge(BaseModel):
    source: int
    target: int
    relation: str = ""
    source_db: str = ""


class GraphNode(BaseModel):
    id: int
    label: str
    entity_type: str = ""
    raw_id: str = ""
    source: str = ""
    score: Optional[float] = None
    snippet: str = ""
