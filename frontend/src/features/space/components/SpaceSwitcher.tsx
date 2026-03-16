import type { SpaceSummary } from "../types/space";

type SpaceSwitcherProps = {
  currentSpace: string;
  spaces: SpaceSummary[];
  loading: boolean;
  onSelect: (spaceName: string) => void;
  onOpenCreate: () => void;
};

export function SpaceSwitcher({ currentSpace, spaces, loading, onSelect, onOpenCreate }: SpaceSwitcherProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        flexWrap: "wrap",
        padding: "10px 16px 0 16px",
      }}
    >
      <div style={{ fontSize: 12, color: "#666" }}>Current Space</div>
      <select value={currentSpace} onChange={(e) => onSelect(e.target.value)} style={{ minWidth: 180, padding: "6px 8px" }}>
        {spaces.map((space) => (
          <option key={space.space_name} value={space.space_name}>
            {space.display_name || space.space_name} [{space.status}]
          </option>
        ))}
      </select>
      <button onClick={onOpenCreate} style={{ padding: "6px 10px" }}>
        新建 Space
      </button>
      <div style={{ fontSize: 12, color: "#666" }}>{loading ? "spaces loading..." : currentSpace || "-"}</div>
    </div>
  );
}
