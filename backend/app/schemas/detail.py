from typing import Any, Dict, Optional

from pydantic import BaseModel


class EdgeDetailRequest(BaseModel):
    src: int
    dst: int
    relation: str
    source_db: Optional[str] = None


class NodeDetailResp(BaseModel):
    vid: int
    props: Dict[str, Any]


class EdgeDetailResp(BaseModel):
    src: int
    dst: int
    props: Dict[str, Any]
