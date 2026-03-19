import type { CompiledTargetPlan, ImportMode, ImportSource, IntegrationLevel } from "./draft";

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
