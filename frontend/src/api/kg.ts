import { apiFetchJson, apiGet, apiPost } from "./http";
import type {
  EdgeDetailResp,
  EdgePatchResp,
  EditableFieldsResp,
  EntityTypeItem,
  DiscoveryEntityCandidatesResp,
  GraphDiscoveryExpandResp,
  GraphDiscoveryResp,
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
  spaceName?: string;
};

type SubgraphParams = {
  root_vid: number;
  hop: number;
  relations: string[];
  max_nodes: number;
  max_edges: number;
  signal?: AbortSignal;
  spaceName?: string;
};

type ExpandParams = {
  from_vid: number;
  relations: string[];
  existing_node_ids: number[];
  max_nodes: number;
  max_edges: number;
  signal?: AbortSignal;
  spaceName?: string;
};

type SuggestParams = {
  q: string;
  limit: number;
  entity_type?: string;
  source?: string;
  signal?: AbortSignal;
  spaceName?: string;
};

type RawIdSuggestParams = {
  q: string;
  limit: number;
  entity_type?: string;
  source?: string;
  signal?: AbortSignal;
  spaceName?: string;
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
  signal?: AbortSignal;
  spaceName?: string;
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
  spaceName?: string;
};

export async function search(params: SearchParams): Promise<SearchResp> {
  const { signal, spaceName, ...body } = params;
  return apiPost<SearchResp>("/api/search", body, { signal, spaceName });
}

export async function entityTypes(params: { signal?: AbortSignal; spaceName?: string } = {}): Promise<EntityTypeItem[]> {
  return apiGet<EntityTypeItem[]>("/api/entity_types", { signal: params.signal, spaceName: params.spaceName });
}

export async function subgraph(body: SubgraphParams): Promise<SubgraphResp> {
  const { signal, spaceName, ...payload } = body;
  return apiPost<SubgraphResp>("/api/subgraph", payload, { signal, spaceName });
}

export async function expand(body: ExpandParams): Promise<ExpandResp> {
  const { signal, spaceName, ...payload } = body;
  return apiPost<ExpandResp>("/api/expand", payload, { signal, spaceName });
}

export async function relationTypes(params: {
  q?: string;
  limit?: number;
  offset?: number;
  signal?: AbortSignal;
  spaceName?: string;
} = {}): Promise<RelationTypesResp> {
  const search = new URLSearchParams();
  if (params.q?.trim()) search.set("q", params.q.trim());
  if (typeof params.limit === "number") search.set("limit", String(params.limit));
  if (typeof params.offset === "number") search.set("offset", String(params.offset));
  const query = search.toString();
  const suffix = query ? `?${query}` : "";
  return apiGet<RelationTypesResp>(`/api/relation_types${suffix}`, { signal: params.signal, spaceName: params.spaceName });
}

export async function nodeDetail(vid: number, options: { signal?: AbortSignal; spaceName?: string } = {}): Promise<NodeDetailResp> {
  return apiGet<NodeDetailResp>(`/api/node/${vid}`, { signal: options.signal, spaceName: options.spaceName });
}

export async function edgeDetail(body: {
  edge_type: string;
  src: number;
  dst: number;
  rank: string;
  signal?: AbortSignal;
  spaceName?: string;
}): Promise<EdgeDetailResp> {
  const { signal, spaceName, ...payload } = body;
  return apiPost<EdgeDetailResp>("/api/edge_detail", payload, { signal, spaceName });
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
  },
  options: { signal?: AbortSignal; spaceName?: string } = {}
): Promise<NodePatchResp> {
  return apiFetchJson<NodePatchResp>(`/api/node/${vid}`, {
    method: "PATCH",
    body: JSON.stringify(body),
    signal: options.signal,
    spaceName: options.spaceName,
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
  signal?: AbortSignal;
  spaceName?: string;
}): Promise<EdgePatchResp> {
  const { signal, spaceName, ...payload } = body;
  return apiFetchJson<EdgePatchResp>(`/api/edge`, {
    method: "PATCH",
    body: JSON.stringify(payload),
    signal,
    spaceName,
  });
}

export async function suggest({
  q,
  limit,
  entity_type,
  source,
  signal,
  spaceName,
}: SuggestParams): Promise<SuggestResp> {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  if (entity_type?.trim()) params.set("entity_type", entity_type.trim());
  if (source?.trim()) params.set("source", source.trim());

  return apiGet<SuggestResp>(`/api/suggest?${params.toString()}`, { signal, spaceName });
}

export async function suggestRawId({
  q,
  limit,
  entity_type,
  source,
  signal,
  spaceName,
}: RawIdSuggestParams): Promise<RawIdSuggestResp> {
  const params = new URLSearchParams();
  params.set("q", q);
  params.set("limit", String(limit));
  if (entity_type?.trim()) params.set("entity_type", entity_type.trim());
  if (source?.trim()) params.set("source", source.trim());

  return apiGet<RawIdSuggestResp>(`/api/suggest_raw_id?${params.toString()}`, { signal, spaceName });
}

export async function graphDiscovery(body: GraphDiscoveryParams): Promise<GraphDiscoveryResp> {
  const { signal, spaceName, ...payload } = body;
  return apiPost<GraphDiscoveryResp>("/api/graph/discovery", payload, { signal, spaceName });
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
  signal?: AbortSignal;
  spaceName?: string;
}): Promise<GraphDiscoveryExpandResp> {
  const { signal, spaceName, ...payload } = body;
  return apiPost<GraphDiscoveryExpandResp>("/api/graph/discovery/expand", payload, { signal, spaceName });
}

export async function discoveryEntityCandidates(
  params: DiscoveryEntityCandidatesParams
): Promise<DiscoveryEntityCandidatesResp> {
  const { signal, spaceName, ...body } = params;
  return apiPost<DiscoveryEntityCandidatesResp>("/api/discovery/entity_candidates", body, { signal, spaceName });
}
