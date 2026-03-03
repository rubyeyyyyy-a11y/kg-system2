import { useEffect, useState } from "react";
import { entityTypes as entityTypesApi } from "../api/kg";
import { FALLBACK_ENTITY_TYPES } from "../constants/entityTypes";
import type { EntityTypeItem } from "../types/kg";

type UseEntityTypeOptionsResult = {
  options: EntityTypeItem[];
  usedFallback: boolean;
};

export function useEntityTypeOptions(): UseEntityTypeOptionsResult {
  const [options, setOptions] = useState<EntityTypeItem[]>(FALLBACK_ENTITY_TYPES);
  const [usedFallback, setUsedFallback] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadEntityTypes() {
      try {
        const list = await entityTypesApi();
        if (cancelled) return;
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
          return;
        }
      } catch (e: unknown) {
        console.warn("entity_types fetch failed:", e instanceof Error ? e.message : String(e));
      }

      if (cancelled) return;
      setOptions(FALLBACK_ENTITY_TYPES);
      setUsedFallback(true);
    }

    void loadEntityTypes();
    return () => {
      cancelled = true;
    };
  }, []);

  return { options, usedFallback };
}
