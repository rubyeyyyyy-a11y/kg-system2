import { useEffect, useRef, useState } from "react";

import { listImportJobs } from "../api/import";
import { useCurrentSpace } from "../../space/hooks/useCurrentSpace";
import type { ImportJobResp } from "../types/import";

export function useImportJobs(enabled = true) {
  const { currentSpace, switchState } = useCurrentSpace();
  const [jobs, setJobs] = useState<ImportJobResp[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeqRef = useRef(0);
  const scopeKeyRef = useRef("");

  async function reload() {
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    const scopeKey = `${currentSpace}::${switchState.switchNonce}`;
    scopeKeyRef.current = scopeKey;
    setLoading(true);
    try {
      const nextJobs = await listImportJobs();
      if (requestSeqRef.current !== requestSeq || scopeKeyRef.current !== scopeKey) return;
      setJobs(nextJobs);
      setError(null);
    } catch (err) {
      if (requestSeqRef.current !== requestSeq || scopeKeyRef.current !== scopeKey) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (requestSeqRef.current === requestSeq && scopeKeyRef.current === scopeKey) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    setJobs([]);
    setError(null);
  }, [currentSpace, switchState.switchNonce]);

  useEffect(() => {
    if (!enabled) return;
    void reload();
    const timer = window.setInterval(() => {
      void reload();
    }, 4000);
    return () => window.clearInterval(timer);
  }, [enabled, currentSpace, switchState.switchNonce]);

  return { jobs, loading, error, reload, setJobs };
}
