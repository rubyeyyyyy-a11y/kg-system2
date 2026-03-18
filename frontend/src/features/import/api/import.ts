import { apiGet, apiPost, downloadBlob, uploadFile } from "../../../api/http";
import type {
  CleanupJobResp,
  CleanupPlanPreviewResp,
  ImportBatchItem,
  ImportBatchResp,
  ImportDraftResp,
  ImportDraftValidationResp,
  ImportFileUploadResp,
  ImportJobLogsResp,
  ImportJobResp,
  ImportMode,
  ImportPostprocessOptions,
  ImportPreviewResp,
  ImportSchemaOptions,
  ImportSchemaResp,
  ImportSource,
  ImportTargetMapping,
  ImportUpdateStrategy,
} from "../types/import";

const IMPORT_UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;

export async function uploadImportFile(file: File): Promise<ImportFileUploadResp> {
  return uploadFile<ImportFileUploadResp>("/api/import/files", file, "file", { timeoutMs: IMPORT_UPLOAD_TIMEOUT_MS });
}

export async function previewImport(body: {
  file_ids: string[];
  sample_rows: number;
  mode_hint?: ImportMode;
}): Promise<ImportPreviewResp> {
  return apiPost<ImportPreviewResp>("/api/import/preview", body);
}

export async function fetchImportSchema(): Promise<ImportSchemaResp> {
  return apiGet<ImportSchemaResp>("/api/import/schema");
}

export async function fetchImportSchemaPlan(body: {
  file_ids: string[];
  sources: ImportSource[];
  mapping: ImportTargetMapping[];
  schema_options: ImportSchemaOptions;
  workspace_mode?: ImportMode;
}): Promise<{
  schema_create_plan: NonNullable<ImportDraftValidationResp["compiled_plan"]>["schema_create_plan"];
  warnings: string[];
  integration_warnings: string[];
}> {
  return apiPost("/api/import/schema/plan", body);
}

export async function upsertImportDraft(body: {
  draft_id?: string;
  workspace_mode: ImportMode;
  file_ids: string[];
  sources: ImportSource[];
  mapping: ImportTargetMapping[];
  update_strategy: ImportUpdateStrategy;
  schema_options: ImportSchemaOptions;
  postprocess_options: ImportPostprocessOptions;
}): Promise<ImportDraftResp> {
  return apiPost<ImportDraftResp>("/api/import/drafts", body);
}

export async function getImportDraft(draftId: string): Promise<ImportDraftResp> {
  return apiGet<ImportDraftResp>(`/api/import/drafts/${draftId}`);
}

export async function validateImportDraft(draftId: string): Promise<ImportDraftValidationResp> {
  return apiPost<ImportDraftValidationResp>(`/api/import/drafts/${draftId}/validate`, {});
}

export async function submitImportJob(body: { draft_id: string; created_by: string }): Promise<ImportJobResp> {
  return apiPost<ImportJobResp>("/api/import/jobs", body);
}

export async function listImportJobs(): Promise<ImportJobResp[]> {
  return apiGet<ImportJobResp[]>("/api/import/jobs");
}

export async function getImportJob(jobId: string): Promise<ImportJobResp> {
  return apiGet<ImportJobResp>(`/api/import/jobs/${jobId}`);
}

export async function getImportJobLogs(jobId: string): Promise<ImportJobLogsResp> {
  return apiGet<ImportJobLogsResp>(`/api/import/jobs/${jobId}/logs`);
}

export async function cancelImportJob(jobId: string): Promise<ImportJobResp> {
  return apiPost<ImportJobResp>(`/api/import/jobs/${jobId}/cancel`, {});
}

export async function downloadFailedRows(jobId: string): Promise<Blob> {
  return downloadBlob(`/api/import/jobs/${jobId}/failed_rows`);
}

export async function downloadImportArtifact(jobId: string, artifactName: string): Promise<Blob> {
  return downloadBlob(`/api/import/jobs/${jobId}/artifacts/${artifactName}`);
}

export async function listImportBatches(): Promise<ImportBatchResp[]> {
  return apiGet<ImportBatchResp[]>("/api/import/batches");
}

export async function getImportBatch(batchId: string): Promise<ImportBatchResp> {
  return apiGet<ImportBatchResp>(`/api/import/batches/${batchId}`);
}

export async function listImportBatchItems(batchId: string): Promise<ImportBatchItem[]> {
  return apiGet<ImportBatchItem[]>(`/api/import/batches/${batchId}/items`);
}

export async function createImportCleanupJob(body: {
  batch_ids: string[];
  scope: "full_batch" | "relations_only";
  created_by: string;
}): Promise<CleanupJobResp> {
  return apiPost<CleanupJobResp>("/api/import/batches/cleanup", body);
}

export async function createCleanupPlanPreview(body: {
  batch_ids: string[];
  scope: "full_batch" | "relations_only";
  created_by: string;
}): Promise<CleanupPlanPreviewResp> {
  return apiPost<CleanupPlanPreviewResp>("/api/import/batches/cleanup-plan", body);
}

export async function listCleanupJobs(): Promise<CleanupJobResp[]> {
  return apiGet<CleanupJobResp[]>("/api/import/cleanup-jobs");
}

export async function getCleanupJob(cleanupJobId: string): Promise<CleanupJobResp> {
  return apiGet<CleanupJobResp>(`/api/import/cleanup-jobs/${cleanupJobId}`);
}

export async function downloadCleanupArtifact(cleanupJobId: string, artifactName: string): Promise<Blob> {
  return downloadBlob(`/api/import/cleanup-jobs/${cleanupJobId}/artifacts/${artifactName}`);
}
