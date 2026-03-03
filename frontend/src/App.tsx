import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import {
  edgeDetail as edgeDetailApi,
  edgeSearch as edgeSearchApi,
  multiEntityGraph as multiEntityGraphApi,
  multiEntityGraphApplyPaths as multiEntityGraphApplyPathsApi,
  nodeDetail as nodeDetailApi,
  relationTypes as relationTypesApi,
  search as searchApi,
} from "./api/kg";
import { GraphCanvas } from "./components/GraphCanvas";
import { LeftSearchPanel } from "./components/LeftSearchPanel";
import { RelationFilterPanel } from "./components/RelationFilter/RelationFilterPanel";
import { Resizer } from "./components/Resizer";
import { RightDetailPanel } from "./components/RightDetailPanel";
import { TopBar } from "./components/TopBar";
import { useEdgeSuggest } from "./hooks/useEdgeSuggest";
import { useEntityTypeOptions } from "./hooks/useEntityTypeOptions";
import { useGraphData } from "./hooks/useGraphData";
import { useRawIdSuggest } from "./hooks/useRawIdSuggest";
import { useRelationFilter } from "./hooks/useRelationFilter";
import { useSuggest } from "./hooks/useSuggest";
import { useVisibilityRanking } from "./hooks/useVisibilityRanking";
import type {
  EdgeDetailResp,
  EdgeSearchItem,
  EdgeSearchResp,
  MultiEntityGraphResp,
  NodeBrief,
  NodeDetailResp,
  PairPathCandidate,
  RawIdSuggestItem,
  SearchResp,
  Sel,
  SuggestItem,
} from "./types/kg";
import { findEdgeIdByIdentity, isSameEdge, pairKey, relationDisplay } from "./utils/kg";
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

const LEFT_WIDTH_KEY = "kg:leftW";
const RIGHT_WIDTH_KEY = "kg:rightW";
const SIDEBAR_MIN_WIDTH = 320;
const SIDEBAR_MAX_WIDTH = 640;
const SIDEBAR_DEFAULT_WIDTH = 420;

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

export default function App() {
  const [q, setQ] = useState("");
  const [searchName, setSearchName] = useState(true);
  const [searchDesc, setSearchDesc] = useState(true);
  const [entityType, setEntityType] = useState("");
  const [entityRawId, setEntityRawId] = useState("");
  const [source, setSource] = useState("");
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchData, setSearchData] = useState<SearchResp>({ nodes: [], edges: [], total_candidates: 0 });

  const { options: entityTypeOptions, usedFallback: entityTypeFallbackUsed } = useEntityTypeOptions();

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
  const [loadingApplyPathChoice, setLoadingApplyPathChoice] = useState(false);
  const [graphSourceMode, setGraphSourceMode] = useState<"single" | "multi">("single");
  const [lastMultiGraphParams, setLastMultiGraphParams] = useState<MultiGraphParams | null>(null);
  const [lastMultiGraphRequest, setLastMultiGraphRequest] = useState<MultiGraphRequest | null>(null);
  const [pathCandidates, setPathCandidates] = useState<PairPathCandidate[]>([]);
  const [chosenPathByPair, setChosenPathByPair] = useState<Record<string, number>>({});
  const [appliedExtraPaths, setAppliedExtraPaths] = useState<Record<string, number[]>>({});

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

  const applyHighlightRef =
    useRef<((nextNodeId: string | null, nextEdgeId: string | null, force?: boolean) => void) | null>(null);

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
    replaceGraphData,
  } = useGraphData({
    selectedNodeVid,
    onSelectNode: handleSelectNode,
    onClearSelection: handleClearSelection,
  });

  const graphBusy = loadingGraph || loadingMultiGraph || loadingApplyPathChoice;
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
    setLastMultiGraphRequest(request);
  }

  async function runSearchWithParams(nextQ: string, nextEntityRawId: string) {
    const qTrimmed = nextQ.trim();
    const rawIdTrimmed = nextEntityRawId.trim();
    if (!qTrimmed && !rawIdTrimmed) return;

    const useRawId = !!rawIdTrimmed;
    setLoadingSearch(true);
    try {
      const json = await searchApi({
        q: useRawId ? "" : nextQ,
        search_in_name: useRawId ? false : searchName,
        search_in_description: useRawId ? false : searchDesc,
        entity_type: entityType || null,
        source: source || null,
        entity_raw_id: rawIdTrimmed || null,
        entity_raw_id_mode: "contains",
      });
      setSearchData(json);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
    } finally {
      setLoadingSearch(false);
    }
  }

  async function runSearch() {
    await runSearchWithParams(q, entityRawId);
  }

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
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
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
      alert("多实体关系最多支持 8 个实体，请减少选择后重试。");
      return;
    }

    const vids = selectedEntities.map((x) => x.vid);
    const reqRelations = overrideRelations ?? relations;
    const safeK = params.k > 3 ? 3 : params.k < 2 ? 2 : params.k;
    if (safeK !== params.k) {
      alert(`k 已自动调整为 ${safeK}（当前仅支持 2~3）。`);
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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
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
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      alert(msg);
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
      const ek = `${e.source}|${e.target}|${e.relation || ""}|${e.source_db || ""}`;
      edgeMap.set(ek, e);
    }
    for (const e of candidate.edges || []) {
      const ek = `${e.source}|${e.target}|${e.relation || ""}|${e.source_db || ""}`;
      if (edgeMap.has(ek)) continue;
      edgeMap.set(ek, { ...e, is_explain: true });
    }

    const maxNodes = Math.max(2, Number(lastMultiGraphRequest.max_nodes || 300));
    const maxEdges = Math.max(1, Number(lastMultiGraphRequest.max_edges || 20000));
    if (nodeMap.size > maxNodes) {
      alert(`追加失败：节点数将超过上限 ${maxNodes}。请提高 max_nodes 或改用替换。`);
      return;
    }
    if (edgeMap.size > maxEdges) {
      alert(`追加失败：边数将超过上限 ${maxEdges}。请提高 max_edges 或改用替换。`);
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
    if (autoSelectRoot) handleSelectNode(vid);
  }

  async function reloadGraphByCurrentMode(nextRoot: number) {
    if (graphSourceMode === "multi" && lastMultiGraphParams) {
      await runMultiGraph(lastMultiGraphParams);
      return;
    }
    await loadSingleSubgraph(nextRoot);
  }

  async function loadGraphWithFilters(nextRoot: number, nextHop: number, nextRelations: string[]) {
    relationFilter.exitPreview();
    if (graphSourceMode === "multi" && lastMultiGraphParams) {
      await runMultiGraph(lastMultiGraphParams, nextRelations);
      return;
    }
    setGraphSourceMode("single");
    setLastMultiGraphParams(null);
    clearMultiPathState();
    await loadSubgraphWithParams(nextRoot, nextHop, nextRelations);
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

  const effectiveGraphNodes = relationFilter.previewActive ? relationFilter.previewNodes : graphNodes;
  const effectiveGraphEdges = relationFilter.previewActive ? relationFilter.previewEdges : graphEdges;
  const effectiveGraphStats = relationFilter.previewActive
    ? ({
        ...(graphStats || {}),
        relation_preview: true,
        node_count: effectiveGraphNodes.length,
        edge_count: effectiveGraphEdges.length,
      } as Record<string, unknown>)
    : graphStats;

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
    graphNodes: effectiveGraphNodes,
    graphEdges: effectiveGraphEdges,
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
          next[k] = true;
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

  const multiSeedVidSet = useMemo(() => {
    if (graphSourceMode !== "multi" || !lastMultiGraphParams) return new Set<number>();
    const seed = new Set<number>();
    for (const item of lastMultiGraphParams.selectedEntities) seed.add(item.vid);
    return seed;
  }, [graphSourceMode, lastMultiGraphParams]);

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

  const { g6Data, edgeById } = useMemo(() => {
    const nodes = visibleGraphNodes.map((n) => ({
      id: String(n.id),
      label: n.label,
      data: {
        ...n,
        isSeed: multiSeedVidSet.has(n.id),
        seedGroup: multiSeedVidSet.has(n.id) ? "multi" : undefined,
        isRoot: rootVid != null && n.id === rootVid,
        hopLevel: visibleNodeHopLevelMap.get(n.id) ?? 99,
      },
    }));

    const edgeMap = new Map<string, (typeof visibleGraphEdges)[number]>();
    const dupSeqBySignature = new Map<string, number>();
    const edges = visibleGraphEdges.map((e) => {
      const signature = `${e.source}|${e.target}|${e.relation || ""}|${e.source_db || ""}`;
      const seq = dupSeqBySignature.get(signature) || 0;
      dupSeqBySignature.set(signature, seq + 1);
      // Stable edge ids avoid item reference churn when visibility-only toggles change.
      const id = `e:${signature}#${seq}`;
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
  }, [visibleGraphNodes, visibleGraphEdges, rootVid, visibleNodeHopLevelMap, multiSeedVidSet]);

  function selectEdgeWithDetail(target: EdgeSearchItem, edgeId: string | null) {
    const source_db = target.source_db ? String(target.source_db) : undefined;
    setSelectedEdgeGraphId(edgeId);
    setSel({
      kind: "edge",
      src: Number(target.src),
      dst: Number(target.dst),
      relation: String(target.relation || ""),
      source_db,
    });
    setNodeDetail(null);
    void loadEdgeDetail(Number(target.src), Number(target.dst), String(target.relation || ""), source_db);

    if (edgeId) {
      applyHighlightRef.current?.(null, edgeId, true);
    }
  }

  function trySelectEdgeFromCurrentRenderedGraph(target: EdgeSearchItem): boolean {
    const edgeId = findEdgeIdByIdentity(edgeById, {
      src: Number(target.src),
      dst: Number(target.dst),
      relation: String(target.relation || ""),
      source_db: target.source_db,
    });
    if (!edgeId) return false;
    selectEdgeWithDetail(target, edgeId);
    return true;
  }

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

    const edgeId = findEdgeIdByIdentity(edgeById, {
      src: Number(pendingEdgeLocate.src),
      dst: Number(pendingEdgeLocate.dst),
      relation: String(pendingEdgeLocate.relation || ""),
      source_db: pendingEdgeLocate.source_db,
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
        relation: String(pendingEdgeLocate.relation || ""),
        source_db: pendingEdgeLocate.source_db,
      })
    );

    if (existsInGraphData) {
      selectEdgeWithDetail(pendingEdgeLocate, null);
      setEdgeSearchNotice("该边已在当前图数据中，但当前未渲染（请检查自环开关或节点显示状态）。");
    } else {
      const msg = "该边不在当前 hop/relations 限制下可见，请提高 hop 或调整关系筛选后重试。";
      setEdgeSearchNotice(msg);
      alert(msg);
    }

    setPendingEdgeLocate(null);
  }, [pendingEdgeLocate, loadingGraph, loadingMultiGraph, edgeById, rootVid, graphEdges]);

  const selectedNodeBrief = useMemo(() => {
    if (sel.kind !== "node") return null;
    return effectiveGraphNodes.find((n) => n.id === sel.vid) || null;
  }, [sel, effectiveGraphNodes]);

  const selectedNodeIsRoot = sel.kind === "node" && rootVid != null && sel.vid === rootVid;
  const selectedNodeIsVisible = sel.kind === "node" ? visibleNodeIdSet.has(sel.vid) : false;
  const selectedNodeIsAutoTop = sel.kind === "node" ? autoVisibleTopIds.has(sel.vid) : false;
  const selectedNodeExpandClosable = sel.kind === "node" && expandedSourceNodeIds.has(sel.vid);

  const selectedNodeProbeState = sel.kind === "node" ? expandProbeByVid[sel.vid] : undefined;

  const expandButtonDisabled =
    graphBusy ||
    sel.kind !== "node" ||
    selectedNodeProbeState === "loading" ||
    selectedNodeProbeState === "noextra";

  const expandButtonText =
    selectedNodeProbeState === "noextra" ? "Expand（无多余相关节点）" : "Expand（合并 1-hop）";

  const selectedNodeId = sel.kind === "node" ? String(sel.vid) : null;
  const selectedEdgeId = sel.kind === "edge" ? selectedEdgeGraphId : null;

  function handleSearchClick() {
    closeSuggestPanel();
    closeRawIdSuggestPanel();
    void runSearch();
  }

  function handleEdgeSearchClick() {
    closeEdgeSuggestPanel();
    void runEdgeSearch();
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
    <div className="kg-layout" style={layoutStyle}>
      <div className="kg-pane kg-pane-left">
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
          onLoadSubgraph={(vid) => {
            void loadSingleSubgraph(vid);
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
      </div>

      <Resizer side="left" onPointerDown={(e) => beginResize("left", e)} />

      <div className="kg-center">
        <div className="kg-topbar-sticky">
          <TopBar
            rootVid={rootVid}
            loadingGraph={graphBusy}
            hop={hop}
            setHop={setHop}
            relations={relations}
            onOpenRelationFilter={relationFilter.openPanel}
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
            graphStats={effectiveGraphStats}
            relationPreviewActive={relationFilter.previewActive}
            onExitRelationPreview={relationFilter.exitPreview}
          />
        </div>

        <div className="kg-canvas-wrap">
          <GraphCanvas
            g6Data={g6Data}
            edgeById={edgeById}
            renderNodeLabels={renderNodeLabels}
            renderEdgeLabels={renderEdgeLabels}
            edgeLabelSelectedDisplays={edgeLabelSelectedDisplays}
            showSelfLoops={showSelfLoops}
            selectedNodeId={selectedNodeId}
            selectedEdgeId={selectedEdgeId}
            onNodeClick={handleGraphNodeClick}
            onEdgeClick={handleGraphEdgeClick}
            registerApplyHighlight={(fn) => {
              applyHighlightRef.current = fn;
            }}
          />
        </div>
      </div>

      <Resizer side="right" onPointerDown={(e) => beginResize("right", e)} />

      <div className="kg-pane kg-pane-right">
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
            void reroot1hop(vid);
          }}
          expand1hop={(vid) => {
            setGraphSourceMode("single");
            setLastMultiGraphParams(null);
            clearMultiPathState();
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
        />
      </div>

      <RelationFilterPanel
        open={relationFilter.open}
        relationTypes={relationTypes}
        draftRelations={relationFilter.draftRelations}
        appliedRelations={relationFilter.appliedRelations}
        relationCountMap={relationFilter.relationCountMap}
        previewActive={relationFilter.previewActive}
        previewEdgeTotal={relationFilter.previewEdgeTotal}
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
    </div>
  );
}
