import { useState } from "react";

import { EXPAND_AUTO_REVEAL_TOPK, TOP_N_VISIBLE } from "../constants/kg";
import { EdgeDetailView } from "../features/detail/components/EdgeDetailView";
import { NodeDetailView } from "../features/detail/components/NodeDetailView";
import { EditWritebackPanel } from "./EditWritebackPanel";
import type {
  EdgeDetailResp,
  EdgePatchResp,
  ExpandProbeState,
  NodeBrief,
  NodeDetailResp,
  NodePatchResp,
  Sel,
} from "../types/kg";

type PanelGroup = {
  groupRoot: number;
  nodes: NodeBrief[];
  isRootGroup: boolean;
  title: string;
};

type RightDetailPanelProps = {
  allowGraphMutationActions?: boolean;
  discoveryMode?: boolean;
  renderNodeLabels: boolean;
  setRenderNodeLabels: (v: boolean) => void;
  renderEdgeLabels: boolean;
  setRenderEdgeLabels: (v: boolean) => void;
  edgeLabelPickerOpen: boolean;
  setEdgeLabelPickerOpen: (next: boolean | ((v: boolean) => boolean)) => void;
  edgeLabelKeyword: string;
  setEdgeLabelKeyword: (v: string) => void;
  edgeLabelSelectedDisplays: string[];
  setEdgeLabelSelectedDisplays: (next: string[] | ((prev: string[]) => string[])) => void;
  setEdgeLabelSelectionTouched: (v: boolean) => void;
  currentVisibleEdgeLabelDisplays: string[];
  edgeLabelFilteredDisplays: string[];
  edgeLabelSelectedSet: Set<string>;
  edgeLabelAllVisibleChecked: boolean;
  toggleEdgeLabelDisplay: (disp: string) => void;
  showSelfLoops: boolean;
  setShowSelfLoops: (v: boolean) => void;
  visibleSelfLoopCount: number;
  hiddenSelfLoopCount: number;
  hiddenNodesCollapsed: boolean;
  setHiddenNodesCollapsed: (next: boolean | ((v: boolean) => boolean)) => void;
  panelNodes: NodeBrief[];
  hiddenCount: number;
  visibleCount: number;
  graphNodeCount: number;
  panelGroups: PanelGroup[];
  panelGroupCollapsed: Record<string, boolean>;
  setPanelGroupCollapsed: (
    updater: Record<string, boolean> | ((prev: Record<string, boolean>) => Record<string, boolean>)
  ) => void;
  visibleNodeIdSet: Set<number>;
  autoVisibleTopIds: Set<number>;
  rootVid: number | null;
  revealNode: (vid: number, autoSelect?: boolean) => void;
  unrevealNode: (vid: number) => void;
  sel: Sel;
  selectedNodeBrief: NodeBrief | null;
  visibleNodeHopLevelMap: Map<number, number>;
  reroot1hop: (vid: number) => void;
  expand1hop: (vid: number) => void;
  collapseExpandFromNode: (fromVid: number) => void;
  expandButtonDisabled: boolean;
  expandButtonText: string;
  selectedNodeExpandClosable: boolean;
  selectedNodeIsVisible: boolean;
  selectedNodeIsRoot: boolean;
  selectedNodeIsAutoTop: boolean;
  selectedNodeProbeState: ExpandProbeState | undefined;
  loadingGraph: boolean;
  detailLoading: boolean;
  nodeDetail: NodeDetailResp | null;
  edgeDetail: EdgeDetailResp | null;
  relationDisplay: (raw?: string) => string;
  onReloadNodeDetail: (vid: number) => Promise<void>;
  onReloadEdgeDetail: (identity: { edge_type: string; src: number; dst: number; rank: string }) => Promise<void>;
  onSaveNodeEdit: (
    vid: number,
    setFields: Record<string, string>,
    expectedVersion: number,
    updatedBy: string
  ) => Promise<NodePatchResp>;
  onSaveEdgeEdit: (
    identity: { edge_type: string; src: number; dst: number; rank: string },
    setFields: Record<string, string>,
    expectedVersion: number,
    updatedBy: string
  ) => Promise<EdgePatchResp>;
  discoverySeedNodeIds?: Set<number>;
  discoveryExpandEntityOptions?: string[];
  discoveryExpandRelationOptions?: string[];
  discoveryExpandFilters?: {
    entityTypes: string[];
    relationTypes: string[];
  };
  discoveryExpandFilterHint?: string;
  onUpdateDiscoveryExpandFilters?: (
    patch: Partial<{
      entityTypes: string[];
      relationTypes: string[];
    }>
  ) => void;
  onExpandDiscoveryNode?: (vid: number) => void;
  onHideDiscoveryNode?: (vid: number) => void;
};

export function RightDetailPanel({
  allowGraphMutationActions = true,
  discoveryMode = false,
  renderNodeLabels,
  setRenderNodeLabels,
  renderEdgeLabels,
  setRenderEdgeLabels,
  edgeLabelPickerOpen,
  setEdgeLabelPickerOpen,
  edgeLabelKeyword,
  setEdgeLabelKeyword,
  edgeLabelSelectedDisplays,
  setEdgeLabelSelectedDisplays,
  setEdgeLabelSelectionTouched,
  currentVisibleEdgeLabelDisplays,
  edgeLabelFilteredDisplays,
  edgeLabelSelectedSet,
  edgeLabelAllVisibleChecked,
  toggleEdgeLabelDisplay,
  showSelfLoops,
  setShowSelfLoops,
  visibleSelfLoopCount,
  hiddenSelfLoopCount,
  hiddenNodesCollapsed,
  setHiddenNodesCollapsed,
  panelNodes,
  hiddenCount,
  visibleCount,
  graphNodeCount,
  panelGroups,
  panelGroupCollapsed,
  setPanelGroupCollapsed,
  visibleNodeIdSet,
  autoVisibleTopIds,
  rootVid,
  revealNode,
  unrevealNode,
  sel,
  selectedNodeBrief,
  visibleNodeHopLevelMap,
  reroot1hop,
  expand1hop,
  collapseExpandFromNode,
  expandButtonDisabled,
  expandButtonText,
  selectedNodeExpandClosable,
  selectedNodeIsVisible,
  selectedNodeIsRoot,
  selectedNodeIsAutoTop,
  selectedNodeProbeState,
  loadingGraph,
  detailLoading,
  nodeDetail,
  edgeDetail,
  relationDisplay,
  onReloadNodeDetail,
  onReloadEdgeDetail,
  onSaveNodeEdit,
  onSaveEdgeEdit,
  discoverySeedNodeIds,
  discoveryExpandEntityOptions,
  discoveryExpandRelationOptions,
  discoveryExpandFilters,
  discoveryExpandFilterHint,
  onUpdateDiscoveryExpandFilters,
  onExpandDiscoveryNode,
  onHideDiscoveryNode,
}: RightDetailPanelProps) {
  const [editorTab, setEditorTab] = useState<"detail" | "edit" | "direct">("detail");
  const selectedNodeIsSeed = sel.kind === "node" ? Boolean(discoverySeedNodeIds?.has(sel.vid)) : false;

  function toggleExpandFilter(list: string[], value: string) {
    const next = new Set(list);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    return Array.from(next).sort((a, b) => a.localeCompare(b));
  }

  return (
    <div
      style={{
        padding: 12,
        position: "relative",
        zIndex: 5,
        background: "#fff",
      }}
    >
      <h3 style={{ margin: 0 }}>详情</h3>
      <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
        {discoveryMode
          ? "点击节点查看详情；节点支持展开该节点，非 seed 节点支持取消渲染，本次 expand 过滤器仅作用于当前展开。"
          : allowGraphMutationActions
            ? "点击节点/边查看；节点支持 Expand（合并 1-hop）"
            : "点击节点/边查看详情；可继续编辑写回"}
      </div>

      <div
        style={{
          marginTop: 10,
          padding: "8px 10px",
          border: "1px solid #eee",
          borderRadius: 8,
          background: "#fafafa",
          display: "grid",
          gap: 8,
        }}
      >
        <div style={{ fontSize: 13, fontWeight: 600 }}>标签渲染控制（视图层）</div>

        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={renderNodeLabels} onChange={(e) => setRenderNodeLabels(e.target.checked)} />
          渲染节点标签
        </label>

        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={renderEdgeLabels} onChange={(e) => setRenderEdgeLabels(e.target.checked)} />
          渲染边标签（默认关闭）
        </label>

        <div style={{ fontSize: 12, color: "#666" }}>边标签渲染仅影响“文字显示”，不影响边本身是否绘制。</div>

        <div style={{ border: "1px solid #eee", borderRadius: 8, overflow: "hidden", background: "#fff" }}>
          <button
            onClick={() => setEdgeLabelPickerOpen((v) => !v)}
            style={{
              width: "100%",
              textAlign: "left",
              border: "none",
              background: "#fff",
              padding: "8px 10px",
              cursor: "pointer",
              fontSize: 12,
              fontWeight: 600,
            }}
            title="按当前图中存在的边标签（relationDisplay）选择要渲染的边标签"
          >
            {edgeLabelPickerOpen ? "▼" : "▶"} 边标签渲染选择（已选 {edgeLabelSelectedDisplays.length}/
            {currentVisibleEdgeLabelDisplays.length}）
          </button>

          {edgeLabelPickerOpen && (
            <div style={{ borderTop: "1px solid #eee", padding: 8, display: "grid", gap: 8 }}>
              <input
                value={edgeLabelKeyword}
                onChange={(e) => setEdgeLabelKeyword(e.target.value)}
                placeholder="搜索当前图中的边标签（按显示值匹配）"
                style={{ width: "100%", padding: 8, fontSize: 12 }}
              />

              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button
                  onClick={() => {
                    setEdgeLabelSelectionTouched(true);
                    setEdgeLabelSelectedDisplays([...currentVisibleEdgeLabelDisplays]);
                  }}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  全选
                </button>
                <button
                  onClick={() => {
                    setEdgeLabelSelectionTouched(true);
                    setEdgeLabelSelectedDisplays([]);
                  }}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  清空
                </button>
                <button
                  onClick={() => {
                    setEdgeLabelSelectionTouched(true);
                    if (edgeLabelFilteredDisplays.length === 0) return;
                    setEdgeLabelSelectedDisplays((prev) => {
                      const s = new Set(prev);
                      if (edgeLabelAllVisibleChecked) edgeLabelFilteredDisplays.forEach((x) => s.delete(x));
                      else edgeLabelFilteredDisplays.forEach((x) => s.add(x));
                      return Array.from(s).sort((a, b) => a.localeCompare(b));
                    });
                  }}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  {edgeLabelAllVisibleChecked ? "取消当前列表" : "勾选当前列表"}
                </button>
              </div>

              <div style={{ fontSize: 12, color: "#666" }}>
                当前图中边标签（显示值）共 {currentVisibleEdgeLabelDisplays.length} 项
                {edgeLabelKeyword.trim() ? `，筛选后 ${edgeLabelFilteredDisplays.length} 项` : ""}
              </div>

              <div
                style={{
                  border: "1px solid #eee",
                  borderRadius: 6,
                  maxHeight: 220,
                  overflow: "auto",
                  padding: 6,
                  display: "grid",
                  gap: 4,
                  background: "#fafafa",
                }}
              >
                {edgeLabelFilteredDisplays.length === 0 ? (
                  <div style={{ fontSize: 12, color: "#666", padding: 6 }}>当前图中没有匹配的边标签</div>
                ) : (
                  edgeLabelFilteredDisplays.map((disp) => (
                    <label
                      key={disp}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "4px 6px",
                        fontSize: 12,
                        cursor: "pointer",
                        borderRadius: 4,
                        background: edgeLabelSelectedSet.has(disp) ? "#fffbe6" : "transparent",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={edgeLabelSelectedSet.has(disp)}
                        onChange={() => toggleEdgeLabelDisplay(disp)}
                      />
                      <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{disp}</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      <div
        style={{
          marginTop: 10,
          padding: "8px 10px",
          border: "1px solid #eee",
          borderRadius: 8,
          background: "#fafafa",
          display: "grid",
          gap: 6,
        }}
      >
        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={showSelfLoops} onChange={(e) => setShowSelfLoops(e.target.checked)} />
          显示自环边（默认关闭）
        </label>
        <div style={{ fontSize: 12, color: "#666" }}>
          {showSelfLoops ? `当前已显示自环边 ${visibleSelfLoopCount} 条` : `当前已隐藏自环边 ${hiddenSelfLoopCount} 条`}
        </div>
      </div>

      {!discoveryMode ? (
      <div style={{ marginTop: 12, border: "1px solid #eee", borderRadius: 8 }}>
        <button
          onClick={() => setHiddenNodesCollapsed((v) => !v)}
          style={{
            width: "100%",
            textAlign: "left",
            padding: "10px 12px",
            border: "none",
            background: "#fafafa",
            cursor: "pointer",
            borderRadius: 8,
            fontWeight: 600,
          }}
        >
          {hiddenNodesCollapsed ? "▶" : "▼"} 未渲染节点（低优先级）
          <span style={{ color: "#666", fontWeight: 400 }}>
            {" "}
            列表 {panelNodes.length} 个｜当前未渲染 {hiddenCount} 个｜当前显示 {visibleCount}/{graphNodeCount}
            ｜TopN={TOP_N_VISIBLE}
          </span>
        </button>

        {!hiddenNodesCollapsed && (
          <div style={{ borderTop: "1px solid #eee", padding: 8, display: "grid", gap: 8, maxHeight: 360, overflow: "auto" }}>
            {panelGroups.length === 0 ? (
              <div style={{ fontSize: 12, color: "#666", padding: 4 }}>当前没有可管理节点</div>
            ) : (
              panelGroups.map((g) => {
                const key = String(g.groupRoot);
                const collapsed = panelGroupCollapsed[key] ?? true;
                return (
                  <div key={key} style={{ border: "1px solid #f0f0f0", borderRadius: 8, overflow: "hidden" }}>
                    <button
                      onClick={() =>
                        setPanelGroupCollapsed((prev) => ({
                          ...prev,
                          [key]: !(prev[key] ?? true),
                        }))
                      }
                      style={{
                        width: "100%",
                        textAlign: "left",
                        border: "none",
                        background: g.isRootGroup ? "#fff7e6" : "#fafafa",
                        padding: "8px 10px",
                        cursor: "pointer",
                        fontSize: 12,
                        fontWeight: 600,
                      }}
                      title={`groupRoot=${g.groupRoot}`}
                    >
                      {collapsed ? "▶" : "▼"} {g.title}（{g.nodes.length}）
                    </button>

                    {!collapsed && (
                      <div style={{ padding: 8, display: "grid", gap: 8, maxHeight: 220, overflow: "auto" }}>
                        {g.nodes.map((n, idx) => {
                          const currentlyVisible = visibleNodeIdSet.has(n.id);
                          const autoTop = autoVisibleTopIds.has(n.id);
                          const isRoot = rootVid != null && n.id === rootVid;

                          return (
                            <div key={n.id} style={{ border: "1px solid #f0f0f0", borderRadius: 6, padding: 8, background: "#fff" }}>
                              <div style={{ fontWeight: 600, fontSize: 13 }}>
                                #{idx + 1} {n.label}
                              </div>
                              <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                                id={n.id} | {n.entity_type} | 状态={currentlyVisible ? "已渲染" : "未渲染"}
                              </div>
                              <div style={{ marginTop: 4, fontSize: 12, color: autoTop ? "#d46b08" : "#666" }}>
                                {autoTop ? "来源：TopN默认显示（当前被手动隐藏）" : "来源：低优先级"}
                              </div>

                              <div style={{ marginTop: 8, display: "flex", gap: 8, flexWrap: "wrap" }}>
                                <button
                                  onClick={() => revealNode(n.id, true)}
                                  disabled={currentlyVisible}
                                  style={{ padding: "6px 8px", fontSize: 12 }}
                                  title={currentlyVisible ? "该节点当前已渲染" : "恢复渲染到图谱并高亮"}
                                >
                                  恢复渲染
                                </button>
                                <button
                                  onClick={() => unrevealNode(n.id)}
                                  disabled={!currentlyVisible || isRoot}
                                  style={{ padding: "6px 8px", fontSize: 12 }}
                                  title={
                                    isRoot ? "Root 节点不允许隐藏" : !currentlyVisible ? "该节点当前未渲染" : "取消渲染并恢复到初始未渲染状态"
                                  }
                                >
                                  取消渲染
                                </button>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
      ) : null}

      <hr style={{ margin: "12px 0" }} />
      <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
        <button data-testid="detail-panel-tab-detail" onClick={() => setEditorTab("detail")} style={{ padding: "6px 10px", fontSize: 12 }}>
          详情
        </button>
        <button data-testid="detail-panel-tab-edit" onClick={() => setEditorTab("edit")} style={{ padding: "6px 10px", fontSize: 12 }}>
          编辑
        </button>
        <button data-testid="detail-panel-tab-direct" onClick={() => setEditorTab("direct")} style={{ padding: "6px 10px", fontSize: 12 }}>
          直接编辑
        </button>
      </div>

      {editorTab === "detail" ? (
        sel.kind === "none" ? (
          <div style={{ color: "#666", fontSize: 13 }}>未选择节点/边</div>
        ) : sel.kind === "node" ? (
          <div style={{ display: "grid", gap: 10 }}>
            {discoveryMode ? (
              <>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    data-testid="discovery-expand-button"
                    onClick={() => onExpandDiscoveryNode?.(sel.vid)}
                    disabled={expandButtonDisabled}
                    style={{ padding: "8px 12px" }}
                  >
                    {expandButtonText}
                  </button>

                  {!selectedNodeIsSeed ? (
                    <button
                      data-testid="discovery-hide-button"
                      onClick={() => onHideDiscoveryNode?.(sel.vid)}
                      disabled={!selectedNodeIsVisible}
                      style={{ padding: "8px 12px" }}
                    >
                      取消渲染
                    </button>
                  ) : null}
                </div>

                <div style={{ fontSize: 12, color: "#666" }}>
                  {selectedNodeIsSeed
                    ? "当前节点是 seed，不能执行普通取消渲染；请从左侧 seed 列表删除后触发全局 discovery 重跑。"
                    : "当前节点是普通节点，可取消渲染并在左侧 Hidden by User 中恢复。"}
                  {expandButtonText === "无更多相关节点" ? " ｜该节点当前过滤条件下无更多相关节点。" : ""}
                  {discoveryExpandFilterHint ? ` ｜${discoveryExpandFilterHint}` : ""}
                </div>

                <div style={{ display: "grid", gap: 10, border: "1px solid #f0f0f0", borderRadius: 8, background: "#fff", padding: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>本次 Expand 过滤器</div>

                  <div style={{ display: "grid", gap: 6 }}>
                    <div style={{ fontSize: 12, color: "#666" }}>Expand Entity Types</div>
                    <div style={{ display: "grid", gap: 6, maxHeight: 120, overflow: "auto" }}>
                      {(discoveryExpandEntityOptions || []).map((item) => (
                        <label key={item} style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                          <input
                            type="checkbox"
                            checked={Boolean(discoveryExpandFilters?.entityTypes.includes(item))}
                            onChange={() =>
                              onUpdateDiscoveryExpandFilters?.({
                                entityTypes: toggleExpandFilter(discoveryExpandFilters?.entityTypes || [], item),
                              })
                            }
                          />
                          {item}
                        </label>
                      ))}
                    </div>
                  </div>

                  <div style={{ display: "grid", gap: 6 }}>
                    <div style={{ fontSize: 12, color: "#666" }}>Expand Relation Types</div>
                    <div style={{ display: "grid", gap: 6, maxHeight: 120, overflow: "auto" }}>
                      {(discoveryExpandRelationOptions || []).map((item) => (
                        <label key={item} style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 12 }}>
                          <input
                            type="checkbox"
                            checked={Boolean(discoveryExpandFilters?.relationTypes.includes(item))}
                            onChange={() =>
                              onUpdateDiscoveryExpandFilters?.({
                                relationTypes: toggleExpandFilter(discoveryExpandFilters?.relationTypes || [], item),
                              })
                            }
                          />
                          {relationDisplay(item) || item}
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            ) : allowGraphMutationActions ? (
              <>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    onClick={() => reroot1hop(sel.vid)}
                    disabled={loadingGraph}
                    style={{ padding: "8px 12px" }}
                    title="以当前节点作为新 Root，重新加载 1-hop 子图（替换当前图）"
                  >
                    设为 Root 并展开（1-hop）
                  </button>

                  <button
                    onClick={() => expand1hop(sel.vid)}
                    disabled={expandButtonDisabled}
                    style={{ padding: "8px 12px" }}
                    title={
                      selectedNodeProbeState === "noextra"
                        ? "该节点在当前图上下文中没有可新增的 1-hop 邻居（无多余相关节点）"
                        : selectedNodeProbeState === "loading"
                          ? "正在检测该节点是否有可新增的 1-hop 邻居…"
                          : `追加该节点 1-hop 邻居到当前图；新增节点前 ${EXPAND_AUTO_REVEAL_TOPK} 个自动显示`
                    }
                  >
                    {expandButtonText}
                  </button>

                  <button
                    onClick={() => collapseExpandFromNode(sel.vid)}
                    disabled={!selectedNodeExpandClosable || loadingGraph}
                    style={{ padding: "8px 12px" }}
                    title={
                      selectedNodeExpandClosable
                        ? "关闭以该节点为来源的 Expand 展开（撤销该批节点渲染）"
                        : "该节点尚未执行 Expand 或已关闭"
                    }
                  >
                    关闭Expand
                  </button>

                  <button
                    onClick={() => unrevealNode(sel.vid)}
                    disabled={!selectedNodeIsVisible || selectedNodeIsRoot}
                    style={{ padding: "8px 12px" }}
                    title={selectedNodeIsRoot ? "Root 节点不允许隐藏" : "将该节点从图谱中隐藏（可撤销）"}
                  >
                    隐藏节点（可撤销）
                  </button>
                </div>

                <div style={{ fontSize: 12, color: "#666" }}>
                  {selectedNodeIsRoot
                    ? "当前节点是 Root（不可隐藏）"
                    : selectedNodeIsAutoTop
                      ? "当前节点属于 TopN 默认显示（可隐藏并在右侧列表恢复）"
                      : "当前节点为低优先级节点（可在右侧列表恢复/取消渲染）"}
                  {selectedNodeExpandClosable ? " ｜该节点存在可关闭的 Expand 展开内容" : ""}
                  {selectedNodeProbeState === "noextra" ? " ｜Expand：无多余相关节点" : ""}
                </div>
              </>
            ) : (
              <div style={{ fontSize: 12, color: "#666" }}>统一关系发现结果视图下禁用 Root/Expand/隐藏节点等 drill-down 子图操作。</div>
            )}

            <NodeDetailView
              detail={nodeDetail}
              selectedNodeBrief={selectedNodeBrief}
              hopLevel={visibleNodeHopLevelMap.get(sel.vid) ?? null}
              detailLoading={detailLoading}
            />
          </div>
        ) : (
          <EdgeDetailView
            detail={edgeDetail}
            selection={sel}
            detailLoading={detailLoading}
          />
        )
      ) : (
        <EditWritebackPanel
          mode={editorTab === "edit" ? "edit" : "direct"}
          sel={sel}
          nodeDetail={nodeDetail}
          edgeDetail={edgeDetail}
          detailLoading={detailLoading}
          onReloadNodeDetail={onReloadNodeDetail}
          onReloadEdgeDetail={onReloadEdgeDetail}
          onSaveNodeEdit={onSaveNodeEdit}
          onSaveEdgeEdit={onSaveEdgeEdit}
        />
      )}
    </div>
  );
}
