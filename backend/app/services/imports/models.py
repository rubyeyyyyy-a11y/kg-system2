import time
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

"""Internal runtime and persistence models for imports v1.

These models are the source of truth for on-disk JSON payloads under `.run/import-*`.
Field names are intentionally stable for v1 contract freeze; additive fields are preferred
over renames to preserve compatibility with existing snapshots and tests.
"""


ImportMode = Literal["vertex", "edge", "mixed"]
DraftLifecycle = Literal["files_uploaded", "preview_ready", "mapped", "validated"]
JobStatus = Literal[
    "queued",
    "running",
    "post_metadata_refresh",
    "post_es_sync",
    "succeeded",
    "failed_import",
    "failed_postprocess",
    "cancelled",
]
IntegrationLevel = Literal["fully_integrated", "import_only", "partially_integrated"]
ObjectType = Literal["tag", "edge_type"]


class ImportFileRecord(BaseModel):
    """Metadata for one uploaded staging CSV file."""

    file_id: str
    original_name: str
    size_bytes: int
    detected_delimiter: str = ","
    detected_encoding: str = "utf-8"
    row_count: int = 0
    format_version: str = "imports-v1"
    created_at: int = Field(default_factory=lambda: int(time.time()))


class SchemaProperty(BaseModel):
    name: str
    type: str
    nullable: bool = True


class SchemaObject(BaseModel):
    object_type: ObjectType
    name: str
    exists: bool = True
    properties: List[SchemaProperty] = Field(default_factory=list)


class FieldMapping(BaseModel):
    source_column: str
    target_field: str


class ImportTargetConfig(BaseModel):
    object_type: ObjectType
    object_name: str
    discriminator_value: Optional[str] = None
    field_mappings: List[FieldMapping] = Field(default_factory=list)


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
    object_type: ObjectType
    object_name: str
    object_exists: bool
    add_object: bool = False
    add_properties: List[SchemaPropertyPlan] = Field(default_factory=list)
    ignored_columns: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)


class CompiledTargetPlan(BaseModel):
    object_type: ObjectType
    object_name: str
    discriminator_value: Optional[str] = None
    field_mappings: Dict[str, str] = Field(default_factory=dict)
    property_types: Dict[str, str] = Field(default_factory=dict)
    identity_fields: List[str] = Field(default_factory=list)
    update_fields: List[str] = Field(default_factory=list)
    create_fields: List[str] = Field(default_factory=list)
    integration_level: IntegrationLevel = "import_only"
    warnings: List[str] = Field(default_factory=list)


class CompiledImportPlan(BaseModel):
    """Frozen execution plan consumed by jobs; the executor must not read mutable draft state."""

    plan_id: str
    format_version: str = "imports-v1"
    mode: ImportMode
    file_ids: List[str] = Field(default_factory=list)
    discriminator_column: Optional[str] = None
    targets: List[CompiledTargetPlan] = Field(default_factory=list)
    schema_create_plan: List[SchemaObjectPlan] = Field(default_factory=list)
    update_strategy: UpdateStrategy = Field(default_factory=UpdateStrategy)
    rank_generation_strategy: Literal["preserve_input", "system_generated"] = "preserve_input"
    postprocess_options: PostprocessOptions = Field(default_factory=PostprocessOptions)
    warnings: List[str] = Field(default_factory=list)
    integration_level: IntegrationLevel = "import_only"
    compiled_at: int = Field(default_factory=lambda: int(time.time()))


class DraftValidationResult(BaseModel):
    """Draft validation output.

    Validation in v1 covers file format, mapping, and import rules only.
    It does not guarantee Nebula existence checks or final write success.
    """

    passed: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)
    semantic_notes: List[str] = Field(default_factory=list)
    compiled_plan: Optional[CompiledImportPlan] = None
    validated_at: int = Field(default_factory=lambda: int(time.time()))


class ImportDraft(BaseModel):
    """Persisted mutable draft definition stored before job submission."""

    draft_id: str
    format_version: str = "imports-v1"
    status: DraftLifecycle
    mode: ImportMode
    file_ids: List[str] = Field(default_factory=list)
    discriminator_column: Optional[str] = None
    mapping: List[ImportTargetConfig] = Field(default_factory=list)
    update_strategy: UpdateStrategy = Field(default_factory=UpdateStrategy)
    schema_options: SchemaOptions = Field(default_factory=SchemaOptions)
    postprocess_options: PostprocessOptions = Field(default_factory=PostprocessOptions)
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
    validation: Optional[DraftValidationResult] = None


class JobEvent(BaseModel):
    """Line-oriented job event payload written to `events.jsonl`."""

    event_type: str = "job_event"
    ts: int = Field(default_factory=lambda: int(time.time()))
    level: Literal["info", "warn", "error"] = "info"
    message: str
    context: Dict[str, Any] = Field(default_factory=dict)


class ImportJobState(BaseModel):
    """Persisted job state stored in `state.json`; this is the job fact source for v1."""

    job_id: str
    format_version: str = "imports-v1"
    draft_id: str
    status: JobStatus
    created_by: str
    mode: ImportMode
    plan_id: str
    file_ids: List[str] = Field(default_factory=list)
    compiled_plan_path: str
    failed_rows_path: str
    normalized_rows_path: str
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int = Field(default_factory=lambda: int(time.time()))
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
    interrupted: bool = False
    metadata_refreshed: bool = False
    es_sync_skipped: bool = False
    failed_rows_truncated: bool = False
    cancel_effective_at_batch: bool = False
    affected_entity_vids: List[int] = Field(default_factory=list)
    affected_schema_objects: List[str] = Field(default_factory=list)
