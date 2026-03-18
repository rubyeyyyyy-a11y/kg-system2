import type { ImportJobResp } from "../types/import";

type JobPanelProps = {
  jobs: ImportJobResp[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
  onCancel: (jobId: string) => void;
  onDownloadFailedRows: (jobId: string) => void;
  onDownloadArtifact: (jobId: string, artifactName: string) => void;
};

const STATUS_COLOR: Record<ImportJobResp["status"], string> = {
  queued: "#6b7280",
  running: "#2563eb",
  post_metadata_refresh: "#7c3aed",
  post_es_sync: "#9333ea",
  post_verify_index: "#7e22ce",
  succeeded: "#15803d",
  failed_import: "#b91c1c",
  failed_postprocess: "#c2410c",
  cancelled: "#6b7280",
};

function displayStatus(job: ImportJobResp) {
  if (job.status === "queued") return "queued";
  if (job.status === "running") return "importing_per_target";
  if (job.status === "post_metadata_refresh") return "refreshing_metadata";
  if (job.status === "post_es_sync") return "syncing_search_index";
  if (job.status === "post_verify_index") return "verifying_searchable_completion";
  if (job.status === "succeeded") return "done";
  return job.status;
}

export function JobPanel({ jobs, selectedJobId, onSelect, onCancel, onDownloadFailedRows, onDownloadArtifact }: JobPanelProps) {
  const selectedJob = jobs.find((job) => job.job_id === selectedJobId) || jobs[0] || null;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(280px, 360px) minmax(0, 1fr)",
        gap: 16,
      }}
    >
      <div style={{ border: "1px solid rgba(76, 56, 36, 0.14)", borderRadius: 18, overflow: "hidden", background: "#fff" }}>
        {jobs.length === 0 ? (
          <div style={{ padding: 16, color: "#7d6b57" }}>暂无 import job</div>
        ) : (
          jobs.map((job) => (
            <button
              key={job.job_id}
              data-testid={`import-job-item-${job.job_id}`}
              onClick={() => onSelect(job.job_id)}
              style={{
                display: "grid",
                width: "100%",
                textAlign: "left",
                gap: 4,
                padding: 14,
                border: "none",
                borderBottom: "1px solid #f0e6d8",
                background: job.job_id === selectedJobId ? "#fff3dc" : "#fff",
              }}
            >
              <strong>{job.job_id}</strong>
              <span style={{ fontSize: 12, color: STATUS_COLOR[job.status] }}>{displayStatus(job)}</span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>space={job.space_name}</span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>
                processed={job.processed_rows}/{job.total_rows} success={job.success_rows} failed={job.failed_rows}
              </span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>targets={job.targets.length} artifacts={job.artifacts.length}</span>
            </button>
          ))
        )}
      </div>

      <div style={{ border: "1px solid rgba(76, 56, 36, 0.14)", borderRadius: 18, padding: 16, background: "#fffdf8" }}>
        {selectedJob ? (
          <div style={{ display: "grid", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <strong data-testid="import-selected-job-id">{selectedJob.job_id}</strong>
              <span data-testid="import-selected-job-status" style={{ fontSize: 12, color: STATUS_COLOR[selectedJob.status] }}>
                {displayStatus(selectedJob)}
              </span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>workspace={selectedJob.workspace_mode}</span>
              {selectedJob.status === "queued" || selectedJob.status === "running" ? (
                <button data-testid="import-job-cancel-button" onClick={() => onCancel(selectedJob.job_id)} style={{ marginLeft: "auto" }}>
                  取消
                </button>
              ) : null}
              {selectedJob.failed_rows > 0 ? (
                <button onClick={() => onDownloadFailedRows(selectedJob.job_id)} style={{ background: "#fff1f0", borderColor: "#ffccc7" }}>
                  下载默认 failed rows
                </button>
              ) : null}
            </div>

            <div style={{ fontSize: 13, color: "#5b4b38" }}>
              draft={selectedJob.draft_id} | plan={selectedJob.plan_id} | actor={selectedJob.created_by}
            </div>
            <div style={{ fontSize: 13, color: "#5b4b38" }}>
              sources={selectedJob.sources.map((item) => `${item.filename}:${item.inferred_kind}`).join(" | ") || "-"}
            </div>
            <div data-testid="import-job-closure-summary" style={{ fontSize: 13, color: "#5b4b38" }}>
              searchable=
              {selectedJob.completion_summary == null ? "-" : selectedJob.completion_summary.searchable ? "yes" : "no"} | search_status=
              {selectedJob.completion_summary?.search_status || "-"} | index_status=
              {selectedJob.index_status_snapshot?.status || selectedJob.completion_summary?.index_status || "-"} | canonical_docs=
              {selectedJob.index_status_snapshot?.doc_count ?? 0}
            </div>

            <div style={{ display: "grid", gap: 10 }}>
              <strong style={{ fontSize: 14 }}>Per-Target Artifacts</strong>
              {selectedJob.targets.map((target) => {
                const targetArtifacts = selectedJob.artifacts.filter((item) => item.target_id === target.target_id);
                return (
                  <div key={target.target_id} style={{ padding: 12, borderRadius: 12, background: "#f7f0e4", display: "grid", gap: 8 }}>
                    <div style={{ fontWeight: 700 }}>{`${target.object_type} "${target.object_name}" <- ${target.source_filename}`}</div>
                    <div style={{ fontSize: 13, color: "#5b4b38" }}>
                      source_id={target.source_id} | target_id={target.target_id} | columns={target.source_columns.join(", ")}
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {targetArtifacts.map((artifact) => (
                        <button
                          key={artifact.filename}
                          onClick={() => onDownloadArtifact(selectedJob.job_id, artifact.filename)}
                          style={{ background: artifact.kind === "failed_rows" ? "#fff1f0" : "#eef4ff" }}
                        >
                          {artifact.filename}
                        </button>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>

            {selectedJob.error_message ? (
              <div style={{ padding: 12, borderRadius: 12, background: "#fff1f0", color: "#a61d24", fontSize: 13 }}>
                {selectedJob.error_message}
              </div>
            ) : null}
          </div>
        ) : (
          <div style={{ color: "#7d6b57" }}>选择一个 job 查看详情</div>
        )}
      </div>
    </div>
  );
}
