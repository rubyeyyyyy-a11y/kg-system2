import { useEffect, useMemo, useRef, useState } from "react";

import { parseApiError } from "../../utils/httpError";
import {
  cancelImportJob,
  downloadFailedRows,
  downloadImportArtifact,
  fetchImportSchema,
  fetchImportSchemaPlan,
  getImportJobLogs,
  previewImport,
  submitImportJob,
  upsertImportDraft,
  uploadImportFile,
  validateImportDraft,
} from "./api/import";
import { ImportSpaceContextBar } from "./components/ImportSpaceContextBar";
import { JobPanel } from "./components/JobPanel";
import { MappingTable } from "./components/MappingTable";
import { useImportJobs } from "./hooks/useImportJobs";
import { useCreateSpace } from "../space/hooks/useCreateSpace";
import { useCurrentSpace } from "../space/hooks/useCurrentSpace";
import type { CurrentSpaceResp, SpaceSummary } from "../space/types/space";
import type {
  CompiledImportPlan,
  ImportDraftResp,
  ImportFileUploadResp,
  ImportMode,
  ImportObjectType,
  ImportSchemaObjectPlan,
  ImportSchemaResp,
  ImportSource,
  ImportTargetMapping,
} from "./types/import";

type ImportWorkspaceProps = {
  onNotice: (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;
  spaces: SpaceSummary[];
  resolvedCurrent: CurrentSpaceResp | null;
  loadingSpaces: boolean;
  spacesError: string | null;
  refreshSpaces: () => Promise<void>;
  spaceSwitching: boolean;
  spaceSwitchPhase: string;
};

const SURFACE = "#f5efe4";
const CARD = "#fffaf1";
const VALIDATE_FIXED_NOTE =
  "Validate 现在按 target 使用各自 source 校验 identity/property/schema，不再共享第一份文件 columns。";
const INTEGRATION_FIXED_NOTE =
  "Import success does not automatically mean the data enters current search, discovery, or graph primary flows. Check integration level and integration warnings.";
const SPACE_SWITCH_NOTE =
  "Switching current space changes where draft validation, compiled plan freeze, job submission, metadata refresh, and entity ES sync will land.";
const IMPORT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
const IMPORT_MAX_DRAFT_TOTAL_BYTES = 200 * 1024 * 1024;
const IMPORT_MAX_DRAFT_FILES = 5;
const IMPORT_PREVIEW_ROWS = 50;
const LARGE_UPLOAD_HINT_BYTES = 50 * 1024 * 1024;

function formatBytes(bytes: number) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function normalizeColumn(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function aliasLogicalField(column: string) {
  const token = normalizeColumn(column);
  const lookup: Record<string, string> = {
    id: "ID",
    vid: "ID",
    srcvid: "srcVID",
    src_vid: "srcVID",
    subjectourdefinedid: "srcVID",
    dstvid: "dstVID",
    dst_vid: "dstVID",
    objectourdefinedid: "dstVID",
    rank: "rank",
    relation: "relation",
    source: "source",
    evidence: "evidence",
    pmid: "evidence",
    relationdetail: "evidence",
    score: "score",
    entityname: "entity_name",
    entitytype: "entity_type",
    entityrawid: "entity_raw_id",
    description: "description",
  };
  return lookup[token] || "";
}

function suggestTargetFromSource(source: ImportSource, objectType?: ImportObjectType): ImportTargetMapping {
  const nextObjectType = objectType || source.recommended_object_type || (source.inferred_kind === "edge" ? "edge_type" : "tag");
  const aliasMap = new Map(source.alias_hints.map((item) => [item.logical_field, item.source_column]));
  const identity_mapping =
    nextObjectType === "tag"
      ? { id_column: aliasMap.get("ID") || "" }
      : {
          src_column: aliasMap.get("srcVID") || "",
          dst_column: aliasMap.get("dstVID") || "",
          rank_column: aliasMap.get("rank") || "",
        };
  const identityColumns = new Set(Object.values(identity_mapping).filter(Boolean));
  const property_mappings = source.columns
    .filter((column) => !identityColumns.has(column))
    .map((column) => ({
      source_column: column,
      target_field: aliasLogicalField(column) || column,
      logical_field: aliasLogicalField(column) || undefined,
    }));
  return {
    object_type: nextObjectType,
    object_name: nextObjectType === "tag" ? "Entity" : "REL2",
    source_id: source.source_id,
    identity_mapping,
    property_mappings,
    row_selector: null,
    target_options: {},
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

export function ImportWorkspace({
  onNotice,
  spaces,
  resolvedCurrent,
  loadingSpaces,
  spacesError,
  refreshSpaces,
  spaceSwitching,
  spaceSwitchPhase,
}: ImportWorkspaceProps) {
  const { currentSpace, setCurrentSpace } = useCurrentSpace();
  const { createSpace, submitting: creatingSpace, error: createSpaceError } = useCreateSpace();
  const [files, setFiles] = useState<ImportFileUploadResp[]>([]);
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof previewImport>> | null>(null);
  const [schema, setSchema] = useState<ImportSchemaResp | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<ImportMode>("vertex");
  const [sources, setSources] = useState<ImportSource[]>([]);
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
  const [createPanelOpen, setCreatePanelOpen] = useState(false);
  const [spaceActionSummary, setSpaceActionSummary] = useState<{ title: string; message: string } | null>(null);
  const { jobs, loading: jobsLoading, reload: reloadJobs } = useImportJobs(true);
  const effectiveCurrentSpace = currentSpace || resolvedCurrent?.space_name || "";
  const selectedSpace = useMemo(
    () => spaces.find((item) => item.space_name === effectiveCurrentSpace) || null,
    [effectiveCurrentSpace, spaces]
  );
  const defaultSpaceName = useMemo(() => {
    const fromRegistry = spaces.find((item) => item.created_by === "system");
    if (fromRegistry) return fromRegistry.space_name;
    if (resolvedCurrent?.source === "default") return resolvedCurrent.space_name;
    return "";
  }, [resolvedCurrent, spaces]);
  const lastSpaceRef = useRef("");
  const draftTotalBytes = useMemo(() => files.reduce((sum, item) => sum + item.size_bytes, 0), [files]);

  function clearFileBoundState() {
    setPreview(null);
    setSources([]);
    setTargets([]);
    setDraft(null);
    setCompiledPlan(null);
    setSchemaPlan([]);
    setSchemaWarnings([]);
    setIntegrationWarnings([]);
  }

  function clearSpaceBoundState() {
    clearFileBoundState();
    setJobLogs([]);
    setSelectedJobId(null);
  }

  function validateSelectedUpload(file: File) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      return "类型不支持：仅支持 CSV 文件。";
    }
    if (files.length >= IMPORT_MAX_DRAFT_FILES) {
      return `当前 draft 最多允许 ${IMPORT_MAX_DRAFT_FILES} 个文件。`;
    }
    if (file.size > IMPORT_MAX_UPLOAD_BYTES) {
      return `文件过大：单文件上限 ${formatBytes(IMPORT_MAX_UPLOAD_BYTES)}。`;
    }
    if (draftTotalBytes + file.size > IMPORT_MAX_DRAFT_TOTAL_BYTES) {
      return `draft 总大小超限：总上限 ${formatBytes(IMPORT_MAX_DRAFT_TOTAL_BYTES)}。`;
    }
    return "";
  }

  function describeUploadFailure(error: unknown) {
    const parsed = parseApiError(error);
    if (parsed.code === "IMPORT_UPLOAD_TOO_LARGE") {
      return `文件过大：单文件上限 ${formatBytes(IMPORT_MAX_UPLOAD_BYTES)}。`;
    }
    if (parsed.code === "IMPORT_DRAFT_TOTAL_SIZE_EXCEEDED") {
      return `draft 总大小超限：总上限 ${formatBytes(IMPORT_MAX_DRAFT_TOTAL_BYTES)}。`;
    }
    if (parsed.code === "IMPORT_UNSUPPORTED_FILE_TYPE" || parsed.code === "IMPORT_UNSUPPORTED_CONTENT_TYPE") {
      return "类型不支持：仅支持 CSV 文件。";
    }
    if (parsed.message.includes("Request timeout")) {
      return "网络或超时：上传大文件超时，请检查网络后重试。";
    }
    if (parsed.status == null) {
      return "网络或超时：请求未成功到达服务端。";
    }
    return parsed.message;
  }

  useEffect(() => {
    void (async () => {
      try {
        setSchema(await fetchImportSchema());
      } catch (error) {
        const parsed = parseApiError(error);
        onNotice({ level: "error", message: `加载 import schema 失败：${parsed.message}` });
      }
    })();
  }, [effectiveCurrentSpace, onNotice]);

  useEffect(() => {
    if (!effectiveCurrentSpace) return;
    if (lastSpaceRef.current && lastSpaceRef.current !== effectiveCurrentSpace) {
      clearSpaceBoundState();
      onNotice({
        level: "info",
        message: `current space 已切换到 ${effectiveCurrentSpace}。请重新 preview / validate，再提交新的 import job。`,
      });
    }
    lastSpaceRef.current = effectiveCurrentSpace;
  }, [effectiveCurrentSpace, onNotice]);

  useEffect(() => {
    if (jobs.length === 0) {
      if (selectedJobId != null) setSelectedJobId(null);
      return;
    }
    if (selectedJobId == null) {
      setSelectedJobId(jobs[0].job_id);
      return;
    }
    if (!jobs.some((job) => job.job_id === selectedJobId)) setSelectedJobId(jobs[0].job_id);
  }, [jobs, selectedJobId]);

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

  useEffect(() => {
    if (!preview) return;
    setSources(preview.sources || []);
    if (preview.workspace_mode_candidates.length > 0) {
      setWorkspaceMode(preview.workspace_mode_candidates[0]);
    }
    if (targets.length === 0 && preview.sources.length > 0) {
      const nextTargets = preview.sources.map((source) => suggestTargetFromSource(source));
      setTargets(nextTargets);
    }
  }, [preview]);

  const schemaObjects = [
    ...(schema?.tags || []).map((item) => ({ ...item, object_type: "tag" as const })),
    ...(schema?.edge_types || []).map((item) => ({ ...item, object_type: "edge_type" as const })),
  ];
  const currentSpaceStatus = selectedSpace?.status || resolvedCurrent?.registry_status || "-";
  const currentTemplateType = selectedSpace?.template_type || "-";
  const currentIntegrationScope = selectedSpace?.integration_scope || "-";
  const importBlockedReason =
    currentSpaceStatus === "ready"
      ? ""
      : currentSpaceStatus === "provisioning"
        ? `当前 space ${effectiveCurrentSpace || "-"} 仍在 provisioning，暂时不能执行 import。`
        : currentSpaceStatus === "failed"
          ? `当前 space ${effectiveCurrentSpace || "-"} provisioning 失败，暂时不能执行 import。`
          : `当前 space ${effectiveCurrentSpace || "-"} 尚未 ready，暂时不能执行 import。`;
  const canRunImportFlow = !!effectiveCurrentSpace && currentSpaceStatus === "ready";

  function ensureImportReady(actionLabel: string) {
    if (canRunImportFlow) return true;
    onNotice({ level: "warn", message: `${actionLabel}已阻止：${importBlockedReason}` });
    return false;
  }

  async function handleSelectSpace(spaceName: string) {
    if (!spaceName || spaceName === effectiveCurrentSpace) return;
    setCurrentSpace(spaceName);
    setCreatePanelOpen(false);
    setSpaceActionSummary({
      title: `Current space switched to ${spaceName}`,
      message: "Current-space switch coordinator is refreshing readiness and index status. Re-run preview and validate before submitting a new job.",
    });
  }

  async function handleCreateSpace(payload: {
    space_name: string;
    display_name: string;
    description: string;
    template_type: "entity_rel2_default";
    created_by: string;
  }) {
    const resp = await createSpace(payload, { autoSelect: true });
    setCreatePanelOpen(false);
    setSpaceActionSummary({
      title: `Space ${resp.space.space_name} is ready and selected`,
      message: "Next step: upload CSV in this Import Workspace. The current-space switch coordinator will refresh readiness and index status for the new space automatically.",
    });
    onNotice({
      level: "info",
      message: `space ${resp.space.space_name} 已创建并自动切换，下一步请上传 CSV。`,
    });
    return resp;
  }

  async function handleUpload(fileList: FileList | null) {
    if (!ensureImportReady("上传")) return;
    const nextFile = fileList?.[0];
    if (!nextFile) return;
    const selectionError = validateSelectedUpload(nextFile);
    if (selectionError) {
      onNotice({ level: "warn", message: selectionError });
      return;
    }
    setBusy("upload");
    try {
      if (nextFile.size >= LARGE_UPLOAD_HINT_BYTES) {
        onNotice({ level: "info", message: "Uploading large CSV... Files near 100MB may take longer." });
      }
      const uploaded = await uploadImportFile(nextFile);
      clearFileBoundState();
      setFiles((prev) => [...prev, uploaded]);
      onNotice({
        level: "info",
        message: `已上传 ${uploaded.original_name} (${formatBytes(uploaded.size_bytes)}). Preview 会为每个文件生成 source snapshot。`,
      });
    } catch (error) {
      onNotice({ level: "error", message: `上传失败：${describeUploadFailure(error)}` });
    } finally {
      setBusy(null);
    }
  }

  async function handlePreview() {
    if (!ensureImportReady("Preview")) return;
    if (files.length === 0) {
      onNotice({ level: "warn", message: "请先上传 CSV 文件" });
      return;
    }
    setBusy("preview");
    try {
      const nextPreview = await previewImport({
        file_ids: files.map((item) => item.file_id),
        sample_rows: IMPORT_PREVIEW_ROWS,
        mode_hint: workspaceMode,
      });
      setPreview(nextPreview);
      onNotice(
        nextPreview.sources.length > 0
          ? { level: "info", message: `preview 已生成 ${nextPreview.sources.length} 个 draft source` }
          : { level: "warn", message: "preview 未返回 source" }
      );
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `预览失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handleSchemaPlan() {
    if (!ensureImportReady("Schema plan")) return;
    if (sources.length === 0) {
      onNotice({ level: "warn", message: "请先生成 preview / sources" });
      return;
    }
    setBusy("schema_plan");
    try {
      const resp = await fetchImportSchemaPlan({
        file_ids: files.map((item) => item.file_id),
        sources,
        mapping: targets,
        schema_options: {
          allow_create_object: true,
          allow_add_properties: true,
        },
        workspace_mode: workspaceMode,
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

  async function persistDraft() {
    const saved = await upsertImportDraft({
      draft_id: draft?.draft_id,
      workspace_mode: workspaceMode,
      file_ids: files.map((item) => item.file_id),
      sources,
      mapping: targets,
      update_strategy: { mode: "merge_partial", create_if_missing: true, update_existing: true },
      schema_options: { allow_create_object: true, allow_add_properties: true },
      postprocess_options: { refresh_metadata: true, sync_entity_es: true },
    });
    setDraft(saved);
    return saved;
  }

  async function handleSaveDraft() {
    if (!ensureImportReady("保存 draft")) return;
    if (sources.length === 0) {
      onNotice({ level: "warn", message: "请先完成 preview" });
      return;
    }
    setBusy("draft");
    try {
      const saved = await persistDraft();
      onNotice({ level: "info", message: `draft 已保存：${saved.draft_id}` });
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `draft 保存失败：${parsed.message}` });
    } finally {
      setBusy(null);
    }
  }

  async function handleValidate() {
    if (!ensureImportReady("校验")) return;
    setBusy("validate");
    try {
      const currentDraft = draft?.draft_id ? draft : await persistDraft();
      const validation = await validateImportDraft(currentDraft.draft_id);
      setDraft((prev) =>
        prev ? { ...prev, validation, status: validation.passed ? "validated" : prev.status, sources, mapping: targets } : currentDraft
      );
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
    if (!ensureImportReady("提交 job")) return;
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

  async function handleDownloadArtifact(jobId: string, artifactName: string) {
    try {
      const blob = await downloadImportArtifact(jobId, artifactName);
      downloadBlobToFile(blob, artifactName);
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `artifact 下载失败：${parsed.message}` });
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
      <div style={{ maxWidth: 1480, margin: "0 auto", padding: "28px 24px 48px", display: "grid", gap: 18 }}>
        <div style={{ position: "sticky", top: 12, zIndex: 20 }}>
          <ImportSpaceContextBar
            currentSpace={effectiveCurrentSpace}
            current={selectedSpace}
            resolvedCurrent={resolvedCurrent}
            spaces={spaces}
            loading={loadingSpaces}
            error={createSpaceError || spacesError}
            spaceSwitching={spaceSwitching}
            spaceSwitchPhase={spaceSwitchPhase}
            defaultSpaceName={defaultSpaceName}
            createOpen={createPanelOpen}
            createSubmitting={creatingSpace}
            createError={createSpaceError}
            actionSummary={spaceActionSummary}
            onDismissActionSummary={() => setSpaceActionSummary(null)}
            onSelectSpace={(spaceName) => {
              void handleSelectSpace(spaceName);
            }}
            onOpenCreate={() => setCreatePanelOpen(true)}
            onCloseCreate={() => setCreatePanelOpen(false)}
            onRefresh={() => {
              void refreshSpaces();
              void reloadJobs();
            }}
            onCreateSpace={handleCreateSpace}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.35fr) minmax(360px, 460px)", gap: 18 }}>
          <div style={{ display: "grid", gap: 18 }}>
            <section style={{ borderRadius: 24, background: CARD, padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
                <strong>1. Upload + Sources</strong>
                <span style={{ fontSize: 12, color: "#7d6b57" }}>target space={effectiveCurrentSpace || "-"}</span>
                <span style={{ fontSize: 12, color: "#7d6b57" }}>status={currentSpaceStatus}</span>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  disabled={!canRunImportFlow}
                  onChange={(event) => {
                    void handleUpload(event.target.files);
                    event.target.value = "";
                  }}
                />
                <button onClick={() => void handlePreview()} disabled={busy === "preview" || !canRunImportFlow}>
                  生成 Sources 预览
                </button>
                <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span>workspace_mode</span>
                  <select value={workspaceMode} onChange={(event) => setWorkspaceMode(event.target.value as ImportMode)}>
                    <option value="vertex">vertex</option>
                    <option value="edge">edge</option>
                    <option value="mixed">mixed</option>
                  </select>
                </label>
              </div>
              <div style={{ marginBottom: 12, padding: 10, borderRadius: 12, background: "#f6efe4", color: "#6c5b47", fontSize: 13 }}>
                {SPACE_SWITCH_NOTE}
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
              {sources.length > 0 ? (
                <div style={{ display: "grid", gap: 12, marginTop: 16 }}>
                  {sources.map((source) => (
                    <div key={source.source_id} style={{ padding: 14, borderRadius: 14, background: "#fffdf8", border: "1px solid #f0e6d8" }}>
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
                <button
                  onClick={() => {
                    const nextSource = sources[0];
                    if (!nextSource) return;
                    setTargets((prev) => [...prev, suggestTargetFromSource(nextSource)]);
                  }}
                  disabled={!canRunImportFlow || sources.length === 0}
                >
                  新增 Target
                </button>
                <button onClick={() => void handleSaveDraft()} disabled={!canRunImportFlow || sources.length === 0}>
                  保存 draft
                </button>
                <button onClick={() => void handleValidate()} disabled={!canRunImportFlow || sources.length === 0}>
                  运行 Validate
                </button>
                <button onClick={() => void handleSchemaPlan()} disabled={!canRunImportFlow || sources.length === 0}>
                  生成 Plan
                </button>
                <button onClick={() => void handleSubmitJob()} disabled={(!draft?.validation?.passed && !compiledPlan) || !canRunImportFlow}>
                  提交 Job
                </button>
                <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span>created_by</span>
                  <input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} />
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
                      onChange={(next) => setTargets((prev) => prev.map((item, itemIndex) => (itemIndex === index ? next : item)))}
                      onRemove={targets.length > 1 ? () => setTargets((prev) => prev.filter((_, itemIndex) => itemIndex !== index)) : undefined}
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
                  {VALIDATE_FIXED_NOTE}
                </div>
                {draft?.validation?.target_results?.length ? (
                  <div style={{ display: "grid", gap: 12 }}>
                    {draft.validation.target_results.map((item) => (
                      <div key={item.target_id} style={{ padding: 14, borderRadius: 14, background: SURFACE }}>
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
                    <div style={{ padding: 14, borderRadius: 14, background: "#eefbf1", fontSize: 13, color: "#166534" }}>
                      compiled plan frozen: {compiledPlan.plan_id} | workspace={compiledPlan.workspace_mode} | integration=
                      {compiledPlan.integration_level} | space={compiledPlan.space_name}
                    </div>
                    {compiledPlan.targets.map((target) => (
                      <div key={target.target_id} style={{ padding: 12, borderRadius: 12, background: "#f7f0e4", fontSize: 13 }}>
                        {`${target.object_type} "${target.object_name}" <- ${target.source_filename} | columns=${target.source_columns.join(", ")}`}
                      </div>
                    ))}
                    <div style={{ padding: 12, borderRadius: 12, background: "#fffbe6", color: "#ad6800", fontSize: 13 }}>
                      {INTEGRATION_FIXED_NOTE}
                    </div>
                  </div>
                ) : null}
              </div>
            </section>
          </div>

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
                <span style={{ fontSize: 12, color: "#7d6b57" }}>{draft ? `${draft.draft_id} | ${draft.status}` : "未保存"}</span>
              </div>
              <div style={{ display: "grid", gap: 6, fontSize: 13, color: "#5b4b38" }}>
                <div>space={draft?.space_name || effectiveCurrentSpace || "-"}</div>
                <div>template={currentTemplateType}</div>
                <div>workspace_mode={workspaceMode}</div>
                <div>sources={sources.map((item) => item.source_id).join(", ") || "-"}</div>
                <div>targets={targets.length}</div>
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
            <strong>4. Jobs</strong>
            <div style={{ fontSize: 12, color: "#7d6b57" }}>
              {jobsLoading ? "jobs loading..." : `jobs=${jobs.length}`} | space={effectiveCurrentSpace || "-"}
            </div>
          </div>
          <JobPanel
            jobs={jobs}
            selectedJobId={selectedJobId}
            onSelect={setSelectedJobId}
            onCancel={(jobId) => void handleCancelJob(jobId)}
            onDownloadFailedRows={(jobId) => void handleDownloadFailedRows(jobId)}
            onDownloadArtifact={(jobId, artifactName) => void handleDownloadArtifact(jobId, artifactName)}
          />
        </section>
      </div>
    </div>
  );
}
