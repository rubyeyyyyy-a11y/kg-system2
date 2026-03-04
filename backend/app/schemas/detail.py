from typing import Any, Dict, Optional

from pydantic import BaseModel


class EdgeDetailRequest(BaseModel):
    edge_type: str
    src: int
    dst: int
    rank: str


class NodeDetailResp(BaseModel):
    vid: int
    entity_name: str = ""
    entity_type: str = ""
    source: str = ""
    description: str = ""
    entity_raw_id: str = ""
    version: int = 0
    updated_at: int = 0
    updated_by: str = ""
    props: Dict[str, Any]


class EdgeDetailResp(BaseModel):
    edge_type: str
    src: int
    dst: int
    rank: str
    relation: str = ""
    source_db: Optional[str] = None
    evidence: str = ""
    version: int = 0
    updated_at: int = 0
    updated_by: str = ""
    updated: bool = False
    props: Dict[str, Any]
