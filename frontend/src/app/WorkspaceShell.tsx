import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from "react";

import { Resizer } from "../components/Resizer";
import type { WorkspaceMode } from "./WorkspaceTabs";

export type UiNotice = {
  level: "error" | "warn" | "info";
  message: string;
};

type WorkspaceShellProps = {
  layoutStyle: CSSProperties;
  workspaceMode: WorkspaceMode;
  currentSpaceName: string;
  uiNotice: UiNotice | null;
  onDismissNotice: () => void;
  tabs: ReactNode;
  importWorkspace: ReactNode;
  leftPane: ReactNode;
  topBar: ReactNode;
  canvas: ReactNode;
  rightPane: ReactNode;
  overlayPanel?: ReactNode;
  onBeginResize: (side: "left" | "right", event: ReactPointerEvent<HTMLDivElement>) => void;
};

export function WorkspaceShell({
  layoutStyle,
  workspaceMode,
  currentSpaceName,
  uiNotice,
  onDismissNotice,
  tabs,
  importWorkspace,
  leftPane,
  topBar,
  canvas,
  rightPane,
  overlayPanel,
  onBeginResize,
}: WorkspaceShellProps) {
  return (
    <div className="kg-layout" style={layoutStyle}>
      {uiNotice ? (
        <div
          style={{
            position: "fixed",
            top: 8,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 1000,
            maxWidth: 980,
            minWidth: 320,
            padding: "10px 14px",
            borderRadius: 8,
            border:
              uiNotice.level === "error"
                ? "1px solid #ffccc7"
                : uiNotice.level === "warn"
                  ? "1px solid #ffe58f"
                  : "1px solid #91caff",
            background:
              uiNotice.level === "error"
                ? "#fff2f0"
                : uiNotice.level === "warn"
                  ? "#fffbe6"
                  : "#e6f4ff",
            color:
              uiNotice.level === "error"
                ? "#a8071a"
                : uiNotice.level === "warn"
                  ? "#874d00"
                  : "#003a8c",
            fontSize: 13,
            boxShadow: "0 6px 20px rgba(0,0,0,0.12)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 12,
          }}
        >
          <span>{uiNotice.message}</span>
          <button
            onClick={onDismissNotice}
            style={{ border: "none", background: "transparent", cursor: "pointer", color: "inherit" }}
          >
            关闭
          </button>
        </div>
      ) : null}

      {workspaceMode === "import" ? (
        <div style={{ gridColumn: "1 / -1", minWidth: 0, overflow: "auto" }}>
          <div style={{ padding: "12px 16px 0 16px", display: "flex", gap: 8, position: "sticky", top: 0, zIndex: 30 }}>
            {tabs}
          </div>
          {importWorkspace}
        </div>
      ) : (
        <>
          <div className="kg-pane kg-pane-left">
            <div style={{ padding: "12px 16px 0 16px", display: "flex", gap: 8 }}>{tabs}</div>
            {leftPane}
          </div>

          <Resizer side="left" onPointerDown={(event) => onBeginResize("left", event)} />

          <div className="kg-center">
            <div
              className="kg-topbar-sticky"
              data-testid="workspace-topbar"
              data-workspace-mode={workspaceMode}
              data-current-space={currentSpaceName || ""}
            >
              {topBar}
            </div>
            {canvas}
          </div>

          <Resizer side="right" onPointerDown={(event) => onBeginResize("right", event)} />

          <div className="kg-pane kg-pane-right">{rightPane}</div>

          {overlayPanel}
        </>
      )}
    </div>
  );
}
