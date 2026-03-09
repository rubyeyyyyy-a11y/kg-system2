import type { DiscoveryEntityCandidateItem } from "../types/kg";

type EntityCandidateCardProps = {
  item: DiscoveryEntityCandidateItem;
  checked: boolean;
  seeded: boolean;
  onToggleChecked: (id: number) => void;
  onAddSeed: (item: DiscoveryEntityCandidateItem) => void;
  onViewDetail: (item: DiscoveryEntityCandidateItem) => void;
  onLoadSubgraph: (item: DiscoveryEntityCandidateItem) => void;
};

export function EntityCandidateCard({
  item,
  checked,
  seeded,
  onToggleChecked,
  onAddSeed,
  onViewDetail,
  onLoadSubgraph,
}: EntityCandidateCardProps) {
  const candidateId = Number(item.vid || item.id);

  return (
    <div
      style={{
        padding: 10,
        border: seeded ? "1px solid #b7eb8f" : "1px solid #f0f0f0",
        borderRadius: 8,
        background: seeded ? "#f6ffed" : "#fff",
        display: "grid",
        gap: 8,
      }}
    >
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 8, alignItems: "start" }}>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 8, minWidth: 0, flex: "1 1 320px" }}>
          <input
            type="checkbox"
            checked={checked}
            onChange={() => onToggleChecked(candidateId)}
            onClick={(e) => e.stopPropagation()}
            style={{ marginTop: 2 }}
          />
          <button
            type="button"
            onClick={() => onViewDetail(item)}
            style={{
              minWidth: 0,
              flex: 1,
              border: "none",
              background: "transparent",
              padding: 0,
              textAlign: "left",
              cursor: "pointer",
            }}
          >
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "#222",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={item.label}
            >
              {item.label}
            </div>
            <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
              vid={candidateId}
              {item.entity_type ? ` | ${item.entity_type}` : ""}
              {item.source ? ` | ${item.source}` : ""}
              {typeof item.score === "number" ? ` | score=${item.score}` : ""}
            </div>
            {item.snippet ? (
              <div style={{ marginTop: 8, fontSize: 12, color: "#444", lineHeight: 1.5 }}>{item.snippet}</div>
            ) : (
              <div style={{ marginTop: 8, fontSize: 12, color: "#999" }}>暂无 description 摘要</div>
            )}
          </button>
        </div>

        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            justifyContent: "flex-start",
            minWidth: 0,
            maxWidth: "100%",
          }}
        >
          <button
            onClick={() => onViewDetail(item)}
            style={{ padding: "5px 8px", fontSize: 12, flex: "0 1 auto" }}
          >
            查看详情
          </button>
          <button
            onClick={() => onAddSeed(item)}
            disabled={seeded}
            style={{ padding: "5px 8px", fontSize: 12, flex: "0 1 auto" }}
          >
            {seeded ? "已加入 Seeds" : "加入 Seeds"}
          </button>
          <button
            onClick={() => onLoadSubgraph(item)}
            style={{ padding: "5px 8px", fontSize: 12, flex: "0 1 auto" }}
          >
            加载单个子图
          </button>
        </div>
      </div>
    </div>
  );
}
