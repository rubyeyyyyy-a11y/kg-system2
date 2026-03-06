import { useEffect, useState } from "react";
import { entityTypes as entityTypesApi } from "../api/kg";
import { FALLBACK_ENTITY_TYPES } from "../constants/entityTypes";
import type { EntityTypeItem } from "../types/kg";

type UseEntityTypeOptionsResult = {
  options: EntityTypeItem[];
  usedFallback: boolean;
  loading: boolean;
  loaded: boolean;
  ensureLoaded: () => Promise<void>;
};

type UseEntityTypeOptionsParams = {
  deferMs?: number;
};

export function useEntityTypeOptions(params: UseEntityTypeOptionsParams = {}): UseEntityTypeOptionsResult {
  const deferMs = Number.isFinite(params.deferMs) ? Math.max(0, Number(params.deferMs)) : 0;
  const [options, setOptions] = useState<EntityTypeItem[]>(FALLBACK_ENTITY_TYPES);
  const [usedFallback, setUsedFallback] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  async function loadEntityTypesOnce() {
    if (loading || loaded) return;
    setLoading(true);
    try {
      const list = await entityTypesApi();
      const next = Array.isArray(list)
        ? list
            .filter((x) => x && typeof x.entity_type === "string" && x.entity_type.trim())
            .map((x) => ({
              entity_type: String(x.entity_type).trim(),
              count: Number(x.count) > 0 ? Number(x.count) : 0,
            }))
        : [];
      if (next.length > 0) {
        setOptions(next);
        setUsedFallback(false);
      } else {
        setOptions(FALLBACK_ENTITY_TYPES);
        setUsedFallback(true);
      }
    } catch (e: unknown) {
      console.warn("entity_types fetch failed:", e instanceof Error ? e.message : String(e));
      setOptions(FALLBACK_ENTITY_TYPES);
      setUsedFallback(true);
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }

  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (cancelled) return;
      void loadEntityTypesOnce();
    }, deferMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deferMs]);

  return {
    options,
    usedFallback,
    loading,
    loaded,
    ensureLoaded: loadEntityTypesOnce,
  };
}
