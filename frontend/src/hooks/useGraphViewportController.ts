import { useCallback, useState } from "react";

import type { GraphViewportRequest } from "../graph/renderControl";

export function useGraphViewportController() {
  const [viewportRequest, setViewportRequest] = useState<GraphViewportRequest>({
    sequence: 0,
    mode: "none",
    nodeId: null,
  });

  const requestFocusNode = useCallback((nodeId: string) => {
    setViewportRequest((prev) => ({
      sequence: prev.sequence + 1,
      mode: "focus-node",
      nodeId,
    }));
  }, []);

  const requestFitView = useCallback(() => {
    setViewportRequest((prev) => ({
      sequence: prev.sequence + 1,
      mode: "fit-view",
      nodeId: null,
    }));
  }, []);

  return {
    viewportRequest,
    requestFocusNode,
    requestFitView,
  };
}
