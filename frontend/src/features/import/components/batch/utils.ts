import type { CleanupArtifact, CleanupJobResp, ImportBatchResp } from "../../types/import";

export function formatFlag(value: boolean | null | undefined) {
  if (value == null) return "-";
  return value ? "yes" : "no";
}

export function formatTs(ts?: number | null) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

export function formatDuration(durationMs?: number | null) {
  if (durationMs == null) return "-";
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(1)} s`;
}

export function cleanupEnabled(batch: ImportBatchResp) {
  return batch.is_test_data && batch.cleanup_status !== "not_supported";
}

export function artifactByKind(artifacts: CleanupArtifact[], kind: CleanupArtifact["kind"]) {
  return artifacts.find((item) => item.kind === kind) || null;
}

export function stringifySummary(value: unknown) {
  if (value == null) return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function selectRelevantCleanupJob(
  cleanupJobs: CleanupJobResp[],
  selectedBatch: ImportBatchResp | null,
  selectedBatchIds: string[]
): { job: CleanupJobResp | null; label: string } {
  if (cleanupJobs.length === 0) return { job: null, label: "none" };
  const effectiveIds = selectedBatchIds.length > 0 ? selectedBatchIds : selectedBatch?.batch_id ? [selectedBatch.batch_id] : [];
  if (effectiveIds.length > 1) {
    const covering = cleanupJobs.find((job) => effectiveIds.every((batchId) => job.batch_ids.includes(batchId)));
    if (covering) return { job: covering, label: "selected_batches" };
  }
  if (effectiveIds.length === 1) {
    const byBatch = cleanupJobs.find((job) => job.batch_ids.includes(effectiveIds[0]));
    if (byBatch) return { job: byBatch, label: "selected_batch" };
  }
  return { job: cleanupJobs[0], label: "global_latest" };
}
