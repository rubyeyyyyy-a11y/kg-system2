import type { CleanupJobResp, CleanupPlanPreviewResp, CleanupScope, ImportBatchItem, ImportBatchResp } from "../../types/import";
import { CleanupPlanPreviewPanel } from "./CleanupPlanPreviewPanel";
import { CleanupResultPanel } from "./CleanupResultPanel";
import { formatFlag } from "./utils";

type BatchDetailPanelProps = {
  cleanupLoading: boolean;
  cleanupPlanLoading: boolean;
  cleanupPlanPreview: CleanupPlanPreviewResp | null;
  cleanupResultContext: {
    cleanupLabel: string;
    relevantCleanupJob: CleanupJobResp | null;
  };
  onConfirmCleanup: (scope: CleanupScope) => void;
  onDownloadCleanupArtifact: (cleanupJobId: string, artifactName: string) => void;
  onPreviewCleanupPlan: (scope: CleanupScope) => void;
  onQuickCleanup: (scope: CleanupScope) => void;
  selectedBatch: ImportBatchResp | null;
  selectedBatchId: string | null;
  selectedBatchIds: string[];
  selectedBatchItems: ImportBatchItem[];
};

export function BatchDetailPanel({
  cleanupLoading,
  cleanupPlanLoading,
  cleanupPlanPreview,
  cleanupResultContext,
  onConfirmCleanup,
  onDownloadCleanupArtifact,
  onPreviewCleanupPlan,
  onQuickCleanup,
  selectedBatch,
  selectedBatchId,
  selectedBatchIds,
  selectedBatchItems,
}: BatchDetailPanelProps) {
  if (!selectedBatch) {
    return <div style={{ color: "#7d6b57" }}>选择一个 batch 查看详情</div>;
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <strong data-testid="import-selected-batch-id">{selectedBatch.batch_id}</strong>
        <span style={{ fontSize: 12, color: "#7d6b57" }}>status={selectedBatch.status}</span>
        <span style={{ fontSize: 12, color: "#7d6b57" }}>source={selectedBatch.source_type}</span>
        <span style={{ fontSize: 12, color: "#7d6b57" }}>job={selectedBatch.job_id}</span>
      </div>
      <div style={{ fontSize: 13, color: "#5b4b38" }}>
        entity_count={selectedBatch.entity_count} | relation_count={selectedBatch.relation_count} | searchable=
        {formatFlag(selectedBatch.searchable)} | cleanup_status={selectedBatch.cleanup_status}
      </div>
      <div style={{ fontSize: 13, color: "#5b4b38" }}>
        is_test_data={selectedBatch.is_test_data ? "yes" : "no"} | draft={selectedBatch.draft_id} | submission=
        {selectedBatch.submission_id || "-"}
      </div>
      <div style={{ padding: 12, borderRadius: 12, background: "#f6efe4", fontSize: 12, color: "#6c5b47" }}>
        cleanup limits: only test batch supports cleanup; historical imports without ledger are not guaranteed to be restorable; cleanup runs asynchronously in phases and failures require detail review; worker mode is single-process and file-based in V1.5.
      </div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          data-testid="import-batch-preview-cleanup-button"
          onClick={() => onPreviewCleanupPlan("full_batch")}
          disabled={selectedBatchIds.length === 0}
        >
          Preview Cleanup Plan
        </button>
        <button onClick={() => onPreviewCleanupPlan("relations_only")} disabled={selectedBatchIds.length === 0}>
          Preview Relations-Only Plan
        </button>
        <button
          data-testid="import-batch-cleanup-button"
          onClick={() => onQuickCleanup("full_batch")}
          disabled={selectedBatchIds.length === 0}
          title="Compatibility path: submit cleanup directly without preview."
          style={{ opacity: 0.78 }}
        >
          Quick Cleanup (Skip Preview, Compatibility)
        </button>
        <span style={{ fontSize: 12, color: "#7d6b57" }}>selected={selectedBatchIds.length}</span>
      </div>

      {cleanupPlanLoading ? <div style={{ fontSize: 12, color: "#7d6b57" }}>cleanup plan preview loading...</div> : null}
      {cleanupPlanPreview ? (
        <CleanupPlanPreviewPanel
          cleanupPlanPreview={cleanupPlanPreview}
          selectedBatchIds={selectedBatchIds}
          onConfirmCleanup={onConfirmCleanup}
        />
      ) : null}

      <div style={{ display: "grid", gap: 10 }}>
        <strong style={{ fontSize: 14 }}>Batch Items</strong>
        {selectedBatchItems.length === 0 ? (
          <div style={{ color: "#7d6b57", fontSize: 13 }}>当前 batch 没有 ledger items。</div>
        ) : (
          selectedBatchItems.slice(0, 12).map((item) => (
            <div key={item.item_id} style={{ padding: 12, borderRadius: 12, background: "#f7f0e4", fontSize: 13 }}>
              {item.item_type === "entity" ? (
                <div>
                  entity vid={item.vid} name={item.entity_name || "-"} raw_id={item.entity_raw_id || "-"} created_by_batch=
                  {item.created_by_batch ? "yes" : "no"}
                </div>
              ) : (
                <div>
                  relation {item.edge_type || "REL2"} {`${item.src_vid}->${item.dst_vid}@${item.rank}`} relation={item.relation || "-"} created_by_batch=
                  {item.created_by_batch ? "yes" : "no"}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <CleanupResultPanel
        cleanupLoading={cleanupLoading}
        cleanupLabel={cleanupResultContext.cleanupLabel}
        onDownloadCleanupArtifact={onDownloadCleanupArtifact}
        relevantCleanupJob={cleanupResultContext.relevantCleanupJob}
        selectedBatchId={selectedBatchId}
      />
    </div>
  );
}
