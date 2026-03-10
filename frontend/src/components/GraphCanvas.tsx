import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";
import { Text } from "@antv/g";
import { Circle as G6Circle, Graph, register } from "@antv/g6";
import type {
  CachedNodePosition,
  GraphLayoutPlan,
  GraphRenderPatch,
  GraphViewModel,
  GraphViewportRequest,
} from "../graph/renderControl";
import type { EdgeBrief } from "../types/kg";
import { relationDisplay } from "../utils/kg";
import { applyVisibility, createVisibilitySnapshot } from "../utils/visibilityManager";

type G6Node = {
  id: string;
  label: string;
  data: Record<string, unknown>;
  style?: {
    x?: number;
    y?: number;
  };
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

const NODE_TITLE_COLOR = "#262626";
const NODE_SUBTITLE_COLOR = "#8c8c8c";
const TWO_LINE_NODE_TYPE = "kg-two-line-circle";
const TWO_LINE_NODE_REGISTER_FLAG = "__kg_two_line_circle_registered__";

class TwoLineCircleNode extends G6Circle {
  protected drawLabelShape(attributes: any, container: any): void {
    const titleText = String(attributes?.labelText || "").trim();
    const subtitleText = String(attributes?.subtitleText || "").trim();
    const keyShape = this.getShape<any>("key");
    const radius =
      Number(keyShape?.attributes?.r || 0) || Math.max(12, Math.min(...this.getSize(attributes)) / 2);
    const titleY = radius + 6;
    const titleFontSize = Number(attributes?.labelFontSize || 12);
    const subtitleFontSize = Math.max(10, titleFontSize - 1);
    const labelVisible = attributes?.label !== false && !!titleText;

    this.upsert(
      "title",
      Text,
      labelVisible
        ? {
            x: 0,
            y: titleY,
            text: titleText,
            fill: String(attributes?.labelFill || NODE_TITLE_COLOR),
            fontSize: titleFontSize,
            fontWeight: 500,
            textAlign: "center",
            textBaseline: "top",
            pointerEvents: "none",
          }
        : false,
      container
    );

    this.upsert(
      "subtitle",
      Text,
      labelVisible && subtitleText
        ? {
            x: 0,
            y: titleY + titleFontSize + 2,
            text: subtitleText,
            fill: NODE_SUBTITLE_COLOR,
            fontSize: subtitleFontSize,
            textAlign: "center",
            textBaseline: "top",
            pointerEvents: "none",
          }
        : false,
      container
    );
  }
}

if (!(globalThis as Record<string, unknown>)[TWO_LINE_NODE_REGISTER_FLAG]) {
  register("node", TWO_LINE_NODE_TYPE, TwoLineCircleNode);
  (globalThis as Record<string, unknown>)[TWO_LINE_NODE_REGISTER_FLAG] = true;
}

type GraphCanvasProps = {
  viewModel: GraphViewModel;
  renderPatch: GraphRenderPatch;
  layoutPlan: GraphLayoutPlan;
  viewportRequest: GraphViewportRequest;
  renderNodeLabels: boolean;
  renderEdgeLabels: boolean;
  edgeLabelSelectedDisplays: string[];
  showSelfLoops: boolean;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onNodeClick: (vid: number) => void;
  onEdgeClick: (edgeId: string, edge: EdgeBrief) => void;
  onNodePositionChange?: (
    positions: Record<string, { x: number; y: number }>,
    source?: CachedNodePosition["source"]
  ) => void;
  containerStyle?: CSSProperties;
  registerApplyHighlight?: (
    fn: (nextNodeId: string | null, nextEdgeId: string | null, force?: boolean) => void
  ) => void;
};

export function GraphCanvas({
  viewModel,
  renderPatch,
  layoutPlan,
  viewportRequest,
  renderNodeLabels,
  renderEdgeLabels,
  edgeLabelSelectedDisplays,
  showSelfLoops,
  selectedNodeId,
  selectedEdgeId,
  onNodeClick,
  onEdgeClick,
  onNodePositionChange,
  containerStyle,
  registerApplyHighlight,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const viewModelRef = useRef<GraphViewModel>(viewModel);
  const edgeByIdRef = useRef<Map<string, EdgeBrief>>(viewModel.edgeById);
  const onNodePositionChangeRef = useRef<typeof onNodePositionChange>(onNodePositionChange);
  const selectedNodeIdRef = useRef<string | null>(null);
  const selectedEdgeIdRef = useRef<string | null>(null);

  const renderNodeLabelsRef = useRef(true);
  const renderEdgeLabelsRef = useRef(false);
  const edgeLabelSelectedDisplaysRef = useRef<Set<string>>(new Set());
  const showSelfLoopsRef = useRef<boolean>(false);
  const fitAfterRenderRafRef = useRef<number | null>(null);
  const persistPositionsRafRef = useRef<number | null>(null);
  const visibilitySnapshotRef = useRef(createVisibilitySnapshot([]));
  const hiddenEdgeIdSetRef = useRef<Set<string>>(new Set());

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

  function safeStopLayout() {
    const g: any = graphRef.current;
    if (!g || g.destroyed || !g.context?.layout) return;
    try {
      g.stopLayout();
    } catch {
      // ignore
    }
  }

  function clearScheduledFit() {
    if (fitAfterRenderRafRef.current == null) return;
    cancelAnimationFrame(fitAfterRenderRafRef.current);
    fitAfterRenderRafRef.current = null;
  }

  function clearScheduledPositionPersist() {
    if (persistPositionsRafRef.current == null) return;
    cancelAnimationFrame(persistPositionsRafRef.current);
    persistPositionsRafRef.current = null;
  }

  function collectNodePositions(nodeIds: string[]) {
    const g: any = graphRef.current;
    const positions: Record<string, { x: number; y: number }> = {};
    if (!g) return positions;
    for (const nodeId of nodeIds) {
      try {
        const position = g.getElementPosition(nodeId);
        const x = Number(position?.[0]);
        const y = Number(position?.[1]);
        if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
        positions[nodeId] = { x, y };
      } catch {
        // ignore
      }
    }
    return positions;
  }

  function persistVisibleNodePositions(source: CachedNodePosition["source"] = "layout") {
    if (!onNodePositionChangeRef.current) return;
    const positions = collectNodePositions(viewModelRef.current.nodes.map((node) => node.id));
    if (Object.keys(positions).length <= 0) return;
    onNodePositionChangeRef.current(positions, source);
  }

  function toG6Data(model: GraphViewModel): G6Data {
    return {
      nodes: model.nodes.map((node) => ({
        id: node.id,
        label: node.label,
        data: node.data,
        style: node.style,
      })),
      edges: model.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        data: edge.data as EdgeBrief,
      })),
    };
  }

  useEffect(() => {
    viewModelRef.current = viewModel;
    edgeByIdRef.current = viewModel.edgeById;
  }, [viewModel]);

  useEffect(() => {
    onNodePositionChangeRef.current = onNodePositionChange;
  }, [onNodePositionChange]);

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

  function focusNode(nodeId: string) {
    applyHighlight(nodeId, null, true);
    const g: any = graphRef.current;
    if (!g) return;
    try {
      if (typeof g.focusElement === "function") {
        g.focusElement(nodeId, true);
        return;
      }
    } catch {
      // ignore
    }
    try {
      if (typeof g.focusItem === "function") {
        g.focusItem(nodeId, true);
        return;
      }
    } catch {
      // ignore
    }
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
        data: { nodes: [], edges: [] },
        node: {
          type: TWO_LINE_NODE_TYPE,
          style: {
            labelText: (d: any) => (renderNodeLabelsRef.current ? String(d.label || "") : ""),
            subtitleText: (d: any) =>
              renderNodeLabelsRef.current ? String(d?.data?.entity_type || "") : "",
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
              if (d?.data?.fillColor) return String(d.data.fillColor);
              const lvl = Number(d?.data?.hopLevel ?? 99);
              if (lvl === 0) return "#ff7a45";
              if (lvl === 1) return "#ffa940";
              if (lvl === 2) return "#91caff";
              return "#C6E5FF";
            },
            stroke: (d: any) => {
              if (isSeedNode(d)) return "#389e0d";
              if (d?.data?.strokeColor) return String(d.data.strokeColor);
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
            lineWidth: (d: any) => {
              if (d?.data?.is_backbone) return 3;
              if (String(d?.data?.layer || "") === "shared") return 2.5;
              return 2;
            },
            stroke: (d: any) => {
              if (d?.data?.is_backbone) return "#d4380d";
              const layer = String(d?.data?.layer || "");
              if (layer === "shared") return "#1677ff";
              if (layer === "local") return "#595959";
              if (layer === "supplement") return "#bfbfbf";
              return "#8c8c8c";
            },
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

      graphRef.current.on("afterlayout", () => {
        persistVisibleNodePositions("layout");
      });

      graphRef.current.on("node:dragend", (evt: any) => {
        const nodeId =
          evt?.target?.id ??
          evt?.item?.id ??
          (typeof evt?.item?.getID === "function" ? evt.item.getID() : undefined);
        if (!nodeId || !onNodePositionChangeRef.current) return;
        const positions = collectNodePositions([String(nodeId)]);
        if (Object.keys(positions).length <= 0) return;
        onNodePositionChangeRef.current(positions, "drag");
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
    });

    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!graphRef.current) return;
    if (!renderPatch.isInitial) safeStopLayout();
    const shouldRunFullLayout = layoutPlan.mode === "initial-full" || layoutPlan.mode === "manual-full";
    if (shouldRunFullLayout) {
      graphRef.current.setLayout({
        type: "force",
        animation: false,
      } as any);
    } else {
      graphRef.current.setLayout(undefined as any);
    }
    // Keep render aligned with latest container size; avoids stale canvas after layout changes.
    resizeGraphToContainer();
    const graph = graphRef.current as any;
    const applyPatch = async () => {
      if (renderPatch.isInitial) {
        graph.setData(toG6Data(viewModel));
        await graph.render();
      } else {
        if (renderPatch.removedEdgeIds.length > 0) graph.removeEdgeData(renderPatch.removedEdgeIds);
        if (renderPatch.removedNodeIds.length > 0) graph.removeNodeData(renderPatch.removedNodeIds);
        if (renderPatch.addedNodes.length > 0) {
          graph.addNodeData(
            renderPatch.addedNodes.map((node) => ({
              id: node.id,
              label: node.label,
              data: node.data,
              style: node.style,
            }))
          );
        }
        if (renderPatch.addedEdges.length > 0) {
          graph.addEdgeData(
            renderPatch.addedEdges.map((edge) => ({
              id: edge.id,
              source: edge.source,
              target: edge.target,
              label: edge.label,
              data: edge.data,
            }))
          );
        }
        if (renderPatch.updatedNodes.length > 0) {
          graph.updateNodeData(
            renderPatch.updatedNodes.map((node) => ({
              id: node.id,
              label: node.label,
              data: node.data,
              style: node.style,
            }))
          );
        }
        if (renderPatch.updatedEdges.length > 0) {
          graph.updateEdgeData(
            renderPatch.updatedEdges.map((edge) => ({
              id: edge.id,
              source: edge.source,
              target: edge.target,
              label: edge.label,
              data: edge.data,
            }))
          );
        }
        await graph.draw();
      }

      // For initial-full/manual-full, patch draw alone is not enough. Force an explicit layout pass.
      if (shouldRunFullLayout && !renderPatch.isInitial) {
        await graph.layout(graph.getLayout?.());
      }

      visibilitySnapshotRef.current = createVisibilitySnapshot(toG6Data(viewModel).edges);
      hiddenEdgeIdSetRef.current = new Set();
      applyVisibility(
        graphRef.current as any,
        visibilitySnapshotRef.current,
        hiddenEdgeIdSetRef,
        { showSelfLoops: showSelfLoopsRef.current },
        renderPatch.isInitial ? "set-data" : "patch-data"
      );

      applyHighlight(selectedNodeIdRef.current, selectedEdgeIdRef.current, true);

      clearScheduledPositionPersist();
      if (layoutPlan.mode !== "initial-full") {
        persistPositionsRafRef.current = requestAnimationFrame(() => {
          persistVisibleNodePositions(layoutPlan.mode === "incremental-insert" ? "seed" : "layout");
          persistPositionsRafRef.current = null;
        });
      }

      clearScheduledFit();
      if (layoutPlan.mode === "initial-full" || layoutPlan.mode === "manual-full") {
        fitAfterRenderRafRef.current = requestAnimationFrame(() => {
          safeFitView();
          fitAfterRenderRafRef.current = null;
        });
      }
    };

    void applyPatch();
  }, [layoutPlan, renderPatch, viewModel]);

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
    if (viewportRequest.mode !== "focus-node" || !viewportRequest.nodeId) return;
    focusNode(viewportRequest.nodeId);
  }, [viewportRequest]);

  useEffect(() => {
    if (!graphRef.current) return;
    if (viewportRequest.mode !== "fit-view") return;
    safeFitView();
  }, [viewportRequest]);

  useEffect(() => {
    if (!graphRef.current) return;
    try {
      const graph = graphRef.current as any;
      if (viewModelRef.current.nodes.length > 0) {
        graph.updateNodeData(
          viewModelRef.current.nodes.map((node) => ({
            id: node.id,
            label: node.label,
            data: node.data,
            style: node.style,
          }))
        );
      }
      if (viewModelRef.current.edges.length > 0) {
        graph.updateEdgeData(
          viewModelRef.current.edges.map((edge) => ({
            id: edge.id,
            source: edge.source,
            target: edge.target,
            label: edge.label,
            data: edge.data,
          }))
        );
      }
      void graph.draw();
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
  }, [renderNodeLabels, renderEdgeLabels, edgeLabelSelectedDisplays, viewModel]);

  useEffect(() => {
    return () => {
      clearScheduledFit();
      clearScheduledPositionPersist();
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
