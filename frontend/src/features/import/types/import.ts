export type ImportMode = "vertex" | "edge" | "mixed";
export type SourceKind = "vertex" | "edge" | "mixed" | "unknown";
export type ImportObjectType = "tag" | "edge_type";
export type DraftStatus = "files_uploaded" | "preview_ready" | "mapped" | "validated";
export type JobStatus =
  | "queued"
  | "running"
  | "post_metadata_refresh"
  | "post_es_sync"
  | "post_verify_index"
  | "succeeded"
  | "failed_import"
  | "failed_postprocess"
  | "cancelled";
export type IntegrationLevel = "fully_integrated" | "import_only" | "partially_integrated";
export type ImportBatchSourceType = "import_ui" | "team_ingestion";
export type ImportBatchCleanupStatus =
  | "not_requested"
  | "queued"
  | "running"
  | "succeeded"
  | "partial_succeeded"
  | "failed"
  | "not_supported";
export type CleanupJobStatus = "queued" | "running" | "succeeded" | "partial_succeeded" | "failed";
export type CleanupJobPhase =
  | "planning"
  | "deleting_relations"
  | "deleting_entities"
  | "deleting_es_docs"
  | "refreshing_metadata"
  | "reconciling"
  | "verifying"
  | "completed"
  | "failed";

export type ImportFileUploadResp = {
  file_id: string;
  original_name: string;
  size_bytes: number;
  detected_delimiter: string;
  detected_encoding: string;
};

export type ImportSourceAliasHint = {
  source_column: string;
  logical_field: string;
};

export type ImportSource = {
  source_id: string;
  file_id: string;
  filename: string;
  columns: string[];
  sample_rows: Record<string, string>[];
  header_hash: string;
  inferred_kind: SourceKind;
  warnings: string[];
  alias_hints: ImportSourceAliasHint[];
  recommended_object_type?: ImportObjectType | null;
  default_edge_kind?: string | null;
};

export type ImportPreviewResp = {
  sources: ImportSource[];
  workspace_mode_candidates: ImportMode[];
  warnings: string[];
};

export type ImportSchemaProperty = {
  name: string;
  type: string;
  nullable: boolean;
};

export type ImportSchemaObject = {
  object_type: ImportObjectType;
  name: string;
  exists: boolean;
  properties: ImportSchemaProperty[];
};

export type ImportSchemaResp = {
  tags: ImportSchemaObject[];
  edge_types: ImportSchemaObject[];
};

export type ImportIdentityMapping = {
  id_column?: string | null;
  src_column?: string | null;
  dst_column?: string | null;
  rank_column?: string | null;
};

export type ImportPropertyMapping = {
  source_column: string;
  target_field: string;
  logical_field?: string | null;
  default_value?: string | null;
};

export type ImportRowSelector = {
  column: string;
  equals: string;
};

export type ImportTargetMapping = {
  target_id?: string;
  object_type: ImportObjectType;
  object_name: string;
  source_id: string;
  identity_mapping: ImportIdentityMapping;
  property_mappings: ImportPropertyMapping[];
  row_selector?: ImportRowSelector | null;
  target_options: Record<string, unknown>;
};

export type ImportSchemaOptions = {
  allow_create_object: boolean;
  allow_add_properties: boolean;
};

export type ImportUpdateStrategy = {
  mode: "merge_partial";
  create_if_missing: boolean;
  update_existing: boolean;
};

export type ImportPostprocessOptions = {
  refresh_metadata: boolean;
  sync_entity_es: boolean;
};

export type ImportSchemaPropertyPlan = {
  name: string;
  type: string;
  exists: boolean;
  source_column?: string | null;
};

export type ImportSchemaObjectPlan = {
  target_id: string;
  source_id: string;
  object_type: ImportObjectType;
  object_name: string;
  object_exists: boolean;
  add_object: boolean;
  add_properties: ImportSchemaPropertyPlan[];
  ignored_columns: string[];
  integration_warnings: string[];
};

export type CompiledTargetPlan = {
  target_id: string;
  object_type: ImportObjectType;
  object_name: string;
  source_id: string;
  source_file_id: string;
  source_filename: string;
  source_columns: string[];
  inferred_source_kind: SourceKind;
  identity_mapping: ImportIdentityMapping;
  property_mappings: ImportPropertyMapping[];
  row_selector?: ImportRowSelector | null;
  property_types: Record<string, string>;
  identity_fields: string[];
  update_fields: string[];
  create_fields: string[];
  integration_level: IntegrationLevel;
  warnings: string[];
};

export type CompiledImportPlan = {
  plan_id: string;
  space_name: string;
  template_type: string;
  integration_scope: string;
  workspace_mode: ImportMode;
  file_ids: string[];
  sources: ImportSource[];
  targets: CompiledTargetPlan[];
  schema_create_plan: ImportSchemaObjectPlan[];
  update_strategy: Record<string, unknown>;
  rank_generation_strategy: "preserve_input" | "system_generated";
  postprocess_options: Record<string, unknown>;
  warnings: string[];
  integration_level: IntegrationLevel;
  compiled_at: number;
};

export type ImportTargetValidationResp = {
  target_id: string;
  source_id: string;
  object_type: ImportObjectType;
  object_name: string;
  source_columns: string[];
  passed: boolean;
  errors: string[];
  warnings: string[];
  hints: string[];
  scanned_rows: number;
  error_rows: number;
};

export type ImportDraftValidationResp = {
  passed: boolean;
  errors: string[];
  warnings: string[];
  integration_warnings: string[];
  semantic_notes: string[];
  scanned_rows: number;
  error_rows: number;
  errors_truncated: boolean;
  target_results: ImportTargetValidationResp[];
  compiled_plan?: CompiledImportPlan | null;
};

export type ImportDraftResp = {
  draft_id: string;
  space_name: string;
  status: DraftStatus;
  workspace_mode: ImportMode;
  file_ids: string[];
  sources: ImportSource[];
  mapping: ImportTargetMapping[];
  update_strategy: ImportUpdateStrategy;
  schema_options: ImportSchemaOptions;
  postprocess_options: ImportPostprocessOptions;
  validation?: ImportDraftValidationResp | null;
  created_at: number;
  updated_at: number;
};

export type ImportJobArtifact = {
  target_id: string;
  source_id: string;
  kind: "normalized_rows" | "failed_rows" | "summary";
  filename: string;
  path: string;
};

export type ImportJobResp = {
  job_id: string;
  draft_id: string;
  batch_id: string;
  space_name: string;
  template_type: string;
  status: JobStatus;
  created_by: string;
  workspace_mode: ImportMode;
  plan_id: string;
  file_ids: string[];
  sources: ImportSource[];
  targets: CompiledTargetPlan[];
  artifacts: ImportJobArtifact[];
  created_at: number;
  updated_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  cancel_requested: boolean;
  total_rows: number;
  processed_rows: number;
  success_rows: number;
  failed_rows: number;
  warnings: string[];
  integration_warnings: string[];
  integration_level: IntegrationLevel;
  error_message?: string | null;
  interrupted: boolean;
  metadata_refreshed: boolean;
  es_sync_skipped: boolean;
  failed_rows_truncated: boolean;
  cancel_effective_at_batch: boolean;
  affected_entity_vids: number[];
  affected_schema_objects: string[];
  index_status_snapshot?: {
    status: "verified_nonempty" | "verified_empty" | "verified_partial" | "failed";
    doc_count: number;
    nebula_entity_count?: number | null;
    coverage_pct?: number | null;
    note?: string;
    updated_at?: string | null;
  } | null;
  completion_summary?: {
    nebula_write_success: boolean;
    post_es_sync_success: boolean;
    verify_success: boolean;
    registry_index_status_written: boolean;
    imported_docs_visible: boolean;
    searchable: boolean;
    affected_entity_count: number;
    search_status?: string | null;
    index_status?: string | null;
    coverage_pct?: number | null;
    note?: string;
    completed_at?: string | null;
  } | null;
};

export type ImportJobLogsResp = {
  job_id: string;
  lines: string[];
};

export type ImportBatchItem = {
  item_id: string;
  batch_id: string;
  space_id: string;
  job_id: string;
  created_at: number;
  item_type: "entity" | "relation";
  created_by_batch: boolean;
  vid?: number | null;
  entity_raw_id?: string | null;
  entity_name?: string | null;
  src_vid?: number | null;
  dst_vid?: number | null;
  relation?: string | null;
  rank?: number | null;
  edge_type?: string | null;
  row_index?: number | null;
  item_key?: string | null;
};

export type ImportBatchResp = {
  batch_id: string;
  space_id: string;
  source_type: ImportBatchSourceType;
  created_at: number;
  updated_at: number;
  is_test_data: boolean;
  draft_id: string;
  job_id: string;
  submission_id?: string | null;
  status: "queued" | "running" | "succeeded" | "failed_import" | "failed_postprocess" | "cancelled";
  entity_count: number;
  relation_count: number;
  searchable?: boolean | null;
  cleanup_status: ImportBatchCleanupStatus;
  tags: string[];
  notes?: string | null;
  ledger_summary: Record<string, unknown>;
  warning_messages: string[];
};

export type CleanupConflict = {
  vid?: number | null;
  item_type: "entity" | "relation";
  source?: "ledger" | "live_graph";
  reason: string;
  blocking_batch_ids: string[];
  blocking_relations: number;
  details: Record<string, unknown>;
};

export type CleanupPhaseEntry = {
  phase: CleanupJobPhase;
  at: number;
};

export type CleanupArtifact = {
  kind:
    | "summary"
    | "conflicts"
    | "skipped_entities"
    | "skipped_relations"
    | "verify_summary"
    | "plan_summary"
    | "blocked_entities"
    | "deletable_entities"
    | "deletable_relations";
  filename: string;
  path: string;
};

export type CleanupPlanSummary = {
  requested_entity_count: number;
  requested_relation_count: number;
  ledger_blocked_entity_count: number;
  live_graph_blocked_entity_count: number;
  blocked_entity_count: number;
  deletable_entity_count: number;
  deletable_relation_count: number;
  conflict_count: number;
  warnings: string[];
  verification_scope_note: string;
  generated_at: number;
};

export type CleanupBlockedEntityDetail = {
  vid?: number | null;
  entity_name?: string | null;
  entity_raw_id?: string | null;
  item_key?: string | null;
  conflict_sources: Array<"ledger" | "live_graph">;
  conflicts: CleanupConflict[];
};

export type CleanupDeletableEntityDetail = {
  vid?: number | null;
  entity_name?: string | null;
  entity_raw_id?: string | null;
  item_key?: string | null;
};

export type CleanupDeletableRelationDetail = {
  edge_type?: string | null;
  src_vid?: number | null;
  dst_vid?: number | null;
  rank?: number | null;
  relation?: string | null;
  item_key?: string | null;
};

export type CleanupPlanPreviewResp = {
  batch_ids: string[];
  scope: "full_batch" | "relations_only";
  plan_summary: CleanupPlanSummary;
  conflicts: CleanupConflict[];
  blocked_entities: {
    total_count: number;
    sample: CleanupBlockedEntityDetail[];
  };
  deletable_entities: {
    total_count: number;
    sample: CleanupDeletableEntityDetail[];
  };
  deletable_relations: {
    total_count: number;
    sample: CleanupDeletableRelationDetail[];
  };
  warning_messages: string[];
  verification_scope_note: string;
  has_plan_artifacts: boolean;
  artifacts: CleanupArtifact[];
  consistency_note: string;
};

export type CleanupJobResp = {
  cleanup_job_id: string;
  space_id: string;
  batch_ids: string[];
  scope: "full_batch" | "relations_only";
  created_by: string;
  created_at: number;
  updated_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  status: CleanupJobStatus;
  phase: CleanupJobPhase;
  final_phase?: CleanupJobPhase | null;
  phase_history: CleanupPhaseEntry[];
  requested_relation_count: number;
  requested_entity_count: number;
  deleted_relation_count: number;
  deleted_entity_count: number;
  skipped_relation_count: number;
  skipped_entity_count: number;
  deduplicated_relation_count: number;
  deduplicated_entity_count: number;
  conflict_count: number;
  warning_messages: string[];
  error_message?: string | null;
  failure_phase?: string | null;
  failure_kind?: string | null;
  failure_detail: Record<string, unknown>;
  duration_ms?: number | null;
  conflicts: CleanupConflict[];
  plan_summary?: CleanupPlanSummary | null;
  has_plan_artifacts?: boolean;
  verify_summary: Record<string, unknown>;
  metadata_summary: Record<string, unknown>;
  reconcile_summary: Record<string, unknown>;
  artifacts: CleanupArtifact[];
};
