from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class ImportErrorDetail(BaseModel):
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
    sample_rows: int = 200
    mode_hint: Optional[Literal["vertex", "edge", "mixed"]] = None


class ImportSourceAliasHintResp(BaseModel):
    source_column: str
    logical_field: str


class ImportPreviewSourceResp(BaseModel):
    source_id: str
    file_id: str
    filename: str
    columns: List[str] = Field(default_factory=list)
    sample_rows: List[Dict[str, str]] = Field(default_factory=list)
    header_hash: str
    inferred_kind: Literal["vertex", "edge", "mixed", "unknown"]
    warnings: List[str] = Field(default_factory=list)
    alias_hints: List[ImportSourceAliasHintResp] = Field(default_factory=list)
    recommended_object_type: Optional[Literal["tag", "edge_type"]] = None
    default_edge_kind: Optional[str] = None


class ImportPreviewResp(BaseModel):
    sources: List[ImportPreviewSourceResp] = Field(default_factory=list)
    workspace_mode_candidates: List[Literal["vertex", "edge", "mixed"]] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    sample_rows: List[Dict[str, str]] = Field(default_factory=list)
    inferred_mode_candidates: List[Literal["vertex", "edge", "mixed"]] = Field(default_factory=list)


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


class ImportIdentityMappingReq(BaseModel):
    id_column: Optional[str] = None
    src_column: Optional[str] = None
    dst_column: Optional[str] = None
    rank_column: Optional[str] = None


class ImportPropertyMappingReq(BaseModel):
    source_column: str = ""
    target_field: str
    logical_field: Optional[str] = None
    default_value: Optional[str] = None


class ImportRowSelectorReq(BaseModel):
    column: str
    equals: str


class ImportSourceReq(BaseModel):
    source_id: str
    file_id: str
    filename: str = ""
    columns: List[str] = Field(default_factory=list)
    sample_rows: List[Dict[str, str]] = Field(default_factory=list)
    header_hash: str = ""
    inferred_kind: Literal["vertex", "edge", "mixed", "unknown"] = "unknown"
    warnings: List[str] = Field(default_factory=list)
    alias_hints: List[ImportSourceAliasHintResp] = Field(default_factory=list)
    recommended_object_type: Optional[Literal["tag", "edge_type"]] = None
    default_edge_kind: Optional[str] = None


class ImportTargetMappingReq(BaseModel):
    target_id: Optional[str] = None
    object_type: Literal["tag", "edge_type"]
    object_name: str
    source_id: str = ""
    identity_mapping: ImportIdentityMappingReq = Field(default_factory=ImportIdentityMappingReq)
    property_mappings: List[ImportPropertyMappingReq] = Field(default_factory=list)
    row_selector: Optional[ImportRowSelectorReq] = None
    target_options: Dict[str, Any] = Field(default_factory=dict)
    field_mappings: List[ImportFieldMappingReq] = Field(default_factory=list)
    discriminator_value: Optional[str] = None


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
    sources: List[ImportSourceReq] = Field(default_factory=list)
    mapping: List[ImportTargetMappingReq] = Field(default_factory=list)
    schema_options: ImportSchemaOptionsReq = Field(default_factory=ImportSchemaOptionsReq)
    workspace_mode: Optional[Literal["vertex", "edge", "mixed"]] = None
    mode: Optional[Literal["vertex", "edge", "mixed"]] = None

    @model_validator(mode="before")
    @classmethod
    def _compat_mode(cls, data: Any):
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        if "workspace_mode" not in merged and "mode" in merged:
            merged["workspace_mode"] = merged.get("mode")
        return merged


class ImportSchemaPropertyPlanResp(BaseModel):
    name: str
    type: str
    exists: bool
    source_column: Optional[str] = None


class ImportSchemaObjectPlanResp(BaseModel):
    target_id: str = ""
    source_id: str = ""
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
    space_name: Optional[str] = None
    workspace_mode: Optional[Literal["vertex", "edge", "mixed"]] = None
    mode: Optional[Literal["vertex", "edge", "mixed"]] = None
    file_ids: List[str] = Field(default_factory=list)
    sources: List[ImportSourceReq] = Field(default_factory=list)
    mapping: List[ImportTargetMappingReq] = Field(default_factory=list)
    update_strategy: ImportUpdateStrategyReq = Field(default_factory=ImportUpdateStrategyReq)
    schema_options: ImportSchemaOptionsReq = Field(default_factory=ImportSchemaOptionsReq)
    postprocess_options: ImportPostprocessOptionsReq = Field(default_factory=ImportPostprocessOptionsReq)

    @model_validator(mode="before")
    @classmethod
    def _compat_mode(cls, data: Any):
        if not isinstance(data, dict):
            return data
        merged = dict(data)
        if "workspace_mode" not in merged and "mode" in merged:
            merged["workspace_mode"] = merged.get("mode")
        return merged


class CompiledTargetPlanResp(BaseModel):
    target_id: str
    object_type: Literal["tag", "edge_type"]
    object_name: str
    source_id: str
    source_file_id: str = ""
    source_filename: str = ""
    source_columns: List[str] = Field(default_factory=list)
    inferred_source_kind: Literal["vertex", "edge", "mixed", "unknown"] = "unknown"
    identity_mapping: ImportIdentityMappingReq = Field(default_factory=ImportIdentityMappingReq)
    property_mappings: List[ImportPropertyMappingReq] = Field(default_factory=list)
    row_selector: Optional[ImportRowSelectorReq] = None
    property_types: Dict[str, str] = Field(default_factory=dict)
    identity_fields: List[str] = Field(default_factory=list)
    update_fields: List[str] = Field(default_factory=list)
    create_fields: List[str] = Field(default_factory=list)
    integration_level: Literal["fully_integrated", "import_only", "partially_integrated"]
    warnings: List[str] = Field(default_factory=list)


class CompiledImportPlanResp(BaseModel):
    plan_id: str
    space_name: str = ""
    template_type: str = "entity_rel2_default"
    integration_scope: str = "entity_rel2_core"
    workspace_mode: Literal["vertex", "edge", "mixed"]
    mode: Optional[Literal["vertex", "edge", "mixed"]] = None
    file_ids: List[str] = Field(default_factory=list)
    sources: List[ImportPreviewSourceResp] = Field(default_factory=list)
    targets: List[CompiledTargetPlanResp] = Field(default_factory=list)
    schema_create_plan: List[ImportSchemaObjectPlanResp] = Field(default_factory=list)
    update_strategy: Dict[str, Any] = Field(default_factory=dict)
    rank_generation_strategy: Literal["preserve_input", "system_generated"]
    postprocess_options: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    integration_level: Literal["fully_integrated", "import_only", "partially_integrated"]
    compiled_at: int


class ImportTargetValidationResp(BaseModel):
    target_id: str
    source_id: str
    object_type: Literal["tag", "edge_type"]
    object_name: str
    source_columns: List[str] = Field(default_factory=list)
    passed: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    hints: List[str] = Field(default_factory=list)
    scanned_rows: int = 0
    error_rows: int = 0


class ImportDraftValidationResp(BaseModel):
    passed: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    integration_warnings: List[str] = Field(default_factory=list)
    semantic_notes: List[str] = Field(default_factory=list)
    scanned_rows: int = 0
    error_rows: int = 0
    errors_truncated: bool = False
    target_results: List[ImportTargetValidationResp] = Field(default_factory=list)
    compiled_plan: Optional[CompiledImportPlanResp] = None


class ImportDraftResp(BaseModel):
    draft_id: str
    space_name: str = ""
    status: Literal["files_uploaded", "preview_ready", "mapped", "validated"]
    workspace_mode: Literal["vertex", "edge", "mixed"]
    mode: Optional[Literal["vertex", "edge", "mixed"]] = None
    file_ids: List[str] = Field(default_factory=list)
    sources: List[ImportPreviewSourceResp] = Field(default_factory=list)
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
    is_test_data: bool = True


class ImportPostprocessReconcileRequest(BaseModel):
    space_name: Optional[str] = None
    job_id: Optional[str] = None
    actor: str = "postprocess_reconcile"
    refresh_metadata: Optional[bool] = None
    sync_scope: Literal["auto", "none", "job", "space"] = "auto"


class ImportPostprocessReconcileResp(BaseModel):
    space_name: str
    job_id: Optional[str] = None
    refresh_metadata: bool
    sync_scope: Literal["auto", "none", "job", "space"]
    affected_entity_count: int = 0
    metadata_summary: Dict[str, Any] = Field(default_factory=dict)
    sync_summary: Dict[str, Any] = Field(default_factory=dict)
    verify_summary: Optional[Dict[str, Any]] = None
    completion_summary: Dict[str, Any] = Field(default_factory=dict)
    index_status_snapshot: Optional[Dict[str, Any]] = None


class ImportJobArtifactResp(BaseModel):
    target_id: str
    source_id: str
    kind: Literal["normalized_rows", "failed_rows", "summary"]
    filename: str
    path: str


class ImportJobResp(BaseModel):
    job_id: str
    draft_id: str
    batch_id: str = ""
    space_name: str = ""
    template_type: str = "entity_rel2_default"
    status: Literal[
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
    created_by: str
    workspace_mode: Literal["vertex", "edge", "mixed"]
    mode: Optional[Literal["vertex", "edge", "mixed"]] = None
    plan_id: str
    file_ids: List[str] = Field(default_factory=list)
    sources: List[ImportPreviewSourceResp] = Field(default_factory=list)
    targets: List[CompiledTargetPlanResp] = Field(default_factory=list)
    artifacts: List[ImportJobArtifactResp] = Field(default_factory=list)
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
    failure_stage: Optional[
        Literal["metadata_failed", "es_sync_failed", "verify_failed", "registry_write_failed", "interrupted", "cancelled"]
    ] = None
    interrupted: bool = False
    metadata_refreshed: bool = False
    es_sync_skipped: bool = False
    failed_rows_truncated: bool = False
    cancel_effective_at_batch: bool = False
    affected_entity_vids: List[int] = Field(default_factory=list)
    affected_schema_objects: List[str] = Field(default_factory=list)
    index_status_snapshot: Optional[Dict[str, Any]] = None
    completion_summary: Optional[Dict[str, Any]] = None


class ImportJobLogsResp(BaseModel):
    job_id: str
    lines: List[str] = Field(default_factory=list)


class ImportBatchItemResp(BaseModel):
    item_id: str
    batch_id: str
    space_id: str
    job_id: str
    created_at: int
    item_type: Literal["entity", "relation"]
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


class ImportBatchResp(BaseModel):
    batch_id: str
    space_id: str
    source_type: Literal["import_ui", "team_ingestion"]
    created_at: int
    updated_at: int
    is_test_data: bool
    draft_id: str
    job_id: str
    submission_id: Optional[str] = None
    status: Literal["queued", "running", "succeeded", "failed_import", "failed_postprocess", "cancelled"]
    entity_count: int = 0
    relation_count: int = 0
    searchable: Optional[bool] = None
    cleanup_status: Literal["not_requested", "queued", "running", "succeeded", "partial_succeeded", "failed", "not_supported"]
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    ledger_summary: Dict[str, Any] = Field(default_factory=dict)
    warning_messages: List[str] = Field(default_factory=list)


class CleanupConflictResp(BaseModel):
    vid: Optional[int] = None
    item_type: Literal["entity", "relation"]
    source: Literal["ledger", "live_graph"] = "ledger"
    reason: str
    blocking_batch_ids: List[str] = Field(default_factory=list)
    blocking_relations: int = 0
    details: Dict[str, Any] = Field(default_factory=dict)


class CleanupPhaseResp(BaseModel):
    phase: Literal[
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
    at: int


class CleanupArtifactResp(BaseModel):
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


class CleanupPlanSummaryResp(BaseModel):
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
    generated_at: int


class CleanupBlockedEntityDetailResp(BaseModel):
    vid: Optional[int] = None
    entity_name: Optional[str] = None
    entity_raw_id: Optional[str] = None
    item_key: Optional[str] = None
    conflict_sources: List[Literal["ledger", "live_graph"]] = Field(default_factory=list)
    conflicts: List[CleanupConflictResp] = Field(default_factory=list)


class CleanupDeletableEntityDetailResp(BaseModel):
    vid: Optional[int] = None
    entity_name: Optional[str] = None
    entity_raw_id: Optional[str] = None
    item_key: Optional[str] = None


class CleanupDeletableRelationDetailResp(BaseModel):
    edge_type: Optional[str] = None
    src_vid: Optional[int] = None
    dst_vid: Optional[int] = None
    rank: Optional[int] = None
    relation: Optional[str] = None
    item_key: Optional[str] = None


class CleanupBlockedEntityPreviewResp(BaseModel):
    total_count: int = 0
    sample: List[CleanupBlockedEntityDetailResp] = Field(default_factory=list)


class CleanupDeletableEntityPreviewResp(BaseModel):
    total_count: int = 0
    sample: List[CleanupDeletableEntityDetailResp] = Field(default_factory=list)


class CleanupDeletableRelationPreviewResp(BaseModel):
    total_count: int = 0
    sample: List[CleanupDeletableRelationDetailResp] = Field(default_factory=list)


class CleanupPlanPreviewResp(BaseModel):
    batch_ids: List[str] = Field(default_factory=list)
    scope: Literal["full_batch", "relations_only"]
    plan_summary: CleanupPlanSummaryResp
    conflicts: List[CleanupConflictResp] = Field(default_factory=list)
    blocked_entities: CleanupBlockedEntityPreviewResp = Field(default_factory=CleanupBlockedEntityPreviewResp)
    deletable_entities: CleanupDeletableEntityPreviewResp = Field(default_factory=CleanupDeletableEntityPreviewResp)
    deletable_relations: CleanupDeletableRelationPreviewResp = Field(default_factory=CleanupDeletableRelationPreviewResp)
    warning_messages: List[str] = Field(default_factory=list)
    verification_scope_note: str = ""
    has_plan_artifacts: bool = False
    artifacts: List[CleanupArtifactResp] = Field(default_factory=list)
    consistency_note: str = (
        "preview is a point-in-time analysis based on current ledger + graph state; execute recalculates plan before deletion"
    )


class ImportBatchCleanupRequest(BaseModel):
    batch_ids: List[str] = Field(default_factory=list)
    scope: Literal["full_batch", "relations_only"] = "full_batch"
    created_by: str = "import_workspace_cleanup"


class CleanupJobResp(BaseModel):
    cleanup_job_id: str
    space_id: str
    batch_ids: List[str] = Field(default_factory=list)
    scope: Literal["full_batch", "relations_only"]
    created_by: str
    created_at: int
    updated_at: int
    started_at: Optional[int] = None
    finished_at: Optional[int] = None
    status: Literal["queued", "running", "succeeded", "partial_succeeded", "failed"]
    phase: Literal[
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
    final_phase: Optional[
        Literal[
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
    ] = None
    phase_history: List[CleanupPhaseResp] = Field(default_factory=list)
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
    conflicts: List[CleanupConflictResp] = Field(default_factory=list)
    plan_summary: CleanupPlanSummaryResp
    has_plan_artifacts: bool = False
    verify_summary: Dict[str, Any] = Field(default_factory=dict)
    metadata_summary: Dict[str, Any] = Field(default_factory=dict)
    reconcile_summary: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[CleanupArtifactResp] = Field(default_factory=list)
