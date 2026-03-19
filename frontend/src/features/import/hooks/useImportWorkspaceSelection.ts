import { useEffect, useRef, useState } from "react";

import { getImportJobLogs, listImportBatchItems } from "../api/import";
import type { ImportBatchItem, ImportBatchResp, ImportJobResp } from "../types/import";

type UseImportWorkspaceSelectionArgs = {
  jobs: ImportJobResp[];
  batches: ImportBatchResp[];
};

export function useImportWorkspaceSelection({ jobs, batches }: UseImportWorkspaceSelectionArgs) {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [selectedBatchIds, setSelectedBatchIds] = useState<string[]>([]);
  const [selectedBatchItems, setSelectedBatchItems] = useState<ImportBatchItem[]>([]);
  const [jobLogs, setJobLogs] = useState<string[]>([]);
  const [jobsTab, setJobsTab] = useState<"jobs" | "batches">("jobs");
  const jobLogsRequestRef = useRef(0);
  const batchItemsRequestRef = useRef(0);

  useEffect(() => {
    if (jobs.length === 0) {
      setSelectedJobId(null);
      return;
    }
    if (selectedJobId == null || !jobs.some((job) => job.job_id === selectedJobId)) {
      setSelectedJobId(jobs[0].job_id);
    }
  }, [jobs, selectedJobId]);

  useEffect(() => {
    if (batches.length === 0) {
      setSelectedBatchId(null);
      setSelectedBatchIds([]);
      return;
    }
    if (selectedBatchId == null || !batches.some((batch) => batch.batch_id === selectedBatchId)) {
      setSelectedBatchId(batches[0].batch_id);
    }
    setSelectedBatchIds((previous) =>
      previous.filter((batchId) => batches.some((batch) => batch.batch_id === batchId))
    );
  }, [batches, selectedBatchId]);

  useEffect(() => {
    if (!selectedJobId) {
      setJobLogs([]);
      return;
    }
    const requestSeq = jobLogsRequestRef.current + 1;
    jobLogsRequestRef.current = requestSeq;
    void (async () => {
      try {
        const logs = await getImportJobLogs(selectedJobId);
        if (jobLogsRequestRef.current !== requestSeq) return;
        setJobLogs(logs.lines);
      } catch {
        if (jobLogsRequestRef.current !== requestSeq) return;
        setJobLogs([]);
      }
    })();
  }, [jobs, selectedJobId]);

  useEffect(() => {
    if (!selectedBatchId) {
      setSelectedBatchItems([]);
      return;
    }
    const requestSeq = batchItemsRequestRef.current + 1;
    batchItemsRequestRef.current = requestSeq;
    void (async () => {
      try {
        const items = await listImportBatchItems(selectedBatchId);
        if (batchItemsRequestRef.current !== requestSeq) return;
        setSelectedBatchItems(items);
      } catch {
        if (batchItemsRequestRef.current !== requestSeq) return;
        setSelectedBatchItems([]);
      }
    })();
  }, [batches, selectedBatchId]);

  function toggleBatchSelection(batchId: string) {
    setSelectedBatchIds((previous) =>
      previous.includes(batchId) ? previous.filter((item) => item !== batchId) : [...previous, batchId]
    );
  }

  function clearSpaceBoundState() {
    setJobLogs([]);
    setSelectedJobId(null);
    setSelectedBatchId(null);
    setSelectedBatchIds([]);
    setSelectedBatchItems([]);
  }

  return {
    jobLogs,
    jobsTab,
    selectedBatchId,
    selectedBatchIds,
    selectedBatchItems,
    selectedJobId,
    clearSpaceBoundState,
    setJobsTab,
    setSelectedBatchId,
    setSelectedJobId,
    toggleBatchSelection,
  };
}
