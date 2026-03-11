from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

"""FastAPI request/response models for imports v1.

These schemas document the stable HTTP contract. Imports-specific error responses are
standardized around `detail.error_code`, `detail.message`, and optional `field` / `extra`.
"""


class ImportErrorDetail(BaseModel):
    """Standardized imports error detail payload."""

    error_code: str
    message: str
    field: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


class ImportErrorResp(BaseModel):
    detail: ImportErrorDetail


class ImportFileUploadResp(BaseModel):
    file_id: str
    original_name: str
    size_bytes: int
    detected_delimiter: str
    detected_encoding: str


class ImportPreviewRequest(BaseModel):
    file_ids: List[str]
    sample_rows: int = 10
    mode_hint: Optional[Literal["vertex", "edge", "mixed"]] = None


class ImportPreviewResp(BaseModel):
    """Preview response based on staging CSV only; no write or existence checks are performed."""

    columns: List[str]
    sample_rows: List[Dict[str, str]]
    inferred_mode_candidates: List[str]
    warnings: List[str] = Field(default_factory=list)


class ImportSchemaPropertyResp(BaseModel):
    name: str
    type: str
    nullable: bool = True


class ImportSchemaObjectResp(BaseModel):
    object_type: Literal["tag", "edge_type"]
    name: str
    exists: bool = True
    properties: List[ImportSchemaPropertyResp] = Field(default_factory=list)


class ImportSchemaResp(BaseModel):
    tags: List[ImportSchemaObjectResp] = Field(default_factory=list)
    edge_types: List[ImportSchemaObjectResp] = Field(default_factory=list)


class ImportFieldMappingReq(BaseModel):
    source_column: str
    target_field: str


class ImportTargetMappingReq(BaseModel):
    object_type: Literal["tag", "edge_type"]
    object_name: str
    discriminator_value: Optional[str] = None
    field_mappings: List[ImportFieldMappingReq] = Field(default_factory=list)


class ImportUpdateStrategyReq(BaseModel):
    mode: Literal["merge_partial"] = "merge_partial"
    create_if_missing: bool = True
    update_existing: bool = True


class ImportSchemaOptionsReq(BaseModel):
    allow_create_object: bool = True
    allow_add_properties: bool = True


class ImportPostprocessOptionsReq(BaseModel):
    refresh_metadata: bool = True
    sync_entity_es: bool = True


class ImportSchemaPlanRequest(BaseModel):
    file_ids: List[str] = Field(default_factory=list)
    mapping: List[ImportTargetMappingReq] = Field(default_factory=list)
    schema_options: ImportSchemaOptionsReq = Field(default_factory=ImportSchemaOptionsReq)


class ImportSchemaPropertyPlanResp(BaseModel):
    name: str
    type: str
    exists: bool
    source_column: Optional[str] = None


class ImportSchemaObjectPlanResp(BaseModel):
    object_type: Literal["tag", "edge_type"]
    object_name: str
    object_exists: bool
    add_object: bool = False
    add_properties: List[ImportSchemaPropertyPlanResp] = Field(default_factory=list)
    ignored_columns: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)


class ImportSchemaPlanResp(BaseModel):
    schema_create_plan: List[ImportSchemaObjectPlanResp] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)


class ImportDraftUpsertRequest(BaseModel):
    draft_id: Optional[str] = None
    mode: Literal["vertex", "edge", "mixed"]
    file_ids: List[str] = Field(default_factory=list)
    discriminator_column: Optional[str] = None
    mapping: List[ImportTargetMappingReq] = Field(default_factory=list)
    update_strategy: ImportUpdateStrategyReq = Field(default_factory=ImportUpdateStrategyReq)
    schema_options: ImportSchemaOptionsReq = Field(default_factory=ImportSchemaOptionsReq)
    postprocess_options: ImportPostprocessOptionsReq = Field(default_factory=ImportPostprocessOptionsReq)


class CompiledTargetPlanResp(BaseModel):
    object_type: Literal["tag", "edge_type"]
    object_name: str
    discriminator_value: Optional[str] = None
    field_mappings: Dict[str, str] = Field(default_factory=dict)
    property_types: Dict[str, str] = Field(default_factory=dict)
    identity_fields: List[str] = Field(default_factory=list)
    update_fields: List[str] = Field(default_factory=list)
    create_fields: List[str] = Field(default_factory=list)
    integration_level: Literal["fully_integrated", "import_only", "partially_integrated"]
    warnings: List[str] = Field(default_factory=list)


class CompiledImportPlanResp(BaseModel):
    plan_id: str
    mode: Literal["vertex", "edge", "mixed"]
    file_ids: List[str] = Field(default_factory=list)
    discriminator_column: Optional[str] = None
    targets: List[CompiledTargetPlanResp] = Field(default_factory=list)
    schema_create_plan: List[ImportSchemaObjectPlanResp] = Field(default_factory=list)
    update_strategy: Dict[str, Any] = Field(default_factory=dict)
    rank_generation_strategy: Literal["preserve_input", "system_generated"]
    postprocess_options: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    integration_level: Literal["fully_integrated", "import_only", "partially_integrated"]
    compiled_at: int


class ImportDraftValidationResp(BaseModel):
    """Validation response for format/mapping/rule checks only."""

    passed: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)
    semantic_notes: List[str] = Field(default_factory=list)
    compiled_plan: Optional[CompiledImportPlanResp] = None


class ImportDraftResp(BaseModel):
    draft_id: str
    status: Literal["files_uploaded", "preview_ready", "mapped", "validated"]
    mode: Literal["vertex", "edge", "mixed"]
    file_ids: List[str] = Field(default_factory=list)
    discriminator_column: Optional[str] = None
    mapping: List[ImportTargetMappingReq] = Field(default_factory=list)
    update_strategy: Dict[str, Any] = Field(default_factory=dict)
    schema_options: Dict[str, Any] = Field(default_factory=dict)
    postprocess_options: Dict[str, Any] = Field(default_factory=dict)
    validation: Optional[ImportDraftValidationResp] = None
    created_at: int
    updated_at: int


class ImportJobCreateRequest(BaseModel):
    draft_id: str
    created_by: str


class ImportJobResp(BaseModel):
    job_id: str
    draft_id: str
    status: Literal[
        "queued",
        "running",
        "post_metadata_refresh",
        "post_es_sync",
        "succeeded",
        "failed_import",
        "failed_postprocess",
        "cancelled",
    ]
    created_by: str
    mode: Literal["vertex", "edge", "mixed"]
    plan_id: str
    file_ids: List[str] = Field(default_factory=list)
    created_at: int
    updated_at: int
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    cancel_requested: bool = False
    total_rows: int = 0
    processed_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    warnings: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)
    integration_level: Literal["fully_integrated", "import_only", "partially_integrated"] = "import_only"
    error_message: Optional[str] = None
    interrupted: bool = False
    metadata_refreshed: bool = False
    es_sync_skipped: bool = False
    failed_rows_truncated: bool = False
    cancel_effective_at_batch: bool = False
    affected_entity_vids: List[int] = Field(default_factory=list)
    affected_schema_objects: List[str] = Field(default_factory=list)


class ImportJobLogsResp(BaseModel):
    job_id: str
    lines: List[str] = Field(default_factory=list)
