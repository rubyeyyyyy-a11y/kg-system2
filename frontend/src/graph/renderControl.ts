export type GraphMode = "legacy" | "discovery";

export type GraphRenderReason =
  | "initial_discovery"
  | "expand"
  | "collapse"
  | "hide_node"
  | "restore_node"
  | "force_render_dropped"
  | "entity_coverage_toggle"
  | "relation_coverage_toggle"
  | "legacy_replace"
  | "legacy_expand"
  | "legacy_reroot"
  | "legacy_reveal"
  | "legacy_collapse";

export type GraphLayoutMode = "initial-full" | "incremental-insert" | "preserve";

export type GraphViewportMode = "none" | "focus-node";

export type CachedNodePosition = {
  x?: number;
  y?: number;
  source?: "layout" | "drag" | "seed";
  updatedAt?: number;
};

export type GraphRenderMutation = {
  sequence: number;
  graphMode: GraphMode;
  reason: GraphRenderReason;
  anchorNodeId: string | null;
  affectedNodeIds: string[];
};

export type GraphLayoutPlan = {
  mode: GraphLayoutMode;
  reason: GraphRenderReason;
  graphMode: GraphMode;
  anchorNodeId: string | null;
  affectedNodeIds: string[];
};

export type GraphViewportRequest = {
  sequence: number;
  mode: GraphViewportMode;
  nodeId: string | null;
};

export function createGraphRenderMutation(
  graphMode: GraphMode,
  reason: GraphRenderReason,
  sequence = 0,
  patch?: Partial<Pick<GraphRenderMutation, "anchorNodeId" | "affectedNodeIds">>
): GraphRenderMutation {
  return {
    sequence,
    graphMode,
    reason,
    anchorNodeId: patch?.anchorNodeId ?? null,
    affectedNodeIds: patch?.affectedNodeIds ?? [],
  };
}

export function deriveGraphLayoutPlan(mutation: GraphRenderMutation): GraphLayoutPlan {
  if (mutation.graphMode === "legacy") {
    return {
      mode: "initial-full",
      reason: mutation.reason,
      graphMode: mutation.graphMode,
      anchorNodeId: mutation.anchorNodeId,
      affectedNodeIds: mutation.affectedNodeIds,
    };
  }

  switch (mutation.reason) {
    case "initial_discovery":
      return {
        mode: "initial-full",
        reason: mutation.reason,
        graphMode: mutation.graphMode,
        anchorNodeId: mutation.anchorNodeId,
        affectedNodeIds: mutation.affectedNodeIds,
      };
    case "expand":
    case "force_render_dropped":
      return {
        mode: "incremental-insert",
        reason: mutation.reason,
        graphMode: mutation.graphMode,
        anchorNodeId: mutation.anchorNodeId,
        affectedNodeIds: mutation.affectedNodeIds,
      };
    default:
      return {
        mode: "preserve",
        reason: mutation.reason,
        graphMode: mutation.graphMode,
        anchorNodeId: mutation.anchorNodeId,
        affectedNodeIds: mutation.affectedNodeIds,
      };
  }
}

export function hasFinitePosition(position: CachedNodePosition | null | undefined): position is {
  x: number;
  y: number;
} {
  return Number.isFinite(position?.x) && Number.isFinite(position?.y);
}

function hashText(input: string) {
  let hash = 0;
  for (let i = 0; i < input.length; i += 1) hash = (hash * 31 + input.charCodeAt(i)) | 0;
  return Math.abs(hash);
}

export function buildIncrementalNodePosition(
  anchor: { x: number; y: number },
  anchorNodeId: string,
  nodeId: string,
  index: number
) {
  const hash = hashText(`${anchorNodeId}:${nodeId}`);
  const angle = ((hash % 360) * Math.PI) / 180;
  const ring = Math.floor(index / 6);
  const radius = 110 + ring * 42 + (hash % 17);
  return {
    x: anchor.x + Math.cos(angle) * radius,
    y: anchor.y + Math.sin(angle) * radius,
  };
}
