import { useEffect, useRef, useState } from "react";

import { listImportBatches } from "../api/import";
import { useCurrentSpace } from "../../space/hooks/useCurrentSpace";
import type { ImportBatchResp } from "../types/import";

export function useImportBatches(enabled = true) {
  const { currentSpace, switchState } = useCurrentSpace();
  const [batches, setBatches] = useState<ImportBatchResp[]>([]);
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
      const next = await listImportBatches();
      if (requestSeqRef.current !== requestSeq || scopeKeyRef.current !== scopeKey) return;
      setBatches(next);
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
    setBatches([]);
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

  return { batches, loading, error, reload, setBatches };
}
