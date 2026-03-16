import type { CurrentSpaceResp, SpaceSummary } from "../types/space";

type SpaceProvisionStatusProps = {
  current: CurrentSpaceResp | null;
  selected: SpaceSummary | null;
  error: string | null;
};

export function SpaceProvisionStatus({ current, selected, error }: SpaceProvisionStatusProps) {
  if (error) {
    return <div style={{ padding: "8px 16px 0 16px", fontSize: 12, color: "#a8071a" }}>{error}</div>;
  }
  if (!current) return null;
  return (
    <div style={{ padding: "6px 16px 0 16px", fontSize: 12, color: "#666" }}>
      resolved={current.space_name} via {current.source}
      {selected ? ` | status=${selected.status}/${selected.internal_status}` : ""}
      {selected?.status === "ready" ? " | 下一步：切到 Import 导入数据" : ""}
    </div>
  );
}
