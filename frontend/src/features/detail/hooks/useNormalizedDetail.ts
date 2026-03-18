import { useMemo } from "react";

import type { EdgeDetailResp, NodeBrief, NodeDetailResp, Sel } from "../../../types/kg";
import { normalizeEdgeDetail, normalizeNodeDetail, type NormalizedDetail } from "../utils/normalizeDetail";

export function useNormalizedNodeDetail(params: {
  detail: NodeDetailResp | null;
  selectedNodeBrief: NodeBrief | null;
  hopLevel?: number | string | null;
}): NormalizedDetail {
  return useMemo(
    () => normalizeNodeDetail(params),
    [params.detail, params.hopLevel, params.selectedNodeBrief],
  );
}

export function useNormalizedEdgeDetail(params: {
  detail: EdgeDetailResp | null;
  selection: Extract<Sel, { kind: "edge" }> | null;
}): NormalizedDetail {
  return useMemo(() => normalizeEdgeDetail(params), [params.detail, params.selection]);
}
