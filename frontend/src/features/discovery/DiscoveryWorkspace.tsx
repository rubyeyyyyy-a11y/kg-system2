import type { ComponentProps } from "react";

import { DiscoveryPanel } from "../../components/DiscoveryPanel";

type DiscoveryResultExplain = {
  message: string;
  requestSpace: string;
  responseSpace: string;
  nodeCount: number;
  edgeCount: number;
  candidateCount: number;
};

type DiscoveryWorkspaceTopBarProps = {
  discoveryViewMode: "result" | "drilldown";
  currentSpace: string;
  currentSpaceStatus: string;
  currentSpaceIndexStatus: { status: string; doc_count?: number | null } | null;
  discoveryWorkspaceReady: boolean;
  drilldownRootVid: number | null;
  drilldownRootLabel: string;
  drilldownNodeCount: number;
  drilldownEdgeCount: number;
  canReturnToDiscoveryResult: boolean;
  discoveryRequestSpace: string;
  discoveryResponseSpace: string;
  responseGraphStatus: string;
  discoveryNodeCount: number;
  discoveryEdgeCount: number;
  discoveryCandidateCount: number;
  lastRunSeedCount: number;
  currentSeedCount: number;
  graphBusy: boolean;
  discoveryHasPendingChanges: boolean;
  spaceSwitchBlocked: boolean;
  spaceSwitchPhaseLabel: string;
  switchTargetSpace: string;
  effectiveGraphStats: Record<string, unknown> | null;
  discoveryResultExplain: DiscoveryResultExplain | null;
  onRelayout: () => void;
  onFitView: () => void;
  onReturnToDiscoveryResult: () => void;
};

export type DiscoveryWorkspaceSidebarProps = ComponentProps<typeof DiscoveryPanel>;

export function DiscoveryWorkspaceSidebar(props: DiscoveryWorkspaceSidebarProps) {
  return <DiscoveryPanel {...props} />;
}

export function DiscoveryWorkspaceTopBar({
  discoveryViewMode,
  currentSpace,
  currentSpaceStatus,
  currentSpaceIndexStatus,
  discoveryWorkspaceReady,
  drilldownRootVid,
  drilldownRootLabel,
  drilldownNodeCount,
  drilldownEdgeCount,
  canReturnToDiscoveryResult,
  discoveryRequestSpace,
  discoveryResponseSpace,
  responseGraphStatus,
  discoveryNodeCount,
  discoveryEdgeCount,
  discoveryCandidateCount,
  lastRunSeedCount,
  currentSeedCount,
  graphBusy,
  discoveryHasPendingChanges,
  spaceSwitchBlocked,
  spaceSwitchPhaseLabel,
  switchTargetSpace,
  effectiveGraphStats,
  discoveryResultExplain,
  onRelayout,
  onFitView,
  onReturnToDiscoveryResult,
}: DiscoveryWorkspaceTopBarProps) {
  const inDrilldown = discoveryViewMode === "drilldown";
  const activeNodeCount = inDrilldown ? drilldownNodeCount : discoveryNodeCount;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 10px", flexWrap: "wrap" }}>
      <div style={{ fontSize: 13, fontWeight: 600 }}>统一关系发现</div>
      <div style={{ fontSize: 12, color: "#666" }}>space={currentSpace || "-"}</div>
      <div style={{ fontSize: 12, color: "#666" }}>readiness={currentSpaceStatus || "-"}</div>
      {currentSpaceIndexStatus ? (
        <div style={{ fontSize: 12, color: "#666" }}>
          index_status={currentSpaceIndexStatus.status} | canonical_docs={currentSpaceIndexStatus.doc_count}
        </div>
      ) : null}
      {inDrilldown ? (
        <div
          data-testid="discovery-drilldown-contract"
          data-root-vid={drilldownRootVid != null ? String(drilldownRootVid) : ""}
          data-node-count={String(drilldownNodeCount)}
          data-edge-count={String(drilldownEdgeCount)}
          style={{ fontSize: 12, color: "#666" }}
        >
          formal_drilldown=root
          {drilldownRootVid != null ? `:${drilldownRootVid}` : ""}
          {drilldownRootLabel ? ` (${drilldownRootLabel})` : ""}
          {" | "}nodes={drilldownNodeCount} edges={drilldownEdgeCount}
        </div>
      ) : discoveryWorkspaceReady ? (
        <div
          data-testid="discovery-result-contract"
          data-request-space={discoveryRequestSpace}
          data-response-space={discoveryResponseSpace}
          data-node-count={String(discoveryNodeCount)}
          data-edge-count={String(discoveryEdgeCount)}
          data-candidate-count={String(discoveryCandidateCount)}
          style={{ fontSize: 12, color: "#666" }}
        >
          last_run_seeds={lastRunSeedCount} current_seeds={currentSeedCount}
          {" | "}candidates={discoveryCandidateCount}
          {" | "}nodes={discoveryNodeCount} edges={discoveryEdgeCount}
          {discoveryRequestSpace ? ` | request_space=${discoveryRequestSpace}` : ""}
          {discoveryResponseSpace ? ` | response_space=${discoveryResponseSpace}` : ""}
          {responseGraphStatus ? ` | response_graph_status=${responseGraphStatus}` : ""}
          {graphBusy ? " | 加载中…" : ""}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: "#666" }}>
          添加 1 个或多个 seed 节点后运行 discovery，结果会以主题关系图形式渲染在这里。
        </div>
      )}
      {discoveryHasPendingChanges ? (
        <div style={{ width: "100%", fontSize: 12, color: "#ad6800" }}>
          当前 seeds 或 discovery 参数与上次运行结果不一致，请重新生成以同步图谱结果。
        </div>
      ) : null}
      {inDrilldown ? (
        <div style={{ width: "100%", fontSize: 12, color: "#666" }}>
          当前处于统一关系发现下的正式 drill-down 视图；不会隐式跳转到 legacy。
        </div>
      ) : null}
      {spaceSwitchBlocked ? (
        <div
          data-testid="space-switch-state"
          data-switching="true"
          data-switch-phase={spaceSwitchPhaseLabel}
          data-space-name={currentSpace || switchTargetSpace || ""}
          style={{ width: "100%", fontSize: 12, color: "#ad6800" }}
        >
          current space switching: {spaceSwitchPhaseLabel}
        </div>
      ) : null}
      {effectiveGraphStats?.truncated ? (
        <div style={{ width: "100%", fontSize: 12, color: "#ad6800" }}>
          图结果已裁剪：dropped_nodes={Number(effectiveGraphStats?.dropped_nodes || 0)} dropped_edges=
          {Number(effectiveGraphStats?.dropped_edges || 0)} dropped_neighbors=
          {Number(effectiveGraphStats?.dropped_neighbors || 0)} dropped_by_budget=
          {Number(effectiveGraphStats?.dropped_by_budget || 0)} dropped_by_type_budget=
          {Number(effectiveGraphStats?.dropped_by_type_budget || 0)} dropped_generic_hubs=
          {Number(effectiveGraphStats?.dropped_generic_hubs || 0)}
        </div>
      ) : null}
      {discoveryWorkspaceReady && discoveryResultExplain ? (
        <div
          data-testid="discovery-empty-result-notice"
          data-request-space={discoveryResultExplain.requestSpace}
          data-response-space={discoveryResultExplain.responseSpace}
          data-node-count={String(discoveryResultExplain.nodeCount)}
          data-edge-count={String(discoveryResultExplain.edgeCount)}
          data-candidate-count={String(discoveryResultExplain.candidateCount)}
          style={{
            width: "100%",
            fontSize: 12,
            color: "#003a8c",
            background: "#e6f4ff",
            border: "1px solid #91caff",
            borderRadius: 8,
            padding: "8px 10px",
          }}
        >
          {discoveryResultExplain.message}
        </div>
      ) : null}
      <div style={{ marginLeft: "auto", display: "flex", gap: 8, flexWrap: "wrap" }}>
        {inDrilldown ? (
          <button
            data-testid="discovery-return-to-result"
            onClick={onReturnToDiscoveryResult}
            disabled={!canReturnToDiscoveryResult || graphBusy}
            style={{ padding: "7px 10px", fontSize: 12 }}
          >
            返回 Discovery 结果
          </button>
        ) : null}
        <button
          onClick={onRelayout}
          disabled={graphBusy || activeNodeCount <= 0}
          style={{ padding: "7px 10px", fontSize: 12 }}
        >
          整理布局
        </button>
        <button
          onClick={onFitView}
          disabled={activeNodeCount <= 0}
          style={{ padding: "7px 10px", fontSize: 12 }}
        >
          适配视图
        </button>
      </div>
    </div>
  );
}
