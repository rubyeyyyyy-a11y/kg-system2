from __future__ import annotations

import time
from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field


SpaceStatus = Literal["provisioning", "ready", "failed"]
SpaceIndexStatusValue = Literal["verified_nonempty", "verified_empty", "verified_partial", "failed"]
SpaceGraphStatus = Literal["unavailable", "ready"]
SpaceSearchStatus = Literal["unavailable", "empty", "partial", "full", "failed"]
SpaceInternalStatus = Literal[
    "creating_space",
    "waiting_ready",
    "applying_schema",
    "initializing_metadata",
    "ready",
    "failed",
]
TemplateType = Literal["entity_rel2_default"]


class SpaceIndexStatus(BaseModel):
    status: SpaceIndexStatusValue
    doc_count: int = 0
    nebula_entity_count: Optional[int] = None
    coverage_pct: Optional[float] = None
    note: str = ""
    updated_at: Optional[str] = None


class SpaceSummary(BaseModel):
    space_name: str
    display_name: str
    description: str = ""
    template_type: TemplateType = "entity_rel2_default"
    template_version: str
    integration_scope: str
    status: SpaceStatus
    internal_status: SpaceInternalStatus
    created_by: str
    created_at: str
    ready_at: Optional[str] = None
    last_error: Optional[str] = None
    index_status: Optional[SpaceIndexStatus] = None


class SpaceReadiness(BaseModel):
    space_name: str
    graph_status: SpaceGraphStatus = "unavailable"
    search_status: SpaceSearchStatus = "unavailable"
    coverage_pct: Optional[float] = None
    index_status: Optional[SpaceIndexStatus] = None


class SpaceRegistry(BaseModel):
    format_version: str = "spaces-v1"
    updated_at: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    spaces: Dict[str, SpaceSummary] = Field(default_factory=dict)
