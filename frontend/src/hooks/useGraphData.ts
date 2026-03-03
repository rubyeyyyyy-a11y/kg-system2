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
  replaceGraphData: (params: {
    rootVid: number;
    nodes: NodeBrief[];
    edges: EdgeBrief[];
    stats: Record<string, unknown> | null;
    hop?: number;
  }) => void;
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
    replaceGraphData,
  };
}
