import { MappingTable } from "./MappingTable";
import { formatBytes } from "../utils";
import type {
  CompiledImportPlan,
  ImportDraftResp,
  ImportFileUploadResp,
  ImportMode,
  ImportSchemaObject,
  ImportSchemaObjectPlan,
  ImportSource,
  ImportTargetMapping,
} from "../types/import";

type ImportFlowPanelsProps = {
  canRunImportFlow: boolean;
  compiledPlan: CompiledImportPlan | null;
  createdBy: string;
  currentIntegrationScope: string;
  currentSpaceStatus: string;
  draft: ImportDraftResp | null;
  draftTotalBytes: number;
  effectiveCurrentSpace: string;
  files: ImportFileUploadResp[];
  importBlockedReason: string;
  onAddTarget: () => void;
  onCreatedByChange: (value: string) => void;
  onPreview: () => void;
  onRemoveTarget: (index: number) => void;
  onSaveDraft: () => void;
  onSchemaPlan: () => void;
  onSubmitJob: () => void;
  onUpdateTarget: (index: number, nextTarget: ImportTargetMapping) => void;
  onUpload: (fileList: FileList | null) => void;
  onValidate: () => void;
  schemaObjects: ImportSchemaObject[];
  schemaPlan: ImportSchemaObjectPlan[];
  sources: ImportSource[];
  spaceSwitchNote: string;
  submittingJob: boolean;
  surface: string;
  targets: ImportTargetMapping[];
  validateFixedNote: string;
  integrationFixedNote: string;
  workspaceMode: ImportMode;
  onWorkspaceModeChange: (mode: ImportMode) => void;
};

const CARD = "#fffaf1";
const IMPORT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
const IMPORT_MAX_DRAFT_TOTAL_BYTES = 200 * 1024 * 1024;
const IMPORT_MAX_DRAFT_FILES = 5;

export function ImportFlowPanels({
  canRunImportFlow,
  compiledPlan,
  createdBy,
  currentIntegrationScope,
  currentSpaceStatus,
  draft,
  draftTotalBytes,
  effectiveCurrentSpace,
  files,
  importBlockedReason,
  onAddTarget,
  onCreatedByChange,
  onPreview,
  onRemoveTarget,
  onSaveDraft,
  onSchemaPlan,
  onSubmitJob,
  onUpdateTarget,
  onUpload,
  onValidate,
  schemaObjects,
  schemaPlan,
  sources,
  spaceSwitchNote,
  submittingJob,
  surface,
  targets,
  validateFixedNote,
  integrationFixedNote,
  workspaceMode,
  onWorkspaceModeChange,
}: ImportFlowPanelsProps) {
  return (
    <div style={{ display: "grid", gap: 18 }}>
      <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <strong>1. Upload + Sources</strong>
          <span style={{ fontSize: 12, color: "#7d6b57" }}>target space={effectiveCurrentSpace || "-"}</span>
          <span style={{ fontSize: 12, color: "#7d6b57" }}>status={currentSpaceStatus}</span>
          <input
            data-testid="import-file-input"
            type="file"
            accept=".csv,text/csv"
            disabled={!canRunImportFlow}
            onChange={(event) => {
              onUpload(event.target.files);
              event.target.value = "";
            }}
          />
          <button data-testid="import-preview-button" onClick={onPreview} disabled={!canRunImportFlow}>
            生成 Sources 预览
          </button>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>workspace_mode</span>
            <select value={workspaceMode} onChange={(event) => onWorkspaceModeChange(event.target.value as ImportMode)}>
              <option value="vertex">vertex</option>
              <option value="edge">edge</option>
              <option value="mixed">mixed</option>
            </select>
          </label>
        </div>
        <div style={{ marginBottom: 12, padding: 10, borderRadius: 12, background: "#f6efe4", color: "#6c5b47", fontSize: 13 }}>
          {spaceSwitchNote}
        </div>
        <div style={{ marginBottom: 12, padding: 12, borderRadius: 12, background: "#eef4ff", color: "#1d4f91", fontSize: 13 }}>
          <div>CSV only</div>
          <div>Max file size: {formatBytes(IMPORT_MAX_UPLOAD_BYTES)}</div>
          <div>Max draft total size: {formatBytes(IMPORT_MAX_DRAFT_TOTAL_BYTES)}</div>
          <div>Preview returns per-source columns/sample rows and inferred kind</div>
        </div>
        {!canRunImportFlow ? (
          <div style={{ marginBottom: 12, padding: 10, borderRadius: 12, background: "#fff1f0", color: "#a61d24", fontSize: 13 }}>
            {importBlockedReason}
          </div>
        ) : null}
        <div style={{ marginBottom: 12, fontSize: 13, color: "#6c5b47" }}>
          uploaded files={files.length}/{IMPORT_MAX_DRAFT_FILES} | draft total={formatBytes(draftTotalBytes)} /{" "}
          {formatBytes(IMPORT_MAX_DRAFT_TOTAL_BYTES)}
        </div>
        <div style={{ display: "grid", gap: 8 }}>
          {files.map((file) => (
            <div
              key={file.file_id}
              style={{
                display: "flex",
                gap: 12,
                flexWrap: "wrap",
                padding: 12,
                borderRadius: 14,
                background: surface,
                fontSize: 13,
              }}
            >
              <strong>{file.original_name}</strong>
              <span>id={file.file_id}</span>
              <span>{file.detected_encoding}</span>
              <span>delimiter={file.detected_delimiter}</span>
              <span>{file.size_bytes} bytes</span>
            </div>
          ))}
        </div>
        {sources.length > 0 ? (
          <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
            {sources.map((source) => (
              <div
                key={source.source_id}
                data-testid={`import-source-card-${source.source_id}`}
                style={{ padding: 14, borderRadius: 14, background: "#fffdf8", border: "1px solid #f0e6d8" }}
              >
                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <strong>{source.filename}</strong>
                  <span style={{ fontSize: 12, color: "#7d6b57" }}>source_id={source.source_id}</span>
                  <span style={{ fontSize: 12, color: "#7d6b57" }}>kind={source.inferred_kind}</span>
                  <span style={{ fontSize: 12, color: "#7d6b57" }}>recommend={source.recommended_object_type || "-"}</span>
                </div>
                <div style={{ marginTop: 8, fontSize: 13, color: "#5b4b38" }}>columns={source.columns.join(", ")}</div>
                {source.alias_hints.length > 0 ? (
                  <div style={{ marginTop: 8, fontSize: 13, color: "#1d4f91" }}>
                    alias hints={source.alias_hints.map((item) => `${item.source_column}->${item.logical_field}`).join(", ")}
                  </div>
                ) : null}
                {source.sample_rows.length > 0 ? (
                  <div style={{ overflowX: "auto", marginTop: 10 }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: "#f6efe4" }}>
                          {source.columns.map((column) => (
                            <th key={column} style={{ textAlign: "left", padding: 6 }}>
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {source.sample_rows.slice(0, 3).map((row, index) => (
                          <tr key={index} style={{ borderTop: "1px solid #f0e6d8" }}>
                            {source.columns.map((column) => (
                              <td key={column} style={{ padding: 6 }}>
                                {row[column] || ""}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <strong>2. Targets</strong>
          <button onClick={onAddTarget} disabled={!canRunImportFlow || sources.length === 0}>
            新增 Target
          </button>
          <button data-testid="import-save-draft-button" onClick={onSaveDraft} disabled={!canRunImportFlow || sources.length === 0}>
            保存 draft
          </button>
          <button data-testid="import-validate-button" onClick={onValidate} disabled={!canRunImportFlow || sources.length === 0}>
            运行 Validate
          </button>
          <button onClick={onSchemaPlan} disabled={!canRunImportFlow || sources.length === 0}>
            生成 Plan
          </button>
          <button
            data-testid="import-submit-job-button"
            onClick={onSubmitJob}
            disabled={(!draft?.validation?.passed && !compiledPlan) || !canRunImportFlow || submittingJob}
          >
            提交 Job
          </button>
          <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span>created_by</span>
            <input value={createdBy} onChange={(event) => onCreatedByChange(event.target.value)} />
          </label>
        </div>

        {targets.length > 0 ? (
          <div style={{ display: "grid", gap: 14 }}>
            {targets.map((target, index) => (
              <MappingTable
                key={target.target_id || `${target.object_name}-${index}`}
                target={target}
                sources={sources}
                schemaObjects={schemaObjects}
                onChange={(next) => onUpdateTarget(index, next)}
                onRemove={targets.length > 1 ? () => onRemoveTarget(index) : undefined}
              />
            ))}
          </div>
        ) : (
          <div style={{ color: "#7d6b57", fontSize: 13 }}>先上传并预览 CSV，再创建 target。</div>
        )}
      </section>

      <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <strong>3. Plan / Validate</strong>
          <span style={{ fontSize: 12, color: "#7d6b57" }}>space={effectiveCurrentSpace || "-"}</span>
          <span style={{ fontSize: 12, color: "#7d6b57" }}>scope={currentIntegrationScope}</span>
        </div>
        <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
          <div style={{ padding: 12, borderRadius: 12, background: "#eef4ff", color: "#1d4f91", fontSize: 13 }}>
            {validateFixedNote}
          </div>
          {draft?.validation?.target_results?.length ? (
            <div style={{ display: "grid", gap: 12 }}>
              {draft.validation.target_results.map((item) => (
                <div key={item.target_id} style={{ padding: 14, borderRadius: 14, background: surface }}>
                  <div style={{ fontWeight: 700 }}>
                    {item.object_type} `{item.object_name}` | source={item.source_id} | {item.passed ? "passed" : "failed"}
                  </div>
                  <div style={{ marginTop: 6, fontSize: 13 }}>columns={item.source_columns.join(", ")}</div>
                  <div style={{ marginTop: 6, fontSize: 13 }}>
                    scanned_rows={item.scanned_rows} | error_rows={item.error_rows}
                  </div>
                  {item.hints.length > 0 ? (
                    <div style={{ marginTop: 6, fontSize: 13, color: "#1d4f91" }}>hints={item.hints.join(" | ")}</div>
                  ) : null}
                  {item.errors.map((error, index) => (
                    <div key={`${item.target_id}-error-${index}`} style={{ marginTop: 6, color: "#a61d24", fontSize: 13 }}>
                      {error}
                    </div>
                  ))}
                  {item.warnings.map((warning, index) => (
                    <div key={`${item.target_id}-warning-${index}`} style={{ marginTop: 6, color: "#ad6800", fontSize: 13 }}>
                      {warning}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          ) : null}

          {schemaPlan.length > 0 ? (
            <div style={{ display: "grid", gap: 12 }}>
              {schemaPlan.map((item) => (
                <div key={`${item.target_id}-${item.object_name}`} style={{ padding: 14, borderRadius: 14, background: "#fffdf8" }}>
                  <div style={{ fontWeight: 700 }}>
                    {`${item.object_type} "${item.object_name}" <- source ${item.source_id} ${item.object_exists ? "(existing)" : "(new)"}`}
                  </div>
                  <div style={{ marginTop: 6, fontSize: 13 }}>
                    add_properties:
                    {item.add_properties.length > 0
                      ? ` ${item.add_properties.map((prop) => `${prop.name}:${prop.type}`).join(", ")}`
                      : " none"}
                  </div>
                  {item.ignored_columns.length > 0 ? (
                    <div style={{ marginTop: 6, fontSize: 13, color: "#7d6b57" }}>
                      ignored columns: {item.ignored_columns.join(", ")}
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}

          {compiledPlan ? (
            <div style={{ display: "grid", gap: 10 }}>
              <div data-testid="import-compiled-plan-summary" style={{ padding: 14, borderRadius: 14, background: "#eefbf1", fontSize: 13, color: "#166534" }}>
                compiled plan frozen: {compiledPlan.plan_id} | workspace={compiledPlan.workspace_mode} | integration=
                {compiledPlan.integration_level} | space={compiledPlan.space_name}
              </div>
              {compiledPlan.targets.map((target) => (
                <div key={target.target_id} style={{ padding: 12, borderRadius: 12, background: "#f7f0e4", fontSize: 13 }}>
                  {`${target.object_type} "${target.object_name}" <- ${target.source_filename} | columns=${target.source_columns.join(", ")}`}
                </div>
              ))}
              <div style={{ padding: 12, borderRadius: 12, background: "#fffbe6", color: "#ad6800", fontSize: 13 }}>
                {integrationFixedNote}
              </div>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
