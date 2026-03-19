import { useEffect, useMemo, useState } from "react";

import { parseApiError } from "../../../utils/httpError";
import {
  fetchImportSchema,
  fetchImportSchemaPlan,
  previewImport,
  upsertImportDraft,
  uploadImportFile,
  validateImportDraft,
} from "../api/import";
import { suggestTargetFromSource } from "../importRules";
import { formatBytes } from "../utils";
import type {
  CompiledImportPlan,
  ImportDraftResp,
  ImportFileUploadResp,
  ImportMode,
  ImportSchemaObject,
  ImportSchemaObjectPlan,
  ImportSchemaResp,
  ImportSource,
  ImportTargetMapping,
} from "../types/import";

type NoticeFn = (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;
type EnsureReadyFn = (actionLabel: string) => boolean;

type UseImportDraftFlowArgs = {
  ensureReady: EnsureReadyFn;
  onNotice: NoticeFn;
};

const IMPORT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
const IMPORT_MAX_DRAFT_TOTAL_BYTES = 200 * 1024 * 1024;
const IMPORT_MAX_DRAFT_FILES = 5;
const IMPORT_PREVIEW_ROWS = 50;
const LARGE_UPLOAD_HINT_BYTES = 50 * 1024 * 1024;

export function useImportDraftFlow({ ensureReady, onNotice }: UseImportDraftFlowArgs) {
  const [busyAction, setBusyAction] = useState<"upload" | "preview" | "schema_plan" | "draft" | "validate" | null>(null);
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

  const draftTotalBytes = useMemo(() => files.reduce((sum, item) => sum + item.size_bytes, 0), [files]);
  const schemaObjects = useMemo<ImportSchemaObject[]>(
    () => [
      ...(schema?.tags || []).map((item) => ({ ...item, object_type: "tag" as const })),
      ...(schema?.edge_types || []).map((item) => ({ ...item, object_type: "edge_type" as const })),
    ],
    [schema]
  );

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
  }, [onNotice]);

  useEffect(() => {
    if (!preview) return;
    setSources(preview.sources || []);
    if (preview.workspace_mode_candidates.length > 0) {
      setWorkspaceMode(preview.workspace_mode_candidates[0]);
    }
    setTargets((previous) =>
      previous.length === 0 && preview.sources.length > 0
        ? preview.sources.map((source) => suggestTargetFromSource(source))
        : previous
    );
  }, [preview]);

  async function handleUpload(fileList: FileList | null) {
    if (!ensureReady("上传")) return;
    const nextFile = fileList?.[0];
    if (!nextFile) return;
    const selectionError = validateSelectedUpload(nextFile);
    if (selectionError) {
      onNotice({ level: "warn", message: selectionError });
      return;
    }
    setBusyAction("upload");
    try {
      if (nextFile.size >= LARGE_UPLOAD_HINT_BYTES) {
        onNotice({ level: "info", message: "Uploading large CSV... Files near 100MB may take longer." });
      }
      const uploaded = await uploadImportFile(nextFile);
      clearFileBoundState();
      setFiles((previous) => [...previous, uploaded]);
      onNotice({
        level: "info",
        message: `已上传 ${uploaded.original_name} (${formatBytes(uploaded.size_bytes)}). Preview 会为每个文件生成 source snapshot。`,
      });
    } catch (error) {
      onNotice({ level: "error", message: `上传失败：${describeUploadFailure(error)}` });
    } finally {
      setBusyAction(null);
    }
  }

  async function handlePreview() {
    if (!ensureReady("Preview")) return;
    if (files.length === 0) {
      onNotice({ level: "warn", message: "请先上传 CSV 文件" });
      return;
    }
    setBusyAction("preview");
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
      setBusyAction(null);
    }
  }

  async function handleSchemaPlan() {
    if (!ensureReady("Schema plan")) return;
    if (sources.length === 0) {
      onNotice({ level: "warn", message: "请先生成 preview / sources" });
      return;
    }
    setBusyAction("schema_plan");
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
      setBusyAction(null);
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
    if (!ensureReady("保存 draft")) return;
    if (sources.length === 0) {
      onNotice({ level: "warn", message: "请先完成 preview" });
      return;
    }
    setBusyAction("draft");
    try {
      const saved = await persistDraft();
      onNotice({ level: "info", message: `draft 已保存：${saved.draft_id}` });
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `draft 保存失败：${parsed.message}` });
    } finally {
      setBusyAction(null);
    }
  }

  async function handleValidate() {
    if (!ensureReady("校验")) return;
    setBusyAction("validate");
    try {
      const currentDraft = draft?.draft_id ? draft : await persistDraft();
      const validation = await validateImportDraft(currentDraft.draft_id);
      setDraft((previous) =>
        previous
          ? { ...previous, validation, status: validation.passed ? "validated" : previous.status, sources, mapping: targets }
          : currentDraft
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
      setBusyAction(null);
    }
  }

  function addTarget() {
    const nextSource = sources[0];
    if (!nextSource) return;
    setTargets((previous) => [...previous, suggestTargetFromSource(nextSource)]);
  }

  function updateTarget(index: number, nextTarget: ImportTargetMapping) {
    setTargets((previous) => previous.map((item, itemIndex) => (itemIndex === index ? nextTarget : item)));
  }

  function removeTarget(index: number) {
    setTargets((previous) => previous.filter((_, itemIndex) => itemIndex !== index));
  }

  return {
    busyAction,
    compiledPlan,
    draft,
    draftTotalBytes,
    files,
    integrationWarnings,
    preview,
    schemaObjects,
    schemaPlan,
    schemaWarnings,
    sources,
    targets,
    workspaceMode,
    addTarget,
    clearSpaceBoundState,
    handlePreview,
    handleSaveDraft,
    handleSchemaPlan,
    handleUpload,
    handleValidate,
    removeTarget,
    setWorkspaceMode,
    updateTarget,
  };
}
