# Frontend Refactor Full Code

## src/types/kg.ts
```ts
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
```

## src/constants/kg.ts
```ts
export const TOP_N_VISIBLE = 30;
export const EXPAND_AUTO_REVEAL_TOPK = 20;

export const MIN_CHARS = 2;
export const SUGGEST_LIMIT = 12;
export const DEBOUNCE_MS = 250;
```

## src/api/http.ts
```ts
export async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as T;
}

export async function apiGet<T>(url: string): Promise<T> {
  const resp = await fetch(url);
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as T;
}
```

## src/api/kg.ts
```ts
import { apiGet, apiPost } from "./http";
import type {
  EdgeDetailResp,
  ExpandResp,
  NodeDetailResp,
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

export async function search(body: SearchParams): Promise<SearchResp> {
  return apiPost<SearchResp>("/api/search", body);
}

export async function subgraph(body: SubgraphParams): Promise<SubgraphResp> {
  return apiPost<SubgraphResp>("/api/subgraph", body);
}

export async function expand(body: ExpandParams): Promise<ExpandResp> {
  return apiPost<ExpandResp>("/api/expand", body);
}

export async function relationTypes(): Promise<string[]> {
  return apiGet<string[]>("/api/relation_types");
}

export async function nodeDetail(vid: number): Promise<NodeDetailResp> {
  return apiGet<NodeDetailResp>(`/api/node/${vid}`);
}

export async function edgeDetail(body: {
  src: number;
  dst: number;
  relation: string;
  source_db: string | null;
}): Promise<EdgeDetailResp> {
  return apiPost<EdgeDetailResp>("/api/edge_detail", body);
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
```

## src/utils/kg.ts
```ts
import type { EdgeBrief, NodeBrief } from "../types/kg";

export function relationDisplay(raw?: string): string {
  const s = String(raw || "").trim();
  if (!s) return "";
  return s.split("|")[0].trim();
}

export function edgeKey(e: EdgeBrief): string {
  return `${e.source}|${e.target}|${e.relation || ""}|${e.source_db || ""}`;
}

export function getNodeLabelById(
  vid: number | null | undefined,
  graphNodes: NodeBrief[],
  searchNodes: NodeBrief[]
): string {
  if (vid == null) return "-";
  const inGraph = graphNodes.find((n) => n.id === vid);
  if (inGraph?.label) return inGraph.label;
  const inSearch = searchNodes.find((n) => n.id === vid);
  if (inSearch?.label) return inSearch.label;
  return String(vid);
}
```

## src/hooks/useSuggest.ts
```ts
import { useEffect, useRef, useState } from "react";
import type { Dispatch, KeyboardEvent, RefObject, SetStateAction } from "react";
import { suggest as fetchSuggestApi } from "../api/kg";
import { DEBOUNCE_MS, MIN_CHARS, SUGGEST_LIMIT } from "../constants/kg";
import type { SuggestItem } from "../types/kg";

type UseSuggestParams = {
  q: string;
  entityType: string;
  source: string;
  onSelect: (item: SuggestItem) => void;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
};

type UseSuggestResult = {
  suggestOpen: boolean;
  suggestItems: SuggestItem[];
  suggestLoading: boolean;
  suggestError: string | null;
  suggestHighlightIndex: number;
  suggestWrapRef: RefObject<HTMLDivElement | null>;
  onInputChange: (value: string) => void;
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  setSuggestHighlightIndex: Dispatch<SetStateAction<number>>;
  openSuggestPanel: () => void;
  closeSuggestPanel: () => void;
  selectSuggestCandidate: (item: SuggestItem) => void;
};

export function useSuggest({
  q,
  entityType,
  source,
  onSelect,
  onQueryChange,
  onSearch,
}: UseSuggestParams): UseSuggestResult {
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestItems, setSuggestItems] = useState<SuggestItem[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [suggestHighlightIndex, setSuggestHighlightIndex] = useState(-1);

  const suggestWrapRef = useRef<HTMLDivElement>(null);
  const suggestAbortRef = useRef<AbortController | null>(null);
  const suggestReqIdRef = useRef(0);
  const suppressNextSuggestRef = useRef(false);
  const prevSuggestDepsRef = useRef<{ q: string; entityType: string; source: string }>({
    q: "",
    entityType: "",
    source: "",
  });

  function invalidateSuggestRequest() {
    suggestReqIdRef.current += 1;
    if (suggestAbortRef.current) {
      suggestAbortRef.current.abort();
      suggestAbortRef.current = null;
    }
  }

  function clearSuggestPanelState() {
    setSuggestOpen(false);
    setSuggestItems([]);
    setSuggestLoading(false);
    setSuggestError(null);
    setSuggestHighlightIndex(-1);
  }

  function closeSuggestPanel() {
    invalidateSuggestRequest();
    clearSuggestPanelState();
  }

  function openSuggestPanel() {
    setSuggestOpen(true);
  }

  async function fetchSuggest(keyword: string) {
    const reqId = suggestReqIdRef.current + 1;
    suggestReqIdRef.current = reqId;

    if (suggestAbortRef.current) suggestAbortRef.current.abort();
    const controller = new AbortController();
    suggestAbortRef.current = controller;

    setSuggestOpen(true);
    setSuggestLoading(true);
    setSuggestError(null);
    setSuggestHighlightIndex(-1);

    try {
      const json = await fetchSuggestApi({
        q: keyword,
        limit: SUGGEST_LIMIT,
        entity_type: entityType,
        source,
        signal: controller.signal,
      });

      if (reqId !== suggestReqIdRef.current) return;
      setSuggestItems(Array.isArray(json.items) ? json.items : []);
      setSuggestError(null);
      setSuggestOpen(true);
    } catch (e: unknown) {
      if (controller.signal.aborted) return;
      if (reqId !== suggestReqIdRef.current) return;
      const msg = e instanceof Error ? e.message : String(e);
      console.warn("suggest error:", msg);
      setSuggestItems([]);
      setSuggestError("候选请求失败（不影响搜索）");
      setSuggestOpen(true);
    } finally {
      if (reqId === suggestReqIdRef.current) setSuggestLoading(false);
    }
  }

  function selectSuggestCandidate(item: SuggestItem) {
    suppressNextSuggestRef.current = true;
    onSelect(item);
    closeSuggestPanel();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      if (!suggestOpen || suggestItems.length === 0) return;
      e.preventDefault();
      setSuggestHighlightIndex((prev) => (prev < 0 ? 0 : (prev + 1) % suggestItems.length));
      return;
    }

    if (e.key === "ArrowUp") {
      if (!suggestOpen || suggestItems.length === 0) return;
      e.preventDefault();
      setSuggestHighlightIndex((prev) => {
        if (prev < 0) return suggestItems.length - 1;
        return prev <= 0 ? suggestItems.length - 1 : prev - 1;
      });
      return;
    }

    if (e.key === "Enter") {
      if (suggestOpen && suggestItems.length > 0) {
        e.preventDefault();
        const idx = suggestHighlightIndex >= 0 ? suggestHighlightIndex : 0;
        const item = suggestItems[idx];
        if (item) selectSuggestCandidate(item);
        return;
      }
      closeSuggestPanel();
      onSearch();
      return;
    }

    if (e.key === "Escape" && suggestOpen) {
      e.preventDefault();
      closeSuggestPanel();
    }
  }

  function onInputChange(value: string) {
    onQueryChange(value);
  }

  useEffect(() => {
    const keyword = q.trim();
    const prev = prevSuggestDepsRef.current;
    const qChanged = prev.q !== keyword;
    const filterChanged = prev.entityType !== entityType || prev.source !== source;

    prevSuggestDepsRef.current = { q: keyword, entityType, source };

    if (suppressNextSuggestRef.current) {
      suppressNextSuggestRef.current = false;
      return;
    }

    if (keyword.length < MIN_CHARS) {
      closeSuggestPanel();
      return;
    }

    if (filterChanged && !suggestOpen && !qChanged) return;
    if (!qChanged && !filterChanged) return;

    const timer = window.setTimeout(() => {
      void fetchSuggest(keyword);
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [q, entityType, source, suggestOpen]);

  useEffect(() => {
    if (!suggestOpen) return;
    const onDocMouseDown = (e: MouseEvent) => {
      const el = suggestWrapRef.current;
      if (el && !el.contains(e.target as Node)) closeSuggestPanel();
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
    };
  }, [suggestOpen]);

  useEffect(() => {
    return () => {
      invalidateSuggestRequest();
    };
  }, []);

  return {
    suggestOpen,
    suggestItems,
    suggestLoading,
    suggestError,
    suggestHighlightIndex,
    suggestWrapRef,
    onInputChange,
    onKeyDown,
    setSuggestHighlightIndex,
    openSuggestPanel,
    closeSuggestPanel,
    selectSuggestCandidate,
  };
}
```

## src/hooks/useGraphData.ts
```ts
import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { expand, subgraph } from "../api/kg";
import { EXPAND_AUTO_REVEAL_TOPK } from "../constants/kg";
import type { EdgeBrief, ExpandProbeState, NodeBrief } from "../types/kg";
import { edgeKey } from "../utils/kg";

type GraphStats = Record<string, unknown> | null;

type UseGraphDataParams = {
  selectedNodeVid: number | null;
  onSelectNode: (vid: number) => void;
  onClearSelection: () => void;
};

type UseGraphDataResult = {
  rootVid: number | null;
  setRootVid: Dispatch<SetStateAction<number | null>>;
  hop: number;
  setHop: Dispatch<SetStateAction<number>>;
  relations: string[];
  setRelations: Dispatch<SetStateAction<string[]>>;
  loadingGraph: boolean;
  graphNodes: NodeBrief[];
  graphEdges: EdgeBrief[];
  graphStats: GraphStats;
  manualRevealedNodeIds: Set<number>;
  manualHiddenNodeIds: Set<number>;
  nodeGroupRootById: Record<number, number>;
  expandedSourceNodeIds: Set<number>;
  hiddenNodesCollapsed: boolean;
  setHiddenNodesCollapsed: Dispatch<SetStateAction<boolean>>;
  panelGroupCollapsed: Record<string, boolean>;
  setPanelGroupCollapsed: Dispatch<SetStateAction<Record<string, boolean>>>;
  expandProbeByVid: Record<number, ExpandProbeState>;
  loadSubgraphWithParams: (nextRoot: number, nextHop: number, nextRelations: string[]) => Promise<void>;
  loadSubgraph: (nextRoot: number) => Promise<void>;
  expand1hop: (fromVid: number) => Promise<void>;
  reroot1hop: (vid: number) => Promise<void>;
  revealNode: (vid: number, autoSelect?: boolean) => void;
  unrevealNode: (vid: number) => void;
  collapseExpandFromNode: (fromVid: number) => void;
  resetExpandProbeCache: () => void;
  probeExpand1hop: (fromVid: number) => Promise<void>;
};

export function useGraphData({
  selectedNodeVid,
  onSelectNode,
  onClearSelection,
}: UseGraphDataParams): UseGraphDataResult {
  const [rootVid, setRootVid] = useState<number | null>(null);
  const [hop, setHop] = useState(1);
  const [relations, setRelations] = useState<string[]>([]);
  const [loadingGraph, setLoadingGraph] = useState(false);

  const [graphNodes, setGraphNodes] = useState<NodeBrief[]>([]);
  const [graphEdges, setGraphEdges] = useState<EdgeBrief[]>([]);
  const [graphStats, setGraphStats] = useState<GraphStats>(null);

  const [manualRevealedNodeIds, setManualRevealedNodeIds] = useState<Set<number>>(new Set());
  const [manualHiddenNodeIds, setManualHiddenNodeIds] = useState<Set<number>>(new Set());
  const [nodeGroupRootById, setNodeGroupRootById] = useState<Record<number, number>>({});
  const [expandedSourceNodeIds, setExpandedSourceNodeIds] = useState<Set<number>>(new Set());

  const [hiddenNodesCollapsed, setHiddenNodesCollapsed] = useState(false);
  const [panelGroupCollapsed, setPanelGroupCollapsed] = useState<Record<string, boolean>>({});
  const [expandProbeByVid, setExpandProbeByVid] = useState<Record<number, ExpandProbeState>>({});

  const rootVidRef = useRef<number | null>(null);
  const relationsRef = useRef<string[]>([]);
  const graphNodesRef = useRef<NodeBrief[]>([]);
  const expandProbeTokenByVidRef = useRef<Record<number, number>>({});

  useEffect(() => {
    rootVidRef.current = rootVid;
  }, [rootVid]);

  useEffect(() => {
    relationsRef.current = relations;
  }, [relations]);

  useEffect(() => {
    graphNodesRef.current = graphNodes;
  }, [graphNodes]);

  function resetPanelGroupingForNewRoot(nodes: NodeBrief[], nextRoot: number) {
    const m: Record<number, number> = {};
    for (const n of nodes) m[n.id] = nextRoot;
    setNodeGroupRootById(m);
    setPanelGroupCollapsed({ [String(nextRoot)]: false });
  }

  function resetExpandProbeCache() {
    setExpandProbeByVid({});
    expandProbeTokenByVidRef.current = {};
  }

  async function loadSubgraphWithParams(nextRoot: number, nextHop: number, nextRelations: string[]) {
    setLoadingGraph(true);
    try {
      const json = await subgraph({
        root_vid: nextRoot,
        hop: nextHop,
        relations: nextRelations,
        max_nodes: 80,
        max_edges: 300,
      });

      setRootVid(nextRoot);
      setGraphNodes(json.nodes);
      setGraphEdges(json.edges);
      setGraphStats(json.stats as Record<string, unknown>);

      setManualRevealedNodeIds(new Set());
      setManualHiddenNodeIds(new Set());
      setExpandedSourceNodeIds(new Set());
      setHiddenNodesCollapsed(false);

      resetExpandProbeCache();
      resetPanelGroupingForNewRoot(json.nodes, nextRoot);
      onClearSelection();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
    } finally {
      setLoadingGraph(false);
    }
  }

  async function loadSubgraph(nextRoot: number) {
    await loadSubgraphWithParams(nextRoot, hop, relations);
  }

  async function expand1hop(fromVid: number) {
    if (!rootVid) return;
    setLoadingGraph(true);
    try {
      const existingIds = graphNodes.map((n) => n.id);
      const json = await expand({
        from_vid: fromVid,
        relations,
        existing_node_ids: existingIds,
        max_nodes: 80,
        max_edges: 300,
      });

      if ((json.added_nodes?.length || 0) === 0 && (json.added_edges?.length || 0) === 0) {
        setExpandProbeByVid((prev) => ({ ...prev, [fromVid]: "noextra" }));
        alert("该节点暂无可扩展的 1-hop 邻居，或邻居已全部在当前图中。");
        return;
      }
      setExpandProbeByVid((prev) => ({ ...prev, [fromVid]: "hasextra" }));

      const nodeMap = new Map<number, NodeBrief>();
      for (const n of graphNodes) nodeMap.set(n.id, n);
      for (const n of json.added_nodes) nodeMap.set(n.id, n);

      const edgeSet = new Set<string>();
      const mergedEdges: EdgeBrief[] = [];
      for (const e of graphEdges) {
        const k = edgeKey(e);
        if (!edgeSet.has(k)) {
          edgeSet.add(k);
          mergedEdges.push(e);
        }
      }
      for (const e of json.added_edges) {
        const k = edgeKey(e);
        if (!edgeSet.has(k)) {
          edgeSet.add(k);
          mergedEdges.push(e);
        }
      }

      setGraphNodes(Array.from(nodeMap.values()));
      setGraphEdges(mergedEdges);
      setGraphStats({
        ...(graphStats || {}),
        node_count: json.stats.node_count_after,
        policy: json.stats.policy,
        dropped_nodes: json.stats.dropped_nodes,
      });

      setNodeGroupRootById((prev) => {
        const next = { ...prev };
        for (const n of json.added_nodes) {
          if (!(n.id in next)) next[n.id] = fromVid;
        }
        return next;
      });

      setPanelGroupCollapsed((prev) => {
        const k = String(fromVid);
        if (k in prev) return prev;
        return { ...prev, [k]: fromVid === rootVid ? false : true };
      });

      setExpandedSourceNodeIds((prev) => {
        const next = new Set(prev);
        next.add(fromVid);
        return next;
      });

      const autoShowIds = json.added_nodes.slice(0, EXPAND_AUTO_REVEAL_TOPK).map((n) => n.id);
      if (autoShowIds.length > 0) {
        setManualRevealedNodeIds((prev) => {
          const next = new Set(prev);
          for (const id of autoShowIds) next.add(id);
          return next;
        });

        setManualHiddenNodeIds((prev) => {
          const next = new Set(prev);
          let changed = false;
          for (const id of autoShowIds) {
            if (next.has(id)) {
              next.delete(id);
              changed = true;
            }
          }
          return changed ? next : prev;
        });

        onSelectNode(autoShowIds[0]);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
    } finally {
      setLoadingGraph(false);
    }
  }

  async function reroot1hop(vid: number) {
    setLoadingGraph(true);
    try {
      const json = await subgraph({
        root_vid: vid,
        hop: 1,
        relations,
        max_nodes: 80,
        max_edges: 300,
      });

      setHop(1);
      setRootVid(vid);
      setGraphNodes(json.nodes);
      setGraphEdges(json.edges);
      setGraphStats(json.stats as Record<string, unknown>);

      setManualRevealedNodeIds(new Set());
      setManualHiddenNodeIds(new Set());
      setExpandedSourceNodeIds(new Set());
      setHiddenNodesCollapsed(false);

      resetExpandProbeCache();
      resetPanelGroupingForNewRoot(json.nodes, vid);
      onClearSelection();
      onSelectNode(vid);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
    } finally {
      setLoadingGraph(false);
    }
  }

  function revealNode(vid: number, autoSelect = false) {
    setManualHiddenNodeIds((prev) => {
      if (!prev.has(vid)) return prev;
      const next = new Set(prev);
      next.delete(vid);
      return next;
    });
    setManualRevealedNodeIds((prev) => {
      if (prev.has(vid)) return prev;
      const next = new Set(prev);
      next.add(vid);
      return next;
    });

    if (autoSelect) onSelectNode(vid);
  }

  function unrevealNode(vid: number) {
    if (rootVid != null && vid === rootVid) return;
    setManualHiddenNodeIds((prev) => {
      if (prev.has(vid)) return prev;
      const next = new Set(prev);
      next.add(vid);
      return next;
    });
    setManualRevealedNodeIds((prev) => {
      if (!prev.has(vid)) return prev;
      const next = new Set(prev);
      next.delete(vid);
      return next;
    });

    if (selectedNodeVid === vid) onClearSelection();
  }

  function collapseExpandFromNode(fromVid: number) {
    const targetIds = graphNodes
      .filter((n) => nodeGroupRootById[n.id] === fromVid && n.id !== fromVid)
      .map((n) => n.id);

    if (targetIds.length === 0) {
      alert("当前节点没有可关闭的 Expand 展开内容。");
      return;
    }

    setManualRevealedNodeIds((prev) => {
      const next = new Set(prev);
      for (const id of targetIds) next.delete(id);
      return next;
    });

    setManualHiddenNodeIds((prev) => {
      const next = new Set(prev);
      for (const id of targetIds) {
        if (rootVid != null && id === rootVid) continue;
        next.add(id);
      }
      return next;
    });

    if (selectedNodeVid != null && targetIds.includes(selectedNodeVid)) onClearSelection();

    setExpandedSourceNodeIds((prev) => {
      const next = new Set(prev);
      next.delete(fromVid);
      return next;
    });
  }

  async function probeExpand1hop(fromVid: number) {
    const curRoot = rootVidRef.current;
    const curGraphNodes = graphNodesRef.current;
    const curRelations = relationsRef.current;

    if (curRoot == null) return;
    const existsInGraph = curGraphNodes.some((n) => n.id === fromVid);
    if (!existsInGraph) return;

    const nextToken = (expandProbeTokenByVidRef.current[fromVid] || 0) + 1;
    expandProbeTokenByVidRef.current[fromVid] = nextToken;
    setExpandProbeByVid((prev) => ({ ...prev, [fromVid]: "loading" }));

    try {
      const existingIds = curGraphNodes.map((n) => n.id);
      const json = await expand({
        from_vid: fromVid,
        relations: curRelations,
        existing_node_ids: existingIds,
        max_nodes: 20,
        max_edges: 200,
      });

      if (expandProbeTokenByVidRef.current[fromVid] !== nextToken) return;

      const addedN = json.added_nodes?.length || 0;
      const addedE = json.added_edges?.length || 0;
      const droppedRaw = (json.stats as Record<string, unknown>)?.dropped_nodes;
      const dropped = typeof droppedRaw === "number" ? droppedRaw : Number(droppedRaw ?? 0);

      const state: ExpandProbeState =
        addedN === 0 && addedE === 0 && dropped === 0 ? "noextra" : "hasextra";

      setExpandProbeByVid((prev) => ({ ...prev, [fromVid]: state }));
    } catch {
      if (expandProbeTokenByVidRef.current[fromVid] !== nextToken) return;
      setExpandProbeByVid((prev) => ({ ...prev, [fromVid]: "hasextra" }));
    }
  }

  useEffect(() => {
    if (selectedNodeVid == null) return;
    void probeExpand1hop(selectedNodeVid);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedNodeVid]);

  return {
    rootVid,
    setRootVid,
    hop,
    setHop,
    relations,
    setRelations,
    loadingGraph,
    graphNodes,
    graphEdges,
    graphStats,
    manualRevealedNodeIds,
    manualHiddenNodeIds,
    nodeGroupRootById,
    expandedSourceNodeIds,
    hiddenNodesCollapsed,
    setHiddenNodesCollapsed,
    panelGroupCollapsed,
    setPanelGroupCollapsed,
    expandProbeByVid,
    loadSubgraphWithParams,
    loadSubgraph,
    expand1hop,
    reroot1hop,
    revealNode,
    unrevealNode,
    collapseExpandFromNode,
    resetExpandProbeCache,
    probeExpand1hop,
  };
}
```

## src/hooks/useVisibilityRanking.ts
```ts
import { useMemo } from "react";
import { TOP_N_VISIBLE } from "../constants/kg";
import type { EdgeBrief, NodeBrief } from "../types/kg";
import { getNodeLabelById } from "../utils/kg";

type PanelGroup = {
  groupRoot: number;
  nodes: NodeBrief[];
  isRootGroup: boolean;
  title: string;
};

type UseVisibilityRankingParams = {
  graphNodes: NodeBrief[];
  graphEdges: EdgeBrief[];
  rootVid: number | null;
  manualHiddenNodeIds: Set<number>;
  manualRevealedNodeIds: Set<number>;
  showSelfLoops: boolean;
  nodeGroupRootById: Record<number, number>;
  searchNodes: NodeBrief[];
};

type UseVisibilityRankingResult = {
  visibleGraphNodes: NodeBrief[];
  hiddenGraphNodes: NodeBrief[];
  visibleNodeIdSet: Set<number>;
  visibleGraphEdges: EdgeBrief[];
  hiddenSelfLoopCount: number;
  visibleSelfLoopCount: number;
  autoVisibleTopIds: Set<number>;
  rankedGraphNodes: NodeBrief[];
  lowPriorityNodeIds: Set<number>;
  visibleNodeHopLevelMap: Map<number, number>;
  panelNodes: NodeBrief[];
  panelGroups: PanelGroup[];
  hiddenCount: number;
  visibleCount: number;
};

export function useVisibilityRanking({
  graphNodes,
  graphEdges,
  rootVid,
  manualHiddenNodeIds,
  manualRevealedNodeIds,
  showSelfLoops,
  nodeGroupRootById,
  searchNodes,
}: UseVisibilityRankingParams): UseVisibilityRankingResult {
  const {
    visibleGraphNodes,
    hiddenGraphNodes,
    visibleNodeIdSet,
    visibleGraphEdges,
    hiddenSelfLoopCount,
    visibleSelfLoopCount,
    autoVisibleTopIds,
    rankedGraphNodes,
    lowPriorityNodeIds,
  } = useMemo(() => {
    const nodeMap = new Map<number, NodeBrief>();
    for (const n of graphNodes) nodeMap.set(n.id, n);

    const degreeMap = new Map<number, number>();
    const directToRootSet = new Set<number>();
    for (const n of graphNodes) degreeMap.set(n.id, 0);

    for (const e of graphEdges) {
      degreeMap.set(e.source, (degreeMap.get(e.source) || 0) + 1);
      degreeMap.set(e.target, (degreeMap.get(e.target) || 0) + 1);

      if (rootVid != null) {
        if (e.source === rootVid && e.target !== rootVid) directToRootSet.add(e.target);
        if (e.target === rootVid && e.source !== rootVid) directToRootSet.add(e.source);
      }
    }

    const ranked = [...graphNodes].sort((a, b) => {
      const aIsRoot = rootVid != null && a.id === rootVid ? 1 : 0;
      const bIsRoot = rootVid != null && b.id === rootVid ? 1 : 0;
      if (aIsRoot !== bIsRoot) return bIsRoot - aIsRoot;

      const aDirect = directToRootSet.has(a.id) ? 1 : 0;
      const bDirect = directToRootSet.has(b.id) ? 1 : 0;
      if (aDirect !== bDirect) return bDirect - aDirect;

      const aDeg = degreeMap.get(a.id) || 0;
      const bDeg = degreeMap.get(b.id) || 0;
      if (aDeg !== bDeg) return bDeg - aDeg;

      return a.id - b.id;
    });

    const topSet = new Set<number>(ranked.slice(0, TOP_N_VISIBLE).map((n) => n.id));
    if (rootVid != null) topSet.add(rootVid);

    const finalVisibleIds = new Set<number>();
    for (const id of topSet) if (nodeMap.has(id)) finalVisibleIds.add(id);
    for (const id of manualRevealedNodeIds) if (nodeMap.has(id)) finalVisibleIds.add(id);
    if (rootVid != null && nodeMap.has(rootVid)) finalVisibleIds.add(rootVid);
    for (const id of manualHiddenNodeIds) {
      if (rootVid != null && id === rootVid) continue;
      finalVisibleIds.delete(id);
    }

    const visibleNodes = ranked.filter((n) => finalVisibleIds.has(n.id));
    const hiddenNodes = ranked.filter((n) => !finalVisibleIds.has(n.id));

    const edgeCandidates = graphEdges.filter(
      (e) => finalVisibleIds.has(e.source) && finalVisibleIds.has(e.target)
    );
    const selfLoops = edgeCandidates.filter((e) => e.source === e.target);
    const nonSelfLoops = edgeCandidates.filter((e) => e.source !== e.target);
    const visibleEdges = showSelfLoops ? edgeCandidates : nonSelfLoops;

    const lowPriorityIds = new Set<number>();
    for (const n of ranked) if (!topSet.has(n.id)) lowPriorityIds.add(n.id);

    return {
      visibleGraphNodes: visibleNodes,
      hiddenGraphNodes: hiddenNodes,
      visibleNodeIdSet: finalVisibleIds,
      visibleGraphEdges: visibleEdges,
      hiddenSelfLoopCount: selfLoops.length,
      visibleSelfLoopCount: showSelfLoops ? selfLoops.length : 0,
      autoVisibleTopIds: topSet,
      rankedGraphNodes: ranked,
      lowPriorityNodeIds: lowPriorityIds,
    };
  }, [graphNodes, graphEdges, rootVid, manualRevealedNodeIds, manualHiddenNodeIds, showSelfLoops]);

  const visibleNodeHopLevelMap = useMemo(() => {
    const m = new Map<number, number>();
    for (const n of visibleGraphNodes) m.set(n.id, 99);
    if (rootVid == null || !visibleNodeIdSet.has(rootVid)) return m;

    const adj = new Map<number, number[]>();
    for (const n of visibleGraphNodes) adj.set(n.id, []);
    for (const e of visibleGraphEdges) {
      if (!visibleNodeIdSet.has(e.source) || !visibleNodeIdSet.has(e.target)) continue;
      adj.get(e.source)?.push(e.target);
      if (e.source !== e.target) adj.get(e.target)?.push(e.source);
    }

    const q = [rootVid];
    m.set(rootVid, 0);
    let head = 0;
    while (head < q.length) {
      const cur = q[head++];
      const curLvl = m.get(cur) ?? 99;
      for (const nb of adj.get(cur) || []) {
        if ((m.get(nb) ?? 99) > curLvl + 1) {
          m.set(nb, curLvl + 1);
          q.push(nb);
        }
      }
    }
    return m;
  }, [visibleGraphNodes, visibleGraphEdges, visibleNodeIdSet, rootVid]);

  const panelNodes = useMemo(() => {
    const manualHiddenTopIds = new Set<number>();
    for (const id of manualHiddenNodeIds) {
      if (rootVid != null && id === rootVid) continue;
      if (autoVisibleTopIds.has(id)) manualHiddenTopIds.add(id);
    }

    const panelIdSet = new Set<number>([...lowPriorityNodeIds, ...manualHiddenTopIds]);
    return rankedGraphNodes.filter((n) => panelIdSet.has(n.id));
  }, [rankedGraphNodes, lowPriorityNodeIds, manualHiddenNodeIds, autoVisibleTopIds, rootVid]);

  const panelGroups = useMemo(() => {
    const groups = new Map<number, NodeBrief[]>();
    const fallback = rootVid ?? -1;

    for (const n of panelNodes) {
      const g = nodeGroupRootById[n.id] ?? fallback;
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g)?.push(n);
    }

    const arr = Array.from(groups.entries()).map(([groupRoot, nodes]) => ({
      groupRoot,
      nodes,
      isRootGroup: rootVid != null && groupRoot === rootVid,
      title: `根节点：${getNodeLabelById(groupRoot, graphNodes, searchNodes)}`,
    }));

    arr.sort((a, b) => {
      if (a.isRootGroup !== b.isRootGroup) return a.isRootGroup ? -1 : 1;
      return a.groupRoot - b.groupRoot;
    });

    return arr;
  }, [panelNodes, nodeGroupRootById, rootVid, graphNodes, searchNodes]);

  return {
    visibleGraphNodes,
    hiddenGraphNodes,
    visibleNodeIdSet,
    visibleGraphEdges,
    hiddenSelfLoopCount,
    visibleSelfLoopCount,
    autoVisibleTopIds,
    rankedGraphNodes,
    lowPriorityNodeIds,
    visibleNodeHopLevelMap,
    panelNodes,
    panelGroups,
    hiddenCount: hiddenGraphNodes.length,
    visibleCount: visibleGraphNodes.length,
  };
}
```

## src/components/GraphCanvas.tsx
```tsx
import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";
import { Graph } from "@antv/g6";
import type { EdgeBrief } from "../types/kg";
import { relationDisplay } from "../utils/kg";

type G6Node = {
  id: string;
  label: string;
  data: Record<string, unknown>;
};

type G6Edge = {
  id: string;
  source: string;
  target: string;
  label: string;
  data: EdgeBrief;
};

type G6Data = {
  nodes: G6Node[];
  edges: G6Edge[];
};

type GraphCanvasProps = {
  g6Data: G6Data;
  edgeById: Map<string, EdgeBrief>;
  renderNodeLabels: boolean;
  renderEdgeLabels: boolean;
  edgeLabelSelectedDisplays: string[];
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onNodeClick: (vid: number) => void;
  onEdgeClick: (edgeId: string, edge: EdgeBrief) => void;
  containerStyle?: CSSProperties;
  registerApplyHighlight?: (
    fn: (nextNodeId: string | null, nextEdgeId: string | null, force?: boolean) => void
  ) => void;
};

export function GraphCanvas({
  g6Data,
  edgeById,
  renderNodeLabels,
  renderEdgeLabels,
  edgeLabelSelectedDisplays,
  selectedNodeId,
  selectedEdgeId,
  onNodeClick,
  onEdgeClick,
  containerStyle,
  registerApplyHighlight,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const edgeByIdRef = useRef<Map<string, EdgeBrief>>(new Map());
  const selectedNodeIdRef = useRef<string | null>(null);
  const selectedEdgeIdRef = useRef<string | null>(null);

  const renderNodeLabelsRef = useRef(true);
  const renderEdgeLabelsRef = useRef(false);
  const edgeLabelSelectedDisplaysRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    edgeByIdRef.current = edgeById;
  }, [edgeById]);

  useEffect(() => {
    renderNodeLabelsRef.current = renderNodeLabels;
  }, [renderNodeLabels]);

  useEffect(() => {
    renderEdgeLabelsRef.current = renderEdgeLabels;
  }, [renderEdgeLabels]);

  useEffect(() => {
    edgeLabelSelectedDisplaysRef.current = new Set(edgeLabelSelectedDisplays);
  }, [edgeLabelSelectedDisplays]);

  function applyHighlight(nextNodeId: string | null, nextEdgeId: string | null, force = false) {
    const g: any = graphRef.current;
    if (!g) return;

    const prevNodeId = selectedNodeIdRef.current;
    const prevEdgeId = selectedEdgeIdRef.current;

    const safeSetState = (id: string, state: unknown[]) => {
      try {
        g.setElementState(id, state);
      } catch {
        // ignore
      }
    };
    const safeZ = (id: string, z: number) => {
      try {
        g.setElementZIndex(id, z);
      } catch {
        // ignore
      }
    };

    if (!force) {
      if (prevNodeId && prevNodeId !== nextNodeId) safeSetState(prevNodeId, []);
      if (prevEdgeId && prevEdgeId !== nextEdgeId) safeSetState(prevEdgeId, []);
    }

    selectedNodeIdRef.current = nextNodeId;
    selectedEdgeIdRef.current = nextEdgeId;

    if (nextNodeId) {
      safeSetState(nextNodeId, ["selected"]);
      safeZ(nextNodeId, 10);
    }
    if (nextEdgeId) {
      safeSetState(nextEdgeId, ["selected"]);
      safeZ(nextEdgeId, 9);
    }

    if (force && !nextNodeId && prevNodeId) safeSetState(prevNodeId, []);
    if (force && !nextEdgeId && prevEdgeId) safeSetState(prevEdgeId, []);
  }

  useEffect(() => {
    if (registerApplyHighlight) registerApplyHighlight(applyHighlight);
  }, [registerApplyHighlight]);

  useEffect(() => {
    if (!containerRef.current) return;

    if (!graphRef.current) {
      graphRef.current = new Graph({
        container: containerRef.current,
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight,
        autoFit: "view",
        data: { nodes: [], edges: [] },
        layout: { type: "force" },
        node: {
          style: {
            labelText: (d: any) => (renderNodeLabelsRef.current ? String(d.label || "") : ""),
            labelPlacement: "bottom",
            size: (d: any) => {
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return 36;
              if (lvl === 1) return 31;
              if (lvl === 2) return 27;
              return 24;
            },
            fill: (d: any) => {
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return "#ff7a45";
              if (lvl === 1) return "#ffa940";
              if (lvl === 2) return "#91caff";
              return "#C6E5FF";
            },
            stroke: (d: any) => {
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return "#d4380d";
              if (lvl === 1) return "#d46b08";
              if (lvl === 2) return "#1677ff";
              return "#5B8FF9";
            },
            lineWidth: (d: any) => {
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return 3;
              if (lvl === 1) return 2.5;
              if (lvl === 2) return 2;
              return 1.5;
            },
            cursor: "pointer",
            interactive: true as any,
          },
          state: {
            selected: {
              lineWidth: 3,
              shadowBlur: 12,
              shadowColor: "#faad14",
              stroke: "#faad14",
            },
          },
        },
        edge: {
          style: {
            labelText: (d: any) => {
              const disp = relationDisplay(String(d.data?.relation || d.relation || d.label || ""));
              if (!renderEdgeLabelsRef.current) return "";
              if (!disp) return "";
              return edgeLabelSelectedDisplaysRef.current.has(disp) ? disp : "";
            },
            labelBackground: true,
            cursor: "pointer",
            interactive: true as any,
            lineWidth: 2,
          },
          state: {
            selected: {
              lineWidth: 4,
              shadowBlur: 10,
              shadowColor: "#faad14",
              stroke: "#faad14",
            },
          },
        },
        behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
      });

      graphRef.current.on("node:click", (evt: any) => {
        const itemId =
          evt?.target?.id ??
          evt?.item?.id ??
          (typeof evt?.item?.getID === "function" ? evt.item.getID() : undefined);

        const vid = Number(itemId);
        if (!Number.isFinite(vid)) return;

        applyHighlight(String(vid), null);
        onNodeClick(vid);
      });

      graphRef.current.on("edge:click", (evt: any) => {
        const edgeId =
          evt?.item?.id ??
          evt?.target?.id ??
          evt?.target?.cfg?.id ??
          evt?.target?.cfg?.parent?.id ??
          evt?.target?.cfg?.parent?.cfg?.id;

        if (!edgeId) return;
        applyHighlight(null, String(edgeId));

        const e = edgeByIdRef.current.get(String(edgeId));
        if (!e) return;
        onEdgeClick(String(edgeId), e);
      });
    }

    const onResize = () => {
      const g: any = graphRef.current;
      const el = containerRef.current;
      if (!g || !el) return;
      try {
        g.setSize(el.clientWidth, el.clientHeight);
      } catch {
        // ignore
      }
    };

    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
    };
  }, [onNodeClick, onEdgeClick]);

  useEffect(() => {
    if (!graphRef.current) return;
    graphRef.current.setData(g6Data);
    graphRef.current.render();
    applyHighlight(selectedNodeIdRef.current, selectedEdgeIdRef.current, true);
  }, [g6Data]);

  useEffect(() => {
    if (!graphRef.current) return;
    applyHighlight(selectedNodeId, selectedEdgeId, true);
  }, [selectedNodeId, selectedEdgeId]);

  useEffect(() => {
    if (!graphRef.current) return;
    try {
      graphRef.current.render();
      applyHighlight(selectedNodeIdRef.current, selectedEdgeIdRef.current, true);
    } catch {
      // ignore
    }
  }, [renderNodeLabels, renderEdgeLabels, edgeLabelSelectedDisplays]);

  useEffect(() => {
    return () => {
      if (!graphRef.current) return;
      graphRef.current.destroy();
      graphRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        minWidth: 0,
        overflow: "hidden",
        position: "relative",
        ...containerStyle,
      }}
    />
  );
}
```

## src/components/LeftSearchPanel.tsx
```tsx
import type { Dispatch, KeyboardEvent, RefObject, SetStateAction } from "react";
import type { SearchResp, SuggestItem } from "../types/kg";

type LeftSearchPanelProps = {
  q: string;
  onQChange: (value: string) => void;
  loadingSearch: boolean;
  onSearch: () => void;
  onSearchInputKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  suggestWrapRef: RefObject<HTMLDivElement | null>;
  suggestOpen: boolean;
  suggestLoading: boolean;
  suggestError: string | null;
  suggestItems: SuggestItem[];
  suggestHighlightIndex: number;
  setSuggestHighlightIndex: Dispatch<SetStateAction<number>>;
  onSelectSuggestItem: (item: SuggestItem) => void;
  searchName: boolean;
  setSearchName: (value: boolean) => void;
  searchDesc: boolean;
  setSearchDesc: (value: boolean) => void;
  entityType: string;
  setEntityType: (value: string) => void;
  source: string;
  setSource: (value: string) => void;
  searchData: SearchResp;
  rootVid: number | null;
  onLoadSubgraph: (vid: number) => void;
};

export function LeftSearchPanel({
  q,
  onQChange,
  loadingSearch,
  onSearch,
  onSearchInputKeyDown,
  suggestWrapRef,
  suggestOpen,
  suggestLoading,
  suggestError,
  suggestItems,
  suggestHighlightIndex,
  setSuggestHighlightIndex,
  onSelectSuggestItem,
  searchName,
  setSearchName,
  searchDesc,
  setSearchDesc,
  entityType,
  setEntityType,
  source,
  setSource,
  searchData,
  rootVid,
  onLoadSubgraph,
}: LeftSearchPanelProps) {
  return (
    <div style={{ padding: 16, borderRight: "1px solid #eee", overflow: "auto" }}>
      <h3 style={{ margin: 0 }}>实体检索（Top100）</h3>

      <div ref={suggestWrapRef} style={{ marginTop: 12, position: "relative" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            style={{ flex: 1, padding: 8 }}
            placeholder="关键词（模糊）"
            value={q}
            onChange={(e) => onQChange(e.target.value)}
            onKeyDown={onSearchInputKeyDown}
          />
          <button onClick={onSearch} disabled={loadingSearch} style={{ padding: "8px 12px" }}>
            {loadingSearch ? "搜索中…" : "搜索"}
          </button>
        </div>

        {suggestOpen && (
          <div
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: "calc(100% + 6px)",
              zIndex: 30,
              border: "1px solid #e5e6eb",
              borderRadius: 8,
              background: "#fff",
              boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              maxHeight: 360,
              overflow: "auto",
            }}
          >
            {suggestLoading ? (
              <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
            ) : suggestError ? (
              <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选请求失败（不影响搜索）</div>
            ) : suggestItems.length === 0 ? (
              <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选（继续输入以缩小范围）</div>
            ) : (
              suggestItems.map((item, idx) => {
                const active = idx === suggestHighlightIndex;
                return (
                  <div
                    key={`${item.vid}-${item.label}-${idx}`}
                    onMouseEnter={() => setSuggestHighlightIndex(idx)}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => onSelectSuggestItem(item)}
                    style={{
                      padding: "8px 10px",
                      cursor: "pointer",
                      borderBottom: idx === suggestItems.length - 1 ? "none" : "1px solid #f0f0f0",
                      background: active ? "#e6f4ff" : "#fff",
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>{item.label}</div>
                    <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                      vid={item.vid}
                      {item.entity_type ? ` | ${item.entity_type}` : ""}
                      {item.source ? ` | ${item.source}` : ""}
                      {typeof item.score === "number" ? ` | score=${item.score}` : ""}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      <div style={{ marginTop: 10, display: "grid", gap: 6, fontSize: 13 }}>
        <label>
          <input type="checkbox" checked={searchName} onChange={(e) => setSearchName(e.target.checked)} /> 搜索 entity_name
        </label>
        <label>
          <input type="checkbox" checked={searchDesc} onChange={(e) => setSearchDesc(e.target.checked)} /> 搜索 description
        </label>
      </div>

      <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
        <input
          style={{ padding: 8 }}
          placeholder="过滤 entity_type（可选，如 disease）"
          value={entityType}
          onChange={(e) => setEntityType(e.target.value)}
        />
        <input
          style={{ padding: 8 }}
          placeholder="过滤 source（可选，如 UMLS）"
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
      </div>

      <div style={{ marginTop: 10, color: "#666", fontSize: 12 }}>
        候选数量：{searchData.total_candidates}（返回 Top100）
      </div>
      <hr style={{ margin: "12px 0" }} />

      <div style={{ display: "grid", gap: 10 }}>
        {searchData.nodes.map((n) => (
          <div
            key={n.id}
            style={{
              padding: 10,
              border: rootVid === n.id ? "1px solid #333" : "1px solid #f0f0f0",
              borderRadius: 8,
              cursor: "pointer",
            }}
            onClick={() => onLoadSubgraph(n.id)}
            title="点击切换为该实体的子图"
          >
            <div style={{ fontWeight: 600 }}>{n.label}</div>
            <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
              id={n.id} | {n.entity_type} | {n.source} | score={n.score}
            </div>
            {n.snippet ? <div style={{ fontSize: 12, marginTop: 6 }}>{n.snippet}</div> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
```

## src/components/TopBar.tsx
```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { relationDisplay } from "../utils/kg";

type TopBarProps = {
  rootVid: number | null;
  loadingGraph: boolean;
  hop: number;
  setHop: (nextHop: number) => void;
  relationTypes: string[];
  relations: string[];
  setRelations: (next: string[]) => void;
  loadSubgraphWithParams: (nextRoot: number, nextHop: number, nextRelations: string[]) => Promise<void>;
  loadSubgraph: (nextRoot: number) => Promise<void>;
  graphStats: Record<string, unknown> | null;
};

export function TopBar({
  rootVid,
  loadingGraph,
  hop,
  setHop,
  relationTypes,
  relations,
  setRelations,
  loadSubgraphWithParams,
  loadSubgraph,
  graphStats,
}: TopBarProps) {
  const [relPickerOpen, setRelPickerOpen] = useState(false);
  const [relPickerDraft, setRelPickerDraft] = useState<string[]>([]);
  const [relPickerKeyword, setRelPickerKeyword] = useState("");
  const relPickerWrapRef = useRef<HTMLDivElement>(null);

  function openRelationPicker() {
    setRelPickerDraft([...relations]);
    setRelPickerKeyword("");
    setRelPickerOpen(true);
  }

  function closeRelationPicker() {
    setRelPickerOpen(false);
    setRelPickerKeyword("");
  }

  function toggleDraftRelation(r: string) {
    setRelPickerDraft((prev) => {
      const s = new Set(prev);
      s.has(r) ? s.delete(r) : s.add(r);
      return Array.from(s);
    });
  }

  useEffect(() => {
    if (!relPickerOpen) return;
    const onDocMouseDown = (e: MouseEvent) => {
      const el = relPickerWrapRef.current;
      if (el && !el.contains(e.target as Node)) closeRelationPicker();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRelationPicker();
    };
    document.addEventListener("mousedown", onDocMouseDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [relPickerOpen]);

  const relPickerFilteredTypes = useMemo(() => {
    const kw = relPickerKeyword.trim().toLowerCase();
    if (!kw) return relationTypes;
    return relationTypes.filter((r) => r.toLowerCase().includes(kw));
  }, [relationTypes, relPickerKeyword]);

  const relPickerDraftSet = useMemo(() => new Set(relPickerDraft), [relPickerDraft]);

  const relationButtonText = useMemo(() => {
    if (relations.length === 0) return "筛选关系（全部）";
    if (relations.length <= 2) return `筛选关系（${relations.map(relationDisplay).join(", ")}）`;
    return `筛选关系（已选 ${relations.length}）`;
  }, [relations]);

  const relDraftAllVisibleChecked =
    relPickerFilteredTypes.length > 0 && relPickerFilteredTypes.every((r) => relPickerDraftSet.has(r));

  const nodeCount = typeof graphStats?.node_count === "number" ? graphStats.node_count : undefined;
  const edgeCount = typeof graphStats?.edge_count === "number" ? graphStats.edge_count : undefined;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 10px",
        borderBottom: "1px solid #eee",
        minWidth: 0,
        position: "relative",
      }}
    >
      <div style={{ fontSize: 13, color: "#444", whiteSpace: "nowrap" }}>
        Root: {rootVid ?? "-"} {loadingGraph ? "（加载中…）" : ""}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <label style={{ fontSize: 13 }}>Hop</label>
        <select value={hop} onChange={(e) => setHop(Number(e.target.value))}>
          <option value={1}>1</option>
          <option value={2}>2</option>
          <option value={3}>3</option>
        </select>
      </div>

      <div ref={relPickerWrapRef} style={{ position: "relative", minWidth: 0 }}>
        <button
          onClick={() => (relPickerOpen ? closeRelationPicker() : openRelationPicker())}
          style={{
            padding: "7px 10px",
            border: "1px solid #d9d9d9",
            background: "#fff",
            borderRadius: 6,
            cursor: "pointer",
            fontSize: 12,
            maxWidth: 260,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {relationButtonText} {relPickerOpen ? "▲" : "▼"}
        </button>

        {relPickerOpen && (
          <div
            style={{
              position: "absolute",
              top: "calc(100% + 6px)",
              left: 0,
              width: 380,
              background: "#fff",
              border: "1px solid #ddd",
              borderRadius: 8,
              boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
              zIndex: 50,
              padding: 10,
              display: "grid",
              gap: 8,
            }}
          >
            <div style={{ fontWeight: 600, fontSize: 13 }}>Relation 筛选（数据层）</div>
            <input
              value={relPickerKeyword}
              onChange={(e) => setRelPickerKeyword(e.target.value)}
              placeholder="搜索 relation（包含匹配）"
              style={{ width: "100%", padding: 8, fontSize: 12 }}
            />
            <div style={{ fontSize: 12, color: "#666" }}>
              草稿已选 {relPickerDraft.length} / 总数 {relationTypes.length}
              {relPickerKeyword.trim() ? `（当前列表 ${relPickerFilteredTypes.length} 项）` : ""}
            </div>

            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <button onClick={() => setRelPickerDraft([...relationTypes])} style={{ padding: "6px 8px", fontSize: 12 }}>
                全选
              </button>
              <button onClick={() => setRelPickerDraft([])} style={{ padding: "6px 8px", fontSize: 12 }}>
                清空
              </button>
              <button
                onClick={() => {
                  if (relPickerFilteredTypes.length === 0) return;
                  setRelPickerDraft((prev) => {
                    const s = new Set(prev);
                    if (relDraftAllVisibleChecked) relPickerFilteredTypes.forEach((r) => s.delete(r));
                    else relPickerFilteredTypes.forEach((r) => s.add(r));
                    return Array.from(s);
                  });
                }}
                style={{ padding: "6px 8px", fontSize: 12 }}
              >
                {relDraftAllVisibleChecked ? "取消当前列表" : "勾选当前列表"}
              </button>
            </div>

            <div
              style={{
                border: "1px solid #eee",
                borderRadius: 6,
                maxHeight: 260,
                overflow: "auto",
                padding: 6,
                display: "grid",
                gap: 4,
                background: "#fafafa",
              }}
            >
              {relPickerFilteredTypes.length === 0 ? (
                <div style={{ fontSize: 12, color: "#666", padding: 6 }}>没有匹配的 relation</div>
              ) : (
                relPickerFilteredTypes.map((r) => (
                  <label
                    key={r}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      padding: "4px 6px",
                      fontSize: 12,
                      cursor: "pointer",
                      borderRadius: 4,
                      background: relPickerDraftSet.has(r) ? "#fffbe6" : "transparent",
                    }}
                  >
                    <input type="checkbox" checked={relPickerDraftSet.has(r)} onChange={() => toggleDraftRelation(r)} />
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 315 }}>
                      {r}
                    </span>
                  </label>
                ))
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button
                onClick={() => {
                  setRelPickerDraft([...relations]);
                  closeRelationPicker();
                }}
                style={{ padding: "6px 10px", fontSize: 12 }}
              >
                取消
              </button>
              <button
                onClick={async () => {
                  const next = [...relPickerDraft];
                  setRelations(next);
                  closeRelationPicker();
                  if (rootVid != null) await loadSubgraphWithParams(rootVid, hop, next);
                }}
                style={{ padding: "6px 10px", fontSize: 12 }}
              >
                应用
              </button>
            </div>
          </div>
        )}
      </div>

      <button
        onClick={() => {
          setRelations([]);
          if (rootVid != null) void loadSubgraphWithParams(rootVid, hop, []);
        }}
        style={{ padding: "7px 10px", fontSize: 12 }}
      >
        清空筛选
      </button>

      <button
        onClick={() => {
          if (rootVid != null) void loadSubgraph(rootVid);
        }}
        disabled={!rootVid}
        style={{ marginLeft: "auto", padding: "8px 12px" }}
      >
        重新加载子图
      </button>

      <div style={{ fontSize: 12, color: "#666", whiteSpace: "nowrap" }}>
        {nodeCount != null && edgeCount != null ? `缓存 nodes=${nodeCount} edges=${edgeCount}` : ""}
      </div>
    </div>
  );
}
```

## src/components/RightDetailPanel.tsx
```tsx
import { EXPAND_AUTO_REVEAL_TOPK, TOP_N_VISIBLE } from "../constants/kg";
import type {
  EdgeDetailResp,
  ExpandProbeState,
  NodeBrief,
  NodeDetailResp,
  Sel,
} from "../types/kg";

type PanelGroup = {
  groupRoot: number;
  nodes: NodeBrief[];
  isRootGroup: boolean;
  title: string;
};

type RightDetailPanelProps = {
  renderNodeLabels: boolean;
  setRenderNodeLabels: (v: boolean) => void;
  renderEdgeLabels: boolean;
  setRenderEdgeLabels: (v: boolean) => void;
  edgeLabelPickerOpen: boolean;
  setEdgeLabelPickerOpen: (next: boolean | ((v: boolean) => boolean)) => void;
  edgeLabelKeyword: string;
  setEdgeLabelKeyword: (v: string) => void;
  edgeLabelSelectedDisplays: string[];
  setEdgeLabelSelectedDisplays: (next: string[] | ((prev: string[]) => string[])) => void;
  setEdgeLabelSelectionTouched: (v: boolean) => void;
  currentVisibleEdgeLabelDisplays: string[];
  edgeLabelFilteredDisplays: string[];
  edgeLabelSelectedSet: Set<string>;
  edgeLabelAllVisibleChecked: boolean;
  toggleEdgeLabelDisplay: (disp: string) => void;
  showSelfLoops: boolean;
  setShowSelfLoops: (v: boolean) => void;
  visibleSelfLoopCount: number;
  hiddenSelfLoopCount: number;
  hiddenNodesCollapsed: boolean;
  setHiddenNodesCollapsed: (next: boolean | ((v: boolean) => boolean)) => void;
  panelNodes: NodeBrief[];
  hiddenCount: number;
  visibleCount: number;
  graphNodeCount: number;
  panelGroups: PanelGroup[];
  panelGroupCollapsed: Record<string, boolean>;
  setPanelGroupCollapsed: (
    updater: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)
  ) => void;
  visibleNodeIdSet: Set<number>;
  autoVisibleTopIds: Set<number>;
  rootVid: number | null;
  revealNode: (vid: number, autoSelect?: boolean) => void;
  unrevealNode: (vid: number) => void;
  sel: Sel;
  selectedNodeBrief: NodeBrief | null;
  visibleNodeHopLevelMap: Map<number, number>;
  reroot1hop: (vid: number) => void;
  expand1hop: (vid: number) => void;
  collapseExpandFromNode: (fromVid: number) => void;
  expandButtonDisabled: boolean;
  expandButtonText: string;
  selectedNodeExpandClosable: boolean;
  selectedNodeIsVisible: boolean;
  selectedNodeIsRoot: boolean;
  selectedNodeIsAutoTop: boolean;
  selectedNodeProbeState: ExpandProbeState | undefined;
  loadingGraph: boolean;
  detailLoading: boolean;
  nodeDetail: NodeDetailResp | null;
  edgeDetail: EdgeDetailResp | null;
  relationDisplay: (raw?: string) => string;
};

export function RightDetailPanel({
  renderNodeLabels,
  setRenderNodeLabels,
  renderEdgeLabels,
  setRenderEdgeLabels,
  edgeLabelPickerOpen,
  setEdgeLabelPickerOpen,
  edgeLabelKeyword,
  setEdgeLabelKeyword,
  edgeLabelSelectedDisplays,
  setEdgeLabelSelectedDisplays,
  setEdgeLabelSelectionTouched,
  currentVisibleEdgeLabelDisplays,
  edgeLabelFilteredDisplays,
  edgeLabelSelectedSet,
  edgeLabelAllVisibleChecked,
  toggleEdgeLabelDisplay,
  showSelfLoops,
  setShowSelfLoops,
  visibleSelfLoopCount,
  hiddenSelfLoopCount,
  hiddenNodesCollapsed,
  setHiddenNodesCollapsed,
  panelNodes,
  hiddenCount,
  visibleCount,
  graphNodeCount,
  panelGroups,
  panelGroupCollapsed,
  setPanelGroupCollapsed,
  visibleNodeIdSet,
  autoVisibleTopIds,
  rootVid,
  revealNode,
  unrevealNode,
  sel,
  selectedNodeBrief,
  visibleNodeHopLevelMap,
  reroot1hop,
  expand1hop,
  collapseExpandFromNode,
  expandButtonDisabled,
  expandButtonText,
  selectedNodeExpandClosable,
  selectedNodeIsVisible,
  selectedNodeIsRoot,
  selectedNodeIsAutoTop,
  selectedNodeProbeState,
  loadingGraph,
  detailLoading,
  nodeDetail,
  edgeDetail,
  relationDisplay,
}: RightDetailPanelProps) {
  return (
    <div
      style={{
        padding: 12,
        borderLeft: "1px solid #eee",
        overflow: "auto",
        position: "relative",
        zIndex: 5,
        background: "#fff",
      }}
    >
      <h3 style={{ margin: 0 }}>详情</h3>
      <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>点击节点/边查看；节点支持 Expand（合并 1-hop）</div>

      <div
        style={{
          marginTop: 10,
          padding: "8px 10px",
          border: "1px solid #eee",
          borderRadius: 8,
          background: "#fafafa",
          display: "grid",
          gap: 8,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600 }}>标签渲染控制（视图层）</div>

        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={renderNodeLabels} onChange={(e) => setRenderNodeLabels(e.target.checked)} />
          渲染节点标签
        </label>

        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={renderEdgeLabels} onChange={(e) => setRenderEdgeLabels(e.target.checked)} />
          渲染边标签（默认关闭）
        </label>

        <div style={{ fontSize: 12, color: "#666" }}>边标签渲染仅影响“文字显示”，不影响边本身是否绘制。</div>

        <div style={{ border: "1px solid #eee", borderRadius: 8, overflow: "hidden", background: "#fff" }}>
          <button
            onClick={() => setEdgeLabelPickerOpen((v) => !v)}
            style={{
              width: "100%",
              textAlign: "left",
              border: "none",
              background: "#fff",
              padding: "8px 10px",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 600,
            }}
            title="按当前图中存在的边标签（relationDisplay）选择要渲染的边标签"
          >
            {edgeLabelPickerOpen ? "▼" : "▶"} 边标签渲染选择（已选 {edgeLabelSelectedDisplays.length}/
            {currentVisibleEdgeLabelDisplays.length}）
          </button>

          {edgeLabelPickerOpen && (
            <div style={{ borderTop: "1px solid #eee", padding: 8, display: "grid", gap: 8 }}>
              <input
                value={edgeLabelKeyword}
                onChange={(e) => setEdgeLabelKeyword(e.target.value)}
                placeholder="搜索当前图中的边标签（按显示值匹配）"
                style={{ width: "100%", padding: 8, fontSize: 12 }}
              />

              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button
                  onClick={() => {
                    setEdgeLabelSelectionTouched(true);
                    setEdgeLabelSelectedDisplays([...currentVisibleEdgeLabelDisplays]);
                  }}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  全选
                </button>
                <button
                  onClick={() => {
                    setEdgeLabelSelectionTouched(true);
                    setEdgeLabelSelectedDisplays([]);
                  }}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  清空
                </button>
                <button
                  onClick={() => {
                    setEdgeLabelSelectionTouched(true);
                    if (edgeLabelFilteredDisplays.length === 0) return;
                    setEdgeLabelSelectedDisplays((prev) => {
                      const s = new Set(prev);
                      if (edgeLabelAllVisibleChecked) edgeLabelFilteredDisplays.forEach((x) => s.delete(x));
                      else edgeLabelFilteredDisplays.forEach((x) => s.add(x));
                      return Array.from(s).sort((a, b) => a.localeCompare(b));
                    });
                  }}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  {edgeLabelAllVisibleChecked ? "取消当前列表" : "勾选当前列表"}
                </button>
              </div>

              <div style={{ fontSize: 12, color: "#666" }}>
                当前图中边标签（显示值）共 {currentVisibleEdgeLabelDisplays.length} 项
                {edgeLabelKeyword.trim() ? `，筛选后 ${edgeLabelFilteredDisplays.length} 项` : ""}
              </div>

              <div
                style={{
                  border: "1px solid #eee",
                  borderRadius: 6,
                  maxHeight: 220,
                  overflow: "auto",
                  padding: 6,
                  display: "grid",
                  gap: 4,
                  background: "#fafafa",
                }}
              >
                {edgeLabelFilteredDisplays.length === 0 ? (
                  <div style={{ fontSize: 12, color: "#666", padding: 6 }}>当前图中没有匹配的边标签</div>
                ) : (
                  edgeLabelFilteredDisplays.map((disp) => (
                    <label
                      key={disp}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "4px 6px",
                        fontSize: 12,
                        cursor: "pointer",
                        borderRadius: 4,
                        background: edgeLabelSelectedSet.has(disp) ? "#fffbe6" : "transparent",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={edgeLabelSelectedSet.has(disp)}
                        onChange={() => toggleEdgeLabelDisplay(disp)}
                      />
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{disp}</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div
        style={{
          marginTop: 10,
          padding: "8px 10px",
          border: "1px solid #eee",
          borderRadius: 8,
          background: "#fafafa",
          display: "grid",
          gap: 6,
        }}
      >
        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={showSelfLoops} onChange={(e) => setShowSelfLoops(e.target.checked)} />
          显示自环边（默认关闭）
        </label>
        <div style={{ fontSize: 12, color: "#666" }}>
          {showSelfLoops ? `当前已显示自环边 ${visibleSelfLoopCount} 条` : `当前已隐藏自环边 ${hiddenSelfLoopCount} 条`}
        </div>
      </div>

      <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 8 }}>
        <button
          onClick={() => setHiddenNodesCollapsed((v) => !v)}
          style={{
            width: "100%",
            textAlign: "left",
            padding: "10px 12px",
            border: "none",
            background: "#fafafa",
            cursor: "pointer",
            borderRadius: 8,
            fontWeight: 600,
          }}
        >
          {hiddenNodesCollapsed ? "▶" : "▼"} 未渲染节点（低优先级）
          <span style={{ color: "#666", fontWeight: 400 }}>
            {" "}
            列表 {panelNodes.length} 个｜当前未渲染 {hiddenCount} 个｜当前显示 {visibleCount}/{graphNodeCount}
            ｜TopN={TOP_N_VISIBLE}
          </span>
        </button>

        {!hiddenNodesCollapsed && (
          <div style={{ borderTop: "1px solid #eee", padding: 8, display: "grid", gap: 8, maxHeight: 360, overflow: "auto" }}>
            {panelGroups.length === 0 ? (
              <div style={{ fontSize: 12, color: "#666", padding: 4 }}>当前没有可管理节点</div>
            ) : (
              panelGroups.map((g) => {
                const key = String(g.groupRoot);
                const collapsed = panelGroupCollapsed[key] ?? (g.isRootGroup ? false : true);
                return (
                  <div key={key} style={{ border: "1px solid #f0f0f0", borderRadius: 8, overflow: "hidden" }}>
                    <button
                      onClick={() =>
                        setPanelGroupCollapsed((prev) => ({
                          ...prev,
                          [key]: !(prev[key] ?? (g.isRootGroup ? false : true)),
                        }))
                      }
                      style={{
                        width: "100%",
                        textAlign: "left",
                        border: "none",
                        background: g.isRootGroup ? "#fff7e6" : "#fafafa",
                        padding: "8px 10px",
                        cursor: "pointer",
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                      title={`groupRoot=${g.groupRoot}`}
                    >
                      {collapsed ? "▶" : "▼"} {g.title}（{g.nodes.length}）
                    </button>

                    {!collapsed && (
                      <div style={{ padding: 8, display: "grid", gap: 8, maxHeight: 220, overflow: "auto" }}>
                        {g.nodes.map((n, idx) => {
                          const currentlyVisible = visibleNodeIdSet.has(n.id);
                          const autoTop = autoVisibleTopIds.has(n.id);
                          const isRoot = rootVid != null && n.id === rootVid;

                          return (
                            <div key={n.id} style={{ border: "1px solid #f0f0f0", borderRadius: 6, padding: 8, background: "#fff" }}>
                              <div style={{ fontWeight: 600, fontSize: 13 }}>
                                #{idx + 1} {n.label}
                              </div>
                              <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                                id={n.id} | {n.entity_type} | 状态={currentlyVisible ? "已渲染" : "未渲染"}
                              </div>
                              <div style={{ marginTop: 4, fontSize: 12, color: autoTop ? "#d46b08" : "#666" }}>
                                {autoTop ? "来源：TopN默认显示（当前被手动隐藏）" : "来源：低优先级"}
                              </div>

                              <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
                                <button
                                  onClick={() => revealNode(n.id, true)}
                                  disabled={currentlyVisible}
                                  style={{ padding: "6px 8px", fontSize: 12 }}
                                  title={currentlyVisible ? "该节点当前已渲染" : "恢复渲染到图谱并高亮"}
                                >
                                  恢复渲染
                                </button>
                                <button
                                  onClick={() => unrevealNode(n.id)}
                                  disabled={!currentlyVisible || isRoot}
                                  style={{ padding: "6px 8px", fontSize: 12 }}
                                  title={
                                    isRoot ? "Root 节点不允许隐藏" : !currentlyVisible ? "该节点当前未渲染" : "取消渲染并恢复到初始未渲染状态"
                                  }
                                >
                                  取消渲染
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      <hr style={{ margin: "12px 0" }} />

      {sel.kind === "none" ? (
        <div style={{ color: "#666", fontSize: 13 }}>未选择节点/边</div>
      ) : sel.kind === "node" ? (
        <div style={{ display: "grid", gap: 10 }}>
          <div style={{ fontWeight: 700 }}>{selectedNodeBrief?.label || `Node ${sel.vid}`}</div>
          <div style={{ fontSize: 12, color: "#666" }}>
            id={sel.vid} | type={selectedNodeBrief?.entity_type} | raw_id={selectedNodeBrief?.raw_id} | source=
            {selectedNodeBrief?.source} | hop_level={visibleNodeHopLevelMap.get(sel.vid) ?? "-"}
          </div>

          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              onClick={() => reroot1hop(sel.vid)}
              disabled={loadingGraph}
              style={{ padding: "8px 12px" }}
              title="以当前节点作为新 Root，重新加载 1-hop 子图（替换当前图）"
            >
              设为 Root 并展开（1-hop）
            </button>

            <button
              onClick={() => expand1hop(sel.vid)}
              disabled={expandButtonDisabled}
              style={{ padding: "8px 12px" }}
              title={
                selectedNodeProbeState === "noextra"
                  ? "该节点在当前图上下文中没有可新增的 1-hop 邻居（无多余相关节点）"
                  : selectedNodeProbeState === "loading"
                  ? "正在检测该节点是否有可新增的 1-hop 邻居…"
                  : `追加该节点 1-hop 邻居到当前图；新增节点前 ${EXPAND_AUTO_REVEAL_TOPK} 个自动显示`
              }
            >
              {expandButtonText}
            </button>

            <button
              onClick={() => collapseExpandFromNode(sel.vid)}
              disabled={!selectedNodeExpandClosable || loadingGraph}
              style={{ padding: "8px 12px" }}
              title={
                selectedNodeExpandClosable
                  ? "关闭以该节点为来源的 Expand 展开（撤销该批节点渲染）"
                  : "该节点尚未执行 Expand 或已关闭"
              }
            >
              关闭Expand
            </button>

            <button
              onClick={() => unrevealNode(sel.vid)}
              disabled={!selectedNodeIsVisible || selectedNodeIsRoot}
              style={{ padding: "8px 12px" }}
              title={selectedNodeIsRoot ? "Root 节点不允许隐藏" : "将该节点从图谱中隐藏（可撤销）"}
            >
              隐藏节点（可撤销）
            </button>
          </div>

          <div style={{ fontSize: 12, color: "#666" }}>
            {selectedNodeIsRoot
              ? "当前节点是 Root（不可隐藏）"
              : selectedNodeIsAutoTop
              ? "当前节点属于 TopN 默认显示（可隐藏并在右侧列表恢复）"
              : "当前节点为低优先级节点（可在右侧列表恢复/取消渲染）"}
            {selectedNodeExpandClosable ? " ｜该节点存在可关闭的 Expand 展开内容" : ""}
            {selectedNodeProbeState === "noextra" ? " ｜Expand：无多余相关节点" : ""}
          </div>

          <div style={{ fontSize: 12, color: "#666" }}>{detailLoading ? "加载详情中…" : ""}</div>

          {selectedNodeBrief?.snippet ? <div style={{ fontSize: 13, lineHeight: 1.4 }}>{selectedNodeBrief.snippet}</div> : null}

          {nodeDetail?.props ? (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Properties</div>
              <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(nodeDetail.props, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          <div style={{ fontWeight: 700 }}>Edge</div>
          <div style={{ fontSize: 12, color: "#666" }}>
            src={sel.src} → dst={sel.dst}
          </div>
          <div style={{ fontSize: 12, color: "#666" }}>
            relation={relationDisplay(sel.relation)} | source_db={sel.source_db || "-"}
          </div>

          <div style={{ fontSize: 12, color: "#666" }}>{detailLoading ? "加载详情中…" : ""}</div>

          {edgeDetail?.props ? (
            <div style={{ marginTop: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 6 }}>Properties</div>
              <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(edgeDetail.props, null, 2)}</pre>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
```

## src/App.tsx
```tsx
import { useEffect, useMemo, useState } from "react";
import {
  edgeDetail as edgeDetailApi,
  nodeDetail as nodeDetailApi,
  relationTypes as relationTypesApi,
  search as searchApi,
} from "./api/kg";
import { GraphCanvas } from "./components/GraphCanvas";
import { LeftSearchPanel } from "./components/LeftSearchPanel";
import { RightDetailPanel } from "./components/RightDetailPanel";
import { TopBar } from "./components/TopBar";
import { useGraphData } from "./hooks/useGraphData";
import { useSuggest } from "./hooks/useSuggest";
import { useVisibilityRanking } from "./hooks/useVisibilityRanking";
import type { EdgeDetailResp, NodeDetailResp, SearchResp, Sel } from "./types/kg";
import { relationDisplay } from "./utils/kg";

export default function App() {
  const [q, setQ] = useState("");
  const [searchName, setSearchName] = useState(true);
  const [searchDesc, setSearchDesc] = useState(true);
  const [entityType, setEntityType] = useState("");
  const [source, setSource] = useState("");
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchData, setSearchData] = useState<SearchResp>({ nodes: [], edges: [], total_candidates: 0 });

  const [sel, setSel] = useState<Sel>({ kind: "none" });
  const [nodeDetail, setNodeDetail] = useState<NodeDetailResp | null>(null);
  const [edgeDetail, setEdgeDetail] = useState<EdgeDetailResp | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedEdgeGraphId, setSelectedEdgeGraphId] = useState<string | null>(null);

  const [relationTypes, setRelationTypes] = useState<string[]>([]);

  const [renderNodeLabels, setRenderNodeLabels] = useState(true);
  const [renderEdgeLabels, setRenderEdgeLabels] = useState(false);
  const [edgeLabelPickerOpen, setEdgeLabelPickerOpen] = useState(false);
  const [edgeLabelKeyword, setEdgeLabelKeyword] = useState("");
  const [edgeLabelSelectedDisplays, setEdgeLabelSelectedDisplays] = useState<string[]>([]);
  const [edgeLabelSelectionTouched, setEdgeLabelSelectionTouched] = useState(false);

  const [showSelfLoops, setShowSelfLoops] = useState(false);

  async function loadNodeDetail(vid: number) {
    setDetailLoading(true);
    try {
      setNodeDetail(await nodeDetailApi(vid));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
    } finally {
      setDetailLoading(false);
    }
  }

  async function loadEdgeDetail(src: number, dst: number, relation: string, source_db?: string) {
    setDetailLoading(true);
    try {
      setEdgeDetail(
        await edgeDetailApi({
          src,
          dst,
          relation,
          source_db: source_db || null,
        })
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
    } finally {
      setDetailLoading(false);
    }
  }

  function handleClearSelection() {
    setSel({ kind: "none" });
    setNodeDetail(null);
    setEdgeDetail(null);
    setSelectedEdgeGraphId(null);
  }

  function handleSelectNode(vid: number) {
    setSel({ kind: "node", vid });
    setEdgeDetail(null);
    setSelectedEdgeGraphId(null);
    void loadNodeDetail(vid);
  }

  const selectedNodeVid = sel.kind === "node" ? sel.vid : null;

  const {
    rootVid,
    hop,
    setHop,
    relations,
    setRelations,
    loadingGraph,
    graphNodes,
    graphEdges,
    graphStats,
    manualRevealedNodeIds,
    manualHiddenNodeIds,
    nodeGroupRootById,
    expandedSourceNodeIds,
    hiddenNodesCollapsed,
    setHiddenNodesCollapsed,
    panelGroupCollapsed,
    setPanelGroupCollapsed,
    expandProbeByVid,
    loadSubgraphWithParams,
    loadSubgraph,
    expand1hop,
    reroot1hop,
    revealNode,
    unrevealNode,
    collapseExpandFromNode,
  } = useGraphData({
    selectedNodeVid,
    onSelectNode: handleSelectNode,
    onClearSelection: handleClearSelection,
  });

  async function runSearch() {
    if (!q.trim()) return;
    setLoadingSearch(true);
    try {
      const json = await searchApi({
        q,
        search_in_name: searchName,
        search_in_description: searchDesc,
        entity_type: entityType || null,
        source: source || null,
      });
      setSearchData(json);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
    } finally {
      setLoadingSearch(false);
    }
  }

  const {
    suggestOpen,
    suggestItems,
    suggestLoading,
    suggestError,
    suggestHighlightIndex,
    suggestWrapRef,
    onInputChange,
    onKeyDown,
    setSuggestHighlightIndex,
    closeSuggestPanel,
    selectSuggestCandidate,
  } = useSuggest({
    q,
    entityType,
    source,
    onSelect: (item) => {
      setQ(item.label);
      void loadSubgraph(item.vid);
    },
    onQueryChange: setQ,
    onSearch: () => {
      void runSearch();
    },
  });

  const {
    visibleGraphNodes,
    visibleNodeIdSet,
    visibleGraphEdges,
    hiddenSelfLoopCount,
    visibleSelfLoopCount,
    autoVisibleTopIds,
    visibleNodeHopLevelMap,
    panelNodes,
    panelGroups,
    hiddenCount,
    visibleCount,
  } = useVisibilityRanking({
    graphNodes,
    graphEdges,
    rootVid,
    manualHiddenNodeIds,
    manualRevealedNodeIds,
    showSelfLoops,
    nodeGroupRootById,
    searchNodes: searchData.nodes,
  });

  useEffect(() => {
    if (panelGroups.length === 0) return;
    setPanelGroupCollapsed((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const g of panelGroups) {
        const k = String(g.groupRoot);
        if (!(k in next)) {
          next[k] = g.isRootGroup ? false : true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [panelGroups, setPanelGroupCollapsed]);

  useEffect(() => {
    async function loadRelationTypes() {
      try {
        setRelationTypes(await relationTypesApi());
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        console.warn(msg);
      }
    }
    void loadRelationTypes();
  }, []);

  const currentVisibleEdgeLabelDisplays = useMemo(() => {
    const set = new Set<string>();
    for (const e of visibleGraphEdges) {
      const d = relationDisplay(e.relation);
      if (d) set.add(d);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [visibleGraphEdges]);

  useEffect(() => {
    setEdgeLabelSelectedDisplays((prev) => {
      if (!edgeLabelSelectionTouched) {
        return [...currentVisibleEdgeLabelDisplays];
      }
      const allow = new Set(currentVisibleEdgeLabelDisplays);
      return prev.filter((x) => allow.has(x));
    });
  }, [currentVisibleEdgeLabelDisplays, edgeLabelSelectionTouched]);

  const edgeLabelSelectedSet = useMemo(
    () => new Set(edgeLabelSelectedDisplays),
    [edgeLabelSelectedDisplays]
  );

  const edgeLabelFilteredDisplays = useMemo(() => {
    const kw = edgeLabelKeyword.trim().toLowerCase();
    if (!kw) return currentVisibleEdgeLabelDisplays;
    return currentVisibleEdgeLabelDisplays.filter((x) => x.toLowerCase().includes(kw));
  }, [currentVisibleEdgeLabelDisplays, edgeLabelKeyword]);

  const edgeLabelAllVisibleChecked =
    edgeLabelFilteredDisplays.length > 0 &&
    edgeLabelFilteredDisplays.every((x) => edgeLabelSelectedSet.has(x));

  function toggleEdgeLabelDisplay(disp: string) {
    setEdgeLabelSelectionTouched(true);
    setEdgeLabelSelectedDisplays((prev) => {
      const s = new Set(prev);
      s.has(disp) ? s.delete(disp) : s.add(disp);
      return Array.from(s).sort((a, b) => a.localeCompare(b));
    });
  }

  const { g6Data, edgeById } = useMemo(() => {
    const nodes = visibleGraphNodes.map((n) => ({
      id: String(n.id),
      label: n.label,
      data: {
        ...n,
        isRoot: rootVid != null && n.id === rootVid,
        hopLevel: visibleNodeHopLevelMap.get(n.id) ?? 99,
      },
    }));

    const edgeMap = new Map<string, (typeof visibleGraphEdges)[number]>();
    const edges = visibleGraphEdges.map((e, idx) => {
      const id = `e-${idx}-${e.source}-${e.target}-${e.relation || ""}-${e.source_db || ""}`;
      edgeMap.set(id, e);
      return {
        id,
        source: String(e.source),
        target: String(e.target),
        label: e.relation || "",
        data: e,
      };
    });

    return { g6Data: { nodes, edges }, edgeById: edgeMap };
  }, [visibleGraphNodes, visibleGraphEdges, rootVid, visibleNodeHopLevelMap]);

  const selectedNodeBrief = useMemo(() => {
    if (sel.kind !== "node") return null;
    return graphNodes.find((n) => n.id === sel.vid) || null;
  }, [sel, graphNodes]);

  const selectedNodeIsRoot = sel.kind === "node" && rootVid != null && sel.vid === rootVid;
  const selectedNodeIsVisible = sel.kind === "node" ? visibleNodeIdSet.has(sel.vid) : false;
  const selectedNodeIsAutoTop = sel.kind === "node" ? autoVisibleTopIds.has(sel.vid) : false;
  const selectedNodeExpandClosable = sel.kind === "node" && expandedSourceNodeIds.has(sel.vid);

  const selectedNodeProbeState = sel.kind === "node" ? expandProbeByVid[sel.vid] : undefined;

  const expandButtonDisabled =
    loadingGraph ||
    sel.kind !== "node" ||
    selectedNodeProbeState === "loading" ||
    selectedNodeProbeState === "noextra";

  const expandButtonText =
    selectedNodeProbeState === "noextra" ? "Expand（无多余相关节点）" : "Expand（合并 1-hop）";

  const selectedNodeId = sel.kind === "node" ? String(sel.vid) : null;
  const selectedEdgeId = sel.kind === "edge" ? selectedEdgeGraphId : null;

  function handleSearchClick() {
    closeSuggestPanel();
    void runSearch();
  }

  function handleGraphNodeClick(vid: number) {
    handleSelectNode(vid);
  }

  function handleGraphEdgeClick(edgeId: string, edge: (typeof visibleGraphEdges)[number]) {
    const src = Number(edge.source);
    const dst = Number(edge.target);
    const relation = String(edge.relation || "");
    const source_db = edge.source_db ? String(edge.source_db) : undefined;
    if (!Number.isFinite(src) || !Number.isFinite(dst) || !relation) return;

    setSelectedEdgeGraphId(edgeId);
    setSel({ kind: "edge", src, dst, relation, source_db });
    setNodeDetail(null);
    void loadEdgeDetail(src, dst, relation, source_db);
  }

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "420px minmax(0, 1fr) 420px",
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
      }}
    >
      <LeftSearchPanel
        q={q}
        onQChange={onInputChange}
        loadingSearch={loadingSearch}
        onSearch={handleSearchClick}
        onSearchInputKeyDown={onKeyDown}
        suggestWrapRef={suggestWrapRef}
        suggestOpen={suggestOpen}
        suggestLoading={suggestLoading}
        suggestError={suggestError}
        suggestItems={suggestItems}
        suggestHighlightIndex={suggestHighlightIndex}
        setSuggestHighlightIndex={setSuggestHighlightIndex}
        onSelectSuggestItem={selectSuggestCandidate}
        searchName={searchName}
        setSearchName={setSearchName}
        searchDesc={searchDesc}
        setSearchDesc={setSearchDesc}
        entityType={entityType}
        setEntityType={setEntityType}
        source={source}
        setSource={setSource}
        searchData={searchData}
        rootVid={rootVid}
        onLoadSubgraph={(vid) => {
          void loadSubgraph(vid);
        }}
      />

      <div
        style={{
          display: "grid",
          gridTemplateRows: "56px 1fr",
          minWidth: 0,
          overflow: "hidden",
          position: "relative",
          zIndex: 1,
        }}
      >
        <TopBar
          rootVid={rootVid}
          loadingGraph={loadingGraph}
          hop={hop}
          setHop={setHop}
          relationTypes={relationTypes}
          relations={relations}
          setRelations={setRelations}
          loadSubgraphWithParams={loadSubgraphWithParams}
          loadSubgraph={loadSubgraph}
          graphStats={graphStats}
        />

        <GraphCanvas
          g6Data={g6Data}
          edgeById={edgeById}
          renderNodeLabels={renderNodeLabels}
          renderEdgeLabels={renderEdgeLabels}
          edgeLabelSelectedDisplays={edgeLabelSelectedDisplays}
          selectedNodeId={selectedNodeId}
          selectedEdgeId={selectedEdgeId}
          onNodeClick={handleGraphNodeClick}
          onEdgeClick={handleGraphEdgeClick}
        />
      </div>

      <RightDetailPanel
        renderNodeLabels={renderNodeLabels}
        setRenderNodeLabels={setRenderNodeLabels}
        renderEdgeLabels={renderEdgeLabels}
        setRenderEdgeLabels={setRenderEdgeLabels}
        edgeLabelPickerOpen={edgeLabelPickerOpen}
        setEdgeLabelPickerOpen={setEdgeLabelPickerOpen}
        edgeLabelKeyword={edgeLabelKeyword}
        setEdgeLabelKeyword={setEdgeLabelKeyword}
        edgeLabelSelectedDisplays={edgeLabelSelectedDisplays}
        setEdgeLabelSelectedDisplays={setEdgeLabelSelectedDisplays}
        setEdgeLabelSelectionTouched={setEdgeLabelSelectionTouched}
        currentVisibleEdgeLabelDisplays={currentVisibleEdgeLabelDisplays}
        edgeLabelFilteredDisplays={edgeLabelFilteredDisplays}
        edgeLabelSelectedSet={edgeLabelSelectedSet}
        edgeLabelAllVisibleChecked={edgeLabelAllVisibleChecked}
        toggleEdgeLabelDisplay={toggleEdgeLabelDisplay}
        showSelfLoops={showSelfLoops}
        setShowSelfLoops={setShowSelfLoops}
        visibleSelfLoopCount={visibleSelfLoopCount}
        hiddenSelfLoopCount={hiddenSelfLoopCount}
        hiddenNodesCollapsed={hiddenNodesCollapsed}
        setHiddenNodesCollapsed={setHiddenNodesCollapsed}
        panelNodes={panelNodes}
        hiddenCount={hiddenCount}
        visibleCount={visibleCount}
        graphNodeCount={graphNodes.length}
        panelGroups={panelGroups}
        panelGroupCollapsed={panelGroupCollapsed}
        setPanelGroupCollapsed={setPanelGroupCollapsed}
        visibleNodeIdSet={visibleNodeIdSet}
        autoVisibleTopIds={autoVisibleTopIds}
        rootVid={rootVid}
        revealNode={revealNode}
        unrevealNode={unrevealNode}
        sel={sel}
        selectedNodeBrief={selectedNodeBrief}
        visibleNodeHopLevelMap={visibleNodeHopLevelMap}
        reroot1hop={(vid) => {
          void reroot1hop(vid);
        }}
        expand1hop={(vid) => {
          void expand1hop(vid);
        }}
        collapseExpandFromNode={collapseExpandFromNode}
        expandButtonDisabled={expandButtonDisabled}
        expandButtonText={expandButtonText}
        selectedNodeExpandClosable={selectedNodeExpandClosable}
        selectedNodeIsVisible={selectedNodeIsVisible}
        selectedNodeIsRoot={selectedNodeIsRoot}
        selectedNodeIsAutoTop={selectedNodeIsAutoTop}
        selectedNodeProbeState={selectedNodeProbeState}
        loadingGraph={loadingGraph}
        detailLoading={detailLoading}
        nodeDetail={nodeDetail}
        edgeDetail={edgeDetail}
        relationDisplay={relationDisplay}
      />
    </div>
  );
}
```

