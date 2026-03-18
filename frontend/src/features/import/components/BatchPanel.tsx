import type { CleanupArtifact, CleanupJobResp, CleanupPlanPreviewResp, ImportBatchItem, ImportBatchResp } from "../types/import";

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
  onPreviewCleanupPlan: (scope: "full_batch" | "relations_only") => void;
  onConfirmCleanup: (scope: "full_batch" | "relations_only") => void;
  onQuickCleanup: (scope: "full_batch" | "relations_only") => void;
  onDownloadCleanupArtifact: (cleanupJobId: string, artifactName: string) => void;
};

function formatFlag(value: boolean | null | undefined) {
  if (value == null) return "-";
  return value ? "yes" : "no";
}

function formatTs(ts?: number | null) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function formatDuration(durationMs?: number | null) {
  if (durationMs == null) return "-";
  if (durationMs < 1000) return `${durationMs} ms`;
  return `${(durationMs / 1000).toFixed(1)} s`;
}

function cleanupEnabled(batch: ImportBatchResp) {
  return batch.is_test_data && batch.cleanup_status !== "not_supported";
}

function artifactByKind(artifacts: CleanupArtifact[], kind: CleanupArtifact["kind"]) {
  return artifacts.find((item) => item.kind === kind) || null;
}

function stringifySummary(value: unknown) {
  if (value == null) return "-";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function selectRelevantCleanupJob(
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
  const { job: relevantCleanupJob, label: cleanupLabel } = selectRelevantCleanupJob(cleanupJobs, selectedBatch, selectedBatchIds);
  const verifyArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "verify_summary") : null;
  const summaryArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "summary") : null;
  const conflictArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "conflicts") : null;
  const planSummaryArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "plan_summary") : null;
  const blockedEntitiesArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "blocked_entities") : null;
  const deletableEntitiesArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "deletable_entities") : null;
  const deletableRelationsArtifact = relevantCleanupJob ? artifactByKind(relevantCleanupJob.artifacts, "deletable_relations") : null;
  const planSummary = relevantCleanupJob?.plan_summary || null;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(300px, 380px) minmax(0, 1fr)",
        gap: 16,
      }}
    >
      <div style={{ border: "1px solid rgba(76, 56, 36, 0.14)", borderRadius: 18, overflow: "hidden", background: "#fff" }}>
        {batches.length === 0 ? (
          <div style={{ padding: 16, color: "#7d6b57" }}>暂无 batch 历史</div>
        ) : (
          batches.map((batch) => (
            <button
              key={batch.batch_id}
              data-testid={`import-batch-item-${batch.batch_id}`}
              onClick={() => onSelectBatch(batch.batch_id)}
              style={{
                display: "grid",
                width: "100%",
                textAlign: "left",
                gap: 4,
                padding: 14,
                border: "none",
                borderBottom: "1px solid #f0e6d8",
                background: batch.batch_id === selectedBatchId ? "#fff3dc" : "#fff",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <input
                  data-testid={`import-batch-select-${batch.batch_id}`}
                  type="checkbox"
                  checked={selectedBatchIds.includes(batch.batch_id)}
                  disabled={!cleanupEnabled(batch)}
                  onChange={() => onToggleBatch(batch.batch_id)}
                  onClick={(event) => event.stopPropagation()}
                />
                <strong>{batch.batch_id}</strong>
              </div>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>
                {batch.source_type} | created_at={new Date(batch.created_at * 1000).toLocaleString()}
              </span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>
                entities={batch.entity_count} relations={batch.relation_count} searchable={formatFlag(batch.searchable)}
              </span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>
                cleanup={batch.cleanup_status} | is_test_data={batch.is_test_data ? "yes" : "no"}
              </span>
            </button>
          ))
        )}
      </div>

      <div style={{ border: "1px solid rgba(76, 56, 36, 0.14)", borderRadius: 18, padding: 16, background: "#fffdf8" }}>
        {selectedBatch ? (
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
            {cleanupPlanLoading ? (
              <div style={{ fontSize: 12, color: "#7d6b57" }}>cleanup plan preview loading...</div>
            ) : null}
            {cleanupPlanPreview ? (
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

            <div style={{ display: "grid", gap: 10 }}>
              <strong style={{ fontSize: 14 }}>Cleanup Result</strong>
              {cleanupLoading ? <div style={{ color: "#7d6b57", fontSize: 13 }}>cleanup jobs loading...</div> : null}
              {relevantCleanupJob ? (
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
                        ? `latest cleanup for ${selectedBatch.batch_id}`
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
                    started_at={formatTs(relevantCleanupJob.started_at)} | finished_at={formatTs(relevantCleanupJob.finished_at)} | duration={formatDuration(relevantCleanupJob.duration_ms)}
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
              ) : (
                <div style={{ color: "#7d6b57", fontSize: 13 }}>暂无 cleanup job</div>
              )}
            </div>

            {relevantCleanupJob ? (
              <>
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
            ) : null}
          </div>
        ) : (
          <div style={{ color: "#7d6b57" }}>选择一个 batch 查看详情</div>
        )}
      </div>
    </div>
  );
}
