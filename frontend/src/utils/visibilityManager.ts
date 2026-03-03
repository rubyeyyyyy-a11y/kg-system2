import type { EdgeBrief } from "../types/kg";

type GraphLike = {
  hideElement: (id: string[] | string, animation?: boolean) => Promise<void> | void;
  showElement: (id: string[] | string, animation?: boolean) => Promise<void> | void;
};

export type VisibilityFlags = {
  showSelfLoops: boolean;
  hiddenEdgeIdSet?: Set<string>;
};

export type VisibilityEdgeMeta = {
  id: string;
  source: string;
  target: string;
  edge: EdgeBrief;
  isSelfLoop: boolean;
};

export type VisibilitySnapshot = {
  edgeIds: string[];
  edgeMetaById: Map<string, VisibilityEdgeMeta>;
};

export function createVisibilitySnapshot(
  edges: Array<{
    id: string;
    source: string;
    target: string;
    data: EdgeBrief;
  }>
): VisibilitySnapshot {
  const edgeIds: string[] = [];
  const edgeMetaById = new Map<string, VisibilityEdgeMeta>();
  for (const e of edges) {
    const source = String(e.source);
    const target = String(e.target);
    edgeIds.push(e.id);
    edgeMetaById.set(e.id, {
      id: e.id,
      source,
      target,
      edge: e.data,
      isSelfLoop: source === target,
    });
  }
  return { edgeIds, edgeMetaById };
}

function shouldEdgeBeVisible(edge: VisibilityEdgeMeta, flags: VisibilityFlags): boolean {
  if (!flags.showSelfLoops && edge.isSelfLoop) return false;
  if (flags.hiddenEdgeIdSet?.has(edge.id)) return false;
  return true;
}

export function applyVisibility(
  graph: GraphLike | null,
  snapshot: VisibilitySnapshot,
  hiddenEdgeIdSetRef: { current: Set<string> },
  flags: VisibilityFlags,
  reason: string
) {
  if (!graph) return;

  const nextHidden = new Set<string>();
  let selfLoopEdges = 0;
  let visibleNonSelfEdges = 0;
  for (const edgeId of snapshot.edgeIds) {
    const meta = snapshot.edgeMetaById.get(edgeId);
    if (!meta) continue;
    if (meta.isSelfLoop) selfLoopEdges += 1;
    if (!shouldEdgeBeVisible(meta, flags)) nextHidden.add(edgeId);
    else if (!meta.isSelfLoop) visibleNonSelfEdges += 1;
  }

  const prevHidden = hiddenEdgeIdSetRef.current;
  const toHide: string[] = [];
  const toShow: string[] = [];

  for (const id of nextHidden) {
    if (!prevHidden.has(id)) toHide.push(id);
  }
  for (const id of prevHidden) {
    if (!nextHidden.has(id)) toShow.push(id);
  }

  if (toHide.length > 0) graph.hideElement(toHide, false);
  if (toShow.length > 0) graph.showElement(toShow, false);
  hiddenEdgeIdSetRef.current = nextHidden;

  console.info(
    `[visibility] ${reason}: totalEdges=${snapshot.edgeIds.length}, selfLoopEdges=${selfLoopEdges}, hiddenEdges=${nextHidden.size}, visibleNonSelfEdges=${visibleNonSelfEdges}`
  );
}
