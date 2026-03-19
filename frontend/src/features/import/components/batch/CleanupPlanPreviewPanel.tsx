import type { CleanupPlanPreviewResp, CleanupScope } from "../../types/import";
import { stringifySummary } from "./utils";

type CleanupPlanPreviewPanelProps = {
  cleanupPlanPreview: CleanupPlanPreviewResp;
  selectedBatchIds: string[];
  onConfirmCleanup: (scope: CleanupScope) => void;
};

export function CleanupPlanPreviewPanel({
  cleanupPlanPreview,
  selectedBatchIds,
  onConfirmCleanup,
}: CleanupPlanPreviewPanelProps) {
  return (
    <div data-testid="cleanup-plan-preview" style={{ display: "grid", gap: 10, borderRadius: 12, padding: 12, background: "#edf8ff", fontSize: 13 }}>
      <strong>Cleanup Plan Preview ({cleanupPlanPreview.scope})</strong>
      <div>
        requested_entities={cleanupPlanPreview.plan_summary.requested_entity_count} | requested_relations=
        {cleanupPlanPreview.plan_summary.requested_relation_count}
      </div>
      <div>
        deletable_entities={cleanupPlanPreview.plan_summary.deletable_entity_count} | deletable_relations=
        {cleanupPlanPreview.plan_summary.deletable_relation_count}
      </div>
      <div>
        blocked_entities={cleanupPlanPreview.plan_summary.blocked_entity_count} | ledger_blocked=
        {cleanupPlanPreview.plan_summary.ledger_blocked_entity_count} | live_graph_blocked=
        {cleanupPlanPreview.plan_summary.live_graph_blocked_entity_count}
      </div>
      <div>
        conflicts={cleanupPlanPreview.plan_summary.conflict_count} | preview_artifacts=
        {cleanupPlanPreview.has_plan_artifacts ? "yes" : "no"}
      </div>
      <div>verification_scope_note={cleanupPlanPreview.verification_scope_note || "-"}</div>
      <div style={{ fontSize: 12, color: "#5b4b38" }}>
        {cleanupPlanPreview.consistency_note ||
          "preview is point-in-time; execute will recalculate before deletion."}
      </div>
      <div>
        sample.blocked={cleanupPlanPreview.blocked_entities.sample.length} / {cleanupPlanPreview.blocked_entities.total_count}
        {" | "}
        sample.conflicts={cleanupPlanPreview.conflicts.slice(0, 5).length} / {cleanupPlanPreview.conflicts.length}
      </div>
      {cleanupPlanPreview.blocked_entities.sample.length > 0 ? (
        <div style={{ fontSize: 12, color: "#5b4b38" }}>
          blocked sample:{" "}
          {cleanupPlanPreview.blocked_entities.sample
            .map((item) => `${item.vid ?? "-"}:${item.entity_name || item.entity_raw_id || "-"}`)
            .join(", ")}
        </div>
      ) : null}
      {cleanupPlanPreview.conflicts.length > 0 ? (
        <div style={{ fontSize: 12, color: "#5b4b38" }}>
          conflict sample:{" "}
          {cleanupPlanPreview.conflicts
            .slice(0, 3)
            .map((item) => `vid=${item.vid ?? "-"} ${item.source || "-"}:${item.reason}`)
            .join(" | ")}
        </div>
      ) : null}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button
          data-testid="import-batch-confirm-cleanup-button"
          onClick={() => onConfirmCleanup(cleanupPlanPreview.scope)}
          disabled={selectedBatchIds.length === 0}
        >
          Confirm Cleanup ({cleanupPlanPreview.scope})
        </button>
      </div>
      <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>{stringifySummary(cleanupPlanPreview.warning_messages)}</pre>
    </div>
  );
}
