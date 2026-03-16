import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from app.services.spaces.models import SpaceIndexStatus

ImportMode = Literal["vertex", "edge", "mixed"]
SourceKind = Literal["vertex", "edge", "mixed", "unknown"]
DraftLifecycle = Literal["files_uploaded", "preview_ready", "mapped", "validated"]
JobStatus = Literal[
    "queued",
    "running",
    "post_metadata_refresh",
    "post_es_sync",
    "post_verify_index",
    "succeeded",
    "failed_import",
    "failed_postprocess",
    "cancelled",
]
JobFailureStage = Literal[
    "metadata_failed",
    "es_sync_failed",
    "verify_failed",
    "registry_write_failed",
    "interrupted",
    "cancelled",
]
IntegrationLevel = Literal["fully_integrated", "import_only", "partially_integrated"]
ObjectType = Literal["tag", "edge_type"]

IDENTITY_FIELDS = {"ID", "srcVID", "dstVID", "rank"}


def _ts() -> int:
    return int(time.time())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _merge_field_mappings(
    identity_mapping: dict[str, Any] | None,
    property_mappings: list[dict[str, Any]] | None,
    field_mappings: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    identity = {
        key: value
        for key, value in dict(identity_mapping or {}).items()
        if value not in {None, ""}
    }
    properties = list(property_mappings or [])
    if identity or properties or not field_mappings:
        return identity, properties
    for item in field_mappings:
        source_column = str(item.get("source_column") or "").strip()
        target_field = str(item.get("target_field") or "").strip()
        if not source_column or not target_field:
            continue
        if target_field == "ID":
            identity["id_column"] = source_column
        elif target_field == "srcVID":
            identity["src_column"] = source_column
        elif target_field == "dstVID":
            identity["dst_column"] = source_column
        elif target_field == "rank":
            identity["rank_column"] = source_column
        else:
            properties.append({"source_column": source_column, "target_field": target_field})
    return identity, properties


class ImportFileRecord(BaseModel):
    file_id: str
    original_name: str
    size_bytes: int
    detected_delimiter: str = ","
    detected_encoding: str = "utf-8"
    row_count: int = 0
    row_count_pending: bool = True
    format_version: str = "imports-v2"
    created_at: int = Field(default_factory=_ts)


class SchemaProperty(BaseModel):
    name: str
    type: str
    nullable: bool = True


class SchemaObject(BaseModel):
    object_type: ObjectType
    name: str
    exists: bool = True
    properties: List[SchemaProperty] = Field(default_factory=list)


class SourceAliasHint(BaseModel):
    source_column: str
    logical_field: str


class DraftSource(BaseModel):
    source_id: str
    file_id: str
    filename: str
    columns: List[str] = Field(default_factory=list)
    sample_rows: List[Dict[str, str]] = Field(default_factory=list)
    header_hash: str = ""
    inferred_kind: SourceKind = "unknown"
    warnings: List[str] = Field(default_factory=list)
    alias_hints: List[SourceAliasHint] = Field(default_factory=list)
    recommended_object_type: Optional[ObjectType] = None


class FieldMapping(BaseModel):
    source_column: str
    target_field: str


class IdentityMapping(BaseModel):
    id_column: Optional[str] = None
    src_column: Optional[str] = None
    dst_column: Optional[str] = None
    rank_column: Optional[str] = None

    def mapped_columns(self) -> List[str]:
        return [item for item in [self.id_column, self.src_column, self.dst_column, self.rank_column] if item]


class PropertyMapping(BaseModel):
    source_column: str
    target_field: str
    logical_field: Optional[str] = None


class RowSelector(BaseModel):
    column: str
    equals: str


class ImportTargetConfig(BaseModel):
    target_id: str = Field(default_factory=lambda: _new_id("target"))
    object_type: ObjectType
    object_name: str
    source_id: str = ""
    identity_mapping: IdentityMapping = Field(default_factory=IdentityMapping)
    property_mappings: List[PropertyMapping] = Field(default_factory=list)
    row_selector: Optional[RowSelector] = None
    target_options: Dict[str, Any] = Field(default_factory=dict)
    field_mappings: List[FieldMapping] = Field(default_factory=list, exclude=True)
    discriminator_value: Optional[str] = Field(default=None, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _compat_from_legacy(cls, data: Any):
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        identity_mapping, property_mappings = _merge_field_mappings(
            merged.get("identity_mapping"),
            merged.get("property_mappings"),
            merged.get("field_mappings"),
        )
        merged["identity_mapping"] = identity_mapping
        merged["property_mappings"] = property_mappings
        if not merged.get("target_id"):
            merged["target_id"] = _new_id("target")
        return merged


class UpdateStrategy(BaseModel):
    mode: Literal["merge_partial"] = "merge_partial"
    create_if_missing: bool = True
    update_existing: bool = True


class SchemaOptions(BaseModel):
    allow_create_object: bool = True
    allow_add_properties: bool = True


class PostprocessOptions(BaseModel):
    refresh_metadata: bool = True
    sync_entity_es: bool = True


class SchemaPropertyPlan(BaseModel):
    name: str
    type: str
    exists: bool
    source_column: Optional[str] = None


class SchemaObjectPlan(BaseModel):
    target_id: str = ""
    source_id: str = ""
    object_type: ObjectType
    object_name: str
    object_exists: bool
    add_object: bool = False
    add_properties: List[SchemaPropertyPlan] = Field(default_factory=list)
    ignored_columns: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)


class CompiledTargetPlan(BaseModel):
    target_id: str
    object_type: ObjectType
    object_name: str
    source_id: str = ""
    source_file_id: str = ""
    source_filename: str = ""
    source_columns: List[str] = Field(default_factory=list)
    inferred_source_kind: SourceKind = "unknown"
    identity_mapping: IdentityMapping = Field(default_factory=IdentityMapping)
    property_mappings: List[PropertyMapping] = Field(default_factory=list)
    row_selector: Optional[RowSelector] = None
    property_types: Dict[str, str] = Field(default_factory=dict)
    identity_fields: List[str] = Field(default_factory=list)
    update_fields: List[str] = Field(default_factory=list)
    create_fields: List[str] = Field(default_factory=list)
    integration_level: IntegrationLevel = "import_only"
    warnings: List[str] = Field(default_factory=list)
    field_mappings: Dict[str, str] = Field(default_factory=dict, exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _compat_field_map(cls, data: Any):
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        identity_mapping, property_mappings = _merge_field_mappings(
            merged.get("identity_mapping"),
            merged.get("property_mappings"),
            [
                {"source_column": source_column, "target_field": target_field}
                for source_column, target_field in dict(merged.get("field_mappings") or {}).items()
            ],
        )
        merged["identity_mapping"] = identity_mapping
        merged["property_mappings"] = property_mappings
        if not merged.get("target_id"):
            merged["target_id"] = _new_id("target")
        return merged


class CompiledImportPlan(BaseModel):
    plan_id: str
    format_version: str = "imports-v2"
    space_name: str = ""
    template_type: str = "entity_rel2_default"
    integration_scope: str = "entity_rel2_core"
    workspace_mode: ImportMode = "vertex"
    mode: Optional[ImportMode] = None
    file_ids: List[str] = Field(default_factory=list)
    sources: List[DraftSource] = Field(default_factory=list)
    targets: List[CompiledTargetPlan] = Field(default_factory=list)
    schema_create_plan: List[SchemaObjectPlan] = Field(default_factory=list)
    update_strategy: UpdateStrategy = Field(default_factory=UpdateStrategy)
    rank_generation_strategy: Literal["preserve_input", "system_generated"] = "preserve_input"
    postprocess_options: PostprocessOptions = Field(default_factory=PostprocessOptions)
    warnings: List[str] = Field(default_factory=list)
    integration_level: IntegrationLevel = "import_only"
    compiled_at: int = Field(default_factory=_ts)

    @model_validator(mode="before")
    @classmethod
    def _compat_mode(cls, data: Any):
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        if "workspace_mode" not in merged and "mode" in merged:
            merged["workspace_mode"] = merged.get("mode")
        if "mode" not in merged and "workspace_mode" in merged:
            merged["mode"] = merged.get("workspace_mode")
        return merged


class TargetValidationResult(BaseModel):
    target_id: str
    source_id: str
    object_type: ObjectType
    object_name: str
    source_columns: List[str] = Field(default_factory=list)
    passed: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    hints: List[str] = Field(default_factory=list)
    scanned_rows: int = 0
    error_rows: int = 0


class DraftValidationResult(BaseModel):
    passed: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)
    semantic_notes: List[str] = Field(default_factory=list)
    scanned_rows: int = 0
    error_rows: int = 0
    errors_truncated: bool = False
    target_results: List[TargetValidationResult] = Field(default_factory=list)
    compiled_plan: Optional[CompiledImportPlan] = None
    validated_at: int = Field(default_factory=_ts)


class ImportDraft(BaseModel):
    draft_id: str
    format_version: str = "imports-v2"
    space_name: str = ""
    status: DraftLifecycle
    workspace_mode: ImportMode = "vertex"
    mode: Optional[ImportMode] = None
    file_ids: List[str] = Field(default_factory=list)
    sources: List[DraftSource] = Field(default_factory=list)
    mapping: List[ImportTargetConfig] = Field(default_factory=list)
    update_strategy: UpdateStrategy = Field(default_factory=UpdateStrategy)
    schema_options: SchemaOptions = Field(default_factory=SchemaOptions)
    postprocess_options: PostprocessOptions = Field(default_factory=PostprocessOptions)
    created_at: int = Field(default_factory=_ts)
    updated_at: int = Field(default_factory=_ts)
    validation: Optional[DraftValidationResult] = None

    @model_validator(mode="before")
    @classmethod
    def _compat_mode(cls, data: Any):
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        if "workspace_mode" not in merged and "mode" in merged:
            merged["workspace_mode"] = merged.get("mode")
        if "mode" not in merged and "workspace_mode" in merged:
            merged["mode"] = merged.get("workspace_mode")
        return merged


class JobEvent(BaseModel):
    event_type: str = "job_event"
    ts: int = Field(default_factory=_ts)
    level: Literal["info", "warn", "error"] = "info"
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)


class ImportCompletionSummary(BaseModel):
    nebula_write_success: bool = False
    post_es_sync_success: bool = False
    verify_success: bool = False
    registry_index_status_written: bool = False
    imported_docs_visible: bool = False
    searchable: bool = False
    affected_entity_count: int = 0
    search_status: Optional[str] = None
    index_status: Optional[str] = None
    coverage_pct: Optional[float] = None
    note: str = ""
    completed_at: Optional[str] = None
    failure_stage: Optional[JobFailureStage] = None


class JobArtifact(BaseModel):
    target_id: str
    source_id: str
    kind: Literal["normalized_rows", "failed_rows", "summary"]
    filename: str
    path: str


class ImportJobState(BaseModel):
    job_id: str
    format_version: str = "imports-v2"
    draft_id: str
    space_name: str = ""
    template_type: str = "entity_rel2_default"
    status: JobStatus
    created_by: str
    workspace_mode: ImportMode = "vertex"
    mode: Optional[ImportMode] = None
    plan_id: str
    file_ids: List[str] = Field(default_factory=list)
    sources: List[DraftSource] = Field(default_factory=list)
    targets: List[CompiledTargetPlan] = Field(default_factory=list)
    compiled_plan_path: str
    artifacts: List[JobArtifact] = Field(default_factory=list)
    failed_rows_path: Optional[str] = None
    normalized_rows_path: Optional[str] = None
    created_at: int = Field(default_factory=_ts)
    updated_at: int = Field(default_factory=_ts)
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    cancel_requested: bool = False
    total_rows: int = 0
    processed_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    warnings: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)
    integration_level: IntegrationLevel = "import_only"
    error_message: Optional[str] = None
    failure_stage: Optional[JobFailureStage] = None
    interrupted: bool = False
    metadata_refreshed: bool = False
    es_sync_skipped: bool = False
    failed_rows_truncated: bool = False
    cancel_effective_at_batch: bool = False
    affected_entity_vids: List[int] = Field(default_factory=list)
    affected_schema_objects: List[str] = Field(default_factory=list)
    index_status_snapshot: Optional[SpaceIndexStatus] = None
    completion_summary: Optional[ImportCompletionSummary] = None

    @model_validator(mode="before")
    @classmethod
    def _compat_mode(cls, data: Any):
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        if "workspace_mode" not in merged and "mode" in merged:
            merged["workspace_mode"] = merged.get("mode")
        if "mode" not in merged and "workspace_mode" in merged:
            merged["mode"] = merged.get("workspace_mode")
        return merged
