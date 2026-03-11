import { useEffect, useState } from "react";

import { parseApiError } from "../../utils/httpError";
import {
  cancelImportJob,
  downloadFailedRows,
  fetchImportSchema,
  fetchImportSchemaPlan,
  getImportJobLogs,
  previewImport,
  submitImportJob,
  upsertImportDraft,
  uploadImportFile,
  validateImportDraft,
} from "./api/import";
import { JobPanel } from "./components/JobPanel";
import { MappingTable } from "./components/MappingTable";
import { useImportJobs } from "./hooks/useImportJobs";
import type {
  CompiledImportPlan,
  ImportDraftResp,
  ImportFileUploadResp,
  ImportMode,
  ImportSchemaObjectPlan,
  ImportSchemaResp,
  ImportTargetMapping,
} from "./types/import";

type ImportWorkspaceProps = {
  onNotice: (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;
};

const SURFACE = "#f5efe4";
const CARD = "#fffaf1";
const VALIDATE_FIXED_NOTE =
  "Validate only checks CSV format, column mapping, and import rules. It is not a Nebula existence preflight and does not guarantee final write success.";
const INTEGRATION_FIXED_NOTE =
  "Import success does not automatically mean the data enters current search, discovery, or graph primary flows. Check integration level and integration warnings.";

function defaultFieldForColumn(column: string, mode: ImportMode) {
  const normalized = column.trim().toLowerCase();
  const vertexMap: Record<string, string> = {
    id: "ID",
    entity_name: "entity_name",
    entity_type: "entity_type",
    entity_raw_id: "entity_raw_id",
    description: "description",
    source: "source",
  };
  const edgeMap: Record<string, string> = {
    srcvid: "srcVID",
    dstvid: "dstVID",
    subject_our_defined_id: "srcVID",
    object_our_defined_id: "dstVID",
    relation: "relation",
    source: "source",
    pmid: "evidence",
    relation_detail: "evidence",
    score: "score",
    rank: "rank",
  };
  return mode === "edge" ? edgeMap[normalized] || "" : vertexMap[normalized] || "";
}

function buildDefaultTarget(mode: ImportMode, columns: string[]): ImportTargetMapping {
  return {
    object_type: mode === "edge" ? "edge_type" : "tag",
    object_name: mode === "edge" ? "REL2" : "Entity",
    discriminator_value: "",
    field_mappings: columns.map((column) => ({
      source_column: column,
      target_field: defaultFieldForColumn(column, mode),
    })),
  };
}

function downloadBlobToFile(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function formatTs(ts?: number | null) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function integrationLabel(level?: string | null) {
  if (level === "fully_integrated") return "fully integrated";
  if (level === "partially_integrated") return "partially integrated";
  if (level === "import_only") return "import-only";
  return "-";
}

export function ImportWorkspace({ onNotice }: ImportWorkspaceProps) {
  const [files, setFiles] = useState<ImportFileUploadResp[]>([]);
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof previewImport>> | null>(null);
  const [schema, setSchema] = useState<ImportSchemaResp | null>(null);
  const [mode, setMode] = useState<ImportMode>("vertex");
  const [discriminatorColumn, setDiscriminatorColumn] = useState("");
  const [targets, setTargets] = useState<ImportTargetMapping[]>([]);
  const [draft, setDraft] = useState<ImportDraftResp | null>(null);
  const [compiledPlan, setCompiledPlan] = useState<CompiledImportPlan | null>(null);
  const [schemaPlan, setSchemaPlan] = useState<ImportSchemaObjectPlan[]>([]);
  const [schemaWarnings, setSchemaWarnings] = useState<string[]>([]);
  const [integrationWarnings, setIntegrationWarnings] = useState<string[]>([]);
  const [createdBy, setCreatedBy] = useState("import_workspace");
  const [jobLogs, setJobLogs] = useState<string[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const { jobs, loading: jobsLoading, reload: reloadJobs } = useImportJobs(true);

  useEffect(() => {
    void (async () => {
      try {
        setSchema(await fetchImportSchema());
      } catch (error) {
        const parsed = parseApiError(error);
        onNotice({ level: "error", message: `加载 import schema 失败：${parsed.message}` });
      }
    })();
  }, [onNotice]);

  useEffect(() => {
    if (selectedJobId == null && jobs.length > 0) setSelectedJobId(jobs[0].job_id);
  }, [jobs, selectedJobId]);

  useEffect(() => {
    if (!preview?.columns?.length) return;
    if (targets.length === 0) {
      setTargets([buildDefaultTarget(mode, preview.columns)]);
      return;
    }
    setTargets((prev) =>
      prev.map((target) => ({
        ...target,
        field_mappings:
          target.field_mappings.length === preview.columns.length
            ? target.field_mappings
            : preview.columns.map((column) => ({
                source_column: column,
                target_field: defaultFieldForColumn(column, target.object_type === "edge_type" ? "edge" : "vertex"),
              })),
      }))
    );
  }, [mode, preview, targets.length]);

  useEffect(() => {
    if (!selectedJobId) {
      setJobLogs([]);
      return;
    }
    void (async () => {
      try {
        const logs = await getImportJobLogs(selectedJobId);
        setJobLogs(logs.lines);
      } catch {
        setJobLogs([]);
      }
    })();
  }, [selectedJobId, jobs]);

  async function handleUpload(fileList: FileList | null) {
    const nextFile = fileList?.[0];
    if (!nextFile) return;
    setBusy("upload");
    try {
      const uploaded = await uploadImportFile(nextFile);
      setFiles((prev) => [...prev, uploaded]);
      onNotice({ level: "info", message: `已上传 ${uploaded.original_name}` });
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `上传失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handlePreview() {
    if (files.length === 0) {
      onNotice({ level: "warn", message: "请先上传 CSV 文件" });
      return;
    }
    setBusy("preview");
    try {
      const nextPreview = await previewImport({
        file_ids: files.map((item) => item.file_id),
        sample_rows: 8,
        mode_hint: mode,
      });
      setPreview(nextPreview);
      onNotice(nextPreview.warnings.length > 0 ? { level: "warn", message: nextPreview.warnings[0] } : null);
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `预览失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handleSchemaPlan() {
    if (!preview) {
      onNotice({ level: "warn", message: "请先生成 preview" });
      return;
    }
    setBusy("schema_plan");
    try {
      const resp = await fetchImportSchemaPlan({
        file_ids: files.map((item) => item.file_id),
        mapping: targets,
        schema_options: {
          allow_create_object: true,
          allow_add_properties: true,
        },
      });
      setSchemaPlan(resp.schema_create_plan || []);
      setSchemaWarnings(resp.warnings || []);
      setIntegrationWarnings(resp.integration_warnings || []);
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `schema plan 失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handleSaveDraft() {
    if (!preview) {
      onNotice({ level: "warn", message: "请先完成 preview" });
      return;
    }
    setBusy("draft");
    try {
      const saved = await upsertImportDraft({
        draft_id: draft?.draft_id,
        mode,
        file_ids: files.map((item) => item.file_id),
        discriminator_column: mode === "mixed" ? discriminatorColumn : null,
        mapping: targets,
        update_strategy: { mode: "merge_partial", create_if_missing: true, update_existing: true },
        schema_options: { allow_create_object: true, allow_add_properties: true },
        postprocess_options: { refresh_metadata: true, sync_entity_es: true },
      });
      setDraft(saved);
      onNotice({ level: "info", message: `draft 已保存：${saved.draft_id}` });
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `draft 保存失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handleValidate() {
    if (!draft) {
      await handleSaveDraft();
    }
    if (!draft?.draft_id) return;
    setBusy("validate");
    try {
      const validation = await validateImportDraft(draft.draft_id);
      setDraft((prev) => (prev ? { ...prev, validation, status: validation.passed ? "validated" : prev.status } : prev));
      setCompiledPlan(validation.compiled_plan || null);
      setIntegrationWarnings(validation.integration_warnings || []);
      setSchemaWarnings(validation.warnings || []);
      onNotice(
        validation.passed
          ? { level: "info", message: `draft 校验通过，compiled plan=${validation.compiled_plan?.plan_id || "-"}` }
          : { level: "warn", message: validation.errors[0] || "draft 校验失败" }
      );
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `校验失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handleSubmitJob() {
    if (!draft?.draft_id) {
      onNotice({ level: "warn", message: "请先保存并校验 draft" });
      return;
    }
    setBusy("submit");
    try {
      const job = await submitImportJob({ draft_id: draft.draft_id, created_by: createdBy });
      setSelectedJobId(job.job_id);
      await reloadJobs();
      onNotice({ level: "info", message: `job 已提交：${job.job_id}` });
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `提交 job 失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handleDownloadFailedRows(jobId: string) {
    try {
      const blob = await downloadFailedRows(jobId);
      downloadBlobToFile(blob, `${jobId}_failed_rows.csv`);
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `failed rows 下载失败：${parsed.message}` });
    }
  }

  async function handleCancelJob(jobId: string) {
    try {
      await cancelImportJob(jobId);
      await reloadJobs();
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `取消 job 失败：${parsed.message}` });
    }
  }

  const schemaObjects = [
    ...(schema?.tags || []).map((item) => ({ ...item, object_type: "tag" as const })),
    ...(schema?.edge_types || []).map((item) => ({ ...item, object_type: "edge_type" as const })),
  ];

  return (
    <div
      style={{
        minHeight: "100dvh",
        overflow: "auto",
        background:
          "radial-gradient(circle at top left, rgba(202, 171, 114, 0.35), transparent 28%), linear-gradient(180deg, #f9f4ec 0%, #f0e7da 100%)",
        color: "#3d2d1f",
      }}
    >
      <div style={{ maxWidth: 1380, margin: "0 auto", padding: "28px 24px 48px", display: "grid", gap: 18 }}>
        <div
          style={{
            background: "linear-gradient(135deg, rgba(85, 56, 30, 0.95), rgba(129, 88, 45, 0.88))",
            color: "#fff7ed",
            borderRadius: 28,
            padding: 24,
            display: "grid",
            gap: 8,
            boxShadow: "0 24px 80px rgba(94, 63, 32, 0.18)",
          }}
        >
          <div style={{ fontSize: 13, letterSpacing: "0.18em", textTransform: "uppercase", opacity: 0.8 }}>Import Workspace</div>
          <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.1 }}>一期在线批量导入子系统</div>
          <div style={{ maxWidth: 880, fontSize: 14, color: "rgba(255,247,237,0.88)" }}>
            上传 CSV，完成 Draft 预览、列映射、schema create plan、校验、compiled plan 冻结与单 worker 串行 job 执行。
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.2fr) minmax(320px, 420px)", gap: 18 }}>
          <div style={{ display: "grid", gap: 18 }}>
            <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
                <strong>1. CSV Upload</strong>
                <input type="file" accept=".csv,text/csv" onChange={(event) => void handleUpload(event.target.files)} />
                <button onClick={() => void handlePreview()} disabled={busy === "preview"}>
                  生成预览
                </button>
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
                      background: SURFACE,
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
            </section>

            <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
                <strong>2. Draft</strong>
                <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span>Mode</span>
                  <select value={mode} onChange={(event) => setMode(event.target.value as ImportMode)}>
                    <option value="vertex">vertex</option>
                    <option value="edge">edge</option>
                    <option value="mixed">mixed</option>
                  </select>
                </label>
                {mode === "mixed" ? (
                  <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span>discriminator</span>
                    <input value={discriminatorColumn} onChange={(event) => setDiscriminatorColumn(event.target.value)} />
                  </label>
                ) : null}
                <button
                  onClick={() =>
                    setTargets((prev) => [...prev, buildDefaultTarget(mode === "mixed" ? "vertex" : mode, preview?.columns || [])])
                  }
                >
                  新增目标
                </button>
              </div>

              {preview ? (
                <div style={{ display: "grid", gap: 14 }}>
                  <div style={{ fontSize: 13, color: "#6c5b47" }}>
                    columns={preview.columns.join(", ")} | inferred={preview.inferred_mode_candidates.join(", ")}
                  </div>
                  {targets.map((target, index) => (
                    <MappingTable
                      key={`${target.object_name}-${index}`}
                      mode={mode}
                      target={target}
                      schemaObjects={schemaObjects}
                      onChange={(next) => setTargets((prev) => prev.map((item, itemIndex) => (itemIndex === index ? next : item)))}
                      onRemove={targets.length > 1 ? () => setTargets((prev) => prev.filter((_, itemIndex) => itemIndex !== index)) : undefined}
                    />
                  ))}
                  <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                    <button onClick={() => void handleSchemaPlan()}>生成 schema plan</button>
                    <button onClick={() => void handleSaveDraft()}>保存 draft</button>
                    <button onClick={() => void handleValidate()}>运行校验</button>
                    <button onClick={() => void handleSubmitJob()} disabled={!draft?.validation?.passed && !compiledPlan}>
                      提交 job
                    </button>
                    <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span>created_by</span>
                      <input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} />
                    </label>
                  </div>
                </div>
              ) : (
                <div style={{ color: "#7d6b57", fontSize: 13 }}>先上传并预览 CSV，再开始列映射。</div>
              )}
            </section>

            <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
              <strong>3. Preview / Plan</strong>
              {preview ? (
                <div style={{ display: "grid", gap: 14, marginTop: 14 }}>
                  <div style={{ padding: 12, borderRadius: 12, background: "#eef4ff", color: "#1d4f91", fontSize: 13 }}>
                    {VALIDATE_FIXED_NOTE}
                  </div>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: "#f6efe4" }}>
                          {preview.columns.map((column) => (
                            <th key={column} style={{ padding: 8, textAlign: "left" }}>
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.sample_rows.map((row, rowIndex) => (
                          <tr key={rowIndex} style={{ borderTop: "1px solid #f0e6d8" }}>
                            {preview.columns.map((column) => (
                              <td key={column} style={{ padding: 8 }}>
                                {row[column] || ""}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {schemaPlan.length > 0 ? (
                    <div style={{ display: "grid", gap: 12 }}>
                      {schemaPlan.map((item, index) => (
                        <div key={`${item.object_name}-${index}`} style={{ padding: 14, borderRadius: 14, background: SURFACE }}>
                          <div style={{ fontWeight: 700 }}>
                            {item.object_type} `{item.object_name}` {item.object_exists ? "(existing)" : "(new)"}
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
                          {item.integration_warnings.length > 0 ? (
                            <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
                              {item.integration_warnings.map((warning, warningIndex) => (
                                <div
                                  key={`${warning}-${warningIndex}`}
                                  style={{ padding: 10, borderRadius: 10, background: "#fff7e6", color: "#ad6800", fontSize: 13 }}
                                >
                                  {warning}
                                </div>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  ) : null}
                  {compiledPlan ? (
                    <div style={{ display: "grid", gap: 10 }}>
                      <div style={{ padding: 14, borderRadius: 14, background: "#eefbf1", fontSize: 13, color: "#166534" }}>
                        compiled plan frozen: {compiledPlan.plan_id} | mode={compiledPlan.mode} | integration=
                        {compiledPlan.integration_level}
                      </div>
                      <div style={{ padding: 12, borderRadius: 12, background: "#fffbe6", color: "#ad6800", fontSize: 13 }}>
                        {INTEGRATION_FIXED_NOTE}
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </section>
          </div>

          <div style={{ display: "grid", gap: 18 }}>
            <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
              <strong>Warnings</strong>
              <div style={{ display: "grid", gap: 10, marginTop: 14 }}>
                {schemaWarnings.length === 0 &&
                integrationWarnings.length === 0 &&
                (draft?.validation?.errors?.length || 0) === 0 &&
                (draft?.validation?.warnings?.length || 0) === 0 ? (
                  <div style={{ color: "#7d6b57", fontSize: 13 }}>暂无 validate/schema/integration 提示</div>
                ) : null}
                {draft?.validation?.errors?.length ? (
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#a61d24" }}>Validate Errors</div>
                ) : null}
                {schemaWarnings.map((warning, index) => (
                  <div key={`schema-${index}`} style={{ padding: 12, borderRadius: 12, background: "#fffbe6", color: "#ad6800" }}>
                    {warning}
                  </div>
                ))}
                {draft?.validation?.warnings?.length ? (
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#ad6800" }}>Validate Warnings</div>
                ) : null}
                {draft?.validation?.warnings?.map((warning, index) => (
                  <div key={`validate-warning-${index}`} style={{ padding: 12, borderRadius: 12, background: "#fffbe6", color: "#ad6800" }}>
                    {warning}
                  </div>
                ))}
                {draft?.validation?.semantic_notes?.map((note, index) => (
                  <div key={`semantic-note-${index}`} style={{ padding: 12, borderRadius: 12, background: "#eef4ff", color: "#1d4f91" }}>
                    {note}
                  </div>
                ))}
                {integrationWarnings.length > 0 ? (
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#8c4b11" }}>Integration Warnings</div>
                ) : null}
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
              </div>
            </section>

            <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
                <strong>Draft Snapshot</strong>
                <span style={{ fontSize: 12, color: "#7d6b57" }}>{draft ? `${draft.draft_id} | ${draft.status}` : "未保存"}</span>
              </div>
              <div style={{ display: "grid", gap: 6, fontSize: 13, color: "#5b4b38" }}>
                <div>mode={mode}</div>
                <div>files={files.map((item) => item.file_id).join(", ") || "-"}</div>
                <div>updated={formatTs(draft?.updated_at)}</div>
                <div>integration={integrationLabel(compiledPlan?.integration_level)}</div>
                <div>postprocess=metadata refresh + entity ES incremental sync</div>
                <div style={{ color: "#8c4b11" }}>{INTEGRATION_FIXED_NOTE}</div>
              </div>
            </section>

            <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginBottom: 14 }}>
                <strong>Job Logs</strong>
                <span style={{ fontSize: 12, color: "#7d6b57" }}>{selectedJobId || "未选择 job"}</span>
              </div>
              <pre
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
        </div>

        <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 16 }}>
            <strong>4. Import Jobs</strong>
            <div style={{ fontSize: 12, color: "#7d6b57" }}>{jobsLoading ? "jobs loading..." : `jobs=${jobs.length}`}</div>
          </div>
          <JobPanel
            jobs={jobs}
            selectedJobId={selectedJobId}
            onSelect={setSelectedJobId}
            onCancel={(jobId) => void handleCancelJob(jobId)}
            onDownloadFailedRows={(jobId) => void handleDownloadFailedRows(jobId)}
          />
        </section>
      </div>
    </div>
  );
}
