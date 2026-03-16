export type SpaceIndexStatus = {
  status: "verified_nonempty" | "verified_empty" | "verified_partial" | "failed";
  doc_count: number;
  nebula_entity_count?: number | null;
  coverage_pct?: number | null;
  note: string;
  updated_at?: string | null;
};

export type SpaceSummary = {
  space_name: string;
  display_name: string;
  description: string;
  template_type: "entity_rel2_default";
  template_version: string;
  integration_scope: string;
  status: "provisioning" | "ready" | "failed";
  internal_status: string;
  created_by: string;
  created_at: string;
  ready_at?: string | null;
  last_error?: string | null;
  graph_status: "unavailable" | "ready";
  search_status: "unavailable" | "empty" | "partial" | "full" | "failed";
  coverage_pct?: number | null;
  index_status?: SpaceIndexStatus | null;
};

export type CurrentSpaceResp = {
  space_name: string;
  source: "header" | "default";
  header_present: boolean;
  header_value?: string | null;
  registry_status?: string | null;
  graph_status: "unavailable" | "ready";
  search_status: "unavailable" | "empty" | "partial" | "full" | "failed";
  coverage_pct?: number | null;
  index_status?: SpaceIndexStatus | null;
};

export type CreateSpaceRequest = {
  space_name: string;
  display_name: string;
  description: string;
  template_type: "entity_rel2_default";
  created_by: string;
};

export type CreateSpaceResp = {
  space: SpaceSummary;
  status: SpaceSummary["status"];
  integration_scope: string;
  warnings: string[];
};
