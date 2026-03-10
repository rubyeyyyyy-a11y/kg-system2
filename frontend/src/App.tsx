import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import {
  edgeDetail as edgeDetailApi,
  edgeSearch as edgeSearchApi,
  graphDiscovery as graphDiscoveryApi,
  patchEdge as patchEdgeApi,
  patchNode as patchNodeApi,
  multiEntityGraph as multiEntityGraphApi,
  multiEntityGraphApplyPaths as multiEntityGraphApplyPathsApi,
  nodeDetail as nodeDetailApi,
  relationTypes as relationTypesApi,
  search as searchApi,
} from "./api/kg";
import { DiscoveryPanel } from "./components/DiscoveryPanel";
import { LeftSearchPanel } from "./components/LeftSearchPanel";
import { Resizer } from "./components/Resizer";
import { TopBar } from "./components/TopBar";
import { useDiscoveryCandidateResults } from "./hooks/useDiscoveryCandidateResults";
import { useDiscoveryCandidateSearch } from "./hooks/useDiscoveryCandidateSearch";
import { useDiscoveryEntityDetail } from "./hooks/useDiscoveryEntityDetail";
import { useDiscoveryGraphState } from "./hooks/useDiscoveryGraphState";
import { useGraphLayoutController } from "./hooks/useGraphLayoutController";
import { useGraphPatchBuilder } from "./hooks/useGraphPatchBuilder";
import { useDiscoverySeeds } from "./hooks/useDiscoverySeeds";
import { useEdgeSuggest } from "./hooks/useEdgeSuggest";
import { useEntityTypeOptions } from "./hooks/useEntityTypeOptions";
import { useGraphData } from "./hooks/useGraphData";
import { useGraphViewModel } from "./hooks/useGraphViewModel";
import { useGraphViewportController } from "./hooks/useGraphViewportController";
import { useRawIdSuggest } from "./hooks/useRawIdSuggest";
import { useRelationFilter } from "./hooks/useRelationFilter";
import { useSuggest } from "./hooks/useSuggest";
import { useVisibilityRanking } from "./hooks/useVisibilityRanking";
import { parseApiError } from "./utils/httpError";
import type {
  EdgeBrief,
  EdgeDetailResp,
  EdgePatchResp,
  EdgeSearchItem,
  EdgeSearchResp,
  DiscoveryEntityCandidateItem,
  GraphDiscoveryResp,
  MultiEntityGraphResp,
  NodeBrief,
  NodeDetailResp,
  NodePatchResp,
  PairPathCandidate,
  RelationTypeItem,
  RawIdSuggestItem,
  SearchResp,
  Sel,
  SuggestItem,
} from "./types/kg";
import { edgeKey, findEdgeIdByIdentity, isSameEdge, pairKey, relationDisplay } from "./utils/kg";
import "./styles/layout.css";

type MultiGraphParams = {
  selectedEntities: SuggestItem[];
  directOnly: boolean;
  explainPaths: boolean;
  k: 2 | 3;
};

type MultiGraphRequest = {
  vids: number[];
  direct_only: boolean;
  explain_paths: boolean;
  k: 2 | 3;
  relations: string[];
  max_nodes: number;
  max_edges: number;
  per_pair_path_limit: number;
  ignore_direction: boolean;
};

type LegacyWorkspaceSession =
  | {
      kind: "single";
      rootVid: number;
      hop: number;
      relations: string[];
    }
  | {
      kind: "multi";
      params: MultiGraphParams;
      relations: string[];
    }
  | null;

type GraphSourceMode = "single" | "multi" | "discovery";

type WorkspaceMode = "legacy" | "discovery";

type DiscoveryRequest = {
  seed_vids: number[];
  allowed_entity_types: string[];
  allowed_relation_types: string[];
  max_nodes: number;
  max_edges: number;
  top_k_per_type: number;
  include_candidate_candidate_edges: boolean;
  include_seed_seed_edges: boolean;
  hop: number;
  ranking_mode: "v1" | "layered_multiseed";
};

type DiscoveryQueryState = {
  allowedEntityTypes: string[];
  allowedRelationTypes: string[];
  maxNodes: number;
  maxEdges: number;
  topKPerType: number;
  includeCandidateCandidateEdges: boolean;
  includeSeedSeedEdges: boolean;
  hop: number;
};

type DiscoveryRuntimeState = {
  entityTypes: string[];
  relationTypes: string[];
};

type UiNotice = {
  level: "error" | "warn" | "info";
  message: string;
};

const LEFT_WIDTH_KEY = "kg:leftW";
const RIGHT_WIDTH_KEY = "kg:rightW";
const SIDEBAR_MIN_WIDTH = 320;
const SIDEBAR_MAX_WIDTH = 640;
const SIDEBAR_DEFAULT_WIDTH = 420;
const EDGE_TYPE_DEFAULT = "REL2";
const RELATION_TYPES_PAGE_SIZE = 100;
const EMPTY_GRAPH_NODES: NodeBrief[] = [];
const EMPTY_GRAPH_EDGES: EdgeBrief[] = [];
const DISCOVERY_NONE_ENTITY_TYPE = "__none_entity_type_selected__";
const DISCOVERY_NONE_RELATION_TYPE = "__none_relation_type_selected__";
const GraphCanvas = lazy(() => import("./components/GraphCanvas").then((mod) => ({ default: mod.GraphCanvas })));
const RightDetailPanel = lazy(() =>
  import("./components/RightDetailPanel").then((mod) => ({ default: mod.RightDetailPanel }))
);
const RelationFilterPanel = lazy(() =>
  import("./components/RelationFilter/RelationFilterPanel").then((mod) => ({ default: mod.RelationFilterPanel }))
);

function clampSidebarWidth(next: number) {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(next)));
}

function loadSidebarWidth(key: string) {
  if (typeof window === "undefined") return SIDEBAR_DEFAULT_WIDTH;
  const raw = window.localStorage.getItem(key);
  const parsed = Number(raw);
  if (!Number.isFinite(parsed)) return SIDEBAR_DEFAULT_WIDTH;
  return clampSidebarWidth(parsed);
}

function mergeRelationTypeItems(prev: RelationTypeItem[], next: RelationTypeItem[]) {
  const merged = new Map<string, RelationTypeItem>();
  for (const item of prev) {
    const key = String(item.relation_type || "").trim();
    if (!key) continue;
    merged.set(key, item);
  }
  for (const item of next) {
    const key = String(item.relation_type || "").trim();
    if (!key) continue;
    merged.set(key, item);
  }
  return Array.from(merged.values());
}

function LoadingPanel({ message, style }: { message: string; style?: CSSProperties }) {
  return (
    <div
      style={{
        display: "grid",
        placeItems: "center",
        minHeight: 160,
        color: "#666",
        fontSize: 13,
        background: "#fff",
        ...style,
      }}
    >
      {message}
    </div>
  );
}

function hashText(input: string) {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) hash = (hash * 31 + input.charCodeAt(i)) | 0;
  return Math.abs(hash);
}

function discoveryTypeColor(entityType: string) {
  const text = String(entityType || "").trim();
  if (!text) return { fill: "#d9d9d9", stroke: "#8c8c8c" };
  const hue = hashText(text) % 360;
  return {
    fill: `hsl(${hue} 68% 78%)`,
    stroke: `hsl(${hue} 58% 42%)`,
  };
}

export default function App() {
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("legacy");
  const [q, setQ] = useState("");
  const [searchName, setSearchName] = useState(true);
  const [searchDesc, setSearchDesc] = useState(false);
  const [entityType, setEntityType] = useState("");
  const [entityRawId, setEntityRawId] = useState("");
  const [source, setSource] = useState("");
  const [loadingSearch, setLoadingSearch] = useState(false);
  const searchAbortRef = useRef<AbortController | null>(null);
  const [searchData, setSearchData] = useState<SearchResp>({ nodes: [], edges: [], total_candidates: 0 });
  const [searchSelectedVid, setSearchSelectedVid] = useState<number | null>(null);
  const [uiNotice, setUiNotice] = useState<UiNotice | null>(null);

  const {
    options: entityTypeOptions,
    usedFallback: entityTypeFallbackUsed,
    ensureLoaded: ensureEntityTypesLoaded,
  } = useEntityTypeOptions({ deferMs: 1200 });

  const [edgeQ, setEdgeQ] = useState("");
  const [edgeSearchInRelation, setEdgeSearchInRelation] = useState(true);
  const [edgeSearchInProps, setEdgeSearchInProps] = useState(true);
  const [edgeSearchSourceDb, setEdgeSearchSourceDb] = useState("");
  const [edgeSearchRelation, setEdgeSearchRelation] = useState("");
  const [loadingEdgeSearch, setLoadingEdgeSearch] = useState(false);
  const [edgeSearchData, setEdgeSearchData] = useState<EdgeSearchResp>({ edges: [], total_candidates: 0 });
  const [edgeSearchNotice, setEdgeSearchNotice] = useState<string | null>(null);
  const [pendingEdgeLocate, setPendingEdgeLocate] = useState<EdgeSearchItem | null>(null);

  const [loadingMultiGraph, setLoadingMultiGraph] = useState(false);
  const [loadingDiscovery, setLoadingDiscovery] = useState(false);
  const [loadingApplyPathChoice, setLoadingApplyPathChoice] = useState(false);
  const [graphSourceMode, setGraphSourceMode] = useState<GraphSourceMode>("single");
  const [legacyWorkspaceSession, setLegacyWorkspaceSession] = useState<LegacyWorkspaceSession>(null);
  const [lastMultiGraphParams, setLastMultiGraphParams] = useState<MultiGraphParams | null>(null);
  const [lastMultiGraphRequest, setLastMultiGraphRequest] = useState<MultiGraphRequest | null>(null);
  const [lastDiscoveryRequest, setLastDiscoveryRequest] = useState<DiscoveryRequest | null>(null);
  const discoverySeedsState = useDiscoverySeeds();
  const [discoveryResult, setDiscoveryResult] = useState<GraphDiscoveryResp | null>(null);
  const discoveryCandidateSearch = useDiscoveryCandidateSearch();
  const discoveryCandidateResults = useDiscoveryCandidateResults({
    query: discoveryCandidateSearch.query,
    onError: (message) => setUiNotice({ level: "error", message: `候选搜索失败：${message}` }),
  });
  const [discoveryQuery, setDiscoveryQuery] = useState<DiscoveryQueryState>({
    allowedEntityTypes: [],
    allowedRelationTypes: [],
    maxNodes: 90,
    maxEdges: 140,
    topKPerType: 12,
    includeCandidateCandidateEdges: true,
    includeSeedSeedEdges: false,
    hop: 3,
  });
  const [discoveryRuntimeFilters, setDiscoveryRuntimeFilters] = useState<DiscoveryRuntimeState>({
    entityTypes: [],
    relationTypes: [],
  });
  const [discoveryExpandFilters, setDiscoveryExpandFilters] = useState<DiscoveryRuntimeState>({
    entityTypes: [],
    relationTypes: [],
  });
  const [discoveryRenderedPanelCollapsed, setDiscoveryRenderedPanelCollapsed] = useState(true);
  const [discoveryDroppedPanelCollapsed, setDiscoveryDroppedPanelCollapsed] = useState(false);
  const [pathCandidates, setPathCandidates] = useState<PairPathCandidate[]>([]);
  const [chosenPathByPair, setChosenPathByPair] = useState<Record<string, number>>({});
  const [appliedExtraPaths, setAppliedExtraPaths] = useState<Record<string, number[]>>({});

  const [sel, setSel] = useState<Sel>({ kind: "none" });
  const [nodeDetail, setNodeDetail] = useState<NodeDetailResp | null>(null);
  const [edgeDetail, setEdgeDetail] = useState<EdgeDetailResp | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedEdgeGraphId, setSelectedEdgeGraphId] = useState<string | null>(null);
  const [discoveryExpandProbeNodeId, setDiscoveryExpandProbeNodeId] = useState<number | null>(null);
  const discoveryExpandProbeTokenRef = useRef(0);

  const [relationTypeCatalogItems, setRelationTypeCatalogItems] = useState<RelationTypeItem[]>([]);
  const [relationTypeCatalogQuery, setRelationTypeCatalogQuery] = useState("");
  const [relationTypeCatalogMatchedTotal, setRelationTypeCatalogMatchedTotal] = useState(0);
  const [relationTypeCatalogNextOffset, setRelationTypeCatalogNextOffset] = useState<number | null>(0);
  const [relationTypeCatalogHasMore, setRelationTypeCatalogHasMore] = useState(false);
  const [relationTypeCatalogLoading, setRelationTypeCatalogLoading] = useState(false);

  const [renderNodeLabels, setRenderNodeLabels] = useState(true);
  const [renderEdgeLabels, setRenderEdgeLabels] = useState(false);
  const [edgeLabelPickerOpen, setEdgeLabelPickerOpen] = useState(false);
  const [edgeLabelKeyword, setEdgeLabelKeyword] = useState("");
  const [edgeLabelSelectedDisplays, setEdgeLabelSelectedDisplays] = useState<string[]>([]);
  const [edgeLabelSelectionTouched, setEdgeLabelSelectionTouched] = useState(false);

  const [showSelfLoops, setShowSelfLoops] = useState(false);

  const applyHighlightRef =
    useRef<((nextNodeId: string | null, nextEdgeId: string | null, force?: boolean) => void) | null>(null);
  const { viewportRequest, requestFocusNode, requestFitView } = useGraphViewportController();

  const loadNodeDetail = useCallback(async (vid: number) => {
    setDetailLoading(true);
    try {
      setNodeDetail(await nodeDetailApi(vid));
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `节点详情加载失败：${parsed.message}` });
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadEdgeDetail = useCallback(async (src: number, dst: number, rank: string, edgeType = EDGE_TYPE_DEFAULT) => {
    setDetailLoading(true);
    try {
      setEdgeDetail(
        await edgeDetailApi({
          edge_type: edgeType,
          src,
          dst,
          rank,
        })
      );
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `边详情加载失败：${parsed.message}` });
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const discoverySeeds = discoverySeedsState.items;

  const discoveryDetail = useDiscoveryEntityDetail({
    loadNodeDetail,
    setSel,
    setNodeDetail,
    setEdgeDetail,
    setSelectedEdgeGraphId,
  });

  async function saveNodeEdit(
    vid: number,
    setFields: Record<string, string>,
    expectedVersion: number,
    updatedBy: string
  ): Promise<NodePatchResp> {
    const resp = await patchNodeApi(vid, {
      set: setFields,
      expected_version: expectedVersion,
      updated_by: updatedBy,
    });

    updateNodeInGraph(vid, {
      label: resp.updated.entity_name ?? undefined,
      entity_type: resp.updated.entity_type ?? undefined,
      source: resp.updated.source ?? undefined,
      snippet: resp.updated.description ?? undefined,
    });
    setSearchData((prev) => ({
      ...prev,
      nodes: prev.nodes.map((n) =>
        n.id === vid
          ? {
              ...n,
              label: resp.updated.entity_name ?? n.label,
              entity_type: resp.updated.entity_type ?? n.entity_type,
              source: resp.updated.source ?? n.source,
              snippet: resp.updated.description ?? n.snippet,
            }
          : n
      ),
    }));
    setNodeDetail((prev) => {
      if (!prev || prev.vid !== vid) return prev;
      return {
        ...prev,
        ...resp.updated,
        version: resp.version,
        updated_at: resp.updated_at,
        updated_by: resp.updated_by,
      };
    });
    discoverySeedsState.setItems((prev) =>
      prev.map((item) =>
        item.vid === vid
          ? {
              ...item,
              label: resp.updated.entity_name ?? item.label,
              entity_type: resp.updated.entity_type ?? item.entity_type,
              source: resp.updated.source ?? item.source,
            }
          : item
      )
    );
    setDiscoveryResult((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        nodes: prev.nodes.map((node) =>
          node.id === vid
            ? {
                ...node,
                label: resp.updated.entity_name ?? node.label,
                entity_type: resp.updated.entity_type ?? node.entity_type,
                source: resp.updated.source ?? node.source,
                snippet: resp.updated.description ?? node.snippet,
              }
            : node
        ),
      };
    });
    discoveryCandidateResults.patchCandidate(vid, {
      label: resp.updated.entity_name ?? undefined,
      entity_type: resp.updated.entity_type ?? undefined,
      source: resp.updated.source ?? undefined,
      snippet: resp.updated.description ?? undefined,
      description: resp.updated.description ?? undefined,
    });
    setLastMultiGraphParams((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        selectedEntities: prev.selectedEntities.map((item) =>
          item.vid === vid
            ? {
                ...item,
                label: resp.updated.entity_name ?? item.label,
                entity_type: resp.updated.entity_type ?? item.entity_type,
                source: resp.updated.source ?? item.source,
              }
            : item
        ),
      };
    });
    setLegacyWorkspaceSession((prev) => {
      if (!prev || prev.kind !== "multi") return prev;
      return {
        ...prev,
        params: {
          ...prev.params,
          selectedEntities: prev.params.selectedEntities.map((item) =>
            item.vid === vid
              ? {
                  ...item,
                  label: resp.updated.entity_name ?? item.label,
                  entity_type: resp.updated.entity_type ?? item.entity_type,
                  source: resp.updated.source ?? item.source,
                }
              : item
          ),
        },
      };
    });
    return resp;
  }

  async function saveEdgeEdit(
    identity: { edge_type: string; src: number; dst: number; rank: string },
    setFields: Record<string, string>,
    expectedVersion: number,
    updatedBy: string
  ): Promise<EdgePatchResp> {
    const resp = await patchEdgeApi({
      edge_type: identity.edge_type || EDGE_TYPE_DEFAULT,
      src: identity.src,
      dst: identity.dst,
      rank: identity.rank,
      set: setFields,
      expected_version: expectedVersion,
      updated_by: updatedBy,
    });

    updateEdgeInGraph(
      {
        source: identity.src,
        target: identity.dst,
        rank: identity.rank,
        edge_type: identity.edge_type,
      },
      {
        relation: resp.updated.relation,
        source_db: resp.updated.source,
      }
    );
    setEdgeDetail((prev) => {
      if (!prev) return prev;
      const same =
        Number(prev.src) === Number(identity.src) &&
        Number(prev.dst) === Number(identity.dst) &&
        String(prev.rank) === String(identity.rank) &&
        String(prev.edge_type || EDGE_TYPE_DEFAULT) === String(identity.edge_type || EDGE_TYPE_DEFAULT);
      if (!same) return prev;
      return {
        ...prev,
        relation: resp.updated.relation ?? prev.relation,
        source_db: resp.updated.source ?? prev.source_db,
        evidence: resp.updated.evidence ?? prev.evidence,
        version: resp.version,
        updated_at: resp.updated_at,
        updated_by: resp.updated_by,
      };
    });
    setEdgeSearchData((prev) => ({
      ...prev,
      edges: prev.edges.map((e) => {
        const same =
          Number(e.src) === Number(identity.src) &&
          Number(e.dst) === Number(identity.dst) &&
          String(e.rank) === String(identity.rank) &&
          String(e.edge_type || EDGE_TYPE_DEFAULT) === String(identity.edge_type || EDGE_TYPE_DEFAULT);
        if (!same) return e;
        return {
          ...e,
          relation: resp.updated.relation ?? e.relation,
          source_db: resp.updated.source ?? e.source_db,
        };
      }),
    }));
    setDiscoveryResult((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        edges: prev.edges.map((edge) => {
          const same =
            Number(edge.source) === Number(identity.src) &&
            Number(edge.target) === Number(identity.dst) &&
            String(edge.rank || "0") === String(identity.rank) &&
            String(edge.edge_type || EDGE_TYPE_DEFAULT) === String(identity.edge_type || EDGE_TYPE_DEFAULT);
          if (!same) return edge;
          return {
            ...edge,
            relation: resp.updated.relation ?? edge.relation,
            source_db: resp.updated.source ?? edge.source_db,
          };
        }),
      };
    });
    return resp;
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
    clearGraphData,
    mergeGraphData,
    replaceGraphData,
    updateNodeInGraph,
    updateEdgeInGraph,
    budgetPresetLabel,
    canLoadMoreEdges,
    loadMoreEdges,
    renderMutation: legacyRenderMutation,
    requestRelayout: requestLegacyRelayout,
  } = useGraphData({
    selectedNodeVid,
    onSelectNode: handleSelectNode,
    onClearSelection: handleClearSelection,
    onNotice: (level, message) => setUiNotice({ level, message }),
  });

  const graphBusy = loadingGraph || loadingMultiGraph || loadingDiscovery || loadingApplyPathChoice;
  const [leftW, setLeftW] = useState<number>(() => loadSidebarWidth(LEFT_WIDTH_KEY));
  const [rightW, setRightW] = useState<number>(() => loadSidebarWidth(RIGHT_WIDTH_KEY));
  const resizingSideRef = useRef<"left" | "right" | null>(null);

  useEffect(() => {
    window.localStorage.setItem(LEFT_WIDTH_KEY, String(leftW));
  }, [leftW]);

  useEffect(() => {
    window.localStorage.setItem(RIGHT_WIDTH_KEY, String(rightW));
  }, [rightW]);

  useEffect(() => {
    const onPointerMove = (e: PointerEvent) => {
      const side = resizingSideRef.current;
      if (!side) return;
      if (side === "left") {
        setLeftW(clampSidebarWidth(e.clientX));
      } else {
        setRightW(clampSidebarWidth(window.innerWidth - e.clientX));
      }
    };

    const stopResizing = () => {
      if (!resizingSideRef.current) return;
      resizingSideRef.current = null;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResizing);
    window.addEventListener("pointercancel", stopResizing);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResizing);
      window.removeEventListener("pointercancel", stopResizing);
      stopResizing();
    };
  }, []);

  function beginResize(side: "left" | "right", e: ReactPointerEvent<HTMLDivElement>) {
    e.preventDefault();
    resizingSideRef.current = side;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
  }

  const layoutStyle = useMemo(
    () =>
      ({
        "--leftW": `${leftW}px`,
        "--rightW": `${rightW}px`,
      }) as CSSProperties,
    [leftW, rightW]
  );

  const relationFilter = useRelationFilter({
    appliedRelations: relations,
    graphNodes,
    graphEdges,
    rootVid,
  });

  function clearMultiPathState() {
    setLastMultiGraphRequest(null);
    setPathCandidates([]);
    setChosenPathByPair({});
    setAppliedExtraPaths({});
  }

  function rememberSingleLegacySession(nextRoot: number, nextHop: number, nextRelations: string[]) {
    setLegacyWorkspaceSession({
      kind: "single",
      rootVid: nextRoot,
      hop: nextHop,
      relations: [...nextRelations],
    });
  }

  function rememberCurrentLegacySession() {
    if (graphSourceMode === "multi" && lastMultiGraphParams) {
      setLegacyWorkspaceSession({
        kind: "multi",
        params: { ...lastMultiGraphParams, selectedEntities: [...lastMultiGraphParams.selectedEntities] },
        relations: [...relations],
      });
      return;
    }
    if (graphSourceMode === "single" && rootVid != null) {
      rememberSingleLegacySession(rootVid, hop, relations);
    }
  }

  function applyDiscoveryPayload(
    json: GraphDiscoveryResp,
    request: DiscoveryRequest,
    options?: { resetRuntimeFilters?: boolean }
  ) {
    const resetRuntimeFilters = options?.resetRuntimeFilters ?? true;
    const nodeMap = new Map<number, NodeBrief>();
    for (const node of json.nodes || []) nodeMap.set(node.id, node);
    for (const seed of discoverySeeds) {
      const existing = nodeMap.get(seed.vid);
      if (!existing) {
        nodeMap.set(seed.vid, {
          id: seed.vid,
          label: seed.label,
          entity_type: seed.entity_type || "",
          source: seed.source,
          role: "seed",
        });
        continue;
      }
      nodeMap.set(seed.vid, {
        ...existing,
        label: existing.label || seed.label,
        entity_type: existing.entity_type || seed.entity_type || "",
        source: existing.source || seed.source,
        role: "seed",
      });
    }

    const nextPayload: GraphDiscoveryResp = {
      ...json,
      nodes: Array.from(nodeMap.values()),
      edges: Array.isArray(json.edges) ? json.edges : [],
    };

    replaceGraphData({
      rootVid: request.seed_vids[0],
      nodes: nextPayload.nodes,
      edges: nextPayload.edges,
      stats: (nextPayload.stats || null) as Record<string, unknown> | null,
      hop: request.hop,
    });
    setDiscoveryResult(nextPayload);
    setLastDiscoveryRequest(request);
    discoveryGraphState.initializeFromDiscovery(nextPayload);
    if (resetRuntimeFilters) {
      const nextEntityFacetValues = (nextPayload.facets?.entity_types || []).map((item) => item.entity_type);
      const nextRelationFacetValues = (nextPayload.facets?.relation_types || []).map((item) => item.relation_type);
      const restoreSelectedFilters = (requestValues: string[], allValues: string[], emptySentinel: string) => {
        if (requestValues.includes(emptySentinel)) return [];
        if (requestValues.length === 0) return allValues;
        const allowed = new Set(requestValues);
        return allValues.filter((item) => allowed.has(item));
      };
      const nextRuntimeFilters = {
        entityTypes: restoreSelectedFilters(
          request.allowed_entity_types,
          nextEntityFacetValues,
          DISCOVERY_NONE_ENTITY_TYPE
        ),
        relationTypes: restoreSelectedFilters(
          request.allowed_relation_types,
          nextRelationFacetValues,
          DISCOVERY_NONE_RELATION_TYPE
        ),
      };
      setDiscoveryRuntimeFilters(nextRuntimeFilters);
      setDiscoveryExpandFilters({
        entityTypes: [...nextRuntimeFilters.entityTypes],
        relationTypes: [...nextRuntimeFilters.relationTypes],
      });
    }
    setGraphSourceMode("discovery");
    setLastMultiGraphParams(null);
    clearMultiPathState();
    setRenderEdgeLabels(true);
  }

  async function restoreLegacyWorkspace() {
    if (legacyWorkspaceSession?.kind === "multi") {
      setRelations(legacyWorkspaceSession.relations);
      await runMultiGraph(legacyWorkspaceSession.params, legacyWorkspaceSession.relations);
      return;
    }
    if (legacyWorkspaceSession?.kind === "single") {
      setGraphSourceMode("single");
      setHop(legacyWorkspaceSession.hop);
      setRelations(legacyWorkspaceSession.relations);
      setLastMultiGraphParams(null);
      clearMultiPathState();
      await loadSubgraphWithParams(
        legacyWorkspaceSession.rootVid,
        legacyWorkspaceSession.hop,
        legacyWorkspaceSession.relations
      );
      return;
    }
    setGraphSourceMode("single");
    setLastMultiGraphParams(null);
    clearMultiPathState();
    clearGraphData();
  }

  function restoreDiscoveryWorkspace() {
    if (!discoveryResult || !lastDiscoveryRequest) {
      setGraphSourceMode("discovery");
      setLastMultiGraphParams(null);
      clearMultiPathState();
      clearGraphData();
      discoveryGraphState.resetState();
      return;
    }
    applyDiscoveryPayload(discoveryResult, lastDiscoveryRequest, { resetRuntimeFilters: false });
  }

  async function switchWorkspaceMode(nextMode: WorkspaceMode) {
    if (nextMode === workspaceMode) return;
    setUiNotice(null);

    if (nextMode === "discovery") {
      if (graphSourceMode !== "discovery") rememberCurrentLegacySession();
      setWorkspaceMode("discovery");
      void ensureEntityTypesLoaded();
      restoreDiscoveryWorkspace();
      return;
    }

    setWorkspaceMode("legacy");
    if (graphSourceMode === "discovery") {
      await restoreLegacyWorkspace();
    }
  }

  function buildDiscoveryRequest(queryState = discoveryQuery): DiscoveryRequest {
    const currentEntityFacetItems = discoveryResult?.facets?.entity_types || [];
    const currentRelationFacetItems = discoveryResult?.facets?.relation_types || [];
    const entityFacetValues = currentEntityFacetItems.map((item) => item.entity_type);
    const relationFacetValues = currentRelationFacetItems.map((item) => item.relation_type);
    const buildAllowedValues = (selected: string[], available: string[], emptySentinel: string, fallback: string[]) => {
      if (available.length <= 0) return fallback;
      if (selected.length === available.length) return [];
      if (selected.length === 0) return [emptySentinel];
      return selected;
    };
    return {
      seed_vids: discoverySeeds.map((item) => item.vid),
      allowed_entity_types: buildAllowedValues(
        discoveryRuntimeFilters.entityTypes,
        entityFacetValues,
        DISCOVERY_NONE_ENTITY_TYPE,
        queryState.allowedEntityTypes
      ),
      allowed_relation_types: buildAllowedValues(
        discoveryRuntimeFilters.relationTypes,
        relationFacetValues,
        DISCOVERY_NONE_RELATION_TYPE,
        queryState.allowedRelationTypes
      ),
      max_nodes: queryState.maxNodes,
      max_edges: queryState.maxEdges,
      top_k_per_type: queryState.topKPerType,
      include_candidate_candidate_edges: queryState.includeCandidateCandidateEdges,
      include_seed_seed_edges: queryState.includeSeedSeedEdges,
      hop: queryState.hop,
      ranking_mode: "layered_multiseed",
    };
  }

  function discoveryRequestSignature(request: DiscoveryRequest | null) {
    if (!request) return "";
    return JSON.stringify({
      seed_vids: request.seed_vids,
      allowed_entity_types: request.allowed_entity_types,
      allowed_relation_types: request.allowed_relation_types,
      max_nodes: request.max_nodes,
      max_edges: request.max_edges,
      top_k_per_type: request.top_k_per_type,
      include_candidate_candidate_edges: request.include_candidate_candidate_edges,
      include_seed_seed_edges: request.include_seed_seed_edges,
      hop: request.hop,
      ranking_mode: request.ranking_mode,
    });
  }

  function addDiscoverySeedItems(items: SuggestItem[]) {
    discoverySeedsState.addItems(items);
  }

  async function handleRemoveDiscoverySeed(vid: number) {
    const nextSeeds = discoverySeeds.filter((item) => item.vid !== vid);
    discoverySeedsState.removeItem(vid);
    if (graphSourceMode !== "discovery" || !lastDiscoveryRequest) return;
    if (nextSeeds.length <= 0) {
      setDiscoveryResult(null);
      setLastDiscoveryRequest(null);
      clearGraphData();
      discoveryGraphState.resetState();
      handleClearSelection();
      return;
    }
    await runDiscovery({
      ...buildDiscoveryRequest(),
      seed_vids: nextSeeds.map((item) => item.vid),
    });
  }

  function candidateItemToSeed(item: DiscoveryEntityCandidateItem): SuggestItem {
    return {
      vid: Number(item.vid || item.id),
      label: item.label,
      entity_type: item.entity_type || "",
      source: item.source,
      score: item.score,
    };
  }

  function addSelectedDiscoveryCandidatesToSeeds() {
    const selectedIdSet = discoveryCandidateResults.selectedIdSet;
    const selectedItems = discoveryCandidateResults.result.items.filter((item) => selectedIdSet.has(item.vid));
    if (selectedItems.length <= 0) {
      setUiNotice({ level: "info", message: "请先勾选 1 个或多个候选实体。" });
      return;
    }
    addDiscoverySeedItems(selectedItems.map(candidateItemToSeed));
    discoveryCandidateResults.removeSelected(selectedItems.map((item) => item.vid));
  }

  const currentDiscoveryRequest = useMemo(
    () => buildDiscoveryRequest(discoveryQuery),
    [discoveryQuery, discoverySeeds, discoveryRuntimeFilters, discoveryResult]
  );

  const discoveryHasPendingChanges = useMemo(() => {
    if (!lastDiscoveryRequest) {
      return discoverySeeds.length > 0;
    }
    return discoveryRequestSignature(currentDiscoveryRequest) !== discoveryRequestSignature(lastDiscoveryRequest);
  }, [currentDiscoveryRequest, discoverySeeds.length, lastDiscoveryRequest]);

  async function runDiscovery(requestOverride?: DiscoveryRequest) {
    const request = requestOverride ?? buildDiscoveryRequest();
    if (request.seed_vids.length <= 0) {
      setUiNotice({ level: "info", message: "请先添加至少一个 seed 节点。" });
      return;
    }

    if (graphSourceMode !== "discovery") rememberCurrentLegacySession();
    relationFilter.exitPreview();
    setLoadingDiscovery(true);
    try {
      const json = await graphDiscoveryApi(request);
      applyDiscoveryPayload(json, request);
      if (json.stats?.truncated) {
        const droppedByBudget = Number(json.stats.dropped_by_budget || 0);
        const droppedByTypeBudget = Number(json.stats.dropped_by_type_budget || 0);
        const droppedGenericHubs = Number(json.stats.dropped_generic_hubs || 0);
        setUiNotice({
          level: "warn",
          message:
            `统一关系发现结果已裁剪：dropped_nodes=${Number(json.stats.dropped_nodes || 0)} dropped_edges=${Number(json.stats.dropped_edges || 0)} dropped_neighbors=${Number(json.stats.dropped_neighbors || 0)}` +
            ` dropped_by_budget=${droppedByBudget} dropped_by_type_budget=${droppedByTypeBudget} dropped_generic_hubs=${droppedGenericHubs}`,
        });
      }
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `统一关系发现失败：${parsed.message}` });
    } finally {
      setLoadingDiscovery(false);
    }
  }

  function buildChosenPathMap(nextCandidates: PairPathCandidate[]): Record<string, number> {
    const next: Record<string, number> = {};
    for (const pair of nextCandidates) {
      const key = pairKey(pair.u, pair.v);
      if (pair.candidates.length <= 0) {
        next[key] = -1;
        continue;
      }
      const raw = Number(pair.chosen_index);
      const safe = Number.isFinite(raw) && raw >= 0 && raw < pair.candidates.length ? raw : 0;
      next[key] = safe;
    }
    return next;
  }

  function applyMultiGraphPayload(
    json: MultiEntityGraphResp,
    selectedEntities: SuggestItem[],
    root: number,
    params: MultiGraphParams,
    request: MultiGraphRequest
  ) {
    const nodeMap = new Map<number, NodeBrief>();
    for (const n of json.nodes || []) nodeMap.set(n.id, n);
    for (const s of selectedEntities) {
      if (nodeMap.has(s.vid)) continue;
      nodeMap.set(s.vid, {
        id: s.vid,
        label: s.label,
        entity_type: s.entity_type || "",
        source: s.source,
        score: s.score,
      });
    }

    replaceGraphData({
      rootVid: root,
      nodes: Array.from(nodeMap.values()),
      edges: Array.isArray(json.edges) ? json.edges : [],
      stats: (json.stats || null) as Record<string, unknown> | null,
    });

    const nextCandidates = Array.isArray(json.path_candidates) ? json.path_candidates : [];
    setPathCandidates(nextCandidates);
    setChosenPathByPair(buildChosenPathMap(nextCandidates));
    setAppliedExtraPaths({});
    setGraphSourceMode("multi");
    setLastMultiGraphParams({ ...params, selectedEntities });
    setLegacyWorkspaceSession({
      kind: "multi",
      params: { ...params, selectedEntities: [...selectedEntities] },
      relations: [...request.relations],
    });
    setLastMultiGraphRequest(request);
  }

  async function runSearchWithParams(nextQ: string, nextEntityRawId: string) {
    const qTrimmed = nextQ.trim();
    const rawIdTrimmed = nextEntityRawId.trim();
    if (!qTrimmed && !rawIdTrimmed) return;

    const useRawId = !!rawIdTrimmed;
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

    setLoadingSearch(true);
    setUiNotice(null);
    try {
      const json = await searchApi({
        q: useRawId ? "" : nextQ,
        search_in_name: useRawId ? false : searchName,
        search_in_description: useRawId ? false : searchDesc,
        entity_type: entityType || null,
        source: source || null,
        entity_raw_id: rawIdTrimmed || null,
        entity_raw_id_mode: "contains",
        include_edges: false,
        signal: controller.signal,
      });
      setSearchData(json);
      const firstVid = (json.nodes || [])[0]?.id;
      setSearchSelectedVid(Number.isFinite(firstVid) ? Number(firstVid) : null);
      const includeEdgesNote =
        typeof json.meta === "object" && json.meta
          ? String((json.meta as Record<string, unknown>).include_edges_legacy_note || "")
          : "";
      if (includeEdgesNote) {
        setUiNotice({ level: "info", message: includeEdgesNote });
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") {
        return;
      }
      const parsed = parseApiError(e);
      const base = parsed.message || "搜索失败";
      setUiNotice({ level: "error", message: `搜索失败：${base}` });
    } finally {
      if (searchAbortRef.current === controller) {
        setLoadingSearch(false);
      }
    }
  }

  async function runSearch() {
    await runSearchWithParams(q, entityRawId);
  }


  useEffect(() => {
    return () => {
      searchAbortRef.current?.abort();
    };
  }, []);
  async function runEdgeSearch() {
    if (!edgeQ.trim()) return;
    setLoadingEdgeSearch(true);
    setEdgeSearchNotice(null);
    try {
      const json = await edgeSearchApi({
        q: edgeQ,
        search_in_relation: edgeSearchInRelation,
        search_in_props: edgeSearchInProps,
        source_db: edgeSearchSourceDb || null,
        relation: edgeSearchRelation || null,
        limit: 100,
      });
      setEdgeSearchData(json);
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `边搜索失败：${parsed.message}` });
    } finally {
      setLoadingEdgeSearch(false);
    }
  }

  async function runMultiGraph(params: MultiGraphParams, overrideRelations?: string[]) {
    relationFilter.exitPreview();
    const seen = new Set<number>();
    const selectedEntities = params.selectedEntities.filter((x) => {
      if (seen.has(x.vid)) return false;
      seen.add(x.vid);
      return true;
    });

    if (selectedEntities.length < 2) return;
    if (selectedEntities.length > 8) {
      setUiNotice({ level: "warn", message: "多实体关系最多支持 8 个实体，请减少选择后重试。" });
      return;
    }

    const vids = selectedEntities.map((x) => x.vid);
    const reqRelations = overrideRelations ?? relations;
    const safeK = params.k > 3 ? 3 : params.k < 2 ? 2 : params.k;
    if (safeK !== params.k) {
      setUiNotice({ level: "info", message: `k 已自动调整为 ${safeK}（当前仅支持 2~3）。` });
    }
    const reqBody: MultiGraphRequest = {
      vids,
      direct_only: params.explainPaths ? false : params.directOnly,
      explain_paths: params.explainPaths,
      k: safeK as 2 | 3,
      relations: reqRelations,
      max_nodes: 300,
      max_edges: 20000,
      per_pair_path_limit: 1,
      ignore_direction: true,
    };

    setLoadingMultiGraph(true);
    setEdgeSearchNotice(null);
    try {
      const json = await multiEntityGraphApi(reqBody);
      applyMultiGraphPayload(json, selectedEntities, vids[0], { ...params, k: safeK as 2 | 3 }, reqBody);
      if (json.stats?.truncated) {
        setUiNotice({
          level: "warn",
          message: `多实体图结果已裁剪：dropped_nodes=${Number(json.stats?.dropped_nodes || 0)} dropped_edges=${Number(json.stats?.dropped_edges || 0)} dropped_neighbors=${Number(json.stats?.dropped_neighbors || 0)}`,
        });
      }
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `多实体图生成失败：${parsed.message}` });
    } finally {
      setLoadingMultiGraph(false);
    }
  }

  function setChosenPathForPair(u: number, v: number, chosenIndex: number) {
    const key = pairKey(u, v);
    setChosenPathByPair((prev) => ({ ...prev, [key]: chosenIndex }));
  }

  function buildApplyPathChoices(
    candidates: PairPathCandidate[],
    chosenMap: Record<string, number>
  ): Array<{ u: number; v: number; chosen_index: number }> {
    const out: Array<{ u: number; v: number; chosen_index: number }> = [];
    for (const pair of candidates) {
      if (pair.candidates.length <= 0) continue;
      const key = pairKey(pair.u, pair.v);
      const raw = chosenMap[key];
      const fallback = Number(pair.chosen_index);
      const chosenIndex =
        Number.isFinite(raw) && raw >= 0 && raw < pair.candidates.length
          ? raw
          : Number.isFinite(fallback) && fallback >= 0 && fallback < pair.candidates.length
            ? fallback
            : 0;
      out.push({ u: pair.u, v: pair.v, chosen_index: chosenIndex });
    }
    return out;
  }

  async function applyChosenPathForPair(u: number, v: number) {
    if (graphSourceMode !== "multi") return;
    if (!lastMultiGraphRequest || !lastMultiGraphParams) return;

    const target = pathCandidates.find((p) => pairKey(p.u, p.v) === pairKey(u, v));
    if (!target || target.candidates.length <= 0) return;

    const key = pairKey(u, v);
    const selectedRaw = chosenPathByPair[key];
    const selectedIndex =
      Number.isFinite(selectedRaw) && selectedRaw >= 0 && selectedRaw < target.candidates.length ? selectedRaw : 0;

    const nextChosenByPair = { ...chosenPathByPair, [key]: selectedIndex };
    const choices = buildApplyPathChoices(pathCandidates, nextChosenByPair);
    if (choices.length <= 0) return;

    setLoadingApplyPathChoice(true);
    try {
      const json = await multiEntityGraphApplyPathsApi({
        base_request: lastMultiGraphRequest,
        choices,
      });
      const selectedEntities = lastMultiGraphParams.selectedEntities;
      const nextRoot = selectedEntities[0]?.vid ?? lastMultiGraphRequest.vids[0];
      applyMultiGraphPayload(json, selectedEntities, nextRoot, lastMultiGraphParams, lastMultiGraphRequest);
      if (json.stats?.truncated) {
        setUiNotice({
          level: "warn",
          message: `路径应用后图结果被裁剪：dropped_nodes=${Number(json.stats?.dropped_nodes || 0)} dropped_edges=${Number(json.stats?.dropped_edges || 0)} dropped_neighbors=${Number(json.stats?.dropped_neighbors || 0)}`,
        });
      }
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `路径应用失败：${parsed.message}` });
    } finally {
      setLoadingApplyPathChoice(false);
    }
  }

  function appendChosenPathForPair(u: number, v: number) {
    if (graphSourceMode !== "multi") return;
    if (!lastMultiGraphRequest) return;

    const target = pathCandidates.find((p) => pairKey(p.u, p.v) === pairKey(u, v));
    if (!target || target.candidates.length <= 0) return;

    const key = pairKey(u, v);
    const selectedRaw = chosenPathByPair[key];
    const selectedIndex =
      Number.isFinite(selectedRaw) && selectedRaw >= 0 && selectedRaw < target.candidates.length ? selectedRaw : 0;
    const candidate = target.candidates[selectedIndex];
    if (!candidate) return;

    const nodeMap = new Map<number, NodeBrief>();
    for (const n of graphNodes) nodeMap.set(n.id, n);
    for (const nid of candidate.nodes || []) {
      const id = Number(nid);
      if (!Number.isFinite(id) || nodeMap.has(id)) continue;
      nodeMap.set(id, {
        id,
        label: multiEntityLabelMap.get(id) || String(id),
        entity_type: "",
        source: "",
      });
    }

    const edgeMap = new Map<string, (typeof graphEdges)[number]>();
    for (const e of graphEdges) {
      const ek = edgeKey(e);
      edgeMap.set(ek, e);
    }
    for (const e of candidate.edges || []) {
      const ek = edgeKey(e);
      if (edgeMap.has(ek)) continue;
      edgeMap.set(ek, { ...e, is_explain: true });
    }

    const maxNodes = Math.max(2, Number(lastMultiGraphRequest.max_nodes || 300));
    const maxEdges = Math.max(1, Number(lastMultiGraphRequest.max_edges || 20000));
    if (nodeMap.size > maxNodes) {
      setUiNotice({ level: "warn", message: `追加失败：节点数将超过上限 ${maxNodes}。请提高 max_nodes 或改用替换。` });
      return;
    }
    if (edgeMap.size > maxEdges) {
      setUiNotice({ level: "warn", message: `追加失败：边数将超过上限 ${maxEdges}。请提高 max_edges 或改用替换。` });
      return;
    }

    const nextRoot = rootVid ?? lastMultiGraphRequest.vids[0];
    const nextStats = {
      ...((graphStats || {}) as Record<string, unknown>),
      node_count: nodeMap.size,
      edge_count: edgeMap.size,
    };
    replaceGraphData({
      rootVid: nextRoot,
      nodes: Array.from(nodeMap.values()),
      edges: Array.from(edgeMap.values()),
      stats: nextStats,
    });

    setAppliedExtraPaths((prev) => {
      const existing = prev[key] || [];
      if (existing.includes(selectedIndex)) return prev;
      return { ...prev, [key]: [...existing, selectedIndex] };
    });
  }

  async function loadSingleSubgraph(vid: number, autoSelectRoot = true) {
    relationFilter.exitPreview();
    setGraphSourceMode("single");
    setLastMultiGraphParams(null);
    clearMultiPathState();
    await loadSubgraph(vid);
    rememberSingleLegacySession(vid, hop, relations);
    if (autoSelectRoot) handleSelectNode(vid);
  }

  async function loadSelectedSearchSubgraph(vidOverride?: number) {
    const targetVid = Number.isFinite(vidOverride as number) ? Number(vidOverride) : searchSelectedVid;
    if (targetVid == null) {
      setUiNotice({ level: "info", message: "请先在搜索结果中选择一个节点作为 root。" });
      return;
    }
    setSearchSelectedVid(targetVid);
    await loadSingleSubgraph(targetVid);
  }

  async function loadDiscoveryCandidateSubgraph(item: DiscoveryEntityCandidateItem) {
    const vid = Number(item.vid || item.id);
    if (!Number.isFinite(vid)) return;
    if (workspaceMode === "discovery") setWorkspaceMode("legacy");
    await loadSingleSubgraph(vid);
  }

  async function reloadGraphByCurrentMode(nextRoot: number) {
    if (graphSourceMode === "discovery" && lastDiscoveryRequest) {
      await runDiscovery(lastDiscoveryRequest);
      return;
    }
    if (graphSourceMode === "multi" && lastMultiGraphParams) {
      await runMultiGraph(lastMultiGraphParams);
      return;
    }
    await loadSingleSubgraph(nextRoot);
  }

  async function loadGraphWithFilters(nextRoot: number, nextHop: number, nextRelations: string[]) {
    relationFilter.exitPreview();
    if (graphSourceMode === "discovery" && lastDiscoveryRequest) {
      await runDiscovery({
        ...lastDiscoveryRequest,
        allowed_relation_types: nextRelations,
        hop: nextHop,
      });
      return;
    }
    if (graphSourceMode === "multi" && lastMultiGraphParams) {
      await runMultiGraph(lastMultiGraphParams, nextRelations);
      return;
    }
    setGraphSourceMode("single");
    setLastMultiGraphParams(null);
    clearMultiPathState();
    await loadSubgraphWithParams(nextRoot, nextHop, nextRelations);
    rememberSingleLegacySession(nextRoot, nextHop, nextRelations);
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
      void runSearchWithParams(item.label, entityRawId);
    },
    onQueryChange: setQ,
    onSearch: () => {
      void runSearch();
    },
  });

  const {
    suggestOpen: rawIdSuggestOpen,
    suggestItems: rawIdSuggestItems,
    suggestLoading: rawIdSuggestLoading,
    suggestError: rawIdSuggestError,
    suggestHighlightIndex: rawIdSuggestHighlightIndex,
    suggestWrapRef: rawIdSuggestWrapRef,
    onInputChange: onRawIdInputChange,
    onKeyDown: onRawIdKeyDown,
    setSuggestHighlightIndex: setRawIdSuggestHighlightIndex,
    closeSuggestPanel: closeRawIdSuggestPanel,
    selectSuggestCandidate: selectRawIdSuggestCandidate,
  } = useRawIdSuggest({
    q: entityRawId,
    entityType,
    source,
    onSelect: (item: RawIdSuggestItem) => {
      setEntityRawId(item.entity_raw_id);
      if (item.label) setQ(item.label);
      void runSearchWithParams(item.label || q, item.entity_raw_id);
    },
    onQueryChange: setEntityRawId,
    onSearch: () => {
      void runSearch();
    },
  });

  const {
    suggestOpen: edgeSuggestOpen,
    suggestItems: edgeSuggestItems,
    suggestLoading: edgeSuggestLoading,
    suggestError: edgeSuggestError,
    suggestHighlightIndex: edgeSuggestHighlightIndex,
    suggestWrapRef: edgeSuggestWrapRef,
    onInputChange: onEdgeInputChange,
    onKeyDown: onEdgeKeyDown,
    setSuggestHighlightIndex: setEdgeSuggestHighlightIndex,
    closeSuggestPanel: closeEdgeSuggestPanel,
    selectSuggestCandidate: selectEdgeSuggestCandidate,
  } = useEdgeSuggest({
    q: edgeQ,
    relation: edgeSearchRelation,
    sourceDb: edgeSearchSourceDb,
    onSelect: (item) => {
      setEdgeQ(relationDisplay(item.relation) || item.relation);
      void handleSelectEdgeCandidate(item);
    },
    onQueryChange: setEdgeQ,
    onSearch: () => {
      void runEdgeSearch();
    },
  });

  const discoverySelectedSeedVidSet = useMemo(() => {
    const seed = new Set<number>();
    for (const item of discoverySeeds) seed.add(item.vid);
    return seed;
  }, [discoverySeeds]);

  const discoveryRunSeedVidSet = useMemo(() => {
    if (graphSourceMode !== "discovery") return new Set<number>();
    const seed = new Set<number>();
    for (const vid of lastDiscoveryRequest?.seed_vids || []) seed.add(Number(vid));
    if (seed.size === 0) {
      for (const node of discoveryResult?.nodes || []) {
        if (node.role === "seed") seed.add(node.id);
      }
    }
    return seed;
  }, [graphSourceMode, discoveryResult, lastDiscoveryRequest]);

  const discoveryGraphState = useDiscoveryGraphState({
    graphNodes,
    graphEdges,
    maxNodes: lastDiscoveryRequest?.max_nodes ?? discoveryQuery.maxNodes,
    maxEdges: lastDiscoveryRequest?.max_edges ?? discoveryQuery.maxEdges,
    seedNodeIds: discoveryRunSeedVidSet,
    onMergeGraphData: mergeGraphData,
    onNotice: (level, message) => setUiNotice({ level, message }),
  });
  const currentDiscoveryExpandFingerprint = useMemo(
    () =>
      JSON.stringify({
        entityTypes: [...discoveryExpandFilters.entityTypes].sort((a, b) => a.localeCompare(b)),
        relationTypes: [...discoveryExpandFilters.relationTypes].sort((a, b) => a.localeCompare(b)),
      }),
    [discoveryExpandFilters.entityTypes, discoveryExpandFilters.relationTypes]
  );

  const discoveryWorkspaceReady = workspaceMode === "discovery" && graphSourceMode === "discovery" && !!discoveryResult;
  const effectiveGraphNodes =
    workspaceMode === "discovery"
      ? discoveryGraphState.visibleGraphNodes || EMPTY_GRAPH_NODES
      : relationFilter.previewActive
      ? relationFilter.previewNodes
      : graphNodes;
  const effectiveGraphEdges =
    workspaceMode === "discovery"
      ? discoveryGraphState.visibleGraphEdges || EMPTY_GRAPH_EDGES
      : relationFilter.previewActive
      ? relationFilter.previewEdges
      : graphEdges;
  const effectiveGraphStats =
    workspaceMode === "discovery"
      ? ({
          ...(discoveryResult?.stats || {}),
          node_count: discoveryGraphState.visibleGraphNodes.length,
          edge_count: discoveryGraphState.visibleGraphEdges.length,
          rendered_nodes: discoveryGraphState.renderedNodeIds.size,
          rendered_edges: discoveryGraphState.renderedEdgeIds.size,
          hidden_by_user: discoveryGraphState.hiddenNodeIds.size,
        } as Record<string, unknown>)
      : relationFilter.previewActive
      ? ({
          ...(graphStats || {}),
          relation_preview: true,
          node_count: effectiveGraphNodes.length,
          edge_count: effectiveGraphEdges.length,
        } as Record<string, unknown>)
      : graphStats;

  const visibilityRanking = useVisibilityRanking({
    graphNodes: effectiveGraphNodes,
    graphEdges: effectiveGraphEdges,
    rootVid,
    manualHiddenNodeIds,
    manualRevealedNodeIds,
    showSelfLoops,
    nodeGroupRootById,
    searchNodes: searchData.nodes,
  });

  const discoveryVisibleNodeHopLevelMap = useMemo(() => {
    const next = new Map<number, number>();
    if (workspaceMode !== "discovery") return next;
    for (const node of effectiveGraphNodes) {
      const role = String(node.role || "");
      const layer = String(node.layer || "");
      if (role === "seed") next.set(node.id, 0);
      else if (layer === "core") next.set(node.id, 1);
      else if (layer === "shared") next.set(node.id, 2);
      else if (layer === "local") next.set(node.id, 3);
      else next.set(node.id, 4);
    }
    return next;
  }, [workspaceMode, effectiveGraphNodes]);

  const discoveryVisibleNodeIdSet = useMemo(() => {
    const next = new Set<number>();
    if (workspaceMode !== "discovery") return next;
    for (const node of discoveryGraphState.visibleGraphNodes) next.add(node.id);
    return next;
  }, [workspaceMode, discoveryGraphState.visibleGraphNodes]);

  const visibleGraphNodes =
    workspaceMode === "discovery" ? effectiveGraphNodes : visibilityRanking.visibleGraphNodes;
  const visibleNodeIdSet =
    workspaceMode === "discovery" ? discoveryVisibleNodeIdSet : visibilityRanking.visibleNodeIdSet;
  const visibleGraphEdges =
    workspaceMode === "discovery" ? effectiveGraphEdges : visibilityRanking.visibleGraphEdges;
  const hiddenSelfLoopCount =
    workspaceMode === "discovery"
      ? showSelfLoops
        ? 0
        : discoveryGraphState.visibleGraphEdges.filter((edge) => edge.source === edge.target).length
      : visibilityRanking.hiddenSelfLoopCount;
  const visibleSelfLoopCount =
    workspaceMode === "discovery"
      ? showSelfLoops
        ? discoveryGraphState.visibleGraphEdges.filter((edge) => edge.source === edge.target).length
        : 0
      : visibilityRanking.visibleSelfLoopCount;
  const autoVisibleTopIds =
    workspaceMode === "discovery" ? discoveryVisibleNodeIdSet : visibilityRanking.autoVisibleTopIds;
  const visibleNodeHopLevelMap =
    workspaceMode === "discovery" ? discoveryVisibleNodeHopLevelMap : visibilityRanking.visibleNodeHopLevelMap;
  const panelNodes = workspaceMode === "discovery" ? EMPTY_GRAPH_NODES : visibilityRanking.panelNodes;
  const panelGroups = workspaceMode === "discovery" ? [] : visibilityRanking.panelGroups;
  const hiddenCount =
    workspaceMode === "discovery" ? discoveryGraphState.hiddenNodeIds.size : visibilityRanking.hiddenCount;
  const visibleCount =
    workspaceMode === "discovery" ? discoveryGraphState.visibleGraphNodes.length : visibilityRanking.visibleCount;

  useEffect(() => {
    if (workspaceMode === "discovery") return;
    if (panelGroups.length === 0) return;
    setPanelGroupCollapsed((prev) => {
      const next = { ...prev };
      let changed = false;
      for (const g of panelGroups) {
        const k = String(g.groupRoot);
        if (!(k in next)) {
          next[k] = true;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [workspaceMode, panelGroups, setPanelGroupCollapsed]);

  useEffect(() => {
    if (!relationFilter.open) return;
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      setRelationTypeCatalogLoading(true);
      void relationTypesApi({
        q: relationTypeCatalogQuery,
        limit: RELATION_TYPES_PAGE_SIZE,
        offset: 0,
        signal: controller.signal,
      })
        .then((resp) => {
          setRelationTypeCatalogItems(resp.items);
          setRelationTypeCatalogMatchedTotal(resp.matched_total);
          setRelationTypeCatalogNextOffset(resp.next_offset);
          setRelationTypeCatalogHasMore(resp.has_more);
        })
        .catch((e: unknown) => {
          if (e instanceof Error && e.name === "AbortError") return;
          const parsed = parseApiError(e);
          setUiNotice({ level: "warn", message: `关系类型列表加载失败：${parsed.message}` });
        })
        .finally(() => {
          if (!controller.signal.aborted) setRelationTypeCatalogLoading(false);
        });
    }, 180);

    return () => {
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [relationFilter.open, relationTypeCatalogQuery]);

  const handleLoadMoreRelationTypes = useCallback(async () => {
    if (relationTypeCatalogLoading) return;
    if (!relationTypeCatalogHasMore || relationTypeCatalogNextOffset == null) return;
    setRelationTypeCatalogLoading(true);
    try {
      const resp = await relationTypesApi({
        q: relationTypeCatalogQuery,
        limit: RELATION_TYPES_PAGE_SIZE,
        offset: relationTypeCatalogNextOffset,
      });
      setRelationTypeCatalogItems((prev) => mergeRelationTypeItems(prev, resp.items));
      setRelationTypeCatalogMatchedTotal(resp.matched_total);
      setRelationTypeCatalogNextOffset(resp.next_offset);
      setRelationTypeCatalogHasMore(resp.has_more);
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "warn", message: `关系类型列表加载失败：${parsed.message}` });
    } finally {
      setRelationTypeCatalogLoading(false);
    }
  }, [
    relationTypeCatalogHasMore,
    relationTypeCatalogLoading,
    relationTypeCatalogNextOffset,
    relationTypeCatalogQuery,
  ]);

  function handleOpenRelationFilter() {
    setRelationTypeCatalogItems([]);
    setRelationTypeCatalogQuery("");
    setRelationTypeCatalogMatchedTotal(0);
    setRelationTypeCatalogNextOffset(0);
    setRelationTypeCatalogHasMore(false);
    setRelationTypeCatalogLoading(false);
    relationFilter.openPanel();
  }

  function toggleEdgeLabelDisplay(disp: string) {
    setEdgeLabelSelectionTouched(true);
    setEdgeLabelSelectedDisplays((prev) => {
      const s = new Set(prev);
      if (s.has(disp)) {
        s.delete(disp);
      } else {
        s.add(disp);
      }
      return Array.from(s).sort((a, b) => a.localeCompare(b));
    });
  }

  const multiSeedVidSet = useMemo(() => {
    if (graphSourceMode !== "multi" || !lastMultiGraphParams) return new Set<number>();
    const seed = new Set<number>();
    for (const item of lastMultiGraphParams.selectedEntities) seed.add(item.vid);
    return seed;
  }, [graphSourceMode, lastMultiGraphParams]);

  const activeSeedVidSet = graphSourceMode === "multi" ? multiSeedVidSet : discoveryRunSeedVidSet;

  const multiEntityLabelMap = useMemo(() => {
    const m = new Map<number, string>();
    for (const item of lastMultiGraphParams?.selectedEntities || []) {
      if (item.label) m.set(item.vid, item.label);
    }
    for (const n of graphNodes) {
      if (!m.has(n.id) && n.label) m.set(n.id, n.label);
    }
    for (const n of searchData.nodes) {
      if (!m.has(n.id) && n.label) m.set(n.id, n.label);
    }
    return m;
  }, [lastMultiGraphParams, graphNodes, searchData.nodes]);

  const showPathCandidates = graphSourceMode === "multi" && !!lastMultiGraphRequest?.explain_paths;

  const activeRenderMutation =
    workspaceMode === "discovery" ? discoveryGraphState.renderMutation : legacyRenderMutation;
  const { layoutPlan, nodePositionById } = useGraphLayoutController({
    visibleNodeIds: visibleGraphNodes.map((node) => String(node.id)),
    nodePositionCache: workspaceMode === "discovery" ? discoveryGraphState.nodePositionCache : undefined,
    renderMutation: activeRenderMutation,
  });
  const {
    viewModel,
    currentVisibleEdgeLabelDisplays,
    effectiveEdgeLabelSelectedDisplays,
    edgeLabelSelectedSet,
    edgeLabelFilteredDisplays,
    edgeLabelAllVisibleChecked,
  } = useGraphViewModel({
    visibleGraphNodes,
    visibleGraphEdges,
    rootVid,
    visibleNodeHopLevelMap,
    activeSeedVidSet,
    graphSourceMode,
    nodePositionById,
    discoveryTypeColor,
    edgeLabelSelectedDisplays,
    edgeLabelSelectionTouched,
    edgeLabelKeyword,
  });
  const renderPatch = useGraphPatchBuilder(viewModel);

  const selectEdgeWithDetail = useCallback(
    (target: EdgeSearchItem, edgeId: string | null) => {
      const source_db = target.source_db ? String(target.source_db) : undefined;
      const rank = String(target.rank || "0");
      const edge_type = String(target.edge_type || EDGE_TYPE_DEFAULT);
      setSelectedEdgeGraphId(edgeId);
      setSel({
        kind: "edge",
        src: Number(target.src),
        dst: Number(target.dst),
        rank,
        edge_type,
        relation: String(target.relation || ""),
        source_db,
      });
      setNodeDetail(null);
      void loadEdgeDetail(Number(target.src), Number(target.dst), rank, edge_type);

      if (edgeId) {
        applyHighlightRef.current?.(null, edgeId, true);
      }
    },
    [loadEdgeDetail]
  );

  function trySelectEdgeFromCurrentRenderedGraph(target: EdgeSearchItem): boolean {
    const edgeId = findEdgeIdByIdentity(viewModel.edgeById, {
      src: Number(target.src),
      dst: Number(target.dst),
      rank: String(target.rank || "0"),
      edge_type: String(target.edge_type || EDGE_TYPE_DEFAULT),
    });
    if (!edgeId) return false;
    selectEdgeWithDetail(target, edgeId);
    return true;
  }

  useEffect(() => {
    if (workspaceMode !== "discovery" || graphSourceMode !== "discovery") return;
    if (sel.kind !== "node") return;
    setDiscoveryExpandFilters({
      entityTypes: [...discoveryRuntimeFilters.entityTypes],
      relationTypes: [...discoveryRuntimeFilters.relationTypes],
    });
  }, [workspaceMode, graphSourceMode, sel, discoveryRuntimeFilters]);

  useEffect(() => {
    if (workspaceMode !== "discovery" || graphSourceMode !== "discovery" || !discoveryWorkspaceReady) return;
    if (sel.kind !== "node") return;
    const nodeId = sel.vid;
    if (!discoveryGraphState.graphEntityMap.has(nodeId)) return;
    if (discoveryGraphState.getNodeExpandUiState(nodeId, currentDiscoveryExpandFingerprint) === "expanded") {
      setDiscoveryExpandProbeNodeId((prev) => (prev === nodeId ? null : prev));
      return;
    }
    const nextToken = discoveryExpandProbeTokenRef.current + 1;
    discoveryExpandProbeTokenRef.current = nextToken;
    setDiscoveryExpandProbeNodeId(nodeId);
    void discoveryGraphState
      .probeNodeExpand({
        targetNodeId: nodeId,
        allowedEntityTypes: discoveryExpandFilters.entityTypes,
        allowedRelationTypes: discoveryExpandFilters.relationTypes,
        expandTopKPerType: 8,
      })
      .catch((e: unknown) => {
        const parsed = parseApiError(e);
        setUiNotice({ level: "error", message: `Expand 探测失败：${parsed.message}` });
      })
      .finally(() => {
        if (discoveryExpandProbeTokenRef.current !== nextToken) return;
        setDiscoveryExpandProbeNodeId((prev) => (prev === nodeId ? null : prev));
      });
  }, [
    workspaceMode,
    graphSourceMode,
    discoveryWorkspaceReady,
    sel,
    discoveryExpandFilters,
    currentDiscoveryExpandFingerprint,
    discoveryGraphState.graphEntityMap,
  ]);

  async function handleSelectEdgeCandidate(item: EdgeSearchItem) {
    setEdgeSearchNotice(null);

    revealNode(Number(item.src));
    revealNode(Number(item.dst));

    if (trySelectEdgeFromCurrentRenderedGraph(item)) return;

    setPendingEdgeLocate(item);
    await loadSingleSubgraph(Number(item.src), false);
  }

  useEffect(() => {
    if (!pendingEdgeLocate) return;
    if (loadingGraph || loadingMultiGraph) return;

    const edgeId = findEdgeIdByIdentity(viewModel.edgeById, {
      src: Number(pendingEdgeLocate.src),
      dst: Number(pendingEdgeLocate.dst),
      rank: String(pendingEdgeLocate.rank || "0"),
      edge_type: String(pendingEdgeLocate.edge_type || EDGE_TYPE_DEFAULT),
    });

    if (edgeId) {
      selectEdgeWithDetail(pendingEdgeLocate, edgeId);
      setPendingEdgeLocate(null);
      setEdgeSearchNotice(null);
      return;
    }

    if (rootVid !== Number(pendingEdgeLocate.src)) return;

    const existsInGraphData = graphEdges.some((e) =>
      isSameEdge(e, {
        src: Number(pendingEdgeLocate.src),
        dst: Number(pendingEdgeLocate.dst),
        rank: String(pendingEdgeLocate.rank || "0"),
        edge_type: String(pendingEdgeLocate.edge_type || EDGE_TYPE_DEFAULT),
      })
    );

    if (existsInGraphData) {
      selectEdgeWithDetail(pendingEdgeLocate, null);
      setEdgeSearchNotice("该边已在当前图数据中，但当前未渲染（请检查自环开关或节点显示状态）。");
    } else {
      const msg = "该边不在当前 hop/relations 限制下可见，请提高 hop 或调整关系筛选后重试。";
      setEdgeSearchNotice(msg);
      setUiNotice({ level: "warn", message: msg });
    }

    setPendingEdgeLocate(null);
  }, [pendingEdgeLocate, loadingGraph, loadingMultiGraph, viewModel.edgeById, rootVid, graphEdges, selectEdgeWithDetail]);

  const selectedNodeBrief = useMemo(() => {
    if (sel.kind !== "node") return null;
    const graphNode =
      workspaceMode === "discovery"
        ? discoveryGraphState.graphEntityMap.get(sel.vid) || null
        : effectiveGraphNodes.find((n) => n.id === sel.vid) || null;
    if (graphNode) return graphNode;
    if (workspaceMode === "discovery") {
      const candidateNode = discoveryCandidateResults.result.items.find((item) => item.vid === sel.vid);
      if (candidateNode) return candidateNode;
      const seedNode = discoverySeeds.find((item) => item.vid === sel.vid);
      if (seedNode) {
        return {
          id: seedNode.vid,
          label: seedNode.label,
          entity_type: seedNode.entity_type || "",
          source: seedNode.source,
          score: seedNode.score,
        };
      }
    }
    return searchData.nodes.find((n) => n.id === sel.vid) || null;
  }, [
    sel,
    effectiveGraphNodes,
    workspaceMode,
    discoveryGraphState.graphEntityMap,
    discoveryCandidateResults.result.items,
    discoverySeeds,
    searchData.nodes,
  ]);

  const selectedNodeIsRoot = sel.kind === "node" && rootVid != null && sel.vid === rootVid;
  const selectedNodeIsVisible = sel.kind === "node" ? visibleNodeIdSet.has(sel.vid) : false;
  const selectedNodeIsAutoTop = sel.kind === "node" ? autoVisibleTopIds.has(sel.vid) : false;
  const selectedNodeExpandClosable = sel.kind === "node" && expandedSourceNodeIds.has(sel.vid);
  const discoverySelectedExpandSession =
    sel.kind === "node" ? discoveryGraphState.expandSessionMap[String(sel.vid)] : undefined;
  const discoverySelectedNodeExpandUiState =
    sel.kind === "node"
      ? discoveryGraphState.getNodeExpandUiState(sel.vid, currentDiscoveryExpandFingerprint)
      : "collapsed";
  const discoverySelectedExpandFilterMismatch = Boolean(
    discoverySelectedExpandSession?.isExpanded &&
      discoverySelectedExpandSession.requestFingerprint !== currentDiscoveryExpandFingerprint
  );

  const selectedNodeProbeState =
    workspaceMode === "discovery" ? undefined : sel.kind === "node" ? expandProbeByVid[sel.vid] : undefined;

  const expandButtonDisabled =
    workspaceMode === "discovery"
      ? graphBusy ||
        sel.kind !== "node" ||
        (sel.kind === "node" && discoveryExpandProbeNodeId === sel.vid && discoverySelectedNodeExpandUiState !== "expanded") ||
        discoverySelectedNodeExpandUiState === "expanding" ||
        (discoverySelectedNodeExpandUiState === "terminal" && discoveryExpandProbeNodeId !== sel.vid)
      : graphBusy ||
        sel.kind !== "node" ||
        selectedNodeProbeState === "loading" ||
        selectedNodeProbeState === "noextra";

  const expandButtonText =
    workspaceMode === "discovery"
      ? discoverySelectedNodeExpandUiState === "expanded"
        ? "关闭该展开"
        : discoverySelectedNodeExpandUiState === "expanding"
          ? "展开中"
          : sel.kind === "node" && discoveryExpandProbeNodeId === sel.vid
            ? "展开该节点（检测中）"
            : discoverySelectedNodeExpandUiState === "terminal"
              ? "无更多相关节点"
              : "展开该节点"
      : selectedNodeProbeState === "noextra"
        ? "Expand（无多余相关节点）"
        : "Expand（合并 1-hop）";

  const selectedNodeId = sel.kind === "node" ? String(sel.vid) : null;
  const selectedEdgeId = sel.kind === "edge" ? selectedEdgeGraphId : null;

  useEffect(() => {
    if (workspaceMode !== "discovery" || graphSourceMode !== "discovery") return;
    if (sel.kind === "node" && !discoveryGraphState.visibleNodeIdSet.has(sel.vid)) {
      handleClearSelection();
      return;
    }
    if (sel.kind === "edge") {
      const currentEdgeId =
        selectedEdgeGraphId ||
        edgeKey({
          source: sel.src,
          target: sel.dst,
          rank: sel.rank,
          relation: sel.relation,
          edge_type: sel.edge_type,
        } as EdgeBrief);
      if (!discoveryGraphState.visibleEdgeKeySet.has(currentEdgeId)) {
        handleClearSelection();
      }
    }
  }, [
    workspaceMode,
    graphSourceMode,
    sel,
    selectedEdgeGraphId,
    discoveryGraphState.visibleNodeIdSet,
    discoveryGraphState.visibleEdgeKeySet,
  ]);

  function handleSearchClick() {
    closeSuggestPanel();
    closeRawIdSuggestPanel();
    void ensureEntityTypesLoaded();
    void runSearch();
  }

  function handleEdgeSearchClick() {
    closeEdgeSuggestPanel();
    void runEdgeSearch();
  }

  function handleGraphNodeClick(vid: number) {
    handleSelectNode(vid);
  }

  function locateNodeInGraph(vid: number) {
    handleSelectNode(vid);
    requestFocusNode(String(vid));
  }

  function handleRelayoutCurrentGraph() {
    if (visibleGraphNodes.length <= 0) return;
    if (workspaceMode === "discovery") {
      discoveryGraphState.requestRelayout();
    } else {
      requestLegacyRelayout();
    }
  }

  async function handleDiscoveryExpandNode(vid: number) {
    try {
      const result = await discoveryGraphState.toggleNodeExpand({
        targetNodeId: vid,
        allowedEntityTypes: discoveryExpandFilters.entityTypes,
        allowedRelationTypes: discoveryExpandFilters.relationTypes,
        expandMaxNewNodes: 20,
        expandMaxNewEdges: 30,
        expandTopKPerType: 8,
      });
      if (result.action === "collapsed") {
        locateNodeInGraph(vid);
        return;
      }
      const resp = result.response;
      if (!resp || ((resp.new_nodes?.length || 0) <= 0 && (resp.new_edges?.length || 0) <= 0 && (resp.support_edges?.length || 0) <= 0)) {
        setUiNotice({
          level: resp?.terminal ? "info" : "warn",
          message: resp?.terminal ? "该节点当前过滤条件下无更多相关节点。" : "该节点本次 expand 未补入新的节点或边。",
        });
        return;
      }
      locateNodeInGraph(result.firstNodeId ?? vid);
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `Expand 失败：${parsed.message}` });
    }
  }

  function handleHideDiscoveryNode(vid: number) {
    const changed = discoveryGraphState.hideRenderedNode(vid);
    if (changed && sel.kind === "node" && sel.vid === vid) handleClearSelection();
  }

  function handleRestoreHiddenDiscoveryNode(vid: number, locate = false) {
    const changed = discoveryGraphState.restoreHiddenNode(vid);
    if (changed && locate) locateNodeInGraph(vid);
  }

  function handleForceRenderDiscoveryNode(vid: number, locate = false) {
    const changed = discoveryGraphState.forceRenderDroppedNode(vid);
    if (changed && locate) locateNodeInGraph(vid);
  }

  function handleGraphEdgeClick(edgeId: string, edge: (typeof visibleGraphEdges)[number]) {
    const src = Number(edge.source);
    const dst = Number(edge.target);
    const rank = String(edge.rank || "0");
    const edge_type = String(edge.edge_type || EDGE_TYPE_DEFAULT);
    const relation = String(edge.relation || "");
    const source_db = edge.source_db ? String(edge.source_db) : undefined;
    if (!Number.isFinite(src) || !Number.isFinite(dst) || !relation) return;

    setSelectedEdgeGraphId(edgeId);
    setSel({ kind: "edge", src, dst, rank, edge_type, relation, source_db });
    setNodeDetail(null);
    void loadEdgeDetail(src, dst, rank, edge_type);
  }

  async function reloadNodeDetailById(vid: number) {
    await loadNodeDetail(vid);
  }

  async function reloadEdgeDetailByIdentity(identity: { edge_type: string; src: number; dst: number; rank: string }) {
    await loadEdgeDetail(identity.src, identity.dst, identity.rank, identity.edge_type);
  }

  return (
    <div className="kg-layout" style={layoutStyle}>
      {uiNotice ? (
        <div
          style={{
            position: "fixed",
            top: 8,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 1000,
            maxWidth: 980,
            minWidth: 320,
            padding: "10px 14px",
            borderRadius: 8,
            border:
              uiNotice.level === "error"
                ? "1px solid #ffccc7"
                : uiNotice.level === "warn"
                  ? "1px solid #ffe58f"
                  : "1px solid #91caff",
            background:
              uiNotice.level === "error"
                ? "#fff2f0"
                : uiNotice.level === "warn"
                  ? "#fffbe6"
                  : "#e6f4ff",
            color:
              uiNotice.level === "error"
                ? "#a8071a"
                : uiNotice.level === "warn"
                  ? "#874d00"
                  : "#003a8c",
            fontSize: 13,
            boxShadow: "0 6px 20px rgba(0,0,0,0.12)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <span>{uiNotice.message}</span>
          <button
            onClick={() => setUiNotice(null)}
            style={{ border: "none", background: "transparent", cursor: "pointer", color: "inherit" }}
          >
            关闭
          </button>
        </div>
      ) : null}
      <div className="kg-pane kg-pane-left">
        <div style={{ padding: "12px 16px 0 16px", display: "flex", gap: 8 }}>
          <button
            onClick={() => {
              void switchWorkspaceMode("legacy");
            }}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #d9d9d9",
              background: workspaceMode === "legacy" ? "#e6f4ff" : "#fff",
              cursor: "pointer",
              fontWeight: workspaceMode === "legacy" ? 700 : 500,
            }}
          >
            旧模块
          </button>
          <button
            onClick={() => {
              void switchWorkspaceMode("discovery");
            }}
            style={{
              padding: "8px 12px",
              borderRadius: 8,
              border: "1px solid #d9d9d9",
              background: workspaceMode === "discovery" ? "#fff7e6" : "#fff",
              cursor: "pointer",
              fontWeight: workspaceMode === "discovery" ? 700 : 500,
            }}
          >
            统一关系发现
          </button>
        </div>

        {workspaceMode === "legacy" ? (
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
            entityTypeOptions={entityTypeOptions}
            entityTypeFallbackUsed={entityTypeFallbackUsed}
            source={source}
            setSource={setSource}
            entityRawId={entityRawId}
            onRawIdChange={onRawIdInputChange}
            onRawIdInputKeyDown={onRawIdKeyDown}
            rawIdSuggestWrapRef={rawIdSuggestWrapRef}
            rawIdSuggestOpen={rawIdSuggestOpen}
            rawIdSuggestLoading={rawIdSuggestLoading}
            rawIdSuggestError={rawIdSuggestError}
            rawIdSuggestItems={rawIdSuggestItems}
            rawIdSuggestHighlightIndex={rawIdSuggestHighlightIndex}
            setRawIdSuggestHighlightIndex={setRawIdSuggestHighlightIndex}
            onSelectRawIdSuggestItem={selectRawIdSuggestCandidate}
            searchData={searchData}
            rootVid={rootVid}
            searchSelectedVid={searchSelectedVid}
            onSelectSearchResultNode={(vid) => setSearchSelectedVid(vid)}
            onLoadSelectedSubgraph={(vid) => {
              void loadSelectedSearchSubgraph(vid);
            }}
            graphLoadBusy={graphBusy}
            onEntityTypeDemandLoad={() => {
              void ensureEntityTypesLoaded();
            }}
            edgeQ={edgeQ}
            onEdgeQChange={onEdgeInputChange}
            edgeSearchLoading={loadingEdgeSearch}
            onEdgeSearch={handleEdgeSearchClick}
            onEdgeSearchInputKeyDown={onEdgeKeyDown}
            edgeSuggestWrapRef={edgeSuggestWrapRef}
            edgeSuggestOpen={edgeSuggestOpen}
            edgeSuggestLoading={edgeSuggestLoading}
            edgeSuggestError={edgeSuggestError}
            edgeSuggestItems={edgeSuggestItems}
            edgeSuggestHighlightIndex={edgeSuggestHighlightIndex}
            setEdgeSuggestHighlightIndex={setEdgeSuggestHighlightIndex}
            onSelectEdgeSuggestItem={selectEdgeSuggestCandidate}
            edgeSearchInRelation={edgeSearchInRelation}
            setEdgeSearchInRelation={setEdgeSearchInRelation}
            edgeSearchInProps={edgeSearchInProps}
            setEdgeSearchInProps={setEdgeSearchInProps}
            edgeSearchSourceDb={edgeSearchSourceDb}
            setEdgeSearchSourceDb={setEdgeSearchSourceDb}
            edgeSearchRelation={edgeSearchRelation}
            setEdgeSearchRelation={setEdgeSearchRelation}
            edgeSearchData={edgeSearchData}
            onSelectEdgeSearchItem={(item) => {
              void handleSelectEdgeCandidate(item);
            }}
            edgeSearchNotice={edgeSearchNotice}
            loadingMultiGraph={graphBusy}
            onGenerateMultiGraph={(params) => {
              void runMultiGraph(params);
            }}
            showPathCandidates={showPathCandidates}
            pathCandidates={pathCandidates}
            chosenPathByPair={chosenPathByPair}
            appliedExtraPaths={appliedExtraPaths}
            onChoosePathForPair={setChosenPathForPair}
            onApplyPathForPair={(u, v) => {
              void applyChosenPathForPair(u, v);
            }}
            onAppendPathForPair={(u, v) => {
              appendChosenPathForPair(u, v);
            }}
            pathApplyLoading={loadingApplyPathChoice}
            resolveEntityLabel={(vid) => multiEntityLabelMap.get(vid) || String(vid)}
          />
        ) : (
          <DiscoveryPanel
            seeds={discoverySeeds}
            searchQuery={discoveryCandidateSearch.query}
            searchAdvancedOpen={discoveryCandidateSearch.advancedOpen}
            preview={discoveryCandidateResults.preview}
            candidateResult={discoveryCandidateResults.result}
            selectedCandidateIds={discoveryCandidateResults.selectedIdSet}
            seedIdSet={discoverySelectedSeedVidSet}
            query={discoveryQuery}
            runtime={discoveryRuntimeFilters}
            renderCoverage={{
              workingNodeCount: discoveryGraphState.workingNodeCount,
              workingEdgeCount: discoveryGraphState.workingEdgeCount,
              entityTypes: discoveryGraphState.availableEntityTypes,
              relationTypes: discoveryGraphState.availableRelationTypes,
              selectedEntityTypes: discoveryGraphState.selectedEntityTypes,
              selectedRelationTypes: discoveryGraphState.selectedRelationTypes,
            }}
            entityTypeOptions={entityTypeOptions}
            resultFacets={
              discoveryResult
                ? {
                    entityTypes: discoveryResult.facets.entity_types,
                    relationTypes: discoveryResult.facets.relation_types,
                    querySummary: discoveryResult.facets.query_summary,
                    layers: discoveryResult.facets.layers,
                    seeds: discoveryResult.facets.seeds,
                  }
                : null
            }
            resultStats={discoveryResult?.stats || null}
            loading={loadingDiscovery}
            hasPendingChanges={discoveryHasPendingChanges}
            renderedNodes={discoveryGraphState.renderedNodes}
            hiddenNodes={discoveryGraphState.hiddenNodes}
            droppedNodes={{
              droppedByBudget: discoveryGraphState.droppedGroups.droppedByBudget.map((item) => ({
                node: item.node,
                supportEdgesCount: item.supportEdges.length,
                sourceNodeId: item.sourceNodeId,
              })),
              droppedByTypeFilter: discoveryGraphState.droppedGroups.droppedByTypeFilter.map((item) => ({
                node: item.node,
                supportEdgesCount: item.supportEdges.length,
                sourceNodeId: item.sourceNodeId,
              })),
              droppedByRelationFilter: discoveryGraphState.droppedGroups.droppedByRelationFilter.map((item) => ({
                node: item.node,
                supportEdgesCount: item.supportEdges.length,
                sourceNodeId: item.sourceNodeId,
              })),
            }}
            renderedPanelCollapsed={discoveryRenderedPanelCollapsed}
            droppedPanelCollapsed={discoveryDroppedPanelCollapsed}
            onUpdateSearchQuery={discoveryCandidateSearch.updateQuery}
            onToggleSearchAdvanced={discoveryCandidateSearch.toggleAdvancedOpen}
            onSubmitSearch={() => {
              void discoveryCandidateResults.runSearch({
                append: false,
                page: 1,
                queryOverride: discoveryCandidateSearch.query,
              });
            }}
            onClosePreview={discoveryCandidateResults.closePreview}
            onSetPreviewHighlightIndex={discoveryCandidateResults.setPreviewHighlightIndex}
            onSelectPreviewItem={(item) => {
              discoveryCandidateResults.closePreview();
              discoveryDetail.viewCandidateDetail(item);
            }}
            onAddCandidateSeed={(item) => {
              addDiscoverySeedItems([candidateItemToSeed(item)]);
              discoveryCandidateResults.removeSelected([item.vid]);
            }}
            onRemoveSeed={(vid) => {
              void handleRemoveDiscoverySeed(vid);
            }}
            onClearSeeds={discoverySeedsState.clear}
            onLoadMoreCandidates={() => {
              void discoveryCandidateResults.loadMore();
            }}
            onToggleCandidateSelect={discoveryCandidateResults.toggleSelected}
            onClearCandidateSelection={discoveryCandidateResults.clearSelected}
            onAddSelectedCandidates={addSelectedDiscoveryCandidatesToSeeds}
            onViewCandidateDetail={(item) => {
              discoveryDetail.viewCandidateDetail(item);
            }}
            onLoadCandidateSubgraph={(item) => {
              void loadDiscoveryCandidateSubgraph(item);
            }}
            onUpdateQuery={(patch) => setDiscoveryQuery((prev) => ({ ...prev, ...patch }))}
            onUpdateRuntime={(patch) => setDiscoveryRuntimeFilters((prev) => ({ ...prev, ...patch }))}
            onUpdateRenderCoverage={(patch) => {
              if (patch.selectedEntityTypes) {
                discoveryGraphState.setSelectedEntityTypes(patch.selectedEntityTypes);
              }
              if (patch.selectedRelationTypes) {
                discoveryGraphState.setSelectedRelationTypes(patch.selectedRelationTypes);
              }
            }}
            onSetRenderedPanelCollapsed={setDiscoveryRenderedPanelCollapsed}
            onSetDroppedPanelCollapsed={setDiscoveryDroppedPanelCollapsed}
            onLocateNode={locateNodeInGraph}
            onHideRenderedNode={handleHideDiscoveryNode}
            onRestoreHiddenNode={handleRestoreHiddenDiscoveryNode}
            onForceRenderDroppedNode={handleForceRenderDiscoveryNode}
            onViewNodeDetailById={handleSelectNode}
            onRun={() => {
              void runDiscovery();
            }}
          />
        )}
      </div>

      <Resizer side="left" onPointerDown={(e) => beginResize("left", e)} />

      <div className="kg-center">
        <div className="kg-topbar-sticky">
          {workspaceMode === "legacy" ? (
            <TopBar
              rootVid={rootVid}
              loadingGraph={graphBusy}
              graphBudgetLabel={budgetPresetLabel}
              canLoadMoreEdges={canLoadMoreEdges}
              onLoadMoreEdges={() => {
                void loadMoreEdges();
              }}
              hop={hop}
              setHop={setHop}
              relations={relations}
              onOpenRelationFilter={handleOpenRelationFilter}
              onClearRelationsAndReload={() => {
                void (async () => {
                  const nextRelations: string[] = [];
                  setRelations(nextRelations);
                  if (rootVid != null) await loadGraphWithFilters(rootVid, hop, nextRelations);
                })();
              }}
              onReloadSubgraph={() => {
                if (rootVid != null) void reloadGraphByCurrentMode(rootVid);
              }}
              onRelayout={handleRelayoutCurrentGraph}
              onFitView={requestFitView}
              graphStats={effectiveGraphStats}
              relationPreviewActive={relationFilter.previewActive}
              onExitRelationPreview={relationFilter.exitPreview}
            />
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", flexWrap: "wrap" }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>统一关系发现</div>
              {discoveryWorkspaceReady ? (
                <div style={{ fontSize: 12, color: "#666" }}>
                  last_run_seeds={discoveryResult?.stats.seed_count ?? lastDiscoveryRequest?.seed_vids.length ?? 0} current_seeds=
                  {discoverySeeds.length}
                  {" | "}candidates=
                  {discoveryResult?.stats.candidate_count ?? 0}
                  {" | "}nodes={effectiveGraphNodes.length} edges={effectiveGraphEdges.length}
                  {graphBusy ? " | 加载中…" : ""}
                </div>
              ) : (
                <div style={{ fontSize: 12, color: "#666" }}>
                  添加 1 个或多个 seed 节点后运行 discovery，结果会以主题关系图形式渲染在这里。
                </div>
              )}
              {discoveryHasPendingChanges ? (
                <div style={{ width: "100%", fontSize: 12, color: "#ad6800" }}>
                  当前 seeds 或 discovery 参数与上次运行结果不一致，请重新生成以同步图谱结果。
                </div>
              ) : null}
              {effectiveGraphStats?.truncated ? (
                <div style={{ width: "100%", fontSize: 12, color: "#ad6800" }}>
                  图结果已裁剪：dropped_nodes={Number(effectiveGraphStats?.dropped_nodes || 0)} dropped_edges={Number(effectiveGraphStats?.dropped_edges || 0)} dropped_neighbors={Number(effectiveGraphStats?.dropped_neighbors || 0)} dropped_by_budget={Number(effectiveGraphStats?.dropped_by_budget || 0)} dropped_by_type_budget={Number(effectiveGraphStats?.dropped_by_type_budget || 0)} dropped_generic_hubs={Number(effectiveGraphStats?.dropped_generic_hubs || 0)}
                </div>
              ) : null}
              <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  onClick={handleRelayoutCurrentGraph}
                  disabled={graphBusy || !discoveryWorkspaceReady || effectiveGraphNodes.length <= 0}
                  style={{ padding: "7px 10px", fontSize: 12 }}
                >
                  整理布局
                </button>
                <button
                  onClick={requestFitView}
                  disabled={!discoveryWorkspaceReady || effectiveGraphNodes.length <= 0}
                  style={{ padding: "7px 10px", fontSize: 12 }}
                >
                  适配视图
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="kg-canvas-wrap">
          <Suspense fallback={<LoadingPanel message="图谱画布加载中..." style={{ minHeight: "100%" }} />}>
            {workspaceMode === "discovery" && !discoveryWorkspaceReady ? (
              <LoadingPanel message="统一关系发现结果尚未生成。请在左侧添加 seed 节点并运行 discovery。" style={{ minHeight: "100%" }} />
            ) : (
              <GraphCanvas
                viewModel={viewModel}
                renderPatch={renderPatch}
                layoutPlan={layoutPlan}
                viewportRequest={viewportRequest}
                renderNodeLabels={renderNodeLabels}
                renderEdgeLabels={renderEdgeLabels}
                edgeLabelSelectedDisplays={effectiveEdgeLabelSelectedDisplays}
                showSelfLoops={showSelfLoops}
                selectedNodeId={selectedNodeId}
                selectedEdgeId={selectedEdgeId}
                onNodeClick={handleGraphNodeClick}
                onEdgeClick={handleGraphEdgeClick}
                onNodePositionChange={
                  workspaceMode === "discovery"
                    ? (positions, source) => discoveryGraphState.syncNodePositions(positions, source)
                    : undefined
                }
                registerApplyHighlight={(fn) => {
                  applyHighlightRef.current = fn;
                }}
              />
            )}
          </Suspense>
        </div>
      </div>

      <Resizer side="right" onPointerDown={(e) => beginResize("right", e)} />

      <div className="kg-pane kg-pane-right">
        <Suspense fallback={<LoadingPanel message="右侧详情面板加载中..." />}>
          <RightDetailPanel
            allowGraphMutationActions={workspaceMode === "legacy"}
            discoveryMode={workspaceMode === "discovery"}
            renderNodeLabels={renderNodeLabels}
            setRenderNodeLabels={setRenderNodeLabels}
            renderEdgeLabels={renderEdgeLabels}
            setRenderEdgeLabels={setRenderEdgeLabels}
            edgeLabelPickerOpen={edgeLabelPickerOpen}
            setEdgeLabelPickerOpen={setEdgeLabelPickerOpen}
            edgeLabelKeyword={edgeLabelKeyword}
            setEdgeLabelKeyword={setEdgeLabelKeyword}
            edgeLabelSelectedDisplays={effectiveEdgeLabelSelectedDisplays}
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
            graphNodeCount={effectiveGraphNodes.length}
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
              setGraphSourceMode("single");
              setLastMultiGraphParams(null);
              clearMultiPathState();
              rememberSingleLegacySession(vid, 1, relations);
              void reroot1hop(vid);
            }}
            expand1hop={(vid) => {
              setGraphSourceMode("single");
              setLastMultiGraphParams(null);
              clearMultiPathState();
              if (rootVid != null) rememberSingleLegacySession(rootVid, hop, relations);
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
            loadingGraph={graphBusy}
            detailLoading={detailLoading}
            nodeDetail={nodeDetail}
            edgeDetail={edgeDetail}
            relationDisplay={relationDisplay}
            onReloadNodeDetail={reloadNodeDetailById}
            onReloadEdgeDetail={reloadEdgeDetailByIdentity}
            onSaveNodeEdit={saveNodeEdit}
            onSaveEdgeEdit={saveEdgeEdit}
            discoverySeedNodeIds={discoveryRunSeedVidSet}
            discoveryExpandEntityOptions={(discoveryResult?.facets.entity_types || []).map((item) => item.entity_type)}
            discoveryExpandRelationOptions={(discoveryResult?.facets.relation_types || []).map((item) => item.relation_type)}
            discoveryExpandFilters={discoveryExpandFilters}
            discoveryExpandFilterHint={
              discoverySelectedExpandFilterMismatch ? "当前节点已展开；修改过滤器后需先关闭，再按新条件重新展开。" : undefined
            }
            onUpdateDiscoveryExpandFilters={(patch) => {
              setDiscoveryExpandFilters((prev) => ({
                entityTypes: patch.entityTypes ?? prev.entityTypes,
                relationTypes: patch.relationTypes ?? prev.relationTypes,
              }));
              if (discoverySelectedExpandSession?.isExpanded) {
                setUiNotice({
                  level: "info",
                  message: "当前节点已展开；修改 Expand 过滤器后需先关闭，再按新条件重新展开。",
                });
              }
            }}
            onExpandDiscoveryNode={(vid) => {
              void handleDiscoveryExpandNode(vid);
            }}
            onHideDiscoveryNode={handleHideDiscoveryNode}
          />
        </Suspense>
      </div>

      {workspaceMode === "legacy" && relationFilter.open ? (
        <Suspense fallback={<LoadingPanel message="关系筛选面板加载中..." />}>
          <RelationFilterPanel
            relationCatalogItems={relationTypeCatalogItems}
            relationCatalogLoading={relationTypeCatalogLoading}
            relationCatalogHasMore={relationTypeCatalogHasMore}
            relationCatalogMatchedTotal={relationTypeCatalogMatchedTotal}
            relationCatalogQuery={relationTypeCatalogQuery}
            draftRelations={relationFilter.draftRelations}
            appliedRelations={relationFilter.appliedRelations}
            relationCountMap={relationFilter.relationCountMap}
            previewActive={relationFilter.previewActive}
            previewEdgeTotal={relationFilter.previewEdgeTotal}
            onRelationCatalogQueryChange={setRelationTypeCatalogQuery}
            onRelationCatalogLoadMore={() => {
              void handleLoadMoreRelationTypes();
            }}
            onClose={relationFilter.closePanel}
            onToggleDraftRelation={relationFilter.toggleDraftRelation}
            onClearDraft={relationFilter.clearDraft}
            onRestoreApplied={relationFilter.restoreDraftFromApplied}
            onInvertCurrentList={relationFilter.invertDraftByRelations}
            onPreviewOnlyApply={relationFilter.enterPreview}
            onExitPreview={relationFilter.exitPreview}
            onApplyAndReload={() => {
              void (async () => {
                const next = relationFilter.commitDraftAsApplied();
                relationFilter.closePanel();
                setRelations(next);
                if (rootVid != null) await loadGraphWithFilters(rootVid, hop, next);
              })();
            }}
            presets={relationFilter.presets}
            activePresetId={relationFilter.activePresetId}
            onSelectPreset={relationFilter.selectPreset}
            onSavePreset={relationFilter.savePreset}
            onRenamePreset={relationFilter.renamePreset}
            onDeletePreset={relationFilter.deletePreset}
            estimateKeepEdges={relationFilter.estimateKeepEdges}
          />
        </Suspense>
      ) : null}
    </div>
  );
}
