import { useEffect, useRef, useState } from "react";
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
  scopeKey?: string;
  enabled?: boolean;
  spaceName?: string;
};

export function useEntityTypeOptions(params: UseEntityTypeOptionsParams = {}): UseEntityTypeOptionsResult {
  const deferMs = Number.isFinite(params.deferMs) ? Math.max(0, Number(params.deferMs)) : 0;
  const scopeKey = String(params.scopeKey || "").trim();
  const enabled = params.enabled !== false;
  const spaceName = params.spaceName;
  const [options, setOptions] = useState<EntityTypeItem[]>(FALLBACK_ENTITY_TYPES);
  const [usedFallback, setUsedFallback] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const scopeRef = useRef(scopeKey);

  useEffect(() => {
    scopeRef.current = scopeKey;
  }, [scopeKey]);

  useEffect(() => {
    setOptions(FALLBACK_ENTITY_TYPES);
    setUsedFallback(false);
    setLoading(false);
    setLoaded(false);
  }, [scopeKey, enabled]);

  async function loadEntityTypesOnce() {
    if (loading || loaded) return;
    const requestScope = scopeKey;
    setLoading(true);
    try {
      const list = await entityTypesApi({ spaceName });
      if (scopeRef.current !== requestScope) return;
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
      if (scopeRef.current === requestScope) {
        console.warn("entity_types fetch failed:", e instanceof Error ? e.message : String(e));
        setOptions(FALLBACK_ENTITY_TYPES);
        setUsedFallback(true);
      }
    } finally {
      if (scopeRef.current === requestScope) {
        setLoading(false);
        setLoaded(true);
      }
    }
  }

  useEffect(() => {
    if (!enabled) return;
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
  }, [deferMs, enabled, scopeKey, spaceName]);

  return {
    options,
    usedFallback,
    loading,
    loaded,
    ensureLoaded: loadEntityTypesOnce,
  };
}
