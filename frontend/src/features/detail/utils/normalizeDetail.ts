import type { EdgeDetailResp, NodeBrief, NodeDetailResp, Sel } from "../../../types/kg";
import { canonicalizeFieldName, isMeaningfulValue, type ObjectMetaKind } from "../../objectMeta/registry/commonRules";

export type NormalizedDetail = {
  objectType: ObjectMetaKind;
  raw: NodeDetailResp | EdgeDetailResp | null;
  props: Record<string, unknown>;
  allFields: Record<string, unknown>;
  edgeKind?: string;
  title: {
    primary: string;
    secondary?: string;
  };
};

function mergeFields(
  kind: ObjectMetaKind,
  topLevel: Record<string, unknown>,
  props: Record<string, unknown>,
): Record<string, unknown> {
  const merged: Record<string, unknown> = {};
  Object.entries(props).forEach(([key, value]) => {
    merged[canonicalizeFieldName(kind, key)] = value;
  });
  Object.entries(topLevel).forEach(([key, value]) => {
    if (!isMeaningfulValue(value)) return;
    merged[canonicalizeFieldName(kind, key)] = value;
  });
  return merged;
}

export function normalizeNodeDetail(params: {
  detail: NodeDetailResp | null;
  selectedNodeBrief: NodeBrief | null;
  hopLevel?: number | string | null;
}): NormalizedDetail {
  const { detail, selectedNodeBrief, hopLevel } = params;
  const props = detail?.props && typeof detail.props === "object" ? detail.props : {};
  const topLevel: Record<string, unknown> = {
    vid: detail?.vid ?? selectedNodeBrief?.id ?? "",
    entity_name: detail?.entity_name || selectedNodeBrief?.label || "",
    entity_type: detail?.entity_type || selectedNodeBrief?.entity_type || "",
    source: detail?.source || selectedNodeBrief?.source || "",
    description: detail?.description || selectedNodeBrief?.description || selectedNodeBrief?.snippet || "",
    entity_raw_id: detail?.entity_raw_id || selectedNodeBrief?.raw_id || "",
    hop_level: hopLevel ?? "",
    version: detail?.version ?? "",
    updated_at: detail?.updated_at ?? "",
    updated_by: detail?.updated_by ?? "",
  };
  const allFields = mergeFields("node", topLevel, props);
  return {
    objectType: "node",
    raw: detail,
    props,
    allFields,
    title: {
      primary: String(allFields.entity_name || `Node ${String(allFields.vid || "")}`),
      secondary: String(allFields.entity_type || ""),
    },
  };
}

export function normalizeEdgeDetail(params: {
  detail: EdgeDetailResp | null;
  selection: Extract<Sel, { kind: "edge" }> | null;
}): NormalizedDetail {
  const { detail, selection } = params;
  const props = detail?.props && typeof detail.props === "object" ? detail.props : {};
  const topLevel: Record<string, unknown> = {
    edge_type: detail?.edge_type || selection?.edge_type || "REL2",
    src: detail?.src ?? selection?.src ?? "",
    dst: detail?.dst ?? selection?.dst ?? "",
    rank: detail?.rank ?? selection?.rank ?? "",
    relation: detail?.relation || selection?.relation || "",
    source: detail?.source_db || selection?.source_db || "",
    evidence: detail?.evidence || "",
    version: detail?.version ?? "",
    updated_at: detail?.updated_at ?? "",
    updated_by: detail?.updated_by ?? "",
  };
  const allFields = mergeFields("edge", topLevel, props);
  const edgeKind = isMeaningfulValue(allFields.edge_kind) ? String(allFields.edge_kind) : undefined;
  return {
    objectType: "edge",
    raw: detail,
    props,
    allFields,
    edgeKind,
    title: {
      primary: edgeKind || String(allFields.relation || allFields.edge_type || "Edge"),
      secondary: String(allFields.relation || ""),
    },
  };
}
