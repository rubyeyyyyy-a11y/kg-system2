import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import {
  edgeDetail as edgeDetailApi,
  graphDiscovery as graphDiscoveryApi,
  patchEdge as patchEdgeApi,
  patchNode as patchNodeApi,
  nodeDetail as nodeDetailApi,
} from "../api/kg";
import { WorkspaceShell, type UiNotice } from "./WorkspaceShell";
import { WorkspaceTabs, type WorkspaceMode } from "./WorkspaceTabs";
import { DiscoveryWorkspaceSidebar, DiscoveryWorkspaceTopBar } from "../features/discovery/container/DiscoveryWorkspace";
import { useDiscoverySessionController } from "../features/discovery/hooks/useDiscoverySessionController";
import { ImportWorkspace } from "../features/import/container/ImportWorkspace";
import { useSpaceSessionController } from "../features/space/hooks/useSpaceSessionController";
import { useDiscoveryEntityDetail } from "../hooks/useDiscoveryEntityDetail";
import { useDiscoveryGraphState } from "../hooks/useDiscoveryGraphState";
import { useGraphLayoutController } from "../hooks/useGraphLayoutController";
import { useGraphPatchBuilder } from "../hooks/useGraphPatchBuilder";
import { useEntityTypeOptions } from "../hooks/useEntityTypeOptions";
import { useGraphData } from "../hooks/useGraphData";
import { useGraphViewModel } from "../hooks/useGraphViewModel";
import { useGraphViewportController } from "../hooks/useGraphViewportController";
import { useVisibilityRanking } from "../hooks/useVisibilityRanking";
import { parseApiError } from "../utils/httpError";
import type {
  EdgeBrief,
  EdgeDetailResp,
  EdgePatchResp,
  DiscoveryEntityCandidateItem,
  GraphDiscoveryResp,
  NodeBrief,
  NodeDetailResp,
  NodePatchResp,
  Sel,
  SelectionSource,
  SuggestItem,
} from "../types/kg";
import { edgeKey, relationDisplay } from "../utils/kg";
import "../styles/layout.css";

type GraphSourceMode = "discovery" | "drilldown";

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

type DiscoveryResultExplain = {
  message: string;
  requestSpace: string;
  responseSpace: string;
  nodeCount: number;
  edgeCount: number;
  candidateCount: number;
};

const LEFT_WIDTH_KEY = "kg:leftW";
const RIGHT_WIDTH_KEY = "kg:rightW";
const SIDEBAR_MIN_WIDTH = 320;
const SIDEBAR_MAX_WIDTH = 640;
const SIDEBAR_DEFAULT_WIDTH = 420;
const EDGE_TYPE_DEFAULT = "REL2";
const EMPTY_GRAPH_NODES: NodeBrief[] = [];
const EMPTY_GRAPH_EDGES: EdgeBrief[] = [];
const DISCOVERY_NONE_ENTITY_TYPE = "__none_entity_type_selected__";
const DISCOVERY_NONE_RELATION_TYPE = "__none_relation_type_selected__";
const GraphCanvas = lazy(() => import("../components/GraphCanvas").then((mod) => ({ default: mod.GraphCanvas })));
const RightDetailPanel = lazy(() =>
  import("../components/RightDetailPanel").then((mod) => ({ default: mod.RightDetailPanel }))
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

function selectionFollowsDiscoveryVisibility(sel: Sel) {
  return (
    (sel.kind === "node" && sel.source === "graph_node_click") ||
    (sel.kind === "edge" && sel.source === "graph_edge_click")
  );
}

function deriveDiscoveryResultExplain(
  result: GraphDiscoveryResp | null,
  lastRequest: DiscoveryRequest | null
): DiscoveryResultExplain | null {
  if (!result) return null;
  const stats = result.stats || null;
  const requestSpace = String(result.request_space || "").trim();
  const responseSpace = String(result.space_meta?.space_name || requestSpace || "").trim();
  const seedCount = Math.max(0, Number(stats?.seed_count ?? lastRequest?.seed_vids.length ?? 0));
  const nodeCount = Math.max(0, Number(stats?.node_count ?? result.nodes.length ?? 0));
  const edgeCount = Math.max(0, Number(stats?.edge_count ?? result.edges.length ?? 0));
  const candidateCount = Math.max(0, Number(stats?.candidate_count ?? 0));
  const seedOnly = edgeCount === 0 && nodeCount <= Math.max(1, seedCount);
  const noDiscoverableRelations = candidateCount === 0 && edgeCount === 0;
  if (!seedOnly && !noDiscoverableRelations) return null;

  const seedLabel = seedCount > 1 ? "当前 seeds" : "当前 seed";
  const scopeLabel = responseSpace || requestSpace || "当前 space";
  const mismatchSuffix =
    requestSpace && responseSpace && requestSpace !== responseSpace
      ? ` 请求 space=${requestSpace}，响应 space=${responseSpace}。`
      : "";

  return {
    message: `${seedLabel} 在当前 space (${scopeLabel}) 中没有可发现关系边。本次 discovery 请求已成功返回，但结果只包含 seed 节点，不是图谱渲染失败。${mismatchSuffix}`,
    requestSpace,
    responseSpace,
    nodeCount,
    edgeCount,
    candidateCount,
  };
}

function requestSpaceOrFallback(result: { request_space?: string; space_meta?: { space_name?: string } } | null) {
  return String(result?.request_space || result?.space_meta?.space_name || "").trim();
}

export default function AppShell() {
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>("import");
  const [uiNotice, setUiNotice] = useState<UiNotice | null>(null);
  const discoveryResetRef = useRef<(nextSpace: string) => void>(() => undefined);
  const pageResetRef = useRef<(nextSpace: string) => void>(() => undefined);

  const {
    setCurrentSpace,
    currentSpaceStore,
    spaces,
    resolvedCurrent,
    spacesLoading,
    spacesError,
    refreshSpaces,
    effectiveCurrentSpace,
    activeSpaceRef,
    selectedSpaceSummary,
    currentSpaceStatus,
    currentSpaceGraphStatus,
    currentSpaceSearchStatus,
    currentSpaceCoveragePct,
    currentSpaceIndexStatus,
    spaceSwitchState,
    spaceSwitchBlocked,
    spaceSwitchPhaseLabel,
    guardSpaceScopedRequest,
  } = useSpaceSessionController({
    discoveryResetRef,
    pageResetRef,
    onSwitchNotice: setUiNotice,
  });

  const {
    options: entityTypeOptions,
    ensureLoaded: ensureEntityTypesLoaded,
  } = useEntityTypeOptions({
    deferMs: 1200,
    scopeKey: effectiveCurrentSpace,
    enabled: !currentSpaceStore.isSwitching,
    spaceName: effectiveCurrentSpace,
  });

  const discoverySession = useDiscoverySessionController({
    currentSpaceName: effectiveCurrentSpace,
    spaceScopeKey: effectiveCurrentSpace,
    onError: (message) => setUiNotice({ level: "error", message }),
  });

  const {
    discoveryAbortRef,
    loadingDiscovery,
    setLoadingDiscovery,
    lastDiscoveryRequest,
    setLastDiscoveryRequest,
    discoverySeedsState,
    discoveryResult,
    setDiscoveryResult,
    discoveryCandidateSearch,
    discoveryCandidateResults,
    discoveryQuery,
    setDiscoveryQuery,
    discoveryRuntimeFilters,
    setDiscoveryRuntimeFilters,
    discoveryExpandFilters,
    setDiscoveryExpandFilters,
    discoveryRenderedPanelCollapsed,
    setDiscoveryRenderedPanelCollapsed,
    discoveryDroppedPanelCollapsed,
    setDiscoveryDroppedPanelCollapsed,
    resetForSpaceChange: resetDiscoverySession,
  } = discoverySession;

  const [graphSourceMode, setGraphSourceMode] = useState<GraphSourceMode>("discovery");

  const [sel, setSel] = useState<Sel>({ kind: "none" });
  const [nodeDetail, setNodeDetail] = useState<NodeDetailResp | null>(null);
  const [edgeDetail, setEdgeDetail] = useState<EdgeDetailResp | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedEdgeGraphId, setSelectedEdgeGraphId] = useState<string | null>(null);
  const [discoveryExpandProbeNodeId, setDiscoveryExpandProbeNodeId] = useState<number | null>(null);
  const discoveryExpandProbeTokenRef = useRef(0);

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

  useEffect(() => {
    discoveryResetRef.current = resetDiscoverySession;
  }, [resetDiscoverySession]);

  const abortAllSpaceScopedRequests = useCallback(() => {
    discoveryAbortRef.current?.abort();
    discoveryAbortRef.current = null;
  }, [discoveryAbortRef]);

  const loadNodeDetail = useCallback(async (vid: number) => {
    const requestSpace = activeSpaceRef.current;
    setDetailLoading(true);
    try {
      const detail = await nodeDetailApi(vid, { spaceName: requestSpace });
      if (activeSpaceRef.current !== requestSpace) return;
      setNodeDetail(detail);
    } catch (e: unknown) {
      if (activeSpaceRef.current !== requestSpace) return;
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `节点详情加载失败：${parsed.message}` });
    } finally {
      if (activeSpaceRef.current === requestSpace) setDetailLoading(false);
    }
  }, []);

  const loadEdgeDetail = useCallback(async (src: number, dst: number, rank: string, edgeType = EDGE_TYPE_DEFAULT) => {
    const requestSpace = activeSpaceRef.current;
    setDetailLoading(true);
    try {
      const detail = await edgeDetailApi({
        edge_type: edgeType,
        src,
        dst,
        rank,
        spaceName: requestSpace,
      });
      if (activeSpaceRef.current !== requestSpace) return;
      setEdgeDetail(detail);
    } catch (e: unknown) {
      if (activeSpaceRef.current !== requestSpace) return;
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `边详情加载失败：${parsed.message}` });
    } finally {
      if (activeSpaceRef.current === requestSpace) setDetailLoading(false);
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
    }, { spaceName: activeSpaceRef.current });

    updateNodeInGraph(vid, {
      label: resp.updated.entity_name ?? undefined,
      entity_type: resp.updated.entity_type ?? undefined,
      source: resp.updated.source ?? undefined,
      snippet: resp.updated.description ?? undefined,
    });
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
      spaceName: activeSpaceRef.current,
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

  function handleSelectNode(vid: number, source: SelectionSource = "graph_node_click") {
    setSel({ kind: "node", vid, source });
    setEdgeDetail(null);
    setSelectedEdgeGraphId(null);
    void loadNodeDetail(vid);
  }

  const selectedNodeVid = sel.kind === "node" ? sel.vid : null;

  const {
    rootVid,
    setHop,
    setRelations,
    loadingGraph,
    graphNodes,
    graphEdges,
    graphStats,
    manualRevealedNodeIds,
    manualHiddenNodeIds,
    nodeGroupRootById,
    drilldownExpandedNodeIds,
    hiddenNodesCollapsed,
    setHiddenNodesCollapsed,
    panelGroupCollapsed,
    setPanelGroupCollapsed,
    drilldownExpandStateByVid,
    loadDrilldown,
    expand1hop,
    reroot1hop,
    revealNode,
    unrevealNode,
    collapseExpandFromNode,
    clearDrilldownData,
    mergeDrilldownData,
    replaceDrilldownData,
    updateNodeInGraph,
    updateEdgeInGraph,
    renderMutation: drilldownRenderMutation,
    requestRelayout: requestDrilldownRelayout,
  } = useGraphData({
    spaceName: effectiveCurrentSpace,
    drilldownScopeKey: effectiveCurrentSpace,
    selectedNodeVid,
    onSelectNode: handleSelectNode,
    onClearSelection: handleClearSelection,
    onNotice: (level, message) => setUiNotice({ level, message }),
  });

  const graphBusy = loadingGraph || loadingDiscovery;
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

    replaceDrilldownData({
      rootVid: request.seed_vids[0],
      nodes: nextPayload.nodes,
      edges: nextPayload.edges,
      stats: (nextPayload.stats || null) as Record<string, unknown> | null,
      hop: request.hop,
    });
    console.info("discovery payload applied", {
      requestSpace: requestSpaceOrFallback(nextPayload),
      responseSpace: String(nextPayload.space_meta?.space_name || ""),
      graphStatus: nextPayload.space_meta?.graph_status || "",
      nodeCount: Number(nextPayload.stats?.node_count ?? nextPayload.nodes.length ?? 0),
      edgeCount: Number(nextPayload.stats?.edge_count ?? nextPayload.edges.length ?? 0),
      candidateCount: Number(nextPayload.stats?.candidate_count ?? 0),
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
    setRenderEdgeLabels(false);
  }

  function restoreDiscoveryWorkspace() {
    if (!discoveryResult || !lastDiscoveryRequest) {
      setGraphSourceMode("discovery");
      clearDrilldownData();
      discoveryGraphState.resetState();
      return;
    }
    applyDiscoveryPayload(discoveryResult, lastDiscoveryRequest, { resetRuntimeFilters: false });
  }

  function restoreDiscoveryDrilldownResult() {
    restoreDiscoveryWorkspace();
    setUiNotice(null);
  }

  async function switchWorkspaceMode(nextMode: WorkspaceMode) {
    if (nextMode === workspaceMode) return;
    setUiNotice(null);
    setWorkspaceMode(nextMode);
    if (nextMode === "discovery") {
      void ensureEntityTypesLoaded();
      if (graphSourceMode === "discovery") restoreDiscoveryWorkspace();
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
      clearDrilldownData();
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
    const requestSpace = activeSpaceRef.current;
    if (!guardSpaceScopedRequest("统一关系发现")) return;
    if (request.seed_vids.length <= 0) {
      setUiNotice({ level: "info", message: "请先添加至少一个 seed 节点。" });
      return;
    }

    discoveryAbortRef.current?.abort();
    const controller = new AbortController();
    discoveryAbortRef.current = controller;
    setLoadingDiscovery(true);
    try {
      const json = await graphDiscoveryApi({ ...request, signal: controller.signal, spaceName: requestSpace });
      if (controller.signal.aborted) return;
      if (activeSpaceRef.current !== requestSpace) return;
      applyDiscoveryPayload(json, request);
      if (json.warnings?.length) {
        setUiNotice({ level: "warn", message: json.warnings[0] });
      } else if (json.stats?.truncated) {
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
      if (controller.signal.aborted || (e instanceof Error && e.name === "AbortError")) return;
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `统一关系发现失败：${parsed.message}` });
    } finally {
      if (discoveryAbortRef.current === controller) {
        discoveryAbortRef.current = null;
        setLoadingDiscovery(false);
      }
    }
  }

  useEffect(() => {
    return () => {
      abortAllSpaceScopedRequests();
    };
  }, [abortAllSpaceScopedRequests]);
  async function enterDrilldownSubgraph(vid: number, source: SelectionSource) {
    if (!Number.isFinite(vid)) return;
    if (!guardSpaceScopedRequest("正式 Drill-down")) return;
    const loaded = await loadDrilldown(vid);
    if (!loaded) return;
    setGraphSourceMode("drilldown");
    handleSelectNode(vid, source);
  }

  async function loadDiscoveryCandidateSubgraph(item: DiscoveryEntityCandidateItem) {
    const vid = Number(item.vid || item.id);
    setWorkspaceMode("discovery");
    await enterDrilldownSubgraph(vid, "discovery_candidate");
    setUiNotice({ level: "info", message: "已进入统一关系发现下的正式 drill-down 视图。" });
  }

  const discoverySelectedSeedVidSet = useMemo(() => {
    const seed = new Set<number>();
    for (const item of discoverySeeds) seed.add(item.vid);
    return seed;
  }, [discoverySeeds]);

  const discoveryRunSeedVidSet = useMemo(() => {
    const seed = new Set<number>();
    for (const vid of lastDiscoveryRequest?.seed_vids || []) seed.add(Number(vid));
    if (seed.size === 0) {
      for (const node of discoveryResult?.nodes || []) {
        if (node.role === "seed") seed.add(node.id);
      }
    }
    return seed;
  }, [discoveryResult, lastDiscoveryRequest]);

  const discoveryGraphState = useDiscoveryGraphState({
    spaceName: effectiveCurrentSpace,
    scopeKey: effectiveCurrentSpace,
    graphNodes,
    graphEdges,
    maxNodes: lastDiscoveryRequest?.max_nodes ?? discoveryQuery.maxNodes,
    maxEdges: lastDiscoveryRequest?.max_edges ?? discoveryQuery.maxEdges,
    seedNodeIds: discoveryRunSeedVidSet,
    onMergeGraphData: mergeDrilldownData,
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

  const resetPageOrchestrationState = useCallback(() => {
    setGraphSourceMode("discovery");
    discoveryGraphState.resetState();
    clearDrilldownData();
    setHop(1);
    setRelations([]);
    handleClearSelection();
    setRenderEdgeLabels(false);
    setSelectedEdgeGraphId(null);
    setDiscoveryExpandProbeNodeId(null);
  }, [clearDrilldownData, discoveryGraphState]);

  useEffect(() => {
    pageResetRef.current = () => {
      resetPageOrchestrationState();
    };
  }, [resetPageOrchestrationState]);

  const discoveryResultExplain = useMemo(
    () => deriveDiscoveryResultExplain(discoveryResult, lastDiscoveryRequest),
    [discoveryResult, lastDiscoveryRequest]
  );
  const discoveryRequestSpace = requestSpaceOrFallback(discoveryResult);
  const discoveryResponseSpace = String(discoveryResult?.space_meta?.space_name || "").trim();
  const discoveryResultMode = workspaceMode === "discovery" && graphSourceMode === "discovery";
  const discoveryDrilldownMode = workspaceMode === "discovery" && graphSourceMode === "drilldown";
  const discoveryWorkspaceReady = discoveryResultMode && !!discoveryResult;
  const discoveryDrilldownReady = discoveryDrilldownMode && (graphNodes.length > 0 || rootVid != null);
  const effectiveGraphNodes =
    discoveryResultMode
      ? discoveryGraphState.visibleGraphNodes || EMPTY_GRAPH_NODES
      : graphNodes;
  const effectiveGraphEdges =
    discoveryResultMode
      ? discoveryGraphState.visibleGraphEdges || EMPTY_GRAPH_EDGES
      : graphEdges;
  const effectiveGraphStats =
    discoveryResultMode
      ? ({
          ...(discoveryResult?.stats || {}),
          node_count: discoveryGraphState.visibleGraphNodes.length,
          edge_count: discoveryGraphState.visibleGraphEdges.length,
          rendered_nodes: discoveryGraphState.renderedNodeIds.size,
          rendered_edges: discoveryGraphState.renderedEdgeIds.size,
          hidden_by_user: discoveryGraphState.hiddenNodeIds.size,
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
    searchNodes: [],
  });

  const discoveryVisibleNodeHopLevelMap = useMemo(() => {
    const next = new Map<number, number>();
    if (!discoveryResultMode) return next;
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
  }, [discoveryResultMode, effectiveGraphNodes]);

  const discoveryVisibleNodeIdSet = useMemo(() => {
    const next = new Set<number>();
    if (!discoveryResultMode) return next;
    for (const node of discoveryGraphState.visibleGraphNodes) next.add(node.id);
    return next;
  }, [discoveryResultMode, discoveryGraphState.visibleGraphNodes]);

  const visibleGraphNodes =
    discoveryResultMode ? effectiveGraphNodes : visibilityRanking.visibleGraphNodes;
  const visibleNodeIdSet =
    discoveryResultMode ? discoveryVisibleNodeIdSet : visibilityRanking.visibleNodeIdSet;
  const visibleGraphEdges =
    discoveryResultMode ? effectiveGraphEdges : visibilityRanking.visibleGraphEdges;
  const hiddenSelfLoopCount =
    discoveryResultMode
      ? showSelfLoops
        ? 0
        : discoveryGraphState.visibleGraphEdges.filter((edge) => edge.source === edge.target).length
      : visibilityRanking.hiddenSelfLoopCount;
  const visibleSelfLoopCount =
    discoveryResultMode
      ? showSelfLoops
        ? discoveryGraphState.visibleGraphEdges.filter((edge) => edge.source === edge.target).length
        : 0
      : visibilityRanking.visibleSelfLoopCount;
  const autoVisibleTopIds =
    discoveryResultMode ? discoveryVisibleNodeIdSet : visibilityRanking.autoVisibleTopIds;
  const visibleNodeHopLevelMap =
    discoveryResultMode ? discoveryVisibleNodeHopLevelMap : visibilityRanking.visibleNodeHopLevelMap;
  const panelNodes = discoveryResultMode ? EMPTY_GRAPH_NODES : visibilityRanking.panelNodes;
  const panelGroups = discoveryResultMode ? [] : visibilityRanking.panelGroups;
  const hiddenCount =
    discoveryResultMode ? discoveryGraphState.hiddenNodeIds.size : visibilityRanking.hiddenCount;
  const visibleCount =
    discoveryResultMode ? discoveryGraphState.visibleGraphNodes.length : visibilityRanking.visibleCount;

  useEffect(() => {
    if (discoveryResultMode) return;
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
  }, [discoveryResultMode, panelGroups, setPanelGroupCollapsed]);

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

  const activeRenderMutation =
    discoveryResultMode ? discoveryGraphState.renderMutation : drilldownRenderMutation;
  const { layoutPlan, nodePositionById } = useGraphLayoutController({
    visibleNodeIds: visibleGraphNodes.map((node) => String(node.id)),
    nodePositionCache: discoveryResultMode ? discoveryGraphState.nodePositionCache : undefined,
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
    activeSeedVidSet: discoveryRunSeedVidSet,
    graphSourceMode,
    nodePositionById,
    discoveryTypeColor,
    edgeLabelSelectedDisplays,
    edgeLabelSelectionTouched,
    edgeLabelKeyword,
  });
  const renderPatch = useGraphPatchBuilder(viewModel);

  useEffect(() => {
    if (!discoveryResultMode) return;
    if (sel.kind !== "node") return;
    setDiscoveryExpandFilters({
      entityTypes: [...discoveryRuntimeFilters.entityTypes],
      relationTypes: [...discoveryRuntimeFilters.relationTypes],
    });
  }, [discoveryResultMode, sel, discoveryRuntimeFilters]);

  useEffect(() => {
    if (!discoveryResultMode || !discoveryWorkspaceReady) return;
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
        if (e instanceof Error && e.name === "AbortError") return;
        const parsed = parseApiError(e);
        setUiNotice({ level: "error", message: `Expand 探测失败：${parsed.message}` });
      })
      .finally(() => {
        if (discoveryExpandProbeTokenRef.current !== nextToken) return;
        setDiscoveryExpandProbeNodeId((prev) => (prev === nodeId ? null : prev));
      });
  }, [
    discoveryResultMode,
    discoveryWorkspaceReady,
    sel,
    discoveryExpandFilters,
    currentDiscoveryExpandFingerprint,
    discoveryGraphState.graphEntityMap,
  ]);

  const selectedNodeBrief = useMemo(() => {
    if (sel.kind !== "node") return null;
    const graphNode = discoveryResultMode
      ? discoveryGraphState.graphEntityMap.get(sel.vid) || null
      : effectiveGraphNodes.find((n) => n.id === sel.vid) || null;
    if (graphNode) return graphNode;
    if (discoveryResultMode) {
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
    return null;
  }, [
    sel,
    effectiveGraphNodes,
    discoveryResultMode,
    discoveryGraphState.graphEntityMap,
    discoveryCandidateResults.result.items,
    discoverySeeds,
  ]);

  const selectedNodeIsRoot = sel.kind === "node" && rootVid != null && sel.vid === rootVid;
  const selectedNodeIsVisible = sel.kind === "node" ? visibleNodeIdSet.has(sel.vid) : false;
  const selectedNodeIsAutoTop = sel.kind === "node" ? autoVisibleTopIds.has(sel.vid) : false;
  const selectedNodeExpandClosable = sel.kind === "node" && drilldownExpandedNodeIds.has(sel.vid);
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
    discoveryResultMode ? undefined : sel.kind === "node" ? drilldownExpandStateByVid[sel.vid] : undefined;

  const expandButtonDisabled =
    discoveryResultMode
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
    discoveryResultMode
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
    if (!discoveryResultMode) return;
    if (!selectionFollowsDiscoveryVisibility(sel)) return;
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
    discoveryResultMode,
    sel,
    selectedEdgeGraphId,
    discoveryGraphState.visibleNodeIdSet,
    discoveryGraphState.visibleEdgeKeySet,
  ]);

  function handleGraphNodeClick(vid: number) {
    handleSelectNode(vid, "graph_node_click");
  }

  function locateNodeInGraph(vid: number) {
    handleSelectNode(vid, "graph_node_click");
    requestFocusNode(String(vid));
  }

  function handleRelayoutCurrentGraph() {
    if (visibleGraphNodes.length <= 0) return;
    if (discoveryResultMode) {
      discoveryGraphState.requestRelayout();
    } else {
      requestDrilldownRelayout();
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
      if (resp) {
        console.info("discovery expand payload received", {
          requestSpace: requestSpaceOrFallback(resp),
          responseSpace: String(resp.space_meta?.space_name || ""),
          graphStatus: resp.space_meta?.graph_status || "",
          newNodeCount: Number(resp.stats?.new_nodes_count ?? resp.new_nodes?.length ?? 0),
          newEdgeCount: Number(resp.stats?.new_edges_count ?? resp.new_edges?.length ?? 0),
          droppedCount: Number(resp.dropped_candidates?.length ?? 0),
        });
      }
      if (resp?.warnings?.length) {
        setUiNotice({ level: "warn", message: resp.warnings[0] });
      }
      if (!resp || ((resp.new_nodes?.length || 0) <= 0 && (resp.new_edges?.length || 0) <= 0 && (resp.support_edges?.length || 0) <= 0)) {
        setUiNotice({
          level: resp?.terminal ? "info" : "warn",
          message: resp?.terminal ? "该节点当前过滤条件下无更多相关节点。" : "该节点本次 expand 未补入新的节点或边。",
        });
        return;
      }
      locateNodeInGraph(result.firstNodeId ?? vid);
    } catch (e: unknown) {
      if (e instanceof Error && e.name === "AbortError") return;
      const parsed = parseApiError(e);
      setUiNotice({ level: "error", message: `Expand 失败：${parsed.message}` });
    }
  }

  function handleHideDiscoveryNode(vid: number) {
    const changed = discoveryGraphState.hideRenderedNode(vid);
    if (changed && sel.kind === "node" && sel.vid === vid && selectionFollowsDiscoveryVisibility(sel)) {
      handleClearSelection();
    }
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
    setSel({ kind: "edge", src, dst, rank, edge_type, relation, source: "graph_edge_click", source_db });
    setNodeDetail(null);
    void loadEdgeDetail(src, dst, rank, edge_type);
  }

  async function reloadNodeDetailById(vid: number) {
    await loadNodeDetail(vid);
  }

  async function reloadEdgeDetailByIdentity(identity: { edge_type: string; src: number; dst: number; rank: string }) {
    await loadEdgeDetail(identity.src, identity.dst, identity.rank, identity.edge_type);
  }

  const tabs = <WorkspaceTabs workspaceMode={workspaceMode} onSelectMode={(nextMode) => void switchWorkspaceMode(nextMode)} />;

  const importWorkspace = (
    <ImportWorkspace
      onNotice={setUiNotice}
      spaces={spaces}
      resolvedCurrent={resolvedCurrent}
      loadingSpaces={spacesLoading}
      spacesError={spacesError}
      refreshSpaces={refreshSpaces}
      spaceSwitching={spaceSwitchBlocked}
      spaceSwitchPhase={spaceSwitchPhaseLabel}
    />
  );

  const leftPane = (
    <DiscoveryWorkspaceSidebar
      key={`discovery-${effectiveCurrentSpace}`}
      currentSpace={effectiveCurrentSpace}
      selectedSpace={selectedSpaceSummary}
      spaces={spaces}
      spaceLoading={spacesLoading}
      spaceError={spacesError}
      currentSpaceStatus={currentSpaceStatus}
      currentSpaceGraphStatus={currentSpaceGraphStatus}
      currentSpaceSearchStatus={currentSpaceSearchStatus}
      currentSpaceCoveragePct={currentSpaceCoveragePct}
      currentSpaceIndexStatus={currentSpaceIndexStatus}
      spaceSwitching={spaceSwitchBlocked}
      spaceSwitchPhase={spaceSwitchPhaseLabel}
      onSelectSpace={setCurrentSpace}
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
        if (!guardSpaceScopedRequest("候选搜索")) return;
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
        if (!guardSpaceScopedRequest("候选搜索")) return;
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
      onViewNodeDetailById={(vid) => {
        handleSelectNode(vid, discoverySelectedSeedVidSet.has(vid) ? "seed" : "external_detail");
      }}
      onRun={() => {
        void runDiscovery();
      }}
    />
  );

  const topBar = (
    <DiscoveryWorkspaceTopBar
      currentSpace={effectiveCurrentSpace}
      discoveryViewMode={discoveryDrilldownMode ? "drilldown" : "result"}
      currentSpaceStatus={currentSpaceStatus || ""}
      currentSpaceIndexStatus={currentSpaceIndexStatus}
      discoveryWorkspaceReady={discoveryWorkspaceReady}
      drilldownRootVid={discoveryDrilldownMode ? rootVid : null}
      drilldownRootLabel={discoveryDrilldownMode ? selectedNodeBrief?.label || graphNodes.find((node) => node.id === rootVid)?.label || "" : ""}
      drilldownNodeCount={discoveryDrilldownMode ? effectiveGraphNodes.length : 0}
      drilldownEdgeCount={discoveryDrilldownMode ? effectiveGraphEdges.length : 0}
      canReturnToDiscoveryResult={Boolean(discoveryResult && lastDiscoveryRequest)}
      discoveryRequestSpace={discoveryRequestSpace}
      discoveryResponseSpace={discoveryResponseSpace}
      responseGraphStatus={String(discoveryResult?.space_meta?.graph_status || "")}
      discoveryNodeCount={Number(discoveryResult?.stats.node_count ?? effectiveGraphNodes.length ?? 0)}
      discoveryEdgeCount={Number(discoveryResult?.stats.edge_count ?? effectiveGraphEdges.length ?? 0)}
      discoveryCandidateCount={Number(discoveryResult?.stats.candidate_count ?? 0)}
      lastRunSeedCount={Number(discoveryResult?.stats.seed_count ?? lastDiscoveryRequest?.seed_vids.length ?? 0)}
      currentSeedCount={discoverySeeds.length}
      graphBusy={graphBusy}
      discoveryHasPendingChanges={discoveryHasPendingChanges}
      spaceSwitchBlocked={spaceSwitchBlocked}
      spaceSwitchPhaseLabel={spaceSwitchPhaseLabel}
      switchTargetSpace={spaceSwitchState.switchTarget || ""}
      effectiveGraphStats={effectiveGraphStats}
      discoveryResultExplain={discoveryResultExplain}
      onRelayout={handleRelayoutCurrentGraph}
      onFitView={requestFitView}
      onReturnToDiscoveryResult={restoreDiscoveryDrilldownResult}
    />
  );

  const canvas = (
    <div className="kg-canvas-wrap" style={{ position: "relative" }}>
      {spaceSwitchBlocked ? (
        <div
          data-testid="space-switch-overlay"
          data-switching="true"
          data-switch-phase={spaceSwitchPhaseLabel}
          data-space-name={effectiveCurrentSpace || spaceSwitchState.switchTarget || ""}
          style={{
            position: "absolute",
            inset: 12,
            zIndex: 32,
            display: "grid",
            placeItems: "center",
            background: "rgba(255,255,255,0.78)",
            border: "1px solid #e5e6eb",
            borderRadius: 14,
            backdropFilter: "blur(2px)",
          }}
        >
          <div style={{ display: "grid", gap: 6, textAlign: "center", maxWidth: 420, color: "#5b4636" }}>
            <strong>Switching Current Space</strong>
            <div style={{ fontSize: 13 }}>
              target={effectiveCurrentSpace || spaceSwitchState.switchTarget || "-"} | {spaceSwitchPhaseLabel}
            </div>
          </div>
        </div>
      ) : null}
      <Suspense fallback={<LoadingPanel message="图谱画布加载中..." style={{ minHeight: "100%" }} />}>
        {workspaceMode === "discovery" && !discoveryWorkspaceReady && !discoveryDrilldownReady ? (
          <div
            className="kg-canvas-anchor"
            data-testid="discovery-result-anchor"
            data-state="empty"
            data-workspace-mode={workspaceMode}
          >
            <LoadingPanel message="统一关系发现结果尚未生成。请在左侧添加 seed 节点并运行 discovery。" style={{ minHeight: "100%" }} />
          </div>
        ) : (
          <div
            className="kg-canvas-anchor"
            data-testid="discovery-result-anchor"
            data-state={discoveryDrilldownMode ? "drilldown" : "ready"}
            data-workspace-mode={workspaceMode}
          >
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
                discoveryResultMode
                  ? (positions, source) => discoveryGraphState.syncNodePositions(positions, source)
                  : undefined
              }
              registerApplyHighlight={(fn) => {
                applyHighlightRef.current = fn;
              }}
            />
          </div>
        )}
      </Suspense>
    </div>
  );

  const rightPane = (
    <Suspense fallback={<LoadingPanel message="右侧详情面板加载中..." />}>
      <RightDetailPanel
        allowGraphMutationActions={discoveryDrilldownMode}
        discoveryMode={discoveryResultMode}
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
          setGraphSourceMode("drilldown");
          void reroot1hop(vid);
        }}
        expand1hop={(vid) => {
          setGraphSourceMode("drilldown");
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
  );

  return (
    <WorkspaceShell
      layoutStyle={layoutStyle}
      workspaceMode={workspaceMode}
      currentSpaceName={effectiveCurrentSpace}
      uiNotice={uiNotice}
      onDismissNotice={() => setUiNotice(null)}
      tabs={tabs}
      importWorkspace={importWorkspace}
      leftPane={leftPane}
      topBar={topBar}
      canvas={canvas}
      rightPane={rightPane}
      onBeginResize={beginResize}
    />
  );
}
