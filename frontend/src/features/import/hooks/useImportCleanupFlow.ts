import { useEffect, useState } from "react";

import { parseApiError } from "../../../utils/httpError";
import { createCleanupPlanPreview, createImportCleanupJob, downloadCleanupArtifact } from "../api/import";
import type {
  CleanupPlanPreviewResp,
  CleanupScope,
  ImportBatchResp,
} from "../types/import";
import { downloadBlobToFile } from "../utils";

type NoticeFn = (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;

type UseImportCleanupFlowArgs = {
  batches: ImportBatchResp[];
  createdBy: string;
  onNotice: NoticeFn;
  reloadBatches: () => Promise<void>;
  reloadCleanupJobs: () => Promise<void>;
  selectedBatchIds: string[];
  setJobsTab: (tab: "jobs" | "batches") => void;
};

export function useImportCleanupFlow({
  batches,
  createdBy,
  onNotice,
  reloadBatches,
  reloadCleanupJobs,
  selectedBatchIds,
  setJobsTab,
}: UseImportCleanupFlowArgs) {
  const [cleanupPlanPreview, setCleanupPlanPreview] = useState<CleanupPlanPreviewResp | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!cleanupPlanPreview) return;
    const previewBatchKey = [...cleanupPlanPreview.batch_ids].sort().join(",");
    const selectedBatchKey = [...selectedBatchIds].sort().join(",");
    if (previewBatchKey !== selectedBatchKey) {
      setCleanupPlanPreview(null);
    }
  }, [cleanupPlanPreview, selectedBatchIds]);

  async function handlePreviewCleanup(scope: CleanupScope) {
    if (selectedBatchIds.length === 0) {
      onNotice({ level: "warn", message: "请先选择至少一个 test batch" });
      return;
    }
    setPreviewLoading(true);
    try {
      const preview = await createCleanupPlanPreview({
        batch_ids: selectedBatchIds,
        scope,
        created_by: createdBy || "import_workspace_cleanup",
      });
      setCleanupPlanPreview(preview);
      onNotice({
        level: "info",
        message: `cleanup plan 已生成：deletable_entities=${preview.plan_summary.deletable_entity_count}, deletable_relations=${preview.plan_summary.deletable_relation_count}, blocked_entities=${preview.plan_summary.blocked_entity_count}`,
      });
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `cleanup 预览失败：${parsed.message}` });
    } finally {
      setPreviewLoading(false);
    }
  }

  async function submitCleanup(scope: CleanupScope, confirmText: string) {
    if (selectedBatchIds.length === 0) {
      onNotice({ level: "warn", message: "请先选择至少一个 test batch" });
      return;
    }
    const selected = batches.filter((batch) => selectedBatchIds.includes(batch.batch_id));
    const entityCount = selected.reduce((sum, batch) => sum + batch.entity_count, 0);
    const relationCount = selected.reduce((sum, batch) => sum + batch.relation_count, 0);
    const confirmed = window.confirm(
      `${confirmText}\n\nbatch_count=${selected.length}\nscope=${scope}\nentities=${entityCount}\nrelations=${relationCount}\nOnly test-data batches with ledger will be deleted.\nExecute phase will recalculate cleanup plan before delete.`
    );
    if (!confirmed) return;
    setSubmitting(true);
    try {
      const cleanupJob = await createImportCleanupJob({
        batch_ids: selectedBatchIds,
        scope,
        created_by: createdBy || "import_workspace_cleanup",
      });
      await Promise.all([reloadBatches(), reloadCleanupJobs()]);
      onNotice({
        level: "info",
        message: `cleanup job 已创建：${cleanupJob.cleanup_job_id} (${cleanupJob.status})`,
      });
      setCleanupPlanPreview(null);
      setJobsTab("batches");
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `cleanup 提交失败：${parsed.message}` });
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConfirmCleanup(scope: CleanupScope) {
    if (!cleanupPlanPreview) {
      onNotice({ level: "warn", message: "请先预览 cleanup plan" });
      return;
    }
    const previewBatchKey = [...cleanupPlanPreview.batch_ids].sort().join(",");
    const selectedBatchKey = [...selectedBatchIds].sort().join(",");
    if (previewBatchKey !== selectedBatchKey || cleanupPlanPreview.scope !== scope) {
      onNotice({ level: "warn", message: "预览计划与当前选择不一致，请重新 Preview Cleanup Plan" });
      return;
    }
    await submitCleanup(
      scope,
      "Confirm cleanup from preview plan? Preview is point-in-time and execute will recompute plan."
    );
  }

  async function handleQuickCleanup(scope: CleanupScope) {
    await submitCleanup(scope, "Quick cleanup without preview?");
  }

  async function handleDownloadCleanupArtifact(cleanupJobId: string, artifactName: string) {
    try {
      const blob = await downloadCleanupArtifact(cleanupJobId, artifactName);
      downloadBlobToFile(blob, artifactName);
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `cleanup artifact 下载失败：${parsed.message}` });
    }
  }

  function clearCleanupPreview() {
    setCleanupPlanPreview(null);
  }

  return {
    cleanupPlanPreview,
    previewLoading,
    submitting,
    clearCleanupPreview,
    handleConfirmCleanup,
    handleDownloadCleanupArtifact,
    handlePreviewCleanup,
    handleQuickCleanup,
  };
}
