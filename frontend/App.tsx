import { useEffect, useMemo, useRef, useState } from "react";
import { Graph } from "@antv/g6";

type NodeBrief = {
  id: number;
  label: string;
  entity_type: string;
  raw_id?: string;
  source?: string;
  score?: number;
  snippet?: string;
};

type EdgeBrief = {
  source: number;
  target: number;
  relation?: string;
  source_db?: string;
};

type SearchResp = {
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  total_candidates: number;
};

type SubgraphResp = {
  root_vid: number;
  nodes: NodeBrief[];
  edges: EdgeBrief[];
  stats: { node_count: number; edge_count: number; truncated: boolean; dropped_nodes?: number };
};

type ExpandResp = {
  added_nodes: NodeBrief[];
  added_edges: EdgeBrief[];
  stats: { node_count_after: number; dropped_nodes: number; policy: string };
};

type NodeDetailResp = { vid: number; props: Record<string, any> };
type EdgeDetailResp = { src: number; dst: number; props: Record<string, any> };

type Sel =
  | { kind: "none" }
  | { kind: "node"; vid: number }
  | { kind: "edge"; src: number; dst: number; relation: string; source_db?: string };

export default function App() {
  // ----------------------------
  // Left: search
  // ----------------------------
  const [q, setQ] = useState("");
  const [searchName, setSearchName] = useState(true);
  const [searchDesc, setSearchDesc] = useState(true);
  const [entityType, setEntityType] = useState("");
  const [source, setSource] = useState("");
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchData, setSearchData] = useState<SearchResp>({ nodes: [], edges: [], total_candidates: 0 });

  // ----------------------------
  // Right: graph controls
  // ----------------------------
  const [rootVid, setRootVid] = useState<number | null>(null);
  const [hop, setHop] = useState<number>(1);
  const [relationTypes, setRelationTypes] = useState<string[]>([]);
  const [relations, setRelations] = useState<string[]>([]);
  const [loadingGraph, setLoadingGraph] = useState(false);

  // graph state
  const [graphNodes, setGraphNodes] = useState<NodeBrief[]>([]);
  const [graphEdges, setGraphEdges] = useState<EdgeBrief[]>([]);
  const [graphStats, setGraphStats] = useState<any>(null);

  // selection & detail
  const [sel, setSel] = useState<Sel>({ kind: "none" });
  const [nodeDetail, setNodeDetail] = useState<NodeDetailResp | null>(null);
  const [edgeDetail, setEdgeDetail] = useState<EdgeDetailResp | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // refs
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);

  // edge id -> EdgeBrief (because evt.item may be undefined in edge:click)
  const edgeByIdRef = useRef<Map<string, EdgeBrief>>(new Map());

  // highlight refs (only one selected at a time)
  const selectedNodeIdRef = useRef<string | null>(null);
  const selectedEdgeIdRef = useRef<string | null>(null);

  // resize/autofit refs
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const fitTimerRef = useRef<number | null>(null);

  // apply highlight (force=true for after setData/render)
  function applyHighlight(nextNodeId: string | null, nextEdgeId: string | null, force = false) {
    const g: any = graphRef.current;
    if (!g) return;

    const prevNodeId = selectedNodeIdRef.current;
    const prevEdgeId = selectedEdgeIdRef.current;

    const safeSetState = (id: string, state: any) => {
      try {
        g.setElementState(id, state);
      } catch {}
    };
    const safeZ = (id: string, z: number) => {
      try {
        g.setElementZIndex(id, z);
      } catch {}
    };

    // clear previous on normal click
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

    // when clearing, also clear prev if force
    if (force && !nextNodeId && prevNodeId) safeSetState(prevNodeId, []);
    if (force && !nextEdgeId && prevEdgeId) safeSetState(prevEdgeId, []);
  }

  // ----------------------------
  // Auto fit helpers (A: fill middle area aggressively)
  // ----------------------------
  function doFitViewNow() {
    const g: any = graphRef.current;
    const el = containerRef.current;
    if (!g || !el) return;

    // no data -> skip
    if (!graphNodes.length) return;

    try {
      // 尽量多占中间空间（padding 较小）
      // 不同 G6 版本 fitView 签名可能不同，所以做兼容调用
      if (typeof g.fitView === "function") {
        try {
          g.fitView({ padding: [16, 16, 16, 16] });
          return;
        } catch {}
        try {
          g.fitView();
          return;
        } catch {}
      }

      // fallback
      if (typeof g.autoFit === "function") {
        try {
          g.autoFit("view");
          return;
        } catch {}
      }

      if (typeof g.render === "function") {
        // 最后兜底：重新 render 一次
        g.render();
      }
    } catch (err) {
      console.warn("fitView failed:", err);
    }
  }

  function scheduleFitView(delay = 120) {
    if (fitTimerRef.current != null) {
      window.clearTimeout(fitTimerRef.current);
      fitTimerRef.current = null;
    }
    fitTimerRef.current = window.setTimeout(() => {
      doFitViewNow();
      fitTimerRef.current = null;
    }, delay);
  }

  // ----------------------------
  // G6 data mapping (+ build edgeById)
  // ----------------------------
  const { g6Data, edgeById } = useMemo(() => {
    const nodes = graphNodes.map((n) => ({
      id: String(n.id),
      label: n.label,
      data: n,
    }));

    const nextEdgeById = new Map<string, EdgeBrief>();

    const edges = graphEdges.map((e, idx) => {
      const id = `e-${idx}-${e.source}-${e.target}-${e.relation || ""}-${e.source_db || ""}`;
      nextEdgeById.set(id, e);
      return {
        id,
        source: String(e.source),
        target: String(e.target),
        label: e.relation || "",
        data: e,
      };
    });

    return { g6Data: { nodes, edges }, edgeById: nextEdgeById };
  }, [graphNodes, graphEdges]);

  // sync map to ref for event handlers
  useEffect(() => {
    edgeByIdRef.current = edgeById;
  }, [edgeById]);

  // ----------------------------
  // API helpers
  // ----------------------------
  async function apiPost<T>(url: string, body: any): Promise<T> {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${t}`);
    }
    return (await resp.json()) as T;
  }

  async function apiGet<T>(url: string): Promise<T> {
    const resp = await fetch(url);
    if (!resp.ok) {
      const t = await resp.text();
      throw new Error(`HTTP ${resp.status}: ${t}`);
    }
    return (await resp.json()) as T;
  }

  // ----------------------------
  // Left: search
  // ----------------------------
  async function onSearch() {
    if (!q.trim()) return;
    setLoadingSearch(true);
    try {
      const json = await apiPost<SearchResp>("/api/search", {
        q,
        search_in_name: searchName,
        search_in_description: searchDesc,
        entity_type: entityType || null,
        source: source || null,
      });
      setSearchData(json);
    } catch (e: any) {
      alert(e?.message || String(e));
    } finally {
      setLoadingSearch(false);
    }
  }

  // ----------------------------
  // Right: relations
  // ----------------------------
  async function loadRelationTypes() {
    try {
      const rels = await apiGet<string[]>("/api/relation_types");
      setRelationTypes(rels);
    } catch (e: any) {
      console.warn(e?.message || e);
    }
  }

  // ----------------------------
  // Right: subgraph
  // ----------------------------
  async function loadSubgraph(nextRoot: number) {
    setLoadingGraph(true);
    try {
      const json = await apiPost<SubgraphResp>("/api/subgraph", {
        root_vid: nextRoot,
        hop,
        relations,
        max_nodes: 80,
        max_edges: 300,
      });

      setRootVid(nextRoot);
      setGraphNodes(json.nodes);
      setGraphEdges(json.edges);
      setGraphStats(json.stats);

      // reset selection + highlight
      setSel({ kind: "none" });
      setNodeDetail(null);
      setEdgeDetail(null);
      applyHighlight(null, null);
    } catch (e: any) {
      alert(e?.message || String(e));
    } finally {
      setLoadingGraph(false);
    }
  }

  // Expand 1-hop (merge into current graph)
  async function expand1hop(vid: number) {
    if (!rootVid) return;
    setLoadingGraph(true);
    try {
      const existingIds = graphNodes.map((n) => n.id);

      const json = await apiPost<ExpandResp>("/api/expand", {
        from_vid: vid,
        relations,
        existing_node_ids: existingIds,
        max_nodes: 80,
        max_edges: 300,
      });

      // merge nodes
      const nodeMap = new Map<number, NodeBrief>();
      for (const n of graphNodes) nodeMap.set(n.id, n);
      for (const n of json.added_nodes) nodeMap.set(n.id, n);

      // merge edges with uniq
      const edgeKey = (e: EdgeBrief) => `${e.source}|${e.target}|${e.relation || ""}|${e.source_db || ""}`;
      const edgeSet = new Set<string>();
      const mergedEdges: EdgeBrief[] = [];

      for (const e of graphEdges) {
        const k = edgeKey(e);
        if (!edgeSet.has(k)) {
          edgeSet.add(k);
          mergedEdges.push(e);
        }
      }
      for (const e of json.added_edges) {
        const k = edgeKey(e);
        if (!edgeSet.has(k)) {
          edgeSet.add(k);
          mergedEdges.push(e);
        }
      }

      setGraphNodes(Array.from(nodeMap.values()));
      setGraphEdges(mergedEdges);
      setGraphStats({
        ...(graphStats || {}),
        node_count: json.stats.node_count_after,
        edge_count: mergedEdges.length,
        policy: json.stats.policy,
        dropped_nodes: json.stats.dropped_nodes,
      });
    } catch (e: any) {
      alert(e?.message || String(e));
    } finally {
      setLoadingGraph(false);
    }
  }

  // Reroot + load 1-hop subgraph (replace whole graph)
  async function reroot1hop(vid: number) {
    setLoadingGraph(true);
    try {
      const json = await apiPost<SubgraphResp>("/api/subgraph", {
        root_vid: vid,
        hop: 1, // force 1-hop
        relations,
        max_nodes: 80,
        max_edges: 300,
      });

      setHop(1);
      setRootVid(vid);
      setGraphNodes(json.nodes);
      setGraphEdges(json.edges);
      setGraphStats(json.stats);

      // give strong feedback: auto-select new root
      setSel({ kind: "node", vid });
      setEdgeDetail(null);
      setNodeDetail(null);
      applyHighlight(String(vid), null);
      loadNodeDetail(vid);
    } catch (e: any) {
      alert(e?.message || String(e));
    } finally {
      setLoadingGraph(false);
    }
  }

  // Node detail
  async function loadNodeDetail(vid: number) {
    setDetailLoading(true);
    try {
      const json = await apiGet<NodeDetailResp>(`/api/node/${vid}`);
      setNodeDetail(json);
    } catch (e: any) {
      alert(e?.message || String(e));
    } finally {
      setDetailLoading(false);
    }
  }

  // Edge detail
  async function loadEdgeDetail(src: number, dst: number, relation: string, source_db?: string) {
    setDetailLoading(true);
    try {
      const json = await apiPost<EdgeDetailResp>("/api/edge_detail", {
        src,
        dst,
        relation,
        source_db: source_db || null,
      });
      setEdgeDetail(json);
    } catch (e: any) {
      alert(e?.message || String(e));
    } finally {
      setDetailLoading(false);
    }
  }

  // Init relation types once
  useEffect(() => {
    loadRelationTypes();
  }, []);

  // Create graph once; bind events once; update data on g6Data change
  useEffect(() => {
    if (!containerRef.current) return;

    if (!graphRef.current) {
      graphRef.current = new Graph({
        container: containerRef.current,
        width: Math.max(containerRef.current.clientWidth, 320),
        height: Math.max(containerRef.current.clientHeight, 240),

        // 我们手动 fitView，避免 autoFit 在某些更新场景下不稳定/过早触发
        autoFit: false as any,

        data: { nodes: [], edges: [] },

        // 更偏“铺满”的 force 参数（在你的 max_nodes=80 / max_edges=300 下比较合适）
        layout: {
          type: "force",
          preventOverlap: true,
          nodeSize: 26,
          linkDistance: 85,      // 让图不要缩成一团
          nodeStrength: -220,    // 中等偏强排斥，增强铺开感
          edgeStrength: 0.12,
          collideStrength: 0.9,
          alphaDecay: 0.06,
          alphaMin: 0.001,
        } as any,

        node: {
          style: {
            labelText: (d: any) => d.label,
            labelPlacement: "bottom",
            size: 26,
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
            labelText: (d: any) => d.data?.relation || d.relation || d.label || "",
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

      // Node click -> detail + highlight
      graphRef.current.on("node:click", (evt: any) => {
        const itemId =
          evt?.target?.id ??
          evt?.item?.id ??
          (typeof evt?.item?.getID === "function" ? evt.item.getID() : undefined);

        const vid = Number(itemId);
        if (!Number.isFinite(vid)) return;

        applyHighlight(String(vid), null);

        setSel({ kind: "node", vid });
        setEdgeDetail(null);
        loadNodeDetail(vid);
      });

      // Edge click -> detail + highlight
      graphRef.current.on("edge:click", (evt: any) => {
        const edgeId =
          evt?.item?.id ??
          evt?.target?.id ??
          evt?.target?.cfg?.id ??
          evt?.target?.cfg?.parent?.id ??
          evt?.target?.cfg?.parent?.cfg?.id;

        if (!edgeId) {
          console.warn("edge:click no edgeId", evt);
          return;
        }

        applyHighlight(null, String(edgeId));

        const e = edgeByIdRef.current.get(String(edgeId));
        if (!e) {
          console.warn("edge:click edgeId not found in map", { edgeId, mapSize: edgeByIdRef.current.size });
          return;
        }

        const src = Number(e.source);
        const dst = Number(e.target);
        const relation = String(e.relation || "");
        const source_db = e.source_db ? String(e.source_db) : undefined;

        if (!Number.isFinite(src) || !Number.isFinite(dst) || !relation) {
          console.warn("edge:click parse failed (from map)", { edgeId, e });
          return;
        }

        setSel({ kind: "edge", src, dst, relation, source_db });
        setNodeDetail(null);
        loadEdgeDetail(src, dst, relation, source_db);
      });
    }

    const g: any = graphRef.current;
    g.setData(g6Data);
    g.render();

    // re-apply highlight after render
    applyHighlight(selectedNodeIdRef.current, selectedEdgeIdRef.current, true);

    // 数据更新后自动铺满中间区域（A 策略）
    scheduleFitView(140);
  }, [g6Data]);

  // ResizeObserver: middle panel size changes -> resize graph + fitView
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleResize = () => {
      const g: any = graphRef.current;
      if (!g || !containerRef.current) return;

      const w = Math.max(containerRef.current.clientWidth, 320);
      const h = Math.max(containerRef.current.clientHeight, 240);

      try {
        if (typeof g.resize === "function") {
          g.resize(w, h);
        } else {
          // 兼容兜底
          g.setSize?.(w, h);
        }
      } catch (err) {
        console.warn("graph resize failed:", err);
      }

      // 窗口变化时都自适应
      scheduleFitView(80);
    };

    // 初次挂载也执行一次
    handleResize();

    const ro = new ResizeObserver(() => {
      handleResize();
    });
    ro.observe(el);
    resizeObserverRef.current = ro;

    return () => {
      try {
        ro.disconnect();
      } catch {}
      resizeObserverRef.current = null;
    };
  }, []);

  // cleanup graph on unmount
  useEffect(() => {
    return () => {
      if (fitTimerRef.current != null) {
        window.clearTimeout(fitTimerRef.current);
        fitTimerRef.current = null;
      }
      try {
        resizeObserverRef.current?.disconnect();
      } catch {}
      resizeObserverRef.current = null;

      try {
        (graphRef.current as any)?.destroy?.();
      } catch {}
      graphRef.current = null;
    };
  }, []);

  // Derived selected brief
  const selectedNodeBrief = useMemo(() => {
    if (sel.kind !== "node") return null;
    return graphNodes.find((n) => n.id === sel.vid) || null;
  }, [sel, graphNodes]);

  // ----------------------------
  // Render UI
  // ----------------------------
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "420px minmax(0, 1fr) 360px", // avoid overflow covering side panels
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
      }}
    >
      {/* Left */}
      <div style={{ padding: 16, borderRight: "1px solid #eee", overflow: "auto" }}>
        <h3 style={{ margin: 0 }}>实体检索（Top100）</h3>

        <div style={{ marginTop: 12, display: "flex", gap: 8 }}>
          <input
            style={{ flex: 1, padding: 8 }}
            placeholder="关键词（模糊）"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && onSearch()}
          />
          <button onClick={onSearch} disabled={loadingSearch} style={{ padding: "8px 12px" }}>
            {loadingSearch ? "搜索中…" : "搜索"}
          </button>
        </div>

        <div style={{ marginTop: 10, display: "grid", gap: 6, fontSize: 13 }}>
          <label>
            <input type="checkbox" checked={searchName} onChange={(e) => setSearchName(e.target.checked)} /> 搜索 entity_name
          </label>
          <label>
            <input type="checkbox" checked={searchDesc} onChange={(e) => setSearchDesc(e.target.checked)} /> 搜索 description
          </label>
        </div>

        <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
          <input
            style={{ padding: 8 }}
            placeholder="过滤 entity_type（可选，如 disease）"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
          />
          <input
            style={{ padding: 8 }}
            placeholder="过滤 source（可选，如 UMLS）"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          />
        </div>

        <div style={{ marginTop: 10, color: "#666", fontSize: 12 }}>
          候选数量：{searchData.total_candidates}（返回 Top100）
        </div>

        <hr style={{ margin: "12px 0" }} />

        <div style={{ display: "grid", gap: 10 }}>
          {searchData.nodes.map((n) => (
            <div
              key={n.id}
              style={{
                padding: 10,
                border: rootVid === n.id ? "1px solid #333" : "1px solid #f0f0f0",
                borderRadius: 8,
                cursor: "pointer",
              }}
              onClick={() => loadSubgraph(n.id)}
              title="点击切换为该实体的子图"
            >
              <div style={{ fontWeight: 600 }}>{n.label}</div>
              <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                id={n.id} | {n.entity_type} | {n.source} | score={n.score}
              </div>
              {n.snippet ? <div style={{ fontSize: 12, marginTop: 6 }}>{n.snippet}</div> : null}
            </div>
          ))}
        </div>
      </div>

      {/* Middle: controls + graph */}
      <div
        style={{
          display: "grid",
          gridTemplateRows: "56px 1fr",
          minWidth: 0,
          overflow: "hidden",
          position: "relative",
          zIndex: 1,
        }}
      >
        {/* Top controls */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 12px", borderBottom: "1px solid #eee" }}>
          <div style={{ fontSize: 13, color: "#444" }}>
            Root: {rootVid ?? "-"} {loadingGraph ? "（加载中…）" : ""}
          </div>

          <div style={{ marginLeft: 8 }}>
            <label style={{ fontSize: 13, marginRight: 6 }}>Hop</label>
            <select value={hop} onChange={(e) => setHop(Number(e.target.value))}>
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
          </div>

          <div style={{ marginLeft: 8, display: "flex", alignItems: "center", gap: 6 }}>
            <label style={{ fontSize: 13 }}>Relation</label>
            <select
              multiple
              value={relations}
              onChange={(e) => {
                const opts = Array.from(e.target.selectedOptions).map((o) => o.value);
                setRelations(opts);
              }}
              style={{ height: 40, minWidth: 220 }}
              title="不选任何项表示不过滤（全量）"
            >
              {relationTypes.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>

            <button
              onClick={() => {
                setRelations([]);
                if (rootVid) loadSubgraph(rootVid);
              }}
              style={{ padding: "6px 10px" }}
            >
              清空筛选
            </button>
          </div>

          <button
            onClick={() => rootVid && loadSubgraph(rootVid)}
            disabled={!rootVid}
            style={{ marginLeft: "auto", padding: "8px 12px" }}
            title="按当前 hop / relations 重新拉取 root 子图"
          >
            重新加载子图
          </button>

          <div style={{ fontSize: 12, color: "#666" }}>
            {graphStats ? `nodes=${graphStats.node_count} edges=${graphStats.edge_count}` : ""}
          </div>
        </div>

        <div
          ref={containerRef}
          style={{
            width: "100%",
            height: "100%",
            minWidth: 0,
            overflow: "hidden",
            position: "relative",
          }}
        />
      </div>

      {/* Right: detail */}
      <div
        style={{
          padding: 12,
          borderLeft: "1px solid #eee",
          overflow: "auto",
          position: "relative",
          zIndex: 5,
          background: "#fff",
        }}
      >
        <h3 style={{ margin: 0 }}>详情</h3>
        <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>点击节点/边查看；节点支持 Expand（1-hop）</div>

        <hr style={{ margin: "12px 0" }} />

        {sel.kind === "none" ? (
          <div style={{ color: "#666", fontSize: 13 }}>未选择节点/边</div>
        ) : sel.kind === "node" ? (
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ fontWeight: 700 }}>{selectedNodeBrief?.label || `Node ${sel.vid}`}</div>
            <div style={{ fontSize: 12, color: "#666" }}>
              id={sel.vid} | type={selectedNodeBrief?.entity_type} | raw_id={selectedNodeBrief?.raw_id} | source={selectedNodeBrief?.source}
            </div>

            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <button
                onClick={() => reroot1hop(sel.vid)}
                disabled={loadingGraph}
                style={{ padding: "8px 12px" }}
                title="以当前选中的节点作为新的 Root，重新加载它的 1-hop 子图（会替换当前图）"
              >
                设为 Root 并展开（1-hop）
              </button>

              <button
                onClick={() => expand1hop(sel.vid)}
                disabled={loadingGraph}
                style={{ padding: "8px 12px" }}
                title="在当前图基础上追加该节点的 1-hop 邻居（合并，不替换）"
              >
                Expand（合并 1-hop）
              </button>
            </div>

            <div style={{ fontSize: 12, color: "#666" }}>{detailLoading ? "加载详情中…" : ""}</div>

            {selectedNodeBrief?.snippet ? (
              <div style={{ fontSize: 13, lineHeight: 1.4 }}>{selectedNodeBrief.snippet}</div>
            ) : null}

            {nodeDetail?.props ? (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>Properties</div>
                <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(nodeDetail.props, null, 2)}</pre>
              </div>
            ) : null}
          </div>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ fontWeight: 700 }}>Edge</div>
            <div style={{ fontSize: 12, color: "#666" }}>
              src={sel.src} → dst={sel.dst}
            </div>
            <div style={{ fontSize: 12, color: "#666" }}>
              relation={sel.relation} | source_db={sel.source_db || "-"}
            </div>

            <div style={{ fontSize: 12, color: "#666" }}>{detailLoading ? "加载详情中…" : ""}</div>

            {edgeDetail?.props ? (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>Properties</div>
                <pre style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{JSON.stringify(edgeDetail.props, null, 2)}</pre>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}