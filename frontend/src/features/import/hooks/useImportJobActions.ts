import { useState } from "react";

import { parseApiError } from "../../../utils/httpError";
import { cancelImportJob, downloadFailedRows, downloadImportArtifact, submitImportJob } from "../api/import";
import type { ImportDraftResp } from "../types/import";
import { downloadBlobToFile } from "../utils";

type NoticeFn = (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;
type EnsureReadyFn = (actionLabel: string) => boolean;

type UseImportJobActionsArgs = {
  createdBy: string;
  draft: ImportDraftResp | null;
  ensureReady: EnsureReadyFn;
  onNotice: NoticeFn;
  onSelectJob: (jobId: string) => void;
  reloadBatches: () => Promise<void>;
  reloadJobs: () => Promise<void>;
};

export function useImportJobActions({
  createdBy,
  draft,
  ensureReady,
  onNotice,
  onSelectJob,
  reloadBatches,
  reloadJobs,
}: UseImportJobActionsArgs) {
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmitJob() {
    if (!ensureReady("提交 job")) return;
    if (!draft?.draft_id) {
      onNotice({ level: "warn", message: "请先保存并校验 draft" });
      return;
    }
    setSubmitting(true);
    try {
      const job = await submitImportJob({ draft_id: draft.draft_id, created_by: createdBy });
      onSelectJob(job.job_id);
      await reloadJobs();
      await reloadBatches();
      onNotice({ level: "info", message: `job 已提交：${job.job_id}` });
    } catch (error) {
      const parsed = parseApiError(error);
      onNotice({ level: "error", message: `提交 job 失败：${parsed.message}` });
    } finally {
      setSubmitting(false);
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

  return {
    submitting,
    handleCancelJob,
    handleDownloadArtifact,
    handleDownloadFailedRows,
    handleSubmitJob,
  };
}
