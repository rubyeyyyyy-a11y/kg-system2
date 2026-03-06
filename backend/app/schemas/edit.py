from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class EditableFieldItem(BaseModel):
    name: str
    type: Literal["string"] = "string"
    maxLen: int
    multiline: bool = False
    required: bool = False


class EditableFieldGroup(BaseModel):
    fields: List[EditableFieldItem]


class EditableFieldsResp(BaseModel):
    entity: EditableFieldGroup
    edge: EditableFieldGroup
    forbidden_fields: List[str]


class NodePatchRequest(BaseModel):
    set: Dict[str, Any] = Field(default_factory=dict)
    expected_version: int
    updated_by: str


class NodePatchResp(BaseModel):
    vid: int
    updated: Dict[str, Any]
    version: int
    updated_at: int
    updated_by: str


class EdgePatchRequest(BaseModel):
    edge_type: Optional[str] = None
    src: int
    dst: int
    rank: Union[str, int]
    set: Dict[str, Any] = Field(default_factory=dict)
    expected_version: int
    updated_by: str


class EdgeIdentity(BaseModel):
    src: int
    dst: int
    rank: str
    edge_type: str


class EdgePatchResp(BaseModel):
    identity: EdgeIdentity
    updated: Dict[str, Any]
    version: int
    updated_at: int
    updated_by: str
