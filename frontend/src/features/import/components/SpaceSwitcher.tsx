import type { SpaceSummary } from "../../space/types/space";

type SpaceSwitcherProps = {
  currentSpace: string;
  spaces: SpaceSummary[];
  loading: boolean;
  switching?: boolean;
  onSelect: (spaceName: string) => void;
};

export function SpaceSwitcher({ currentSpace, spaces, loading, switching = false, onSelect }: SpaceSwitcherProps) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span style={{ fontSize: 12, letterSpacing: "0.08em", textTransform: "uppercase", color: "#7b6652" }}>Switch Space</span>
      <select
        value={currentSpace}
        onChange={(event) => onSelect(event.target.value)}
        disabled={loading || switching || spaces.length === 0}
        style={{
          minWidth: 220,
          borderRadius: 12,
          border: "1px solid rgba(84, 61, 35, 0.18)",
          background: "#fffdf8",
          padding: "10px 12px",
          color: "#3d2d1f",
        }}
      >
        {spaces.map((space) => (
          <option
            key={space.space_name}
            value={space.space_name}
            disabled={space.status !== "ready" && space.space_name !== currentSpace}
          >
            {(space.display_name || space.space_name).trim()} [{space.status}
            {space.index_status?.status ? ` / ${space.index_status.status}` : ""}]
          </option>
        ))}
      </select>
    </label>
  );
}
