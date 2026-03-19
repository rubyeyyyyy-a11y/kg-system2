import { formatBytes } from "../utils";
import type { CompiledImportPlan, ImportDraftResp, ImportMode, ImportPreviewResp } from "../types/import";

type ImportWorkspaceSidebarProps = {
  compiledPlan: CompiledImportPlan | null;
  currentTemplateType: string;
  draft: ImportDraftResp | null;
  draftTotalBytes: number;
  effectiveCurrentSpace: string;
  integrationWarnings: string[];
  jobLogs: string[];
  preview: ImportPreviewResp | null;
  schemaWarnings: string[];
  selectedJobId: string | null;
  sources: { source_id: string }[];
  targetsCount: number;
  workspaceMode: ImportMode;
  formatTs: (ts?: number | null) => string;
  integrationLabel: (level?: string | null) => string;
};

const CARD = "#fffaf1";

export function ImportWorkspaceSidebar({
  compiledPlan,
  currentTemplateType,
  draft,
  draftTotalBytes,
  effectiveCurrentSpace,
  integrationWarnings,
  jobLogs,
  preview,
  schemaWarnings,
  selectedJobId,
  sources,
  targetsCount,
  workspaceMode,
  formatTs,
  integrationLabel,
}: ImportWorkspaceSidebarProps) {
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <strong>Warnings</strong>
          <span style={{ fontSize: 12, color: "#7d6b57" }}>space={effectiveCurrentSpace || "-"}</span>
        </div>
        <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
          {preview?.warnings?.map((warning, index) => (
            <div key={`preview-warning-${index}`} style={{ padding: 12, borderRadius: 12, background: "#eef4ff", color: "#1d4f91" }}>
              {warning}
            </div>
          ))}
          {schemaWarnings.map((warning, index) => (
            <div key={`schema-${index}`} style={{ padding: 12, borderRadius: 12, background: "#fffbe6", color: "#ad6800" }}>
              {warning}
            </div>
          ))}
          {integrationWarnings.map((warning, index) => (
            <div key={`integration-${index}`} style={{ padding: 12, borderRadius: 12, background: "#fff1f0", color: "#a61d24" }}>
              {warning}
            </div>
          ))}
          {draft?.validation?.errors?.map((error, index) => (
            <div key={`error-${index}`} style={{ padding: 12, borderRadius: 12, background: "#fff1f0", color: "#a61d24" }}>
              {error}
            </div>
          ))}
          {draft?.validation?.semantic_notes?.map((note, index) => (
            <div key={`note-${index}`} style={{ padding: 12, borderRadius: 12, background: "#eef4ff", color: "#1d4f91" }}>
              {note}
            </div>
          ))}
        </div>
      </section>

      <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
          <strong>Draft Snapshot</strong>
          <span data-testid="import-draft-header" style={{ fontSize: 12, color: "#7d6b57" }}>
            {draft ? `${draft.draft_id} | ${draft.status}` : "未保存"}
          </span>
        </div>
        <div style={{ display: "grid", gap: 6, fontSize: 13, color: "#5b4b38" }}>
          <div>space={draft?.space_name || effectiveCurrentSpace || "-"}</div>
          <div>template={currentTemplateType}</div>
          <div>workspace_mode={workspaceMode}</div>
          <div>sources={sources.map((item) => item.source_id).join(", ") || "-"}</div>
          <div>targets={targetsCount}</div>
          <div>draft_total_size={formatBytes(draftTotalBytes)}</div>
          <div>updated={formatTs(draft?.updated_at)}</div>
          <div>integration={integrationLabel(compiledPlan?.integration_level)}</div>
          {draft?.validation ? (
            <div>
              validate scanned_rows={draft.validation.scanned_rows} | error_rows={draft.validation.error_rows} | errors_truncated=
              {draft.validation.errors_truncated ? "yes" : "no"}
            </div>
          ) : null}
        </div>
      </section>

      <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
          <strong>Job Logs</strong>
          <span style={{ fontSize: 12, color: "#7d6b57" }}>
            {selectedJobId || "未选择 job"} | space={effectiveCurrentSpace || "-"}
          </span>
        </div>
        <pre
          data-testid="import-job-logs"
          style={{
            margin: 0,
            padding: 14,
            borderRadius: 14,
            background: "#2f241c",
            color: "#fef2db",
            minHeight: 180,
            maxHeight: 320,
            overflow: "auto",
            fontSize: 12,
            lineHeight: 1.5,
          }}
        >
          {jobLogs.length > 0 ? jobLogs.join("\n") : "暂无日志"}
        </pre>
      </section>
    </div>
  );
}
