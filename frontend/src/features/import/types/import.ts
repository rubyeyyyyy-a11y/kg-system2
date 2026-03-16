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
