export type NodeBrief = {
  id: number;
  label: string;
  entity_type: string;
  raw_id?: string;
  source?: string;
  score?: number;
  snippet?: string;
  role?: "seed" | "candidate";
  seed_support_count?: number;
  seed_support_vids?: number[];
  score_breakdown?: Record<string, unknown>;
};

export type EdgeBrief = {
  source: number;
  target: number;
  rank: string;
  edge_type?: string;
  relation?: string;
  source_db?: string;
  is_explain?: boolean;
  role?: "seed_candidate" | "candidate_candidate" | "seed_seed";
};

export type SearchResp = {
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  total_candidates: number;
  truncated?: boolean;
  meta?: Record<string, unknown>;
};

export type SubgraphResp = {
  root_vid: number;
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  stats: {
    node_count: number;
    edge_count: number;
    truncated: boolean;
    dropped_nodes?: number;
    dropped_edges?: number;
    dropped_neighbors?: number;
    budget_applied?: Record<string, unknown>;
  };
};

export type ExpandResp = {
  added_nodes: NodeBrief[];
  added_edges: EdgeBrief[];
  stats: {
    node_count_after: number;
    edge_count_after?: number;
    added_nodes?: number;
    added_edges?: number;
    truncated?: boolean;
    dropped_nodes: number;
    dropped_edges?: number;
    dropped_neighbors?: number;
    policy: string;
    budget_applied?: Record<string, unknown>;
  };
};

export type NodeDetailResp = {
  vid: number;
  entity_name?: string;
  entity_type?: string;
  source?: string;
  description?: string;
  entity_raw_id?: string;
  version: number;
  updated_at: number;
  updated_by: string;
  props: Record<string, unknown>;
};
export type EdgeDetailResp = {
  edge_type: string;
  src: number;
  dst: number;
  rank: string;
  relation?: string;
  source_db?: string;
  evidence?: string;
  version: number;
  updated_at: number;
  updated_by: string;
  updated?: boolean;
  props: Record<string, unknown>;
};

export type Sel =
  | { kind: "none" }
  | { kind: "node"; vid: number }
  | { kind: "edge"; src: number; dst: number; rank: string; edge_type: string; relation: string; source_db?: string };

export type ExpandProbeState = "loading" | "noextra" | "hasextra";

export type SuggestItem = {
  vid: number;
  label: string;
  entity_type?: string;
  source?: string;
  score?: number;
};

export type SuggestResp = {
  q: string;
  items: SuggestItem[];
  truncated: boolean;
};

export type RawIdSuggestItem = {
  vid: number;
  entity_raw_id: string;
  label?: string;
  entity_type?: string;
  source?: string;
};

export type RawIdSuggestResp = {
  q: string;
  items: RawIdSuggestItem[];
  truncated: boolean;
};

export type EntityTypeItem = {
  entity_type: string;
  count: number;
};

export type RelationTypeItem = {
  relation_type: string;
  count: number;
};

export type RelationTypesResp = {
  items: RelationTypeItem[];
  q: string;
  limit: number;
  offset: number;
  next_offset: number | null;
  has_more: boolean;
  matched_total: number;
};

export type EdgeSearchItem = {
  edge_type: string;
  src: number;
  dst: number;
  rank: string;
  relation: string;
  source_db?: string;
  score?: number;
  src_label?: string;
  dst_label?: string;
  snippet?: string;
};

export type EdgeSuggestResp = {
  q: string;
  items: EdgeSearchItem[];
  truncated: boolean;
};

export type EdgeSearchResp = {
  edges: EdgeSearchItem[];
  total_candidates: number;
};

export type ExplainPathCandidate = {
  path_id: string;
  length: number;
  nodes: number[];
  edges: EdgeBrief[];
  score?: number;
  summary?: string;
};

export type PairPathCandidate = {
  u: number;
  v: number;
  has_direct: boolean;
  chosen_index: number | null;
  candidates: ExplainPathCandidate[];
};

export type MultiEntityGraphResp = {
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  stats: {
    selected?: number;
    direct_edges?: number;
    explained_pairs?: number;
    unconnected?: number[];
    unconnected_pairs?: string[];
    truncated?: boolean;
    dropped_neighbors?: number;
    node_count?: number;
    edge_count?: number;
    budget_applied?: Record<string, unknown>;
    [k: string]: unknown;
  };
  path_candidates?: PairPathCandidate[];
};

export type GraphDiscoveryEntityFacetItem = {
  entity_type: string;
  count: number;
  seed_count: number;
  candidate_count: number;
};

export type GraphDiscoveryRelationFacetItem = {
  relation_type: string;
  count: number;
  seed_candidate_count: number;
  candidate_candidate_count: number;
  seed_seed_count: number;
};

export type GraphDiscoveryResp = {
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  facets: {
    entity_types: GraphDiscoveryEntityFacetItem[];
    relation_types: GraphDiscoveryRelationFacetItem[];
  };
  stats: {
    seed_count: number;
    candidate_count: number;
    node_count: number;
    edge_count: number;
    truncated: boolean;
    dropped_nodes: number;
    dropped_edges: number;
    dropped_neighbors: number;
    recall_candidate_count: number;
    kept_candidate_count: number;
    budget_applied?: Record<string, unknown>;
  };
};

export type EditableFieldSpec = {
  name: string;
  type: "string";
  maxLen: number;
  multiline: boolean;
  required: boolean;
};

export type EditableFieldsResp = {
  entity: { fields: EditableFieldSpec[] };
  edge: { fields: EditableFieldSpec[] };
  forbidden_fields: string[];
};

export type NodePatchResp = {
  vid: number;
  updated: Record<string, string>;
  version: number;
  updated_at: number;
  updated_by: string;
};

export type EdgePatchResp = {
  identity: {
    src: number;
    dst: number;
    rank: string;
    edge_type: string;
  };
  updated: Record<string, string>;
  version: number;
  updated_at: number;
  updated_by: string;
};
