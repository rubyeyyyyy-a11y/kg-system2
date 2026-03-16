import { useEffect, useMemo, useRef } from "react";
import type { KeyboardEvent } from "react";

import type {
  DiscoveryCandidatePreviewState,
  DiscoveryCandidateResultState,
} from "../hooks/useDiscoveryCandidateResults";
import { EntityCandidateCard } from "./EntityCandidateCard";
import type {
  DiscoveryEntityCandidateItem,
  DiscoveryEntityCandidateQueryState,
  EntityTypeItem,
  GraphDiscoveryEntityFacetItem,
  GraphDiscoveryLayerFacetItem,
  GraphDiscoveryQuerySummary,
  GraphDiscoveryRelationFacetItem,
  GraphDiscoverySeedFacetItem,
  NodeBrief,
  SuggestItem,
} from "../types/kg";
import type { SpaceSummary } from "../features/space/types/space";
import { relationDisplay } from "../utils/kg";

type DiscoveryQueryState = {
  allowedEntityTypes: string[];
  allowedRelationTypes: string[];
  maxNodes: number;
  maxEdges: number;
  topKPerType: number;
  includeCandidateCandidateEdges: boolean;
  includeSeedSeedEdges: boolean;
  hop: number;
};

type DiscoveryRuntimeState = {
  entityTypes: string[];
  relationTypes: string[];
};

type DiscoveryRenderCoverageState = {
  workingNodeCount: number;
  workingEdgeCount: number;
  entityTypes: Array<{
    key: string;
    count: number;
  }>;
  relationTypes: Array<{
    key: string;
    count: number;
  }>;
  selectedEntityTypes: string[];
  selectedRelationTypes: string[];
};

type DiscoveryPanelProps = {
  currentSpace: string;
  selectedSpace: SpaceSummary | null;
  spaces: SpaceSummary[];
  spaceLoading: boolean;
  spaceError: string | null;
  currentSpaceStatus: string;
  currentSpaceGraphStatus: SpaceSummary["graph_status"];
  currentSpaceSearchStatus: SpaceSummary["search_status"];
  currentSpaceCoveragePct: number | null;
  currentSpaceIndexStatus: SpaceSummary["index_status"];
  spaceSwitching: boolean;
  spaceSwitchPhase: string;
  onSelectSpace: (spaceName: string) => void;
  seeds: SuggestItem[];
  searchQuery: DiscoveryEntityCandidateQueryState;
  searchAdvancedOpen: boolean;
  preview: DiscoveryCandidatePreviewState;
  candidateResult: DiscoveryCandidateResultState;
  selectedCandidateIds: Set<number>;
  seedIdSet: Set<number>;
  query: DiscoveryQueryState;
  runtime: DiscoveryRuntimeState;
  renderCoverage: DiscoveryRenderCoverageState;
  entityTypeOptions: EntityTypeItem[];
  resultFacets: {
    entityTypes: GraphDiscoveryEntityFacetItem[];
    relationTypes: GraphDiscoveryRelationFacetItem[];
    querySummary: GraphDiscoveryQuerySummary;
    layers: GraphDiscoveryLayerFacetItem[];
    seeds: GraphDiscoverySeedFacetItem[];
  } | null;
  resultStats: {
    ranking_mode?: "v1" | "layered_multiseed";
    seed_count: number;
    seeds_count?: number;
    candidate_count: number;
    node_count: number;
    edge_count: number;
    final_nodes?: number;
    final_edges?: number;
    truncated: boolean;
    core_count?: number;
    shared_count?: number;
    local_count?: number;
    supplement_count?: number;
    dropped_nodes?: number;
    dropped_edges?: number;
    dropped_neighbors?: number;
    dropped_by_budget?: number;
    dropped_by_type_budget?: number;
    dropped_generic_hubs?: number;
  } | null;
  loading: boolean;
  hasPendingChanges: boolean;
  renderedNodes: NodeBrief[];
  hiddenNodes: NodeBrief[];
  droppedNodes: {
    droppedByBudget: Array<{
      node: NodeBrief;
      supportEdgesCount: number;
      sourceNodeId: number | null;
    }>;
    droppedByTypeFilter: Array<{
      node: NodeBrief;
      supportEdgesCount: number;
      sourceNodeId: number | null;
    }>;
    droppedByRelationFilter: Array<{
      node: NodeBrief;
      supportEdgesCount: number;
      sourceNodeId: number | null;
    }>;
  };
  renderedPanelCollapsed: boolean;
  droppedPanelCollapsed: boolean;
  onRemoveSeed: (vid: number) => void;
  onClearSeeds: () => void;
  onUpdateSearchQuery: (patch: Partial<DiscoveryEntityCandidateQueryState>) => void;
  onToggleSearchAdvanced: () => void;
  onSubmitSearch: () => void;
  onClosePreview: () => void;
  onSetPreviewHighlightIndex: (index: number) => void;
  onSelectPreviewItem: (item: DiscoveryEntityCandidateItem) => void;
  onLoadMoreCandidates: () => void;
  onToggleCandidateSelect: (id: number) => void;
  onClearCandidateSelection: () => void;
  onAddSelectedCandidates: () => void;
  onAddCandidateSeed: (item: DiscoveryEntityCandidateItem) => void;
  onViewCandidateDetail: (item: DiscoveryEntityCandidateItem) => void;
  onLoadCandidateSubgraph: (item: DiscoveryEntityCandidateItem) => void;
  onUpdateQuery: (patch: Partial<DiscoveryQueryState>) => void;
  onUpdateRuntime: (patch: Partial<DiscoveryRuntimeState>) => void;
  onUpdateRenderCoverage: (patch: Partial<Pick<DiscoveryRenderCoverageState, "selectedEntityTypes" | "selectedRelationTypes">>) => void;
  onSetRenderedPanelCollapsed: (next: boolean) => void;
  onSetDroppedPanelCollapsed: (next: boolean) => void;
  onLocateNode: (vid: number) => void;
  onHideRenderedNode: (vid: number) => void;
  onRestoreHiddenNode: (vid: number, locate?: boolean) => void;
  onForceRenderDroppedNode: (vid: number, locate?: boolean) => void;
  onViewNodeDetailById: (vid: number) => void;
  onRun: () => void;
};

function candidateStatusMessage(
  candidateResult: DiscoveryCandidateResultState,
  hasQuery: boolean
) {
  const searchStatus = candidateResult.space_meta?.search_status || "unavailable";
  if (searchStatus === "failed") return "当前 space 的 canonical 搜索索引校验失败，请先修复 index_status。";
  if (searchStatus === "unavailable") return "当前 space 的 canonical 搜索索引尚未就绪，当前候选列表不能视为完整结果。";
  if (searchStatus === "partial") return "当前 space 只有 partial canonical index，本次无候选不代表图中无实体。";
  if (searchStatus === "empty") return "当前 space 当前没有可搜索实体。";
  if (hasQuery) return "当前 space 下没有匹配候选。";
  return "请输入关键词并提交搜索。";
}

function CheckboxList({
  items,
  checked,
  renderLabel,
  onToggle,
  onSelectAll,
  onClear,
  emptyText,
}: {
  items: string[];
  checked: Set<string>;
  renderLabel: (key: string) => string;
  onToggle: (key: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
  emptyText: string;
}) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button onClick={onSelectAll} style={{ padding: "6px 8px", fontSize: 12 }}>
          全选
        </button>
        <button onClick={onClear} style={{ padding: "6px 8px", fontSize: 12 }}>
          清空
        </button>
      </div>
      <div
        style={{
          maxHeight: 180,
          overflow: "auto",
          border: "1px solid #eee",
          borderRadius: 8,
          background: "#fff",
          padding: 8,
          display: "grid",
          gap: 6,
        }}
      >
        {items.length === 0 ? (
          <div style={{ fontSize: 12, color: "#666" }}>{emptyText}</div>
        ) : (
          items.map((key) => (
            <label key={key} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, cursor: "pointer" }}>
              <input type="checkbox" checked={checked.has(key)} onChange={() => onToggle(key)} />
              <span>{renderLabel(key)}</span>
            </label>
          ))
        )}
      </div>
    </div>
  );
}

function ManagedNodeList({
  title,
  items,
  emptyText,
  primaryActionLabel,
  onPrimaryAction,
  onLocate,
  onViewDetail,
  locateDisabled,
  isPrimaryDisabled,
}: {
  title: string;
  items: Array<{
    node: NodeBrief;
    meta?: string;
  }>;
  emptyText: string;
  primaryActionLabel: string | ((node: NodeBrief) => string);
  onPrimaryAction: (vid: number) => void;
  onLocate?: (vid: number) => void;
  onViewDetail: (vid: number) => void;
  locateDisabled?: boolean;
  isPrimaryDisabled?: (node: NodeBrief) => boolean;
}) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ fontSize: 12, fontWeight: 600 }}>{title}</div>
      {items.length === 0 ? (
        <div style={{ fontSize: 12, color: "#666" }}>{emptyText}</div>
      ) : (
        items.map(({ node, meta }) => (
          <div
            key={node.id}
            style={{
              border: "1px solid #f0f0f0",
              borderRadius: 8,
              background: "#fff",
              padding: 8,
              display: "grid",
              gap: 6,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600 }}>{node.label || `node ${node.id}`}</div>
            <div style={{ fontSize: 12, color: "#666" }}>
              vid={node.id}
              {node.entity_type ? ` | ${node.entity_type}` : ""}
              {meta ? ` | ${meta}` : ""}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button
                  data-testid={`managed-node-primary-${node.id}`}
                  onClick={() => onPrimaryAction(node.id)}
                  disabled={Boolean(isPrimaryDisabled?.(node))}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  {typeof primaryActionLabel === "function" ? primaryActionLabel(node) : primaryActionLabel}
                </button>
              {onLocate ? (
                <button
                  data-testid={`managed-node-locate-${node.id}`}
                  onClick={() => onLocate(node.id)}
                  disabled={locateDisabled}
                  style={{ padding: "6px 8px", fontSize: 12 }}
                >
                  定位到图中
                </button>
              ) : null}
              <button
                data-testid={`managed-node-view-detail-${node.id}`}
                onClick={() => onViewDetail(node.id)}
                style={{ padding: "6px 8px", fontSize: 12 }}
              >
                查看详情
              </button>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export function DiscoveryPanel({
  currentSpace,
  selectedSpace,
  spaces,
  spaceLoading,
  spaceError,
  currentSpaceStatus,
  currentSpaceGraphStatus,
  currentSpaceSearchStatus,
  currentSpaceCoveragePct,
  currentSpaceIndexStatus,
  spaceSwitching,
  spaceSwitchPhase,
  onSelectSpace,
  seeds,
  searchQuery,
  searchAdvancedOpen,
  preview,
  candidateResult,
  selectedCandidateIds,
  seedIdSet,
  query,
  runtime,
  renderCoverage,
  entityTypeOptions,
  resultFacets,
  resultStats,
  loading,
  hasPendingChanges,
  renderedNodes,
  hiddenNodes,
  droppedNodes,
  renderedPanelCollapsed,
  droppedPanelCollapsed,
  onRemoveSeed,
  onClearSeeds,
  onUpdateSearchQuery,
  onToggleSearchAdvanced,
  onSubmitSearch,
  onClosePreview,
  onSetPreviewHighlightIndex,
  onSelectPreviewItem,
  onLoadMoreCandidates,
  onToggleCandidateSelect,
  onClearCandidateSelection,
  onAddSelectedCandidates,
  onAddCandidateSeed,
  onViewCandidateDetail,
  onLoadCandidateSubgraph,
  onUpdateQuery,
  onUpdateRuntime,
  onUpdateRenderCoverage,
  onSetRenderedPanelCollapsed,
  onSetDroppedPanelCollapsed,
  onLocateNode,
  onHideRenderedNode,
  onRestoreHiddenNode,
  onForceRenderDroppedNode,
  onViewNodeDetailById,
  onRun,
}: DiscoveryPanelProps) {
  const searchWrapRef = useRef<HTMLDivElement>(null);

  const runtimeEntityTypeSet = useMemo(() => new Set(runtime.entityTypes), [runtime.entityTypes]);
  const runtimeRelationTypeSet = useMemo(() => new Set(runtime.relationTypes), [runtime.relationTypes]);
  const coverageEntityTypeSet = useMemo(() => new Set(renderCoverage.selectedEntityTypes), [renderCoverage.selectedEntityTypes]);
  const coverageRelationTypeSet = useMemo(() => new Set(renderCoverage.selectedRelationTypes), [renderCoverage.selectedRelationTypes]);

  useEffect(() => {
    if (!preview.open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      const el = searchWrapRef.current;
      if (el && !el.contains(e.target as Node)) onClosePreview();
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
    };
  }, [onClosePreview, preview.open]);

  function toggleArrayValue(list: string[], value: string) {
    const key = String(value || "").trim();
    if (!key) return list;
    const next = new Set(list);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return Array.from(next).sort((a, b) => a.localeCompare(b));
  }

  function handleSearchKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      if (!preview.open || preview.items.length === 0) return;
      e.preventDefault();
      const nextIndex = preview.highlightIndex < 0 ? 0 : (preview.highlightIndex + 1) % preview.items.length;
      onSetPreviewHighlightIndex(nextIndex);
      return;
    }

    if (e.key === "ArrowUp") {
      if (!preview.open || preview.items.length === 0) return;
      e.preventDefault();
      const nextIndex =
        preview.highlightIndex < 0
          ? preview.items.length - 1
          : preview.highlightIndex <= 0
            ? preview.items.length - 1
            : preview.highlightIndex - 1;
      onSetPreviewHighlightIndex(nextIndex);
      return;
    }

    if (e.key === "Escape" && preview.open) {
      e.preventDefault();
      onClosePreview();
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      onSubmitSearch();
    }
  }

  const summary = resultFacets?.querySummary || null;
  const layerItems = resultFacets?.layers || [];
  const seedSummaryItems = resultFacets?.seeds || [];
  const layerCountMap = useMemo(() => {
    const next = new Map<string, GraphDiscoveryLayerFacetItem>();
    for (const item of layerItems) next.set(item.layer, item);
    return next;
  }, [layerItems]);
  const selectedSeedItems = summary?.selected_seeds?.length
    ? summary.selected_seeds
    : seeds.map((seed) => ({
        id: seed.vid,
        label: seed.label,
        entity_type: seed.entity_type || "",
      }));
  const availableEntityFacetKeys = (resultFacets?.entityTypes || []).map((item) => item.entity_type);
  const availableRelationFacetKeys = (resultFacets?.relationTypes || []).map((item) => item.relation_type);
  const coverageEntityTypeKeys = renderCoverage.entityTypes.map((item) => item.key);
  const coverageRelationTypeKeys = renderCoverage.relationTypes.map((item) => item.key);

  function applyEntityFacetSelection(nextEntityTypes: string[]) {
    onUpdateRuntime({ entityTypes: nextEntityTypes });
    onUpdateQuery({ allowedEntityTypes: nextEntityTypes });
  }

  function applyRelationFacetSelection(nextRelationTypes: string[]) {
    onUpdateRuntime({ relationTypes: nextRelationTypes });
    onUpdateQuery({ allowedRelationTypes: nextRelationTypes });
  }

  function applyRenderCoverageEntitySelection(nextEntityTypes: string[]) {
    onUpdateRenderCoverage({ selectedEntityTypes: nextEntityTypes });
  }

  function applyRenderCoverageRelationSelection(nextRelationTypes: string[]) {
    onUpdateRenderCoverage({ selectedRelationTypes: nextRelationTypes });
  }

  function renderTypeLabel(key: string) {
    return key || "(empty)";
  }

  const statsItems = resultStats
    ? [
        { label: "seeds_count", value: Number(resultStats.seeds_count ?? resultStats.seed_count ?? seeds.length) },
        { label: "core_count", value: Number(resultStats.core_count ?? layerCountMap.get("core")?.node_count ?? 0) },
        { label: "shared_count", value: Number(resultStats.shared_count ?? layerCountMap.get("shared")?.node_count ?? 0) },
        { label: "local_count", value: Number(resultStats.local_count ?? layerCountMap.get("local")?.node_count ?? 0) },
        { label: "supplement_count", value: Number(resultStats.supplement_count ?? layerCountMap.get("supplement")?.node_count ?? 0) },
        { label: "dropped_nodes", value: Number(resultStats.dropped_nodes ?? 0) },
        { label: "dropped_edges", value: Number(resultStats.dropped_edges ?? 0) },
        { label: "dropped_neighbors", value: Number(resultStats.dropped_neighbors ?? 0) },
        { label: "dropped_by_budget", value: Number(resultStats.dropped_by_budget ?? 0) },
        { label: "dropped_by_type_budget", value: Number(resultStats.dropped_by_type_budget ?? 0) },
        { label: "dropped_generic_hubs", value: Number(resultStats.dropped_generic_hubs ?? 0) },
        { label: "final_nodes", value: Number(resultStats.final_nodes ?? resultStats.node_count ?? 0) },
        { label: "final_edges", value: Number(resultStats.final_edges ?? resultStats.edge_count ?? 0) },
      ]
    : [];

  return (
    <div style={{ padding: 16, display: "grid", gap: 14 }}>
      <div>
        <h3 style={{ margin: 0 }}>统一关系发现</h3>
        <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>
          统一搜索、加入 seeds，并基于当前 seeds 生成主题关系图。
        </div>
      </div>

      <div
        style={{
          border: "1px solid #eee",
          borderRadius: 8,
          padding: 12,
          display: "grid",
          gap: 8,
          background: "#fff",
        }}
      >
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ display: "grid", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#666" }}>当前 Space</span>
            <select
              data-testid="current-space-selector"
              value={currentSpace}
              onChange={(e) => onSelectSpace(e.target.value)}
              disabled={spaceLoading || spaceSwitching || spaces.length <= 0}
              style={{ minWidth: 220, padding: "8px 10px" }}
            >
              {spaces.map((space) => (
                <option
                  key={space.space_name}
                  value={space.space_name}
                  disabled={space.status !== "ready" && space.space_name !== currentSpace}
                >
                  {(space.display_name || space.space_name).trim()} [{space.status}]
                </option>
              ))}
            </select>
          </label>
          <div
            data-testid="current-space-display"
            data-space-name={currentSpace || ""}
            data-registry-status={currentSpaceStatus || ""}
            data-graph-status={currentSpaceGraphStatus || "unavailable"}
            data-search-status={currentSpaceSearchStatus || "unavailable"}
            style={{ fontSize: 12, color: "#666" }}
          >
            {spaceLoading
              ? "spaces loading..."
              : `${currentSpace || "-"} | registry_status=${currentSpaceStatus || "-"} | graph_status=${currentSpaceGraphStatus || "unavailable"} | search_status=${currentSpaceSearchStatus || "unavailable"}`}
          </div>
        </div>
        <div style={{ fontSize: 12, color: "#666" }}>
          ES 候选层负责 search / suggest / suggest_raw_id / entity_candidates；Nebula 图层负责 discovery / detail / subgraph / expand / relation_types。
        </div>
        <div style={{ fontSize: 12, color: "#666" }}>
          历史空间需要 canonical backfill 才能恢复完整候选覆盖；managed space 导入后天然按 canonical 契约写入。小空间图结果少通常是规模问题，不是功能失败。
        </div>
        {currentSpaceIndexStatus ? (
          <div
            data-testid="current-space-readiness-display"
            data-space-name={currentSpace || ""}
            data-index-status={currentSpaceIndexStatus.status}
            data-doc-count={String(currentSpaceIndexStatus.doc_count)}
            data-coverage-pct={typeof currentSpaceCoveragePct === "number" ? String(currentSpaceCoveragePct) : ""}
            style={{ fontSize: 12, color: currentSpaceIndexStatus.status === "failed" ? "#a61d24" : "#666" }}
          >
            index_status={currentSpaceIndexStatus.status} | canonical_docs={currentSpaceIndexStatus.doc_count}
            {typeof currentSpaceIndexStatus.nebula_entity_count === "number"
              ? ` | nebula_entities=${currentSpaceIndexStatus.nebula_entity_count}`
              : ""}
            {typeof currentSpaceCoveragePct === "number" ? ` | coverage=${currentSpaceCoveragePct}%` : ""}
            {currentSpaceIndexStatus.note ? ` | ${currentSpaceIndexStatus.note}` : ""}
          </div>
        ) : selectedSpace?.status === "ready" ? (
          <div style={{ fontSize: 12, color: "#666" }}>index_status 尚未写回 registry，请先刷新或执行 verify/backfill。</div>
        ) : null}
        {spaceSwitching ? (
          <div style={{ fontSize: 12, color: "#ad6800" }}>current space switching: {spaceSwitchPhase}</div>
        ) : null}
        {spaceError ? <div style={{ fontSize: 12, color: "#a61d24" }}>space 加载失败：{spaceError}</div> : null}
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 10, background: "#fafafa" }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Query Summary</div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(120px, 1fr))", gap: 8 }}>
          <div style={{ border: "1px solid #eee", borderRadius: 8, background: "#fff", padding: 8 }}>
            <div style={{ fontSize: 11, color: "#666" }}>Search Type</div>
            <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>
              {summary?.search_type || resultStats?.ranking_mode || "layered_multiseed"}
            </div>
          </div>
          <div style={{ border: "1px solid #eee", borderRadius: 8, background: "#fff", padding: 8 }}>
            <div style={{ fontSize: 11, color: "#666" }}>Selected Seeds</div>
            <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>{summary?.selected_seed_count ?? seeds.length}</div>
          </div>
          <div style={{ border: "1px solid #eee", borderRadius: 8, background: "#fff", padding: 8 }}>
            <div style={{ fontSize: 11, color: "#666" }}>Total Entities</div>
            <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>{summary?.total_entities ?? resultStats?.node_count ?? 0}</div>
          </div>
          <div style={{ border: "1px solid #eee", borderRadius: 8, background: "#fff", padding: 8 }}>
            <div style={{ fontSize: 11, color: "#666" }}>Relationships</div>
            <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>
              {summary?.total_relationships ?? resultStats?.edge_count ?? 0}
            </div>
          </div>
        </div>

        <div style={{ display: "grid", gap: 6 }}>
          <div style={{ fontSize: 12, color: "#666" }}>Selected Seeds</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {selectedSeedItems.length === 0 ? (
              <div style={{ fontSize: 12, color: "#999" }}>尚未添加 seed 节点</div>
            ) : (
              selectedSeedItems.map((item) => (
                <span
                  key={item.id}
                  style={{
                    border: "1px solid #d9d9d9",
                    borderRadius: 999,
                    background: "#fff",
                    padding: "4px 8px",
                    fontSize: 12,
                  }}
                >
                  {item.label}
                  {item.entity_type ? ` · ${item.entity_type}` : ""}
                </span>
              ))
            )}
          </div>
        </div>

        {layerItems.length > 0 ? (
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ fontSize: 12, color: "#666" }}>Layer Summary</div>
            <div style={{ display: "grid", gap: 6 }}>
              {layerItems.map((item) => (
                <div
                  key={item.layer}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 8,
                    border: "1px solid #eee",
                    borderRadius: 8,
                    background: "#fff",
                    padding: "6px 8px",
                    fontSize: 12,
                  }}
                >
                  <span>{item.layer}</span>
                  <span>
                    nodes={item.node_count} edges={item.edge_count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {seedSummaryItems.length > 0 ? (
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ fontSize: 12, color: "#666" }}>Seed Coverage</div>
            <div style={{ display: "grid", gap: 6 }}>
              {seedSummaryItems.map((item) => (
                <div
                  key={item.seed_vid}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    gap: 8,
                    border: "1px solid #eee",
                    borderRadius: 8,
                    background: "#fff",
                    padding: "6px 8px",
                    fontSize: 12,
                  }}
                >
                  <span>
                    {item.label || `seed ${item.seed_vid}`}
                    {item.entity_type ? ` · ${item.entity_type}` : ""}
                  </span>
                  <span>
                    core={item.core_path_count} shared={item.shared_touch_count} local={item.local_count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {statsItems.length > 0 ? (
          <div style={{ display: "grid", gap: 6 }}>
            <div style={{ fontSize: 12, color: "#666" }}>Discovery Stats</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(148px, 1fr))", gap: 8 }}>
              {statsItems.map((item) => (
                <div
                  key={item.label}
                  style={{
                    border: "1px solid #eee",
                    borderRadius: 8,
                    background: "#fff",
                    padding: "8px 10px",
                  }}
                >
                  <div style={{ fontSize: 11, color: "#666" }}>{item.label}</div>
                  <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, overflow: "hidden", background: "#fafafa" }}>
        <button
          onClick={() => onSetRenderedPanelCollapsed(!renderedPanelCollapsed)}
          style={{
            width: "100%",
            textAlign: "left",
            border: "none",
            background: "#fafafa",
            padding: "10px 12px",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          {renderedPanelCollapsed ? "▶" : "▼"} Rendered Nodes（{renderedNodes.length}）
        </button>
        {!renderedPanelCollapsed ? (
          <div style={{ borderTop: "1px solid #eee", padding: 12, display: "grid", gap: 8 }}>
            <ManagedNodeList
              title="当前已渲染节点"
              items={renderedNodes.map((node) => ({ node }))}
              emptyText="当前没有已渲染节点"
              primaryActionLabel={(node) => (seedIdSet.has(node.id) ? "Seed 仅支持删除" : "取消渲染")}
              onPrimaryAction={onHideRenderedNode}
              onLocate={onLocateNode}
              onViewDetail={onViewNodeDetailById}
              isPrimaryDisabled={(node) => seedIdSet.has(node.id)}
            />
          </div>
        ) : null}
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, overflow: "hidden", background: "#fafafa" }}>
        <button
          onClick={() => onSetDroppedPanelCollapsed(!droppedPanelCollapsed)}
          style={{
            width: "100%",
            textAlign: "left",
            border: "none",
            background: "#fafafa",
            padding: "10px 12px",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          {droppedPanelCollapsed ? "▶" : "▼"} Dropped / Hidden Nodes（
          {hiddenNodes.length + droppedNodes.droppedByBudget.length + droppedNodes.droppedByTypeFilter.length + droppedNodes.droppedByRelationFilter.length}
          ）
        </button>
        {!droppedPanelCollapsed ? (
          <div style={{ borderTop: "1px solid #eee", padding: 12, display: "grid", gap: 12 }}>
            <ManagedNodeList
              title="Hidden by User"
              items={hiddenNodes.map((node) => ({ node, meta: "hidden_by_user" }))}
              emptyText="当前没有用户隐藏节点"
              primaryActionLabel="恢复显示"
              onPrimaryAction={(vid) => onRestoreHiddenNode(vid, false)}
              onLocate={(vid) => onRestoreHiddenNode(vid, true)}
              onViewDetail={onViewNodeDetailById}
            />
            <ManagedNodeList
              title="Budget Dropped"
              items={droppedNodes.droppedByBudget.map((item) => ({
                node: item.node,
                meta: `support_edges=${item.supportEdgesCount}${item.sourceNodeId != null ? ` | source=${item.sourceNodeId}` : ""}`,
              }))}
              emptyText="当前没有 budget dropped 节点"
              primaryActionLabel="加入渲染"
              onPrimaryAction={(vid) => onForceRenderDroppedNode(vid, false)}
              onViewDetail={onViewNodeDetailById}
            />
            <ManagedNodeList
              title="Type Filtered"
              items={droppedNodes.droppedByTypeFilter.map((item) => ({
                node: item.node,
                meta: `support_edges=${item.supportEdgesCount}${item.sourceNodeId != null ? ` | source=${item.sourceNodeId}` : ""}`,
              }))}
              emptyText="当前没有 type filtered 节点"
              primaryActionLabel="强制显示"
              onPrimaryAction={(vid) => onForceRenderDroppedNode(vid, false)}
              onViewDetail={onViewNodeDetailById}
            />
            <ManagedNodeList
              title="Relation Filtered"
              items={droppedNodes.droppedByRelationFilter.map((item) => ({
                node: item.node,
                meta: `support_edges=${item.supportEdgesCount}${item.sourceNodeId != null ? ` | source=${item.sourceNodeId}` : ""}`,
              }))}
              emptyText="当前没有 relation filtered 节点"
              primaryActionLabel="强制显示"
              onPrimaryAction={(vid) => onForceRenderDroppedNode(vid, false)}
              onViewDetail={onViewNodeDetailById}
            />
          </div>
        ) : null}
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Render Coverage Controls</div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <div style={{ border: "1px solid #eee", borderRadius: 8, background: "#fff", padding: 8 }}>
            <div style={{ fontSize: 11, color: "#666" }}>Working Set Nodes</div>
            <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>{renderCoverage.workingNodeCount}</div>
          </div>
          <div style={{ border: "1px solid #eee", borderRadius: 8, background: "#fff", padding: 8 }}>
            <div style={{ fontSize: 11, color: "#666" }}>Working Set Edges</div>
            <div style={{ marginTop: 4, fontSize: 13, fontWeight: 600 }}>{renderCoverage.workingEdgeCount}</div>
          </div>
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>Entity Types</div>
          <CheckboxList
            items={coverageEntityTypeKeys}
            checked={coverageEntityTypeSet}
            renderLabel={(key) => {
              const found = renderCoverage.entityTypes.find((item) => item.key === key);
              return `${renderTypeLabel(key)} (${found?.count ?? 0})`;
            }}
            onToggle={(key) => applyRenderCoverageEntitySelection(toggleArrayValue(renderCoverage.selectedEntityTypes, key))}
            onSelectAll={() => applyRenderCoverageEntitySelection([...coverageEntityTypeKeys])}
            onClear={() => applyRenderCoverageEntitySelection([])}
            emptyText="当前 working set 中暂无实体类型"
          />
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>Relationship Types</div>
          <CheckboxList
            items={coverageRelationTypeKeys}
            checked={coverageRelationTypeSet}
            renderLabel={(key) => {
              const found = renderCoverage.relationTypes.find((item) => item.key === key);
              const display = relationDisplay(key) || renderTypeLabel(key);
              return `${display} (${found?.count ?? 0})`;
            }}
            onToggle={(key) => applyRenderCoverageRelationSelection(toggleArrayValue(renderCoverage.selectedRelationTypes, key))}
            onSelectAll={() => applyRenderCoverageRelationSelection([...coverageRelationTypeKeys])}
            onClear={() => applyRenderCoverageRelationSelection([])}
            emptyText="当前 working set 中暂无关系类型"
          />
        </div>

        <div style={{ fontSize: 12, color: "#666" }}>
          这里控制的是当前 working set 到 visibleGraph 的即时渲染覆盖，不请求后端，也不会改写 hidden_by_user / dropped_*。
        </div>
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Next Discovery Input Filters</div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>Entity Types</div>
          <CheckboxList
            items={availableEntityFacetKeys}
            checked={runtimeEntityTypeSet}
            renderLabel={(key) => {
              const found = resultFacets?.entityTypes.find((item) => item.entity_type === key);
              return found ? `${renderTypeLabel(key)} (${found.count})` : renderTypeLabel(key);
            }}
            onToggle={(key) => applyEntityFacetSelection(toggleArrayValue(runtime.entityTypes, key))}
            onSelectAll={() => applyEntityFacetSelection([...availableEntityFacetKeys])}
            onClear={() => applyEntityFacetSelection([])}
            emptyText="运行 discovery 后显示"
          />
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>Relationship Types</div>
          <CheckboxList
            items={availableRelationFacetKeys}
            checked={runtimeRelationTypeSet}
            renderLabel={(key) => {
              const found = resultFacets?.relationTypes.find((item) => item.relation_type === key);
              const display = relationDisplay(key) || renderTypeLabel(key);
              return found ? `${display} (${found.count})` : display;
            }}
            onToggle={(key) => applyRelationFacetSelection(toggleArrayValue(runtime.relationTypes, key))}
            onSelectAll={() => applyRelationFacetSelection([...availableRelationFacetKeys])}
            onClear={() => applyRelationFacetSelection([])}
            emptyText="运行 discovery 后显示"
          />
        </div>

        <div style={{ fontSize: 12, color: "#666" }}>
          这一组仍然只作用于下一次“重新生成关系图”。当前图的即时显示优先由上面的 Render Coverage Controls 生效。
        </div>
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Discovery Settings</div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>max_nodes</span>
            <input type="number" min={10} max={1000} value={query.maxNodes} onChange={(e) => onUpdateQuery({ maxNodes: Number(e.target.value) || 0 })} style={{ padding: 8 }} />
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>max_edges</span>
            <input type="number" min={10} max={5000} value={query.maxEdges} onChange={(e) => onUpdateQuery({ maxEdges: Number(e.target.value) || 0 })} style={{ padding: 8 }} />
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>top_k_per_type</span>
            <input type="number" min={1} max={100} value={query.topKPerType} onChange={(e) => onUpdateQuery({ topKPerType: Number(e.target.value) || 0 })} style={{ padding: 8 }} />
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>hop</span>
            <select value={query.hop} onChange={(e) => onUpdateQuery({ hop: Number(e.target.value) || 1 })} style={{ padding: 8 }}>
              <option value={1}>1</option>
              <option value={2}>2</option>
              <option value={3}>3</option>
            </select>
          </label>
        </div>

        <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 12 }}>
          <input
            type="checkbox"
            checked={query.includeCandidateCandidateEdges}
            onChange={(e) => onUpdateQuery({ includeCandidateCandidateEdges: e.target.checked })}
          />
          include_candidate_candidate_edges
        </label>

        <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 12 }}>
          <input
            type="checkbox"
            checked={query.includeSeedSeedEdges}
            onChange={(e) => onUpdateQuery({ includeSeedSeedEdges: e.target.checked })}
          />
          include_seed_seed_edges
        </label>
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 10 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
          <div style={{ fontSize: 13, fontWeight: 700 }}>已选 Seeds</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginLeft: "auto" }}>
            <div style={{ fontSize: 12, color: "#666" }}>已选 {seeds.length}</div>
            <button onClick={onClearSeeds} disabled={loading || seeds.length === 0} style={{ padding: "6px 10px", fontSize: 12 }}>
              清空
            </button>
          </div>
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          {seeds.length === 0 ? (
            <div style={{ fontSize: 12, color: "#666" }}>尚未添加 seed 节点</div>
          ) : (
            seeds.map((seed) => (
              <div
                key={seed.vid}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: 8,
                  alignItems: "center",
                  flexWrap: "wrap",
                  border: "1px solid #f0f0f0",
                  borderRadius: 8,
                  padding: 8,
                  background: "#fafafa",
                }}
              >
                <div style={{ minWidth: 0, flex: "1 1 220px" }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {seed.label}
                  </div>
                  <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                    vid={seed.vid}
                    {seed.entity_type ? ` | ${seed.entity_type}` : ""}
                    {seed.source ? ` | ${seed.source}` : ""}
                  </div>
                </div>
                <button onClick={() => onRemoveSeed(seed.vid)} style={{ padding: "6px 8px", fontSize: 12, marginLeft: "auto" }}>
                  删除
                </button>
              </div>
            ))
          )}
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          <button
            data-testid="discovery-run-button"
            onClick={onRun}
            disabled={loading || seeds.length === 0}
            style={{
              padding: "10px 12px",
              fontSize: 13,
              fontWeight: 600,
              borderRadius: 8,
              border: "1px solid #1677ff",
              background: loading || seeds.length === 0 ? "#f5f5f5" : "#1677ff",
              color: loading || seeds.length === 0 ? "#999" : "#fff",
              cursor: loading || seeds.length === 0 ? "not-allowed" : "pointer",
              width: "100%",
            }}
          >
            {loading ? "生成中…" : "重新生成关系图"}
          </button>
          <div style={{ fontSize: 12, color: "#666" }}>
            当前 seeds 或全局 discovery 过滤条件变更后，点击这里会按最新条件重跑 discovery。
          </div>
          {hasPendingChanges ? (
            <div style={{ fontSize: 12, color: "#ad6800" }}>当前 seeds 或 discovery 参数已变更，需重新生成后才会同步到图结果。</div>
          ) : null}
        </div>
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 12 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700 }}>搜索并添加实体</div>
          <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
            输入时展示轻量预览候选，提交后展示完整 Top100 候选列表。
          </div>
        </div>

        <div ref={searchWrapRef} style={{ position: "relative" }}>
          <input
            data-testid="discovery-search-input"
            value={searchQuery.q}
            onChange={(e) => onUpdateSearchQuery({ q: e.target.value })}
            onKeyDown={handleSearchKeyDown}
            placeholder="搜索实体名称、描述等"
            style={{ width: "100%", padding: "10px 12px" }}
          />
          {preview.open ? (
            <div
              data-testid="discovery-preview-list"
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: "calc(100% + 6px)",
                zIndex: 30,
                border: "1px solid #e5e6eb",
                borderRadius: 8,
                background: "#fff",
                boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                maxHeight: 280,
                overflow: "auto",
              }}
            >
              {preview.loading ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>候选预览加载中…</div>
              ) : preview.error ? (
                <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选预览失败：{preview.error}</div>
              ) : preview.items.length === 0 ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选</div>
              ) : (
                preview.items.map((item, idx) => {
                  const active = idx === preview.highlightIndex;
                  return (
                    <button
                      key={`${item.vid}-${idx}`}
                      type="button"
                      data-testid="discovery-preview-item"
                      data-vid={String(item.vid)}
                      data-label={item.label}
                      data-raw-id={item.raw_id || ""}
                      onMouseEnter={() => onSetPreviewHighlightIndex(idx)}
                      onClick={() => onSelectPreviewItem(item)}
                      style={{
                        width: "100%",
                        border: "none",
                        borderBottom: idx === preview.items.length - 1 ? "none" : "1px solid #f0f0f0",
                        background: active ? "#e6f4ff" : "#fff",
                        padding: "10px 12px",
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{item.label}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                        vid={item.vid}
                        {item.entity_type ? ` | ${item.entity_type}` : ""}
                        {item.source ? ` | ${item.source}` : ""}
                      </div>
                      {item.snippet ? (
                        <div style={{ marginTop: 4, fontSize: 12, color: "#444", lineHeight: 1.5 }}>{item.snippet}</div>
                      ) : null}
                    </button>
                  );
                })
              )}
            </div>
          ) : null}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 8 }}>
          <button data-testid="discovery-search-submit" onClick={onSubmitSearch} disabled={candidateResult.loading} style={{ padding: "8px 12px", width: "100%" }}>
            {candidateResult.loading ? "搜索中…" : "搜索候选"}
          </button>
          <button
            data-testid="discovery-search-advanced-toggle"
            onClick={onToggleSearchAdvanced}
            style={{ padding: "8px 12px", fontSize: 12, width: "100%" }}
          >
            {searchAdvancedOpen ? "收起高级筛选" : "展开高级筛选"}
          </button>
        </div>

        {searchAdvancedOpen ? (
          <div style={{ border: "1px solid #f0f0f0", borderRadius: 8, padding: 12, display: "grid", gap: 8, background: "#fafafa" }}>
            <div style={{ fontSize: 12, fontWeight: 600 }}>高级筛选</div>

            <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
              <span>entity_raw_id</span>
              <input
                value={searchQuery.entityRawId}
                onChange={(e) => onUpdateSearchQuery({ entityRawId: e.target.value })}
                placeholder="可选：按 entity_raw_id 搜索"
                style={{ width: "100%", padding: 8 }}
              />
            </label>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
              <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
                <span>entity_type</span>
                <select
                  data-testid="discovery-search-advanced-entity-type"
                  value={searchQuery.entityType}
                  onChange={(e) => onUpdateSearchQuery({ entityType: e.target.value })}
                  style={{ padding: 8 }}
                >
                  <option value="">全部</option>
                  {entityTypeOptions.map((opt) => (
                    <option key={opt.entity_type} value={opt.entity_type}>
                      {opt.entity_type} ({opt.count})
                    </option>
                  ))}
                </select>
              </label>

              <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
                <span>entity_raw_id_mode</span>
                <select
                  value={searchQuery.entityRawIdMode}
                  onChange={(e) =>
                    onUpdateSearchQuery({
                      entityRawIdMode: e.target.value as DiscoveryEntityCandidateQueryState["entityRawIdMode"],
                    })
                  }
                  style={{ padding: 8 }}
                >
                  <option value="contains">contains</option>
                  <option value="prefix">prefix</option>
                  <option value="exact">exact</option>
                </select>
              </label>
            </div>

            <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
              <span>source</span>
              <input
                value={searchQuery.source}
                onChange={(e) => onUpdateSearchQuery({ source: e.target.value })}
                placeholder="可选：过滤 source"
                style={{ width: "100%", padding: 8 }}
              />
            </label>

            <div style={{ display: "grid", gap: 6, fontSize: 12 }}>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={searchQuery.searchInName}
                  onChange={(e) => onUpdateSearchQuery({ searchInName: e.target.checked })}
                />
                搜索 entity_name
              </label>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={searchQuery.searchInDescription}
                  onChange={(e) => onUpdateSearchQuery({ searchInDescription: e.target.checked })}
                />
                搜索 description
              </label>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={searchQuery.searchInType}
                  onChange={(e) => onUpdateSearchQuery({ searchInType: e.target.checked })}
                />
                搜索 entity_type
              </label>
              <label style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                <input
                  type="checkbox"
                  checked={searchQuery.searchInRawId}
                  onChange={(e) => onUpdateSearchQuery({ searchInRawId: e.target.checked })}
                />
                搜索 entity_raw_id
              </label>
            </div>
          </div>
        ) : null}
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700 }}>完整候选列表</div>
            <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
              已加载 {candidateResult.items.length} 条
              {candidateResult.page > 0 ? ` | 当前页 ${candidateResult.page}` : ""}
              {candidateResult.has_more ? " | 还有更多候选" : candidateResult.items.length > 0 ? " | 已无更多" : ""}
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 8, width: "100%" }}>
            <button
              onClick={onAddSelectedCandidates}
              disabled={selectedCandidateIds.size === 0}
              style={{ padding: "8px 12px", fontSize: 12, width: "100%" }}
            >
              加入已选候选（{selectedCandidateIds.size}）
            </button>
            <button
              onClick={onClearCandidateSelection}
              disabled={selectedCandidateIds.size === 0}
              style={{ padding: "8px 12px", fontSize: 12, width: "100%" }}
            >
              清空勾选
            </button>
          </div>
        </div>

        {candidateResult.error ? (
          <div style={{ fontSize: 12, color: "#d4380d" }}>候选搜索失败：{candidateResult.error}</div>
        ) : null}
        <div
          data-testid="discovery-candidate-space-meta"
          data-space-name={candidateResult.space_meta?.space_name || currentSpace || ""}
          data-graph-status={candidateResult.space_meta?.graph_status || "unavailable"}
          data-search-status={candidateResult.space_meta?.search_status || "unavailable"}
          style={{ fontSize: 12, color: candidateResult.space_meta?.search_status === "failed" ? "#a61d24" : "#666" }}
        >
          candidate_space={candidateResult.space_meta?.space_name || currentSpace || "-"} | graph_status=
          {candidateResult.space_meta?.graph_status || "unavailable"} | search_status=
          {candidateResult.space_meta?.search_status || "unavailable"}
          {typeof candidateResult.space_meta?.coverage_pct === "number" ? ` | coverage=${candidateResult.space_meta.coverage_pct}%` : ""}
          {candidateResult.space_meta?.index_status?.status ? ` | index_status=${candidateResult.space_meta.index_status.status}` : ""}
        </div>

        <div data-testid="discovery-candidate-list" style={{ display: "grid", gap: 10 }}>
          {candidateResult.loading ? (
            <div data-testid="discovery-candidate-loading" style={{ fontSize: 12, color: "#666" }}>候选加载中…</div>
          ) : candidateResult.items.length === 0 ? (
            <div style={{ fontSize: 12, color: "#666" }}>
              {candidateStatusMessage(
                candidateResult,
                Boolean(searchQuery.q.trim() || searchQuery.entityRawId.trim())
              )}
            </div>
          ) : (
            candidateResult.items.map((item) => (
              <EntityCandidateCard
                key={item.vid}
                item={item}
                checked={selectedCandidateIds.has(item.vid)}
                seeded={seedIdSet.has(item.vid)}
                onToggleChecked={onToggleCandidateSelect}
                onAddSeed={onAddCandidateSeed}
                onViewDetail={onViewCandidateDetail}
                onLoadSubgraph={onLoadCandidateSubgraph}
              />
            ))
          )}
        </div>

        {candidateResult.items.length > 0 ? (
          <div style={{ display: "flex", justifyContent: "center" }}>
            <button
              onClick={onLoadMoreCandidates}
              disabled={!candidateResult.has_more || candidateResult.loadingMore}
              style={{ padding: "8px 12px" }}
            >
              {candidateResult.loadingMore ? "加载中…" : candidateResult.has_more ? "加载更多" : "已无更多"}
            </button>
          </div>
        ) : null}
      </div>

    </div>
  );
}
