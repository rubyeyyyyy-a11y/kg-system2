export type SpaceIndexStatus = {
  status: "verified_nonempty" | "verified_empty" | "verified_partial" | "failed";
  doc_count: number;
  nebula_entity_count?: number | null;
  coverage_pct?: number | null;
  note?: string;
  updated_at?: string | null;
};

export type SpaceMeta = {
  space_name: string;
  graph_status: "unavailable" | "ready";
  search_status: "unavailable" | "empty" | "partial" | "full" | "failed";
  coverage_pct?: number | null;
  index_status?: SpaceIndexStatus | null;
};

export type NodeBrief = {
  id: number;
  label: string;
  entity_type: string;
  raw_id?: string;
  source?: string;
  score?: number;
  snippet?: string;
  description?: string;
  role?: "seed" | "candidate";
  layer?: "core" | "shared" | "local" | "supplement" | "";
  priority_score?: number;
  min_seed_distance?: number;
  bridge_seed_count?: number;
  local_anchor_seed?: number | null;
  matched_seed_pairs?: string[];
  seed_support_count?: number;
  seed_support_vids?: number[];
  score_breakdown?: Record<string, unknown>;
  source_tags?: string[];
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
  layer?: "core" | "shared" | "local" | "supplement" | "";
  priority_score?: number;
  seed_support_vids?: number[];
  path_pair?: string;
  is_backbone?: boolean;
  source_tags?: string[];
};

export type SearchResp = {
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  total_candidates: number;
  truncated?: boolean;
  meta?: Record<string, unknown>;
  space_meta: SpaceMeta;
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

export type SelectionSource =
  | "graph_node_click"
  | "graph_edge_click"
  | "search_candidate"
  | "discovery_candidate"
  | "seed"
  | "external_detail";

export type Sel =
  | { kind: "none" }
  | { kind: "node"; vid: number; source: SelectionSource }
  | {
      kind: "edge";
      src: number;
      dst: number;
      rank: string;
      edge_type: string;
      relation: string;
      source: SelectionSource;
      source_db?: string;
    };

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
  space_meta: SpaceMeta;
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
  space_meta: SpaceMeta;
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
  core_count: number;
  shared_count: number;
  local_count: number;
  supplement_count: number;
};

export type GraphDiscoveryRelationFacetItem = {
  relation_type: string;
  count: number;
  seed_candidate_count: number;
  candidate_candidate_count: number;
  seed_seed_count: number;
  core_count: number;
  shared_count: number;
  local_count: number;
  supplement_count: number;
};

export type GraphDiscoveryQuerySummary = {
  search_type: string;
  selected_seed_count: number;
  selected_seeds: Array<{
    id: number;
    label: string;
    entity_type: string;
  }>;
  total_entities: number;
  total_relationships: number;
};

export type GraphDiscoveryLayerFacetItem = {
  layer: "core" | "shared" | "local" | "supplement";
  node_count: number;
  edge_count: number;
};

export type GraphDiscoverySeedFacetItem = {
  seed_vid: number;
  label: string;
  entity_type: string;
  local_count: number;
  shared_touch_count: number;
  core_path_count: number;
};

export type DiscoveryDroppedReason = "budget" | "type_filter" | "relation_filter";

export type GraphDiscoveryDroppedCandidate = {
  node_id: number;
  label: string;
  entity_type: string;
  raw_id: string;
  source: string;
  snippet: string;
  reason: DiscoveryDroppedReason;
  source_node_id?: number | null;
  support_edges: EdgeBrief[];
};

export type GraphDiscoveryNodeCapability = {
  node_id: number;
  expandable: boolean;
  terminal: boolean;
};

export type GraphDiscoveryExpandResp = {
  new_nodes: NodeBrief[];
  new_edges: EdgeBrief[];
  support_edges: EdgeBrief[];
  dropped_candidates: GraphDiscoveryDroppedCandidate[];
  has_more_candidates_before_budget: boolean;
  has_more_candidates_after_filters: boolean;
  terminal: boolean;
  request_space: string;
  space_meta: SpaceMeta;
  warnings?: string[];
  stats: {
    candidate_neighbor_count: number;
    filtered_candidate_count: number;
    new_nodes_count: number;
    new_edges_count: number;
    dropped_by_budget: number;
    dropped_by_type_filter: number;
    dropped_by_relation_filter: number;
    dropped_neighbors: number;
    scanned_rows: number;
    budget_applied?: Record<string, unknown>;
  };
};

export type DiscoveryGraphSourceTag = "discovery_base" | "forced_render" | "manual_restore" | `expand:${string}`;

export type DiscoveryNodeExpandUiState = "collapsed" | "expanding" | "expanded" | "terminal";

export type NodeExpandSession = {
  sourceNodeId: string;
  isExpanded: boolean;
  requestFingerprint: string;
  addedNodeIds: string[];
  addedEdgeIds: string[];
  droppedNodeIds: string[];
  filtersSnapshot: {
    entityTypes: string[];
    relationTypes: string[];
  };
};

export type GraphDiscoveryResp = {
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  request_space: string;
  space_meta: SpaceMeta;
  warnings?: string[];
  facets: {
    entity_types: GraphDiscoveryEntityFacetItem[];
    relation_types: GraphDiscoveryRelationFacetItem[];
    query_summary: GraphDiscoveryQuerySummary;
    layers: GraphDiscoveryLayerFacetItem[];
    seeds: GraphDiscoverySeedFacetItem[];
  };
  stats: {
    ranking_mode?: "v1" | "layered_multiseed";
    seed_count: number;
    seeds_count?: number;
    candidate_count: number;
    node_count: number;
    edge_count: number;
    final_nodes?: number;
    final_edges?: number;
    truncated: boolean;
    core_count?: number;
    shared_count?: number;
    local_count?: number;
    supplement_count?: number;
    dropped_nodes: number;
    dropped_edges: number;
    dropped_neighbors: number;
    dropped_by_budget?: number;
    dropped_by_type_budget?: number;
    dropped_generic_hubs?: number;
    recall_candidate_count: number;
    kept_candidate_count: number;
    budget_applied?: Record<string, unknown>;
  };
  dropped_candidates?: GraphDiscoveryDroppedCandidate[];
  node_capabilities?: GraphDiscoveryNodeCapability[];
};

export type DiscoveryEntityCandidateQueryState = {
  q: string;
  searchInName: boolean;
  searchInDescription: boolean;
  searchInType: boolean;
  searchInRawId: boolean;
  entityType: string;
  source: string;
  entityRawId: string;
  entityRawIdMode: "contains" | "prefix" | "exact";
};

export type DiscoveryEntityCandidateItem = NodeBrief & {
  vid: number;
  raw_id: string;
  snippet: string;
  description: string;
};

export type DiscoveryEntityCandidatesResp = {
  items: DiscoveryEntityCandidateItem[];
  page: number;
  page_size: number;
  returned: number;
  has_more: boolean;
  next_page: number | null;
  meta?: Record<string, unknown>;
  space_meta: SpaceMeta;
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
