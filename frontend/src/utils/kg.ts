import type { EdgeBrief, NodeBrief } from "../types/kg";
import { relationDisplay as relationDisplayText } from "./relation";

export function relationDisplay(raw?: string): string {
  return relationDisplayText(raw);
}

export function edgeKey(e: EdgeBrief): string {
  return `${e.source}|${e.target}|${e.relation || ""}|${e.source_db || ""}`;
}

export function pairKey(u: number, v: number): string {
  return u <= v ? `${u}|${v}` : `${v}|${u}`;
}

export function getNodeLabelById(
  vid: number | null | undefined,
  graphNodes: NodeBrief[],
  searchNodes: NodeBrief[]
): string {
  if (vid == null) return "-";
  const inGraph = graphNodes.find((n) => n.id === vid);
  if (inGraph?.label) return inGraph.label;
  const inSearch = searchNodes.find((n) => n.id === vid);
  if (inSearch?.label) return inSearch.label;
  return String(vid);
}

export type EdgeIdentity = {
  src: number;
  dst: number;
  relation: string;
  source_db?: string;
};

function normalizeSourceDb(v: string | undefined): string {
  return String(v || "").trim();
}

export function isSameEdge(edge: EdgeBrief, target: EdgeIdentity): boolean {
  return (
    Number(edge.source) === Number(target.src) &&
    Number(edge.target) === Number(target.dst) &&
    String(edge.relation || "") === String(target.relation || "") &&
    normalizeSourceDb(edge.source_db) === normalizeSourceDb(target.source_db)
  );
}

export function findEdgeIdByIdentity(edgeById: Map<string, EdgeBrief>, target: EdgeIdentity): string | null {
  for (const [edgeId, edge] of edgeById.entries()) {
    if (isSameEdge(edge, target)) return edgeId;
  }
  return null;
}
