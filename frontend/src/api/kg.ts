import { apiGet, apiPost } from "./http";
import type {
  EdgeDetailResp,
  EdgePatchResp,
  EditableFieldsResp,
  EntityTypeItem,
  EdgeSearchResp,
  EdgeSuggestResp,
  DiscoveryEntityCandidatesResp,
  GraphDiscoveryExpandResp,
  GraphDiscoveryResp,
  MultiEntityGraphResp,
  ExpandResp,
  NodeDetailResp,
  NodePatchResp,
  RawIdSuggestResp,
  RelationTypesResp,
  SearchResp,
  SubgraphResp,
  SuggestResp,
} from "../types/kg";

type SearchParams = {
  q: string;
  search_in_name: boolean;
  search_in_description: boolean;
  entity_type: string | null;
  source: string | null;
  entity_raw_id: string | null;
  entity_raw_id_mode: "contains" | "prefix" | "exact";
  include_edges?: boolean;
  signal?: AbortSignal;
};

type SubgraphParams = {
  root_vid: number;
  hop: number;
  relations: string[];
  max_nodes: number;
  max_edges: number;
};

type ExpandParams = {
  from_vid: number;
  relations: string[];
  existing_node_ids: number[];
  max_nodes: number;
  max_edges: number;
};

type SuggestParams = {
  q: string;
  limit: number;
  entity_type?: string;
  source?: string;
  signal?: AbortSignal;
};

type RawIdSuggestParams = {
  q: string;
  limit: number;
  entity_type?: string;
  source?: string;
  signal?: AbortSignal;
};

type EdgeSuggestParams = {
  q: string;
  limit: number;
  relation?: string;
  source_db?: string;
  signal?: AbortSignal;
};

type EdgeSearchParams = {
  q: string;
  search_in_relation: boolean;
  search_in_props: boolean;
  source_db: string | null;
  relation: string | null;
  limit: number;
};

type MultiEntityGraphParams = {
  vids: number[];
  direct_only: boolean;
  explain_paths: boolean;
  k: number;
  relations: string[];
  max_nodes: number;
  max_edges: number;
  per_pair_path_limit: number;
  ignore_direction: boolean;
};

type MultiEntityGraphApplyPathsParams = {
  base_request: MultiEntityGraphParams;
  choices: Array<{
    u: number;
    v: number;
    chosen_index: number;
  }>;
};

type GraphDiscoveryParams = {
  seed_vids: number[];
  allowed_entity_types: string[];
  allowed_relation_types: string[];
  max_nodes: number;
  max_edges: number;
  top_k_per_type: number;
  include_candidate_candidate_edges: boolean;
  include_seed_seed_edges?: boolean;
  hop: number;
  ranking_mode?: "v1" | "layered_multiseed";
};

type DiscoveryEntityCandidatesParams = {
  q: string;
  page: number;
  page_size: number;
  search_in_name: boolean;
  search_in_description: boolean;
  search_in_type: boolean;
  search_in_raw_id: boolean;
  entity_type: string | null;
  source: string | null;
  entity_raw_id: string | null;
  entity_raw_id_mode: "contains" | "prefix" | "exact";
  signal?: AbortSignal;
};

export async function search(params: SearchParams): Promise<SearchResp> {
  const { signal, ...body } = params;
  return apiPost<SearchResp>("/api/search", body, { signal });
}

export async function entityTypes(): Promise<EntityTypeItem[]> {
  return apiGet<EntityTypeItem[]>("/api/entity_types");
}

export async function subgraph(body: SubgraphParams): Promise<SubgraphResp> {
  return apiPost<SubgraphResp>("/api/subgraph", body);
}

export async function expand(body: ExpandParams): Promise<ExpandResp> {
  return apiPost<ExpandResp>("/api/expand", body);
}

export async function relationTypes(params: {
  q?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
} = {}): Promise<RelationTypesResp> {
  const search = new URLSearchParams();
  if (params.q?.trim()) search.set("q", params.q.trim());
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  const suffix = query ? `?${query}` : "";
  return apiGet<RelationTypesResp>(`/api/relation_types${suffix}`, { signal: params.signal });
}

export async function nodeDetail(vid: number): Promise<NodeDetailResp> {
  return apiGet<NodeDetailResp>(`/api/node/${vid}`);
}

export async function edgeDetail(body: {
  edge_type: string;
  src: number;
  dst: number;
  rank: string;
}): Promise<EdgeDetailResp> {
  return apiPost<EdgeDetailResp>("/api/edge_detail", body);
}

export async function editableFields(): Promise<EditableFieldsResp> {
  return apiGet<EditableFieldsResp>("/api/schema/editable_fields");
}

export async function patchNode(
  vid: number,
  body: {
    set: Record<string, unknown>;
    expected_version: number;
    updated_by: string;
  }
): Promise<NodePatchResp> {
  return apiFetchJson<NodePatchResp>(`/api/node/${vid}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function patchEdge(body: {
  edge_type: string;
  src: number;
  dst: number;
  rank: string;
  set: Record<string, unknown>;
  expected_version: number;
  updated_by: string;
}): Promise<EdgePatchResp> {
  return apiFetchJson<EdgePatchResp>(`/api/edge`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export async function suggest({
  q,
  limit,
  entity_type,
  source,
  signal,
}: SuggestParams): Promise<SuggestResp> {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  if (entity_type?.trim()) params.set("entity_type", entity_type.trim());
  if (source?.trim()) params.set("source", source.trim());

  const resp = await fetch(`/api/suggest?${params.toString()}`, { signal });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as SuggestResp;
}

export async function suggestRawId({
  q,
  limit,
  entity_type,
  source,
  signal,
}: RawIdSuggestParams): Promise<RawIdSuggestResp> {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  if (entity_type?.trim()) params.set("entity_type", entity_type.trim());
  if (source?.trim()) params.set("source", source.trim());

  const resp = await fetch(`/api/suggest_raw_id?${params.toString()}`, { signal });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as RawIdSuggestResp;
}

export async function edgeSuggest({
  q,
  limit,
  relation,
  source_db,
  signal,
}: EdgeSuggestParams): Promise<EdgeSuggestResp> {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  if (relation?.trim()) params.set("relation", relation.trim());
  if (source_db?.trim()) params.set("source_db", source_db.trim());

  const resp = await fetch(`/api/edge_suggest?${params.toString()}`, { signal });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as EdgeSuggestResp;
}

export async function edgeSearch(body: EdgeSearchParams): Promise<EdgeSearchResp> {
  return apiPost<EdgeSearchResp>("/api/edge_search", body);
}

export async function multiEntityGraph(body: MultiEntityGraphParams): Promise<MultiEntityGraphResp> {
  return apiPost<MultiEntityGraphResp>("/api/multi_entity_graph", body);
}

export async function multiEntityGraphApplyPaths(body: MultiEntityGraphApplyPathsParams): Promise<MultiEntityGraphResp> {
  return apiPost<MultiEntityGraphResp>("/api/multi_entity_graph_apply_paths", body);
}

export async function graphDiscovery(body: GraphDiscoveryParams): Promise<GraphDiscoveryResp> {
  return apiPost<GraphDiscoveryResp>("/api/graph/discovery", body);
}

export async function graphDiscoveryExpand(body: {
  target_node_id: number;
  rendered_node_ids: number[];
  rendered_edge_ids?: string[];
  allowed_entity_types: string[];
  allowed_relation_types: string[];
  expand_max_new_nodes: number;
  expand_max_new_edges: number;
  expand_top_k_per_type: number;
  expand_max_hop: number;
}): Promise<GraphDiscoveryExpandResp> {
  return apiPost<GraphDiscoveryExpandResp>("/api/graph/discovery/expand", body);
}

export async function discoveryEntityCandidates(
  params: DiscoveryEntityCandidatesParams
): Promise<DiscoveryEntityCandidatesResp> {
  const { signal, ...body } = params;
  return apiPost<DiscoveryEntityCandidatesResp>("/api/discovery/entity_candidates", body, { signal });
}

async function apiFetchJson<T>(path: string, init: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${text}`);
  }
  return (await resp.json()) as T;
}
