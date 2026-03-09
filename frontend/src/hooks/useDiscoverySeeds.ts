import { useCallback, useMemo, useState } from "react";

import type { SuggestItem } from "../types/kg";

export function useDiscoverySeeds(initial?: SuggestItem[]) {
  const [items, setItems] = useState<SuggestItem[]>(() => initial || []);

  const addItems = useCallback((nextItems: SuggestItem[]) => {
    setItems((prev) => {
      const merged = [...prev];
      const seen = new Set(prev.map((item) => item.vid));
      for (const item of nextItems) {
        if (seen.has(item.vid)) continue;
        seen.add(item.vid);
        merged.push(item);
      }
      return merged;
    });
  }, []);

  const removeItem = useCallback((vid: number) => {
    setItems((prev) => prev.filter((item) => item.vid !== vid));
  }, []);

  const clear = useCallback(() => {
    setItems([]);
  }, []);

  const idSet = useMemo(() => new Set(items.map((item) => item.vid)), [items]);

  return {
    items,
    setItems,
    addItems,
    removeItem,
    clear,
    idSet,
  };
}
