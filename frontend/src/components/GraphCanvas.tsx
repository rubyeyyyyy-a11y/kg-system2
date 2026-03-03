import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";
import { Graph } from "@antv/g6";
import type { EdgeBrief } from "../types/kg";
import { relationDisplay } from "../utils/kg";
import { applyVisibility, createVisibilitySnapshot } from "../utils/visibilityManager";

type G6Node = {
  id: string;
  label: string;
  data: Record<string, unknown>;
};

type G6Edge = {
  id: string;
  source: string;
  target: string;
  label: string;
  data: EdgeBrief;
};

type G6Data = {
  nodes: G6Node[];
  edges: G6Edge[];
};

type GraphCanvasProps = {
  g6Data: G6Data;
  edgeById: Map<string, EdgeBrief>;
  renderNodeLabels: boolean;
  renderEdgeLabels: boolean;
  edgeLabelSelectedDisplays: string[];
  showSelfLoops: boolean;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onNodeClick: (vid: number) => void;
  onEdgeClick: (edgeId: string, edge: EdgeBrief) => void;
  containerStyle?: CSSProperties;
  registerApplyHighlight?: (
    fn: (nextNodeId: string | null, nextEdgeId: string | null, force?: boolean) => void
  ) => void;
};

export function GraphCanvas({
  g6Data,
  edgeById,
  renderNodeLabels,
  renderEdgeLabels,
  edgeLabelSelectedDisplays,
  showSelfLoops,
  selectedNodeId,
  selectedEdgeId,
  onNodeClick,
  onEdgeClick,
  containerStyle,
  registerApplyHighlight,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const edgeByIdRef = useRef<Map<string, EdgeBrief>>(new Map());
  const selectedNodeIdRef = useRef<string | null>(null);
  const selectedEdgeIdRef = useRef<string | null>(null);

  const renderNodeLabelsRef = useRef(true);
  const renderEdgeLabelsRef = useRef(false);
  const edgeLabelSelectedDisplaysRef = useRef<Set<string>>(new Set());
  const showSelfLoopsRef = useRef<boolean>(false);
  const resizeFitTimerRef = useRef<number | null>(null);
  const initialFitDoneRef = useRef(false);
  const initialFitRafRef = useRef<number | null>(null);
  const visibilitySnapshotRef = useRef(createVisibilitySnapshot([]));
  const hiddenEdgeIdSetRef = useRef<Set<string>>(new Set());

  function clearResizeFitTimer() {
    if (resizeFitTimerRef.current == null) return;
    window.clearTimeout(resizeFitTimerRef.current);
    resizeFitTimerRef.current = null;
  }

  function safeFitView() {
    const g: any = graphRef.current;
    if (!g) return;
    try {
      if (typeof g.fitView === "function") g.fitView();
      else if (typeof g.fitToView === "function") g.fitToView();
      else if (typeof g.autoFit === "function") g.autoFit("view");
    } catch {
      // ignore
    }
  }

  function resizeGraphTo(width: number, height: number) {
    if (width <= 0 || height <= 0) return;
    const g: any = graphRef.current;
    if (!g) return;
    try {
      if (typeof g.resize === "function") g.resize(width, height);
      else if (typeof g.setSize === "function") g.setSize(width, height);
    } catch {
      // ignore
    }
  }

  function resizeGraphToContainer() {
    const el = containerRef.current;
    if (!el) return;
    resizeGraphTo(el.clientWidth, el.clientHeight);
  }

  function scheduleResizeFit() {
    clearResizeFitTimer();
    // Resize fires frequently while dragging/splitting; debounce fitView to avoid jitter.
    resizeFitTimerRef.current = window.setTimeout(() => {
      resizeFitTimerRef.current = null;
      safeFitView();
    }, 200);
  }

  useEffect(() => {
    edgeByIdRef.current = edgeById;
  }, [edgeById]);

  useEffect(() => {
    renderNodeLabelsRef.current = renderNodeLabels;
  }, [renderNodeLabels]);

  useEffect(() => {
    renderEdgeLabelsRef.current = renderEdgeLabels;
  }, [renderEdgeLabels]);

  useEffect(() => {
    edgeLabelSelectedDisplaysRef.current = new Set(edgeLabelSelectedDisplays);
  }, [edgeLabelSelectedDisplays]);

  useEffect(() => {
    showSelfLoopsRef.current = showSelfLoops;
  }, [showSelfLoops]);

  function applyHighlight(nextNodeId: string | null, nextEdgeId: string | null, force = false) {
    const g: any = graphRef.current;
    if (!g) return;

    const prevNodeId = selectedNodeIdRef.current;
    const prevEdgeId = selectedEdgeIdRef.current;

    const safeSetState = (id: string, state: unknown[]) => {
      try {
        g.setElementState(id, state);
      } catch {
        // ignore
      }
    };
    const safeZ = (id: string, z: number) => {
      try {
        g.setElementZIndex(id, z);
      } catch {
        // ignore
      }
    };

    if (!force) {
      if (prevNodeId && prevNodeId !== nextNodeId) safeSetState(prevNodeId, []);
      if (prevEdgeId && prevEdgeId !== nextEdgeId) safeSetState(prevEdgeId, []);
    }

    selectedNodeIdRef.current = nextNodeId;
    selectedEdgeIdRef.current = nextEdgeId;

    if (nextNodeId) {
      safeSetState(nextNodeId, ["selected"]);
      safeZ(nextNodeId, 10);
    }
    if (nextEdgeId) {
      safeSetState(nextEdgeId, ["selected"]);
      safeZ(nextEdgeId, 9);
    }

    if (force && !nextNodeId && prevNodeId) safeSetState(prevNodeId, []);
    if (force && !nextEdgeId && prevEdgeId) safeSetState(prevEdgeId, []);
  }

  useEffect(() => {
    if (registerApplyHighlight) registerApplyHighlight(applyHighlight);
  }, [registerApplyHighlight]);

  useEffect(() => {
    if (!containerRef.current) return;

    if (!graphRef.current) {
      const isSeedNode = (d: any) => d?.data?.isSeed === true;

      graphRef.current = new Graph({
        container: containerRef.current,
        width: Math.max(1, containerRef.current.clientWidth),
        height: Math.max(1, containerRef.current.clientHeight),
        autoFit: "view",
        data: { nodes: [], edges: [] },
        layout: { type: "force" },
        node: {
          style: {
            labelText: (d: any) => (renderNodeLabelsRef.current ? String(d.label || "") : ""),
            labelPlacement: "bottom",
            size: (d: any) => {
              if (isSeedNode(d)) return 33;
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return 36;
              if (lvl === 1) return 31;
              if (lvl === 2) return 27;
              return 24;
            },
            fill: (d: any) => {
              if (isSeedNode(d)) return "#bae637";
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return "#ff7a45";
              if (lvl === 1) return "#ffa940";
              if (lvl === 2) return "#91caff";
              return "#C6E5FF";
            },
            stroke: (d: any) => {
              if (isSeedNode(d)) return "#389e0d";
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return "#d4380d";
              if (lvl === 1) return "#d46b08";
              if (lvl === 2) return "#1677ff";
              return "#5B8FF9";
            },
            lineWidth: (d: any) => {
              if (isSeedNode(d)) return 2.6;
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return 3;
              if (lvl === 1) return 2.5;
              if (lvl === 2) return 2;
              return 1.5;
            },
            shadowColor: (d: any) => (isSeedNode(d) ? "#95de64" : "transparent"),
            shadowBlur: (d: any) => (isSeedNode(d) ? 5 : 0),
            cursor: "pointer",
            interactive: true as any,
          },
          state: {
            selected: {
              lineWidth: 3,
              shadowBlur: 12,
              shadowColor: "#faad14",
              stroke: "#faad14",
            },
          },
        },
        edge: {
          style: {
            labelText: (d: any) => {
              const disp = relationDisplay(String(d.data?.relation || d.relation || d.label || ""));
              if (!renderEdgeLabelsRef.current) return "";
              if (!disp) return "";
              return edgeLabelSelectedDisplaysRef.current.has(disp) ? disp : "";
            },
            labelBackground: true,
            cursor: "pointer",
            interactive: true as any,
            lineWidth: 2,
          },
          state: {
            selected: {
              lineWidth: 4,
              shadowBlur: 10,
              shadowColor: "#faad14",
              stroke: "#faad14",
            },
          },
        },
        behaviors: ["drag-canvas", "zoom-canvas", "drag-element"],
      });

      graphRef.current.on("node:click", (evt: any) => {
        const itemId =
          evt?.target?.id ??
          evt?.item?.id ??
          (typeof evt?.item?.getID === "function" ? evt.item.getID() : undefined);

        const vid = Number(itemId);
        if (!Number.isFinite(vid)) return;

        applyHighlight(String(vid), null);
        onNodeClick(vid);
      });

      graphRef.current.on("edge:click", (evt: any) => {
        const edgeId =
          evt?.item?.id ??
          evt?.target?.id ??
          evt?.target?.cfg?.id ??
          evt?.target?.cfg?.parent?.id ??
          evt?.target?.cfg?.parent?.cfg?.id;

        if (!edgeId) return;
        applyHighlight(null, String(edgeId));

        const e = edgeByIdRef.current.get(String(edgeId));
        if (!e) return;
        onEdgeClick(String(edgeId), e);
      });
    }
  }, [onNodeClick, onEdgeClick]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    // Track container size instead of window size so panel drag and grid resize are both covered.
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const width = Math.floor(entry.contentRect.width);
      const height = Math.floor(entry.contentRect.height);
      if (width <= 0 || height <= 0) return;
      resizeGraphTo(width, height);
      scheduleResizeFit();
    });

    observer.observe(el);
    return () => {
      observer.disconnect();
      clearResizeFitTimer();
    };
  }, []);

  useEffect(() => {
    if (!graphRef.current) return;
    // Keep render aligned with latest container size; avoids stale canvas after layout changes.
    resizeGraphToContainer();
    graphRef.current.setData(g6Data);
    graphRef.current.render();

    visibilitySnapshotRef.current = createVisibilitySnapshot(g6Data.edges);
    hiddenEdgeIdSetRef.current = new Set();
    applyVisibility(
      graphRef.current as any,
      visibilitySnapshotRef.current,
      hiddenEdgeIdSetRef,
      { showSelfLoops: showSelfLoopsRef.current },
      "set-data"
    );

    applyHighlight(selectedNodeIdRef.current, selectedEdgeIdRef.current, true);

    if (!initialFitDoneRef.current) {
      initialFitDoneRef.current = true;
      if (initialFitRafRef.current != null) cancelAnimationFrame(initialFitRafRef.current);
      // First render can still be mid-layout; double RAF makes fitView run after paint settles.
      initialFitRafRef.current = requestAnimationFrame(() => {
        initialFitRafRef.current = requestAnimationFrame(() => {
          safeFitView();
          initialFitRafRef.current = null;
        });
      });
    }
  }, [g6Data]);

  useEffect(() => {
    if (!graphRef.current) return;
    applyVisibility(
      graphRef.current as any,
      visibilitySnapshotRef.current,
      hiddenEdgeIdSetRef,
      { showSelfLoops },
      "toggle-self-loop"
    );
  }, [showSelfLoops]);

  useEffect(() => {
    if (!graphRef.current) return;
    applyHighlight(selectedNodeId, selectedEdgeId, true);
  }, [selectedNodeId, selectedEdgeId]);

  useEffect(() => {
    if (!graphRef.current) return;
    try {
      graphRef.current.render();
      applyVisibility(
        graphRef.current as any,
        visibilitySnapshotRef.current,
        hiddenEdgeIdSetRef,
        { showSelfLoops: showSelfLoopsRef.current },
        "render-style-refresh"
      );
      applyHighlight(selectedNodeIdRef.current, selectedEdgeIdRef.current, true);
    } catch {
      // ignore
    }
  }, [renderNodeLabels, renderEdgeLabels, edgeLabelSelectedDisplays]);

  useEffect(() => {
    return () => {
      clearResizeFitTimer();
      if (initialFitRafRef.current != null) cancelAnimationFrame(initialFitRafRef.current);
      initialFitRafRef.current = null;
      if (!graphRef.current) return;
      graphRef.current.destroy();
      graphRef.current = null;
    };
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        minWidth: 0,
        overflow: "hidden",
        position: "relative",
        ...containerStyle,
      }}
    />
  );
}
