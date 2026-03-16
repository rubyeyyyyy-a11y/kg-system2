from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SpaceIndexStatusResp(BaseModel):
    status: Literal["verified_nonempty", "verified_empty", "verified_partial", "failed"]
    doc_count: int = 0
    nebula_entity_count: Optional[int] = None
    coverage_pct: Optional[float] = None
    note: str = ""
    updated_at: Optional[str] = None


class SpaceMetaResp(BaseModel):
    space_name: str
    graph_status: Literal["unavailable", "ready"]
    search_status: Literal["unavailable", "empty", "partial", "full", "failed"]
    coverage_pct: Optional[float] = None
    index_status: Optional[SpaceIndexStatusResp] = None


class SpaceSummaryResp(BaseModel):
    space_name: str
    display_name: str
    description: str = ""
    template_type: Literal["entity_rel2_default"]
    template_version: str
    integration_scope: str
    status: Literal["provisioning", "ready", "failed"]
    internal_status: str
    created_by: str
    created_at: str
    ready_at: Optional[str] = None
    last_error: Optional[str] = None
    graph_status: Literal["unavailable", "ready"]
    search_status: Literal["unavailable", "empty", "partial", "full", "failed"]
    coverage_pct: Optional[float] = None
    index_status: Optional[SpaceIndexStatusResp] = None


class CurrentSpaceResp(BaseModel):
    space_name: str
    source: Literal["header", "default"]
    header_present: bool
    header_value: Optional[str] = None
    registry_status: Optional[str] = None
    graph_status: Literal["unavailable", "ready"]
    search_status: Literal["unavailable", "empty", "partial", "full", "failed"]
    coverage_pct: Optional[float] = None
    index_status: Optional[SpaceIndexStatusResp] = None


class CreateSpaceRequest(BaseModel):
    space_name: str
    display_name: str
    description: str = ""
    template_type: Literal["entity_rel2_default"] = "entity_rel2_default"
    created_by: str


class CreateSpaceResp(BaseModel):
    space: SpaceSummaryResp
    status: Literal["provisioning", "ready", "failed"]
    integration_scope: str
    warnings: list[str] = Field(default_factory=list)
