import { useCallback, useEffect, useState } from "react";

import { parseApiError } from "../../../utils/httpError";
import { getDefaultResolvedSpace, getResolvedCurrentSpace, listSpaces } from "../api/space";
import { getStoredCurrentSpace, setStoredCurrentSpace } from "../store";
import type { CurrentSpaceResp, SpaceSummary } from "../types/space";

type UseSpacesState = {
  spaces: SpaceSummary[];
  resolvedCurrent: CurrentSpaceResp | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

export function useSpaces(): UseSpacesState {
  const [spaces, setSpaces] = useState<SpaceSummary[]>([]);
  const [resolvedCurrent, setResolvedCurrent] = useState<CurrentSpaceResp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [nextSpaces, nextCurrent] = await Promise.all([listSpaces(), getResolvedCurrentSpace()]);
      setSpaces(nextSpaces);
      setResolvedCurrent(nextCurrent);
      if (!getStoredCurrentSpace()) setStoredCurrentSpace(nextCurrent.space_name);
    } catch (err) {
      const parsed = parseApiError(err);
      if (parsed.code === "SPACE_NOT_REGISTERED" || parsed.code === "SPACE_HEADER_INVALID") {
        const fallback = await getDefaultResolvedSpace();
        setStoredCurrentSpace(fallback.space_name);
        setResolvedCurrent(fallback);
        setSpaces(await listSpaces());
      } else {
        setError(parsed.message || "failed to load spaces");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { spaces, resolvedCurrent, loading, error, refresh };
}
