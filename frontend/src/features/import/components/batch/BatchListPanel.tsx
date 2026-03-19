import type { ImportBatchResp } from "../../types/import";
import { cleanupEnabled, formatFlag } from "./utils";

type BatchListPanelProps = {
  batches: ImportBatchResp[];
  selectedBatchId: string | null;
  selectedBatchIds: string[];
  onSelectBatch: (batchId: string) => void;
  onToggleBatch: (batchId: string) => void;
};

export function BatchListPanel({
  batches,
  selectedBatchId,
  selectedBatchIds,
  onSelectBatch,
  onToggleBatch,
}: BatchListPanelProps) {
  if (batches.length === 0) {
    return <div style={{ padding: 16, color: "#7d6b57" }}>暂无 batch 历史</div>;
  }

  return (
    <>
      {batches.map((batch) => (
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
      ))}
    </>
  );
}
