import { useMemo } from "react";
import { relationDisplay } from "../utils/relation";

type TopBarProps = {
  rootVid: number | null;
  loadingGraph: boolean;
  hop: number;
  setHop: (nextHop: number) => void;
  relations: string[];
  onOpenRelationFilter: () => void;
  onClearRelationsAndReload: () => void;
  onReloadSubgraph: () => void;
  graphStats: Record<string, unknown> | null;
  relationPreviewActive: boolean;
  onExitRelationPreview: () => void;
};

export function TopBar({
  rootVid,
  loadingGraph,
  hop,
  setHop,
  relations,
  onOpenRelationFilter,
  onClearRelationsAndReload,
  onReloadSubgraph,
  graphStats,
  relationPreviewActive,
  onExitRelationPreview,
}: TopBarProps) {
  const nodeCount = typeof graphStats?.node_count === "number" ? graphStats.node_count : undefined;
  const edgeCount = typeof graphStats?.edge_count === "number" ? graphStats.edge_count : undefined;

  const relationButtonText = useMemo(() => {
    if (relations.length === 0) return "筛选关系（全部）";
    if (relations.length <= 2) return `筛选关系（${relations.map((x) => relationDisplay(x) || x).join(", ")}）`;
    return `筛选关系（已选 ${relations.length}）`;
  }, [relations]);

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 10px",
        minWidth: 0,
        position: "relative",
        flexWrap: "wrap",
      }}
    >
      <div style={{ fontSize: 13, color: "#444", whiteSpace: "nowrap" }}>
        Root: {rootVid ?? "-"} {loadingGraph ? "（加载中…）" : ""}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <label style={{ fontSize: 13 }}>Hop</label>
        <select value={hop} onChange={(e) => setHop(Number(e.target.value))}>
          <option value={1}>1</option>
          <option value={2}>2</option>
          <option value={3}>3</option>
        </select>
      </div>

      <button
        onClick={onOpenRelationFilter}
        style={{
          padding: "7px 10px",
          border: "1px solid #d9d9d9",
          background: "#fff",
          borderRadius: 6,
          cursor: "pointer",
          fontSize: 12,
          maxWidth: 320,
          overflow: "hidden",
          textOverflow: "ellipsis",
          whiteSpace: "nowrap",
        }}
      >
        {relationButtonText}
      </button>

      <button onClick={onClearRelationsAndReload} style={{ padding: "7px 10px", fontSize: 12 }}>
        清空筛选
      </button>

      {relationPreviewActive ? (
        <button onClick={onExitRelationPreview} style={{ padding: "7px 10px", fontSize: 12 }}>
          退出预览
        </button>
      ) : null}

      <button
        onClick={onReloadSubgraph}
        disabled={!rootVid}
        style={{ marginLeft: "auto", padding: "8px 12px" }}
      >
        重新加载子图
      </button>

      <div style={{ fontSize: 12, color: "#666", whiteSpace: "nowrap" }}>
        {nodeCount != null && edgeCount != null ? `缓存 nodes=${nodeCount} edges=${edgeCount}` : ""}
      </div>
    </div>
  );
}
