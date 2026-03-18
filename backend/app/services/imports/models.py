import time
import uuid
from urllib.parse import quote
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
ImportBatchSourceType = Literal["import_ui", "team_ingestion"]
ImportBatchStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed_import",
    "failed_postprocess",
    "cancelled",
]
ImportBatchCleanupStatus = Literal[
    "not_requested",
    "queued",
    "running",
    "succeeded",
    "partial_succeeded",
    "failed",
    "not_supported",
]
ImportBatchItemType = Literal["entity", "relation"]
CleanupJobScope = Literal["full_batch", "relations_only"]
CleanupJobStatus = Literal["queued", "running", "succeeded", "partial_succeeded", "failed"]
CleanupConflictSource = Literal["ledger", "live_graph"]
CleanupJobPhase = Literal[
    "planning",
    "deleting_relations",
    "deleting_entities",
    "deleting_es_docs",
    "refreshing_metadata",
    "reconciling",
    "verifying",
    "completed",
    "failed",
]

IDENTITY_FIELDS = {"ID", "srcVID", "dstVID", "rank"}


def _ts() -> int:
    return int(time.time())


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def build_import_batch_item_key(
    *,
    item_type: str,
    vid: int | None = None,
    src_vid: int | None = None,
    dst_vid: int | None = None,
    relation: str | None = None,
    rank: int | None = None,
    edge_type: str | None = None,
) -> str:
    if item_type == "entity":
        return f"entity:{int(vid or 0)}"
    relation_name = quote(str(relation or ""), safe="")
    return (
        f"relation:{str(edge_type or 'REL2')}:{int(src_vid or 0)}:{int(dst_vid or 0)}:"
        f"{relation_name}:{int(rank or 0)}"
    )


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
    default_edge_kind: Optional[str] = None


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
    source_column: str = ""
    target_field: str
    logical_field: Optional[str] = None
    default_value: Optional[str] = None


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


class ImportBatchRecord(BaseModel):
    batch_id: str
    space_id: str
    source_type: ImportBatchSourceType = "import_ui"
    created_at: int = Field(default_factory=_ts)
    updated_at: int = Field(default_factory=_ts)
    is_test_data: bool = True
    draft_id: str
    job_id: str
    submission_id: Optional[str] = None
    status: ImportBatchStatus = "queued"
    entity_count: int = 0
    relation_count: int = 0
    searchable: Optional[bool] = None
    cleanup_status: ImportBatchCleanupStatus = "not_requested"
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    ledger_summary: Dict[str, Any] = Field(default_factory=dict)
    warning_messages: List[str] = Field(default_factory=list)


class ImportBatchItemRecord(BaseModel):
    item_id: str = Field(default_factory=lambda: _new_id("batch_item"))
    batch_id: str
    space_id: str
    job_id: str
    created_at: int = Field(default_factory=_ts)
    item_type: ImportBatchItemType
    created_by_batch: bool = True
    vid: Optional[int] = None
    entity_raw_id: Optional[str] = None
    entity_name: Optional[str] = None
    src_vid: Optional[int] = None
    dst_vid: Optional[int] = None
    relation: Optional[str] = None
    rank: Optional[int] = None
    edge_type: Optional[str] = None
    row_index: Optional[int] = None
    item_key: Optional[str] = None

    @model_validator(mode="after")
    def _populate_item_key(self):
        self.item_key = str(
            self.item_key
            or build_import_batch_item_key(
                item_type=self.item_type,
                vid=self.vid,
                src_vid=self.src_vid,
                dst_vid=self.dst_vid,
                relation=self.relation,
                rank=self.rank,
                edge_type=self.edge_type,
            )
        )
        return self


class CleanupJobPhaseRecord(BaseModel):
    phase: CleanupJobPhase
    at: int = Field(default_factory=_ts)


class CleanupJobArtifactRecord(BaseModel):
    kind: Literal[
        "summary",
        "conflicts",
        "skipped_entities",
        "skipped_relations",
        "verify_summary",
        "plan_summary",
        "blocked_entities",
        "deletable_entities",
        "deletable_relations",
    ]
    filename: str
    path: str


class CleanupConflictRecord(BaseModel):
    vid: Optional[int] = None
    item_type: ImportBatchItemType = "entity"
    source: CleanupConflictSource = "ledger"
    reason: str
    blocking_batch_ids: List[str] = Field(default_factory=list)
    blocking_relations: int = 0
    details: Dict[str, Any] = Field(default_factory=dict)


class CleanupPlanSummary(BaseModel):
    requested_entity_count: int = 0
    requested_relation_count: int = 0
    ledger_blocked_entity_count: int = 0
    live_graph_blocked_entity_count: int = 0
    blocked_entity_count: int = 0
    deletable_entity_count: int = 0
    deletable_relation_count: int = 0
    conflict_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    verification_scope_note: str = ""
    generated_at: int = Field(default_factory=_ts)


class CleanupBlockedEntityRecord(BaseModel):
    vid: Optional[int] = None
    entity_name: Optional[str] = None
    entity_raw_id: Optional[str] = None
    item_key: Optional[str] = None
    conflict_sources: List[CleanupConflictSource] = Field(default_factory=list)
    conflicts: List[CleanupConflictRecord] = Field(default_factory=list)


class CleanupDeletableEntityRecord(BaseModel):
    vid: Optional[int] = None
    entity_name: Optional[str] = None
    entity_raw_id: Optional[str] = None
    item_key: Optional[str] = None


class CleanupDeletableRelationRecord(BaseModel):
    edge_type: Optional[str] = None
    src_vid: Optional[int] = None
    dst_vid: Optional[int] = None
    rank: Optional[int] = None
    relation: Optional[str] = None
    item_key: Optional[str] = None


class CleanupJobRecord(BaseModel):
    cleanup_job_id: str
    space_id: str
    batch_ids: List[str] = Field(default_factory=list)
    scope: CleanupJobScope = "full_batch"
    created_by: str = "cleanup_job"
    created_at: int = Field(default_factory=_ts)
    updated_at: int = Field(default_factory=_ts)
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    status: CleanupJobStatus = "queued"
    phase: CleanupJobPhase = "planning"
    final_phase: Optional[CleanupJobPhase] = None
    phase_history: List[CleanupJobPhaseRecord] = Field(default_factory=lambda: [CleanupJobPhaseRecord(phase="planning")])
    requested_relation_count: int = 0
    requested_entity_count: int = 0
    deleted_relation_count: int = 0
    deleted_entity_count: int = 0
    skipped_relation_count: int = 0
    skipped_entity_count: int = 0
    deduplicated_relation_count: int = 0
    deduplicated_entity_count: int = 0
    conflict_count: int = 0
    warning_messages: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None
    failure_phase: Optional[str] = None
    failure_kind: Optional[str] = None
    failure_detail: Dict[str, Any] = Field(default_factory=dict)
    duration_ms: Optional[int] = None
    request_key: Optional[str] = None
    conflicts: List[CleanupConflictRecord] = Field(default_factory=list)
    plan_summary: CleanupPlanSummary = Field(default_factory=CleanupPlanSummary)
    has_plan_artifacts: bool = False
    verify_summary: Dict[str, Any] = Field(default_factory=dict)
    metadata_summary: Dict[str, Any] = Field(default_factory=dict)
    reconcile_summary: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[CleanupJobArtifactRecord] = Field(default_factory=list)


class ImportJobState(BaseModel):
    job_id: str
    format_version: str = "imports-v2"
    draft_id: str
    batch_id: str = ""
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
        if "batch_id" not in merged:
            merged["batch_id"] = ""
        return merged
