import { listImportJobs } from "../api/import";
import type { ImportJobResp } from "../types/import";
import { useImportPollingResource } from "./useImportPollingResource";

const EMPTY_IMPORT_JOBS: ImportJobResp[] = [];

export function useImportJobs(enabled = true) {
  const { data, loading, error, reload, setData } = useImportPollingResource({
    enabled,
    initialData: EMPTY_IMPORT_JOBS,
    load: listImportJobs,
  });

  return { jobs: data, loading, error, reload, setJobs: setData };
}
