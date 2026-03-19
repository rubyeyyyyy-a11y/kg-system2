export type CleanupScope = "full_batch" | "relations_only";
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
  scope: CleanupScope;
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
  scope: CleanupScope;
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
