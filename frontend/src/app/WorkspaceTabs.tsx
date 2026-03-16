export type WorkspaceMode = "discovery" | "import";

type WorkspaceTabsProps = {
  workspaceMode: WorkspaceMode;
  onSelectMode: (nextMode: WorkspaceMode) => void;
};

function buttonStyle(active: boolean, activeBackground: string) {
  return {
    padding: "8px 12px",
    borderRadius: 8,
    border: "1px solid #d9d9d9",
    background: active ? activeBackground : "#fff",
    cursor: "pointer",
    fontWeight: active ? 700 : 500,
  } as const;
}

export function WorkspaceTabs({ workspaceMode, onSelectMode }: WorkspaceTabsProps) {
  return (
    <>
      <button
        data-testid="workspace-tab-discovery"
        onClick={() => onSelectMode("discovery")}
        style={buttonStyle(workspaceMode === "discovery", "#fff7e6")}
      >
        统一关系发现
      </button>
      <button
        data-testid="workspace-tab-import"
        onClick={() => onSelectMode("import")}
        style={buttonStyle(workspaceMode === "import", "#f8ead2")}
      >
        Import
      </button>
    </>
  );
}
