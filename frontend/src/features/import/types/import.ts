export type ImportMode = "vertex" | "edge" | "mixed";
export type ImportObjectType = "tag" | "edge_type";
export type DraftStatus = "files_uploaded" | "preview_ready" | "mapped" | "validated";
export type JobStatus =
  | "queued"
  | "running"
  | "post_metadata_refresh"
  | "post_es_sync"
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

export type ImportPreviewResp = {
  columns: string[];
  sample_rows: Record<string, string>[];
  inferred_mode_candidates: ImportMode[];
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

export type ImportFieldMapping = {
  source_column: string;
  target_field: string;
};

export type ImportTargetMapping = {
  object_type: ImportObjectType;
  object_name: string;
  discriminator_value?: string | null;
  field_mappings: ImportFieldMapping[];
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
  object_type: ImportObjectType;
  object_name: string;
  object_exists: boolean;
  add_object: boolean;
  add_properties: ImportSchemaPropertyPlan[];
  ignored_columns: string[];
  integration_warnings: string[];
};

export type CompiledTargetPlan = {
  object_type: ImportObjectType;
  object_name: string;
  discriminator_value?: string | null;
  field_mappings: Record<string, string>;
  property_types: Record<string, string>;
  identity_fields: string[];
  update_fields: string[];
  create_fields: string[];
  integration_level: IntegrationLevel;
  warnings: string[];
};

export type CompiledImportPlan = {
  plan_id: string;
  mode: ImportMode;
  file_ids: string[];
  discriminator_column?: string | null;
  targets: CompiledTargetPlan[];
  schema_create_plan: ImportSchemaObjectPlan[];
  update_strategy: Record<string, unknown>;
  rank_generation_strategy: "preserve_input" | "system_generated";
  postprocess_options: Record<string, unknown>;
  warnings: string[];
  integration_level: IntegrationLevel;
  compiled_at: number;
};

export type ImportDraftValidationResp = {
  passed: boolean;
  errors: string[];
  warnings: string[];
  integration_warnings: string[];
  semantic_notes: string[];
  compiled_plan?: CompiledImportPlan | null;
};

export type ImportDraftResp = {
  draft_id: string;
  status: DraftStatus;
  mode: ImportMode;
  file_ids: string[];
  discriminator_column?: string | null;
  mapping: ImportTargetMapping[];
  update_strategy: ImportUpdateStrategy;
  schema_options: ImportSchemaOptions;
  postprocess_options: ImportPostprocessOptions;
  validation?: ImportDraftValidationResp | null;
  created_at: number;
  updated_at: number;
};

export type ImportJobResp = {
  job_id: string;
  draft_id: string;
  status: JobStatus;
  created_by: string;
  mode: ImportMode;
  plan_id: string;
  file_ids: string[];
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
};

export type ImportJobLogsResp = {
  job_id: string;
  lines: string[];
};
