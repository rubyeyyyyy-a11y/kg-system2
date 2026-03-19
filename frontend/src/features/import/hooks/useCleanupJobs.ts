import { listCleanupJobs } from "../api/import";
import type { CleanupJobResp } from "../types/import";
import { useImportPollingResource } from "./useImportPollingResource";

const EMPTY_CLEANUP_JOBS: CleanupJobResp[] = [];

export function useCleanupJobs(enabled = true) {
  const { data, loading, error, reload, setData } = useImportPollingResource({
    enabled,
    initialData: EMPTY_CLEANUP_JOBS,
    load: listCleanupJobs,
  });

  return { cleanupJobs: data, loading, error, reload, setCleanupJobs: setData };
}
