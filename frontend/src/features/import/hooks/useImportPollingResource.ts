import { useEffect, useRef, useState } from "react";

import { useCurrentSpace } from "../../space/hooks/useCurrentSpace";

type UseImportPollingResourceOptions<T> = {
  enabled?: boolean;
  intervalMs?: number;
  initialData: T;
  load: () => Promise<T>;
};

export function useImportPollingResource<T>({
  enabled = true,
  intervalMs = 4000,
  initialData,
  load,
}: UseImportPollingResourceOptions<T>) {
  const { currentSpace, switchState } = useCurrentSpace();
  const [data, setData] = useState(initialData);
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
      const next = await load();
      if (requestSeqRef.current !== requestSeq || scopeKeyRef.current !== scopeKey) return;
      setData(next);
      setError(null);
    } catch (error) {
      if (requestSeqRef.current !== requestSeq || scopeKeyRef.current !== scopeKey) return;
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      if (requestSeqRef.current === requestSeq && scopeKeyRef.current === scopeKey) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    setData(initialData);
    setError(null);
  }, [currentSpace, switchState.switchNonce, initialData]);

  useEffect(() => {
    if (!enabled) return;
    void reload();
    const timer = window.setInterval(() => {
      void reload();
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [currentSpace, enabled, intervalMs, switchState.switchNonce]);

  return { data, loading, error, reload, setData };
}
