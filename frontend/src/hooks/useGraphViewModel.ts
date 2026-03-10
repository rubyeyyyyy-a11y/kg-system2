import { useMemo } from "react";

import type { GraphViewModel } from "../graph/renderControl";
import type { EdgeBrief, NodeBrief } from "../types/kg";
import { edgeKey, relationDisplay } from "../utils/kg";

type UseGraphViewModelParams = {
  visibleGraphNodes: NodeBrief[];
  visibleGraphEdges: EdgeBrief[];
  rootVid: number | null;
  visibleNodeHopLevelMap: Map<number, number>;
  activeSeedVidSet: Set<number>;
  graphSourceMode: string;
  nodePositionById: Map<string, { x: number; y: number }>;
  discoveryTypeColor: (entityType: string) => { fill: string; stroke: string };
  edgeLabelSelectedDisplays: string[];
  edgeLabelSelectionTouched: boolean;
  edgeLabelKeyword: string;
};

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b));
    return `{${entries.map(([key, entry]) => `${key}:${stableStringify(entry)}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function useGraphViewModel({
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
}: UseGraphViewModelParams) {
  const currentVisibleEdgeLabelDisplays = useMemo(() => {
    const set = new Set<string>();
    for (const edge of visibleGraphEdges) {
      const display = relationDisplay(edge.relation);
      if (display) set.add(display);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [visibleGraphEdges]);

  const effectiveEdgeLabelSelectedDisplays = useMemo(() => {
    if (!edgeLabelSelectionTouched) return currentVisibleEdgeLabelDisplays;
    const allowed = new Set(currentVisibleEdgeLabelDisplays);
    return edgeLabelSelectedDisplays.filter((item) => allowed.has(item)).sort((a, b) => a.localeCompare(b));
  }, [currentVisibleEdgeLabelDisplays, edgeLabelSelectedDisplays, edgeLabelSelectionTouched]);

  const edgeLabelSelectedSet = useMemo(
    () => new Set(effectiveEdgeLabelSelectedDisplays),
    [effectiveEdgeLabelSelectedDisplays]
  );

  const edgeLabelFilteredDisplays = useMemo(() => {
    const keyword = edgeLabelKeyword.trim().toLowerCase();
    if (!keyword) return currentVisibleEdgeLabelDisplays;
    return currentVisibleEdgeLabelDisplays.filter((item) => item.toLowerCase().includes(keyword));
  }, [currentVisibleEdgeLabelDisplays, edgeLabelKeyword]);

  const edgeLabelAllVisibleChecked =
    edgeLabelFilteredDisplays.length > 0 &&
    edgeLabelFilteredDisplays.every((item) => edgeLabelSelectedSet.has(item));

  const viewModel = useMemo<GraphViewModel>(() => {
    const nodes = visibleGraphNodes.map((node) => {
      const nodeId = String(node.id);
      const typeColor =
        graphSourceMode === "discovery" && !activeSeedVidSet.has(node.id) ? discoveryTypeColor(node.entity_type) : null;
      const style = (() => {
        const position = nodePositionById.get(nodeId);
        if (!position) return undefined;
        return {
          x: position.x,
          y: position.y,
        };
      })();
      const data = {
        ...node,
        isSeed: activeSeedVidSet.has(node.id),
        seedGroup: activeSeedVidSet.has(node.id) ? graphSourceMode : undefined,
        isRoot: rootVid != null && node.id === rootVid,
        hopLevel: visibleNodeHopLevelMap.get(node.id) ?? 99,
        fillColor: typeColor?.fill,
        strokeColor: typeColor?.stroke,
      };
      return {
        id: nodeId,
        label: node.label,
        data,
        style,
        signature: stableStringify({
          id: nodeId,
          label: node.label,
          data,
          style,
        }),
      };
    });

    const edgeById = new Map<string, EdgeBrief>();
    const edges = visibleGraphEdges.map((edge) => {
      const id = edgeKey(edge);
      edgeById.set(id, edge);
      return {
        id,
        source: String(edge.source),
        target: String(edge.target),
        label: edge.relation || "",
        data: edge,
        signature: stableStringify({
          id,
          source: String(edge.source),
          target: String(edge.target),
          label: edge.relation || "",
          data: edge,
        }),
      };
    });

    return {
      nodes,
      edges,
      edgeById,
    };
  }, [
    visibleGraphNodes,
    visibleGraphEdges,
    rootVid,
    visibleNodeHopLevelMap,
    activeSeedVidSet,
    graphSourceMode,
    nodePositionById,
    discoveryTypeColor,
  ]);

  return {
    viewModel,
    currentVisibleEdgeLabelDisplays,
    effectiveEdgeLabelSelectedDisplays,
    edgeLabelSelectedSet,
    edgeLabelFilteredDisplays,
    edgeLabelAllVisibleChecked,
  };
}
