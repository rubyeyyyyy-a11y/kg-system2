export type NodeBrief = {
  id: number;
  label: string;
  entity_type: string;
  raw_id?: string;
  source?: string;
  score?: number;
  snippet?: string;
};

export type EdgeBrief = {
  source: number;
  target: number;
  relation?: string;
  source_db?: string;
  is_explain?: boolean;
};

export type SearchResp = {
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  total_candidates: number;
};

export type SubgraphResp = {
  root_vid: number;
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  stats: { node_count: number; edge_count: number; truncated: boolean; dropped_nodes?: number };
};

export type ExpandResp = {
  added_nodes: NodeBrief[];
  added_edges: EdgeBrief[];
  stats: { node_count_after: number; dropped_nodes: number; policy: string };
};

export type NodeDetailResp = { vid: number; props: Record<string, unknown> };
export type EdgeDetailResp = { src: number; dst: number; props: Record<string, unknown> };

export type Sel =
  | { kind: "none" }
  | { kind: "node"; vid: number }
  | { kind: "edge"; src: number; dst: number; relation: string; source_db?: string };

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

export type EdgeSearchItem = {
  src: number;
  dst: number;
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
    node_count?: number;
    edge_count?: number;
    [k: string]: unknown;
  };
  path_candidates?: PairPathCandidate[];
};
