import { useMemo } from "react";

import {
  buildIncrementalNodePosition,
  deriveGraphLayoutPlan,
  hasFinitePosition,
} from "../graph/renderControl";
import type {
  CachedNodePosition,
  GraphLayoutPlan,
  GraphRenderMutation,
} from "../graph/renderControl";

type UseGraphLayoutControllerParams = {
  visibleNodeIds: string[];
  nodePositionCache?: Record<string, CachedNodePosition>;
  renderMutation: GraphRenderMutation;
};

type UseGraphLayoutControllerResult = {
  layoutPlan: GraphLayoutPlan;
  nodePositionById: Map<string, { x: number; y: number }>;
};

export function useGraphLayoutController({
  visibleNodeIds,
  nodePositionCache,
  renderMutation,
}: UseGraphLayoutControllerParams): UseGraphLayoutControllerResult {
  const layoutPlan = useMemo(() => deriveGraphLayoutPlan(renderMutation), [renderMutation]);

  const nodePositionById = useMemo(() => {
    const next = new Map<string, { x: number; y: number }>();
    const cache = nodePositionCache || {};

    for (const nodeId of visibleNodeIds) {
      const cached = cache[nodeId];
      if (!hasFinitePosition(cached)) continue;
      next.set(nodeId, { x: cached.x, y: cached.y });
    }

    if (layoutPlan.mode !== "incremental-insert" || !layoutPlan.anchorNodeId) {
      return next;
    }

    const anchor = cache[layoutPlan.anchorNodeId];
    if (!hasFinitePosition(anchor)) return next;

    const visibleNodeIdSet = new Set(visibleNodeIds);
    const seededNodeIds = layoutPlan.affectedNodeIds
      .filter((nodeId) => visibleNodeIdSet.has(nodeId))
      .filter((nodeId) => !hasFinitePosition(cache[nodeId]))
      .sort((a, b) => a.localeCompare(b));

    seededNodeIds.forEach((nodeId, index) => {
      next.set(nodeId, buildIncrementalNodePosition(anchor, layoutPlan.anchorNodeId as string, nodeId, index));
    });

    return next;
  }, [layoutPlan, nodePositionCache, renderMutation.sequence, visibleNodeIds]);

  return {
    layoutPlan,
    nodePositionById,
  };
}
