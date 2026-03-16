import { useEffect, useState } from "react";

import { listImportJobs } from "../api/import";
import { useCurrentSpace } from "../../space/hooks/useCurrentSpace";
import type { ImportJobResp } from "../types/import";

export function useImportJobs(enabled = true) {
  const { currentSpace } = useCurrentSpace();
  const [jobs, setJobs] = useState<ImportJobResp[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    try {
      setJobs(await listImportJobs());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!enabled) return;
    void reload();
    const timer = window.setInterval(() => {
      void reload();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [enabled, currentSpace]);

  return { jobs, loading, error, reload, setJobs };
}
