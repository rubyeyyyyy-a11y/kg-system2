import type { CleanupJobResp } from "../../types/import";
import { artifactByKind, formatDuration, formatTs, stringifySummary } from "./utils";

type CleanupResultPanelProps = {
  cleanupLoading: boolean;
  cleanupLabel: string;
  onDownloadCleanupArtifact: (cleanupJobId: string, artifactName: string) => void;
  relevantCleanupJob: CleanupJobResp | null;
  selectedBatchId: string | null;
};

export function CleanupResultPanel({
  cleanupLoading,
  cleanupLabel,
  onDownloadCleanupArtifact,
  relevantCleanupJob,
  selectedBatchId,
}: CleanupResultPanelProps) {
  const verifyArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "verify_summary") : null;
  const summaryArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "summary") : null;
  const conflictArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "conflicts") : null;
  const planSummaryArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "plan_summary") : null;
  const blockedEntitiesArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "blocked_entities") : null;
  const deletableEntitiesArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "deletable_entities") : null;
  const deletableRelationsArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "deletable_relations") : null;
  const planSummary = relevantCleanupJob?.plan_summary || null;

  return (
    <div style={{ display: "grid", gap: 10 }}>
      <strong style={{ fontSize: 14 }}>Cleanup Result</strong>
      {cleanupLoading ? <div style={{ color: "#7d6b57", fontSize: 13 }}>cleanup jobs loading...</div> : null}
      {relevantCleanupJob ? (
        <>
          <div data-testid="cleanup-job-status" style={{ display: "grid", gap: 10, padding: 12, borderRadius: 12, background: "#eef4ff", fontSize: 13 }}>
            <div>
              job={relevantCleanupJob.cleanup_job_id} | status={relevantCleanupJob.status} | phase={relevantCleanupJob.phase} |
              failure_phase={relevantCleanupJob.failure_phase || "-"}
            </div>
            <div style={{ color: "#5b4b38" }}>
              context=
              {cleanupLabel === "selected_batches"
                ? "latest cleanup covering all selected batches"
                : cleanupLabel === "selected_batch"
                  ? `latest cleanup for ${selectedBatchId}`
                  : "global latest cleanup job"}
            </div>
            <div>
              requested_entities={relevantCleanupJob.requested_entity_count} | requested_relations={relevantCleanupJob.requested_relation_count}
            </div>
            <div>
              deleted_entities={relevantCleanupJob.deleted_entity_count} | deleted_relations={relevantCleanupJob.deleted_relation_count}
            </div>
            <div>
              skipped_entities={relevantCleanupJob.skipped_entity_count} | skipped_relations={relevantCleanupJob.skipped_relation_count}
            </div>
            <div>
              deduplicated_entities={relevantCleanupJob.deduplicated_entity_count} | deduplicated_relations={relevantCleanupJob.deduplicated_relation_count} | conflicts=
              {relevantCleanupJob.conflict_count}
            </div>
            <div>
              plan.blocked_entities={planSummary?.blocked_entity_count ?? "-"} | plan.deletable_entities=
              {planSummary?.deletable_entity_count ?? "-"} | plan.deletable_relations={planSummary?.deletable_relation_count ?? "-"}
            </div>
            <div>
              plan.ledger_blocked={planSummary?.ledger_blocked_entity_count ?? "-"} | plan.live_graph_blocked=
              {planSummary?.live_graph_blocked_entity_count ?? "-"} | has_plan_artifacts=
              {relevantCleanupJob.has_plan_artifacts ? "yes" : "no"}
            </div>
            <div>
              started_at={formatTs(relevantCleanupJob.started_at)} | finished_at={formatTs(relevantCleanupJob.finished_at)} | duration=
              {formatDuration(relevantCleanupJob.duration_ms)}
            </div>
            <div>
              error={relevantCleanupJob.error_message || "-"} | failure_kind={relevantCleanupJob.failure_kind || "-"}
            </div>
            <div>plan.verification_scope_note={planSummary?.verification_scope_note || "-"}</div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {summaryArtifact ? (
                <button onClick={() => onDownloadCleanupArtifact(relevantCleanupJob.cleanup_job_id, summaryArtifact.filename)}>
                  Download Summary
                </button>
              ) : null}
              {conflictArtifact ? (
                <button onClick={() => onDownloadCleanupArtifact(relevantCleanupJob.cleanup_job_id, conflictArtifact.filename)}>
                  Download Conflicts
                </button>
              ) : null}
              {verifyArtifact ? (
                <button onClick={() => onDownloadCleanupArtifact(relevantCleanupJob.cleanup_job_id, verifyArtifact.filename)}>
                  Download Verify Summary
                </button>
              ) : null}
              {planSummaryArtifact ? (
                <button onClick={() => onDownloadCleanupArtifact(relevantCleanupJob.cleanup_job_id, planSummaryArtifact.filename)}>
                  Download Plan Summary
                </button>
              ) : null}
              {blockedEntitiesArtifact ? (
                <button onClick={() => onDownloadCleanupArtifact(relevantCleanupJob.cleanup_job_id, blockedEntitiesArtifact.filename)}>
                  Download Blocked Entities
                </button>
              ) : null}
              {deletableEntitiesArtifact ? (
                <button onClick={() => onDownloadCleanupArtifact(relevantCleanupJob.cleanup_job_id, deletableEntitiesArtifact.filename)}>
                  Download Deletable Entities
                </button>
              ) : null}
              {deletableRelationsArtifact ? (
                <button onClick={() => onDownloadCleanupArtifact(relevantCleanupJob.cleanup_job_id, deletableRelationsArtifact.filename)}>
                  Download Deletable Relations
                </button>
              ) : null}
            </div>
          </div>

          <details open style={{ border: "1px solid #e1e8f5", borderRadius: 12, padding: 12, background: "#fff" }}>
            <summary style={{ cursor: "pointer", fontWeight: 700 }}>Conflicts ({relevantCleanupJob.conflict_count})</summary>
            <div data-testid="cleanup-conflicts-summary" style={{ display: "grid", gap: 8, marginTop: 10, fontSize: 13 }}>
              {relevantCleanupJob.conflicts.length === 0 ? (
                <div style={{ color: "#7d6b57" }}>无冲突。</div>
              ) : (
                relevantCleanupJob.conflicts.map((conflict, index) => (
                  <div key={`${conflict.vid || index}-${conflict.reason}`} style={{ padding: 10, borderRadius: 10, background: "#fff7e6" }}>
                    vid={conflict.vid || "-"} | source={conflict.source || "-"} | reason={conflict.reason} | blocking_batches=
                    {conflict.blocking_batch_ids.join(", ") || "-"} | blocking_relations={conflict.blocking_relations}
                  </div>
                ))
              )}
            </div>
          </details>

          {planSummary ? (
            <div style={{ padding: 12, borderRadius: 12, background: "#eefaf4", fontSize: 13 }}>
              <strong>Plan Summary</strong>
              <pre style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>{stringifySummary(planSummary)}</pre>
            </div>
          ) : null}

          <div data-testid="cleanup-verify-summary" style={{ padding: 12, borderRadius: 12, background: "#f7f0e4", fontSize: 13 }}>
            <strong>Verify Summary</strong>
            <pre style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>{stringifySummary(relevantCleanupJob.verify_summary)}</pre>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 10 }}>
            <div style={{ padding: 12, borderRadius: 12, background: "#eefbf1", fontSize: 13 }}>
              <strong>Metadata Summary</strong>
              <pre style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>{stringifySummary(relevantCleanupJob.metadata_summary)}</pre>
            </div>
            <div style={{ padding: 12, borderRadius: 12, background: "#eef4ff", fontSize: 13 }}>
              <strong>Reconcile Summary</strong>
              <pre style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>{stringifySummary(relevantCleanupJob.reconcile_summary)}</pre>
            </div>
          </div>

          <div data-testid="cleanup-error-summary" style={{ padding: 12, borderRadius: 12, background: "#fff1f0", fontSize: 13 }}>
            <strong>Warnings / Error</strong>
            <div style={{ marginTop: 8 }}>error={relevantCleanupJob.error_message || "-"}</div>
            <div>failure_phase={relevantCleanupJob.failure_phase || "-"} | failure_kind={relevantCleanupJob.failure_kind || "-"}</div>
            <pre style={{ margin: "8px 0 0", whiteSpace: "pre-wrap" }}>{stringifySummary(relevantCleanupJob.warning_messages)}</pre>
          </div>
        </>
      ) : (
        <div style={{ color: "#7d6b57", fontSize: 13 }}>暂无 cleanup job</div>
      )}
    </div>
  );
}
