import { listImportBatches } from "../api/import";
import type { ImportBatchResp } from "../types/import";
import { useImportPollingResource } from "./useImportPollingResource";

const EMPTY_IMPORT_BATCHES: ImportBatchResp[] = [];

export function useImportBatches(enabled = true) {
  const { data, loading, error, reload, setData } = useImportPollingResource({
    enabled,
    initialData: EMPTY_IMPORT_BATCHES,
    load: listImportBatches,
  });

  return { batches: data, loading, error, reload, setBatches: setData };
}
