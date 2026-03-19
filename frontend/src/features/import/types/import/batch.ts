export type ImportBatchSourceType = "import_ui" | "team_ingestion";
export type ImportBatchCleanupStatus =
  | "not_requested"
  | "queued"
  | "running"
  | "succeeded"
  | "partial_succeeded"
  | "failed"
  | "not_supported";

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
