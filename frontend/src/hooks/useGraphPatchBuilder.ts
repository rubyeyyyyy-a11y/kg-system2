import { useEffect, useMemo, useRef } from "react";

import { buildGraphRenderPatch } from "../graph/renderControl";
import type { GraphRenderPatch, GraphViewModel } from "../graph/renderControl";

export function useGraphPatchBuilder(viewModel: GraphViewModel): GraphRenderPatch {
  const previousViewModelRef = useRef<GraphViewModel | null>(null);

  const patch = useMemo(() => buildGraphRenderPatch(previousViewModelRef.current, viewModel), [viewModel]);

  useEffect(() => {
    previousViewModelRef.current = viewModel;
  }, [viewModel]);

  return patch;
}
