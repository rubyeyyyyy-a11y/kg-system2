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

export type GraphViewNode = {
  id: string;
  label: string;
  data: Record<string, unknown>;
  style?: {
    x?: number;
    y?: number;
  };
  signature: string;
};

export type GraphViewEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
  data: Record<string, unknown>;
  signature: string;
};

export type GraphViewModel = {
  nodes: GraphViewNode[];
  edges: GraphViewEdge[];
  edgeById: Map<string, any>;
};

export type GraphRenderPatch = {
  isInitial: boolean;
  addedNodes: GraphViewNode[];
  updatedNodes: GraphViewNode[];
  removedNodeIds: string[];
  addedEdges: GraphViewEdge[];
  updatedEdges: GraphViewEdge[];
  removedEdgeIds: string[];
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

export function buildGraphRenderPatch(previous: GraphViewModel | null, current: GraphViewModel): GraphRenderPatch {
  if (!previous) {
    return {
      isInitial: true,
      addedNodes: current.nodes,
      updatedNodes: [],
      removedNodeIds: [],
      addedEdges: current.edges,
      updatedEdges: [],
      removedEdgeIds: [],
    };
  }

  const previousNodesById = new Map(previous.nodes.map((node) => [node.id, node]));
  const currentNodesById = new Map(current.nodes.map((node) => [node.id, node]));
  const previousEdgesById = new Map(previous.edges.map((edge) => [edge.id, edge]));
  const currentEdgesById = new Map(current.edges.map((edge) => [edge.id, edge]));

  const addedNodes: GraphViewNode[] = [];
  const updatedNodes: GraphViewNode[] = [];
  const removedNodeIds: string[] = [];

  for (const node of current.nodes) {
    const previousNode = previousNodesById.get(node.id);
    if (!previousNode) {
      addedNodes.push(node);
      continue;
    }
    if (previousNode.signature !== node.signature) {
      updatedNodes.push(node);
    }
  }
  for (const node of previous.nodes) {
    if (!currentNodesById.has(node.id)) removedNodeIds.push(node.id);
  }

  const addedEdges: GraphViewEdge[] = [];
  const updatedEdges: GraphViewEdge[] = [];
  const removedEdgeIds: string[] = [];

  for (const edge of current.edges) {
    const previousEdge = previousEdgesById.get(edge.id);
    if (!previousEdge) {
      addedEdges.push(edge);
      continue;
    }
    if (previousEdge.signature !== edge.signature) {
      updatedEdges.push(edge);
    }
  }
  for (const edge of previous.edges) {
    if (!currentEdgesById.has(edge.id)) removedEdgeIds.push(edge.id);
  }

  return {
    isInitial: false,
    addedNodes,
    updatedNodes,
    removedNodeIds,
    addedEdges,
    updatedEdges,
    removedEdgeIds,
  };
}
