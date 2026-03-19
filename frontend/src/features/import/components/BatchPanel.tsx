import type { CleanupJobResp, CleanupPlanPreviewResp, CleanupScope, ImportBatchItem, ImportBatchResp } from "../types/import";
import { BatchDetailPanel } from "./batch/BatchDetailPanel";
import { BatchListPanel } from "./batch/BatchListPanel";
import { selectRelevantCleanupJob } from "./batch/utils";

type BatchPanelProps = {
  batches: ImportBatchResp[];
  selectedBatchId: string | null;
  selectedBatchItems: ImportBatchItem[];
  selectedBatchIds: string[];
  cleanupJobs: CleanupJobResp[];
  cleanupLoading: boolean;
  cleanupPlanPreview: CleanupPlanPreviewResp | null;
  cleanupPlanLoading: boolean;
  onSelectBatch: (batchId: string) => void;
  onToggleBatch: (batchId: string) => void;
  onPreviewCleanupPlan: (scope: CleanupScope) => void;
  onConfirmCleanup: (scope: CleanupScope) => void;
  onQuickCleanup: (scope: CleanupScope) => void;
  onDownloadCleanupArtifact: (cleanupJobId: string, artifactName: string) => void;
};

export function BatchPanel({
  batches,
  selectedBatchId,
  selectedBatchItems,
  selectedBatchIds,
  cleanupJobs,
  cleanupLoading,
  cleanupPlanPreview,
  cleanupPlanLoading,
  onSelectBatch,
  onToggleBatch,
  onPreviewCleanupPlan,
  onConfirmCleanup,
  onQuickCleanup,
  onDownloadCleanupArtifact,
}: BatchPanelProps) {
  const selectedBatch = batches.find((batch) => batch.batch_id === selectedBatchId) || batches[0] || null;
  const cleanupResultSelection = selectRelevantCleanupJob(cleanupJobs, selectedBatch, selectedBatchIds);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(300px, 380px) minmax(0, 1fr)",
        gap: 16,
      }}
    >
      <div style={{ border: "1px solid rgba(76, 56, 36, 0.14)", borderRadius: 18, overflow: "hidden", background: "#fff" }}>
        <BatchListPanel
          batches={batches}
          selectedBatchId={selectedBatchId}
          selectedBatchIds={selectedBatchIds}
          onSelectBatch={onSelectBatch}
          onToggleBatch={onToggleBatch}
        />
      </div>

      <div style={{ border: "1px solid rgba(76, 56, 36, 0.14)", borderRadius: 18, padding: 16, background: "#fffdf8" }}>
        <BatchDetailPanel
          cleanupLoading={cleanupLoading}
          cleanupPlanLoading={cleanupPlanLoading}
          cleanupPlanPreview={cleanupPlanPreview}
          cleanupResultContext={{
            cleanupLabel: cleanupResultSelection.label,
            relevantCleanupJob: cleanupResultSelection.job,
          }}
          onConfirmCleanup={onConfirmCleanup}
          onDownloadCleanupArtifact={onDownloadCleanupArtifact}
          onPreviewCleanupPlan={onPreviewCleanupPlan}
          onQuickCleanup={onQuickCleanup}
          selectedBatch={selectedBatch}
          selectedBatchId={selectedBatchId}
          selectedBatchIds={selectedBatchIds}
          selectedBatchItems={selectedBatchItems}
        />
      </div>
    </div>
  );
}
