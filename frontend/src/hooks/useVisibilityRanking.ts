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
    selfLoopEdgeCount,
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
    // Keep full edge candidates stable here. Visibility toggles (e.g. self-loop) should be
    // applied at the graph visibility layer to avoid full data re-render side effects.
    const visibleEdges = edgeCandidates;

    const lowPriorityIds = new Set<number>();
    for (const n of ranked) if (!topSet.has(n.id)) lowPriorityIds.add(n.id);

    return {
      visibleGraphNodes: visibleNodes,
      hiddenGraphNodes: hiddenNodes,
      visibleNodeIdSet: finalVisibleIds,
      visibleGraphEdges: visibleEdges,
      selfLoopEdgeCount: selfLoops.length,
      autoVisibleTopIds: topSet,
      rankedGraphNodes: ranked,
      lowPriorityNodeIds: lowPriorityIds,
    };
  }, [graphNodes, graphEdges, rootVid, manualRevealedNodeIds, manualHiddenNodeIds]);

  const hiddenSelfLoopCount = showSelfLoops ? 0 : selfLoopEdgeCount;
  const visibleSelfLoopCount = showSelfLoops ? selfLoopEdgeCount : 0;

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
