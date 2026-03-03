from typing import Any, Dict, Optional

from pydantic import BaseModel


class EdgeDetailRequest(BaseModel):
    src: int
    dst: int
    rank: str


class NodeDetailResp(BaseModel):
    vid: int
    props: Dict[str, Any]


class EdgeDetailResp(BaseModel):
    src: int
    dst: int
    rank: str
    relation: str = ""
    source_db: Optional[str] = None
    updated: bool = False
    props: Dict[str, Any]


class EdgeUpdateRequest(BaseModel):
    src: int
    dst: int
    rank: str
    props: Dict[str, Any]
