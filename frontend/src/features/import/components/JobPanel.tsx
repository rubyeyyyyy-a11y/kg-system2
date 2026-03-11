import type { ImportJobResp } from "../types/import";

type JobPanelProps = {
  jobs: ImportJobResp[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
  onCancel: (jobId: string) => void;
  onDownloadFailedRows: (jobId: string) => void;
};

const STATUS_COLOR: Record<ImportJobResp["status"], string> = {
  queued: "#6b7280",
  running: "#2563eb",
  post_metadata_refresh: "#7c3aed",
  post_es_sync: "#9333ea",
  succeeded: "#15803d",
  failed_import: "#b91c1c",
  failed_postprocess: "#c2410c",
  cancelled: "#6b7280",
};

function integrationText(job: ImportJobResp) {
  if (job.status !== "succeeded") return "";
  if (job.integration_level === "fully_integrated") return "imported successfully | fully integrated";
  if (job.integration_level === "partially_integrated") return "imported successfully | partially integrated";
  return "imported successfully | import-only";
}

function phaseHint(job: ImportJobResp) {
  if (job.cancel_requested && job.status === "running") return "cancel pending, effective at next batch boundary";
  if (job.status === "post_metadata_refresh") return "postprocess: refreshing metadata from DB";
  if (job.status === "post_es_sync") return "postprocess: syncing entity ES incrementally";
  if (job.status === "cancelled" && job.cancel_effective_at_batch) return "cancelled at batch boundary";
  return "";
}

export function JobPanel({ jobs, selectedJobId, onSelect, onCancel, onDownloadFailedRows }: JobPanelProps) {
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
              <span style={{ fontSize: 12, color: STATUS_COLOR[job.status] }}>{job.status}</span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>
                processed={job.processed_rows}/{job.total_rows} success={job.success_rows} failed={job.failed_rows}
              </span>
              {job.failed_rows > 0 ? <span style={{ fontSize: 12, color: "#a61d24" }}>failed rows available</span> : null}
            </button>
          ))
        )}
      </div>

      <div style={{ border: "1px solid rgba(76, 56, 36, 0.14)", borderRadius: 18, padding: 16, background: "#fffdf8" }}>
        {selectedJob ? (
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <strong>{selectedJob.job_id}</strong>
              <span style={{ fontSize: 12, color: STATUS_COLOR[selectedJob.status] }}>{selectedJob.status}</span>
              <span style={{ fontSize: 12, color: "#7d6b57" }}>mode={selectedJob.mode}</span>
              {selectedJob.status === "queued" || selectedJob.status === "running" ? (
                <button onClick={() => onCancel(selectedJob.job_id)} style={{ marginLeft: "auto" }}>
                  取消
                </button>
              ) : null}
              {selectedJob.failed_rows > 0 ? (
                <button onClick={() => onDownloadFailedRows(selectedJob.job_id)} style={{ background: "#fff1f0", borderColor: "#ffccc7" }}>
                  下载 failed rows
                </button>
              ) : null}
            </div>
            {integrationText(selectedJob) ? (
              <div style={{ padding: 12, borderRadius: 12, background: "#eefbf1", color: "#166534", fontSize: 13 }}>
                {integrationText(selectedJob)}
              </div>
            ) : null}
            {phaseHint(selectedJob) ? (
              <div style={{ padding: 12, borderRadius: 12, background: "#fffbe6", color: "#ad6800", fontSize: 13 }}>
                {phaseHint(selectedJob)}
              </div>
            ) : null}
            <div style={{ fontSize: 13, color: "#5b4b38" }}>
              draft={selectedJob.draft_id} | plan={selectedJob.plan_id} | actor={selectedJob.created_by}
            </div>
            <div style={{ fontSize: 13, color: "#5b4b38" }}>
              metadata={selectedJob.metadata_refreshed ? "done" : "pending"} | es=
              {selectedJob.es_sync_skipped ? "skipped" : selectedJob.affected_entity_vids.length > 0 ? "entity_sync" : "pending"}
            </div>
            <div style={{ fontSize: 13, color: "#5b4b38" }}>integration={selectedJob.integration_level}</div>
            {selectedJob.error_message ? (
              <div style={{ padding: 12, borderRadius: 12, background: "#fff1f0", color: "#a61d24", fontSize: 13 }}>
                {selectedJob.error_message}
              </div>
            ) : null}
            {selectedJob.warnings.length > 0 ? (
              <div style={{ display: "grid", gap: 6 }}>
                {selectedJob.warnings.map((warning, index) => (
                  <div key={`${warning}-${index}`} style={{ padding: 10, borderRadius: 10, background: "#fffbe6", color: "#ad6800" }}>
                    {warning}
                  </div>
                ))}
              </div>
            ) : null}
            {selectedJob.integration_warnings.length > 0 ? (
              <div style={{ display: "grid", gap: 6 }}>
                {selectedJob.integration_warnings.map((warning, index) => (
                  <div key={`${warning}-${index}`} style={{ padding: 10, borderRadius: 10, background: "#fff7e6", color: "#ad6800" }}>
                    {warning}
                  </div>
                ))}
              </div>
            ) : null}
            {selectedJob.failed_rows_truncated ? (
              <div style={{ padding: 10, borderRadius: 10, background: "#fff1f0", color: "#a61d24", fontSize: 13 }}>
                failed_rows.csv reached truncation limit; only the earliest failure rows were persisted.
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
