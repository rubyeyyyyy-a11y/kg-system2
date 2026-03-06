import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { expand, subgraph } from "../api/kg";
import { EXPAND_AUTO_REVEAL_TOPK, SUBGRAPH_BUDGET_PRESETS } from "../constants/kg";
import type { EdgeBrief, ExpandProbeState, NodeBrief } from "../types/kg";
import { parseApiError } from "../utils/httpError";
import { edgeKey } from "../utils/kg";

type GraphStats = Record<string, unknown> | null;

type UseGraphDataParams = {
  selectedNodeVid: number | null;
  onSelectNode: (vid: number) => void;
  onClearSelection: () => void;
  onNotice?: (level: "error" | "warn" | "info", message: string) => void;
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
  replaceGraphData: (params: {
    rootVid: number;
    nodes: NodeBrief[];
    edges: EdgeBrief[];
    stats: Record<string, unknown> | null;
    hop?: number;
  }) => void;
  updateNodeInGraph: (vid: number, patch: Partial<NodeBrief>) => void;
  updateEdgeInGraph: (
    identity: { source: number; target: number; rank: string; edge_type?: string },
    patch: Partial<EdgeBrief>
  ) => void;
  budgetTier: number;
  budgetPresetLabel: string;
  canLoadMoreEdges: boolean;
  loadMoreEdges: () => Promise<void>;
};

export function useGraphData({
  selectedNodeVid,
  onSelectNode,
  onClearSelection,
  onNotice,
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
  const [budgetTier, setBudgetTier] = useState(0);

  const rootVidRef = useRef<number | null>(null);
  const relationsRef = useRef<string[]>([]);
  const graphNodesRef = useRef<NodeBrief[]>([]);
  const expandProbeTokenByVidRef = useRef<Record<number, number>>({});

  function notify(level: "error" | "warn" | "info", message: string) {
    if (!message) return;
    onNotice?.(level, message);
  }

  function summarizeGraphBudgetStats(stats: Record<string, unknown> | null): string {
    if (!stats) return "";
    const truncated = Boolean(stats.truncated);
    const droppedNodes = Number(stats.dropped_nodes || 0);
    const droppedEdges = Number(stats.dropped_edges || 0);
    const droppedNeighbors = Number(stats.dropped_neighbors || 0);
    if (!truncated && droppedNodes <= 0 && droppedEdges <= 0 && droppedNeighbors <= 0) return "";
    return `图结果已按预算裁剪：dropped_nodes=${droppedNodes} dropped_edges=${droppedEdges} dropped_neighbors=${droppedNeighbors}`;
  }

  function currentBudgetPreset() {
    const safeTier = Math.max(0, Math.min(budgetTier, SUBGRAPH_BUDGET_PRESETS.length - 1));
    return SUBGRAPH_BUDGET_PRESETS[safeTier];
  }

  useEffect(() => {
    rootVidRef.current = rootVid;
  }, [rootVid]);

  useEffect(() => {
    relationsRef.current = relations;
  }, [relations]);

  useEffect(() => {
    graphNodesRef.current = graphNodes;
  }, [graphNodes]);

  function replaceGraphData(params: {
    rootVid: number;
    nodes: NodeBrief[];
    edges: EdgeBrief[];
    stats: Record<string, unknown> | null;
    hop?: number;
  }) {
    setRootVid(params.rootVid);
    if (typeof params.hop === "number") setHop(params.hop);
    setGraphNodes(params.nodes);
    setGraphEdges(params.edges);
    setGraphStats(params.stats);

    setManualRevealedNodeIds(new Set());
    setManualHiddenNodeIds(new Set());
    setExpandedSourceNodeIds(new Set());
    setHiddenNodesCollapsed(false);

    resetExpandProbeCache();
    resetPanelGroupingForNewRoot(params.nodes, params.rootVid);
    onClearSelection();
  }

  function updateNodeInGraph(vid: number, patch: Partial<NodeBrief>) {
    setGraphNodes((prev) => prev.map((n) => (n.id === vid ? { ...n, ...patch } : n)));
  }

  function updateEdgeInGraph(
    identity: { source: number; target: number; rank: string; edge_type?: string },
    patch: Partial<EdgeBrief>
  ) {
    setGraphEdges((prev) =>
      prev.map((e) => {
        const same =
          Number(e.source) === Number(identity.source) &&
          Number(e.target) === Number(identity.target) &&
          String(e.rank || "0") === String(identity.rank || "0");
        return same ? { ...e, ...patch } : e;
      })
    );
  }

  function resetPanelGroupingForNewRoot(nodes: NodeBrief[], nextRoot: number) {
    const m: Record<number, number> = {};
    for (const n of nodes) m[n.id] = nextRoot;
    setNodeGroupRootById(m);
    setPanelGroupCollapsed({ [String(nextRoot)]: true });
  }

  function resetExpandProbeCache() {
    setExpandProbeByVid({});
    expandProbeTokenByVidRef.current = {};
  }

  async function loadSubgraphWithParams(
    nextRoot: number,
    nextHop: number,
    nextRelations: string[],
    overrideTier?: number
  ) {
    const tier = Number.isFinite(overrideTier as number)
      ? Math.max(0, Math.min(Number(overrideTier), SUBGRAPH_BUDGET_PRESETS.length - 1))
      : budgetTier;
    const budget = SUBGRAPH_BUDGET_PRESETS[tier];
    setLoadingGraph(true);
    try {
      const json = await subgraph({
        root_vid: nextRoot,
        hop: nextHop,
        relations: nextRelations,
        max_nodes: budget.max_nodes,
        max_edges: budget.max_edges,
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
      const budgetMsg = summarizeGraphBudgetStats(json.stats as Record<string, unknown>);
      if (budgetMsg) notify("warn", budgetMsg);
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      notify("error", `子图加载失败：${parsed.message}`);
    } finally {
      setLoadingGraph(false);
    }
  }

  async function loadSubgraph(nextRoot: number) {
    await loadSubgraphWithParams(nextRoot, hop, relations);
  }

  async function expand1hop(fromVid: number) {
    if (!rootVid) return;
    const budget = currentBudgetPreset();
    setLoadingGraph(true);
    try {
      const existingIds = graphNodes.map((n) => n.id);
      const json = await expand({
        from_vid: fromVid,
        relations,
        existing_node_ids: existingIds,
        max_nodes: budget.max_nodes,
        max_edges: budget.max_edges,
      });

      if ((json.added_nodes?.length || 0) === 0 && (json.added_edges?.length || 0) === 0) {
        setExpandProbeByVid((prev) => ({ ...prev, [fromVid]: "noextra" }));
        notify("info", "该节点暂无可扩展的 1-hop 邻居，或邻居已全部在当前图中。");
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
        edge_count: json.stats.edge_count_after,
        truncated: json.stats.truncated,
        policy: json.stats.policy,
        dropped_nodes: json.stats.dropped_nodes,
        dropped_edges: json.stats.dropped_edges,
        dropped_neighbors: json.stats.dropped_neighbors,
        budget_applied: json.stats.budget_applied,
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
      const budgetMsg = summarizeGraphBudgetStats(json.stats as Record<string, unknown>);
      if (budgetMsg) notify("warn", budgetMsg);
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      notify("error", `Expand 失败：${parsed.message}`);
    } finally {
      setLoadingGraph(false);
    }
  }

  async function reroot1hop(vid: number) {
    const budget = currentBudgetPreset();
    setLoadingGraph(true);
    try {
      const json = await subgraph({
        root_vid: vid,
        hop: 1,
        relations,
        max_nodes: budget.max_nodes,
        max_edges: budget.max_edges,
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
      const budgetMsg = summarizeGraphBudgetStats(json.stats as Record<string, unknown>);
      if (budgetMsg) notify("warn", budgetMsg);
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      notify("error", `切换 root 失败：${parsed.message}`);
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
      notify("info", "当前节点没有可关闭的 Expand 展开内容。");
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
        max_edges: 120,
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
  }, [selectedNodeVid]);

  async function loadMoreEdges() {
    const curRoot = rootVidRef.current;
    if (curRoot == null) {
      notify("info", "当前没有 root，可先从搜索结果加载一个子图。");
      return;
    }
    if (budgetTier >= SUBGRAPH_BUDGET_PRESETS.length - 1) {
      notify("info", "已到最高图预算级别，无法继续加载更多边。");
      return;
    }
    const nextTier = budgetTier + 1;
    setBudgetTier(nextTier);
    notify("info", `图预算已提升到 ${SUBGRAPH_BUDGET_PRESETS[nextTier].label}，正在重载子图…`);
    await loadSubgraphWithParams(curRoot, hop, relations, nextTier);
  }

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
    replaceGraphData,
    updateNodeInGraph,
    updateEdgeInGraph,
    budgetTier,
    budgetPresetLabel: currentBudgetPreset().label,
    canLoadMoreEdges: budgetTier < SUBGRAPH_BUDGET_PRESETS.length - 1,
    loadMoreEdges,
  };
}
