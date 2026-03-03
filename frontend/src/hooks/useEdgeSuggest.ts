import { useEffect, useRef, useState } from "react";
import type { Dispatch, KeyboardEvent, RefObject, SetStateAction } from "react";
import { edgeSuggest as fetchEdgeSuggestApi } from "../api/kg";
import { DEBOUNCE_MS, MIN_CHARS, SUGGEST_LIMIT } from "../constants/kg";
import type { EdgeSearchItem } from "../types/kg";

type UseEdgeSuggestParams = {
  q: string;
  relation: string;
  sourceDb: string;
  onSelect: (item: EdgeSearchItem) => void;
  onQueryChange: (value: string) => void;
  onSearch: () => void;
};

type UseEdgeSuggestResult = {
  suggestOpen: boolean;
  suggestItems: EdgeSearchItem[];
  suggestLoading: boolean;
  suggestError: string | null;
  suggestHighlightIndex: number;
  suggestWrapRef: RefObject<HTMLDivElement | null>;
  onInputChange: (value: string) => void;
  onKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  setSuggestHighlightIndex: Dispatch<SetStateAction<number>>;
  openSuggestPanel: () => void;
  closeSuggestPanel: () => void;
  selectSuggestCandidate: (item: EdgeSearchItem) => void;
};

export function useEdgeSuggest({
  q,
  relation,
  sourceDb,
  onSelect,
  onQueryChange,
  onSearch,
}: UseEdgeSuggestParams): UseEdgeSuggestResult {
  const [suggestOpen, setSuggestOpen] = useState(false);
  const [suggestItems, setSuggestItems] = useState<EdgeSearchItem[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
  const [suggestHighlightIndex, setSuggestHighlightIndex] = useState(-1);

  const suggestWrapRef = useRef<HTMLDivElement>(null);
  const suggestAbortRef = useRef<AbortController | null>(null);
  const suggestReqIdRef = useRef(0);
  const suppressNextSuggestRef = useRef(false);
  const prevSuggestDepsRef = useRef<{ q: string; relation: string; sourceDb: string }>({
    q: "",
    relation: "",
    sourceDb: "",
  });

  function invalidateSuggestRequest() {
    suggestReqIdRef.current += 1;
    if (suggestAbortRef.current) {
      suggestAbortRef.current.abort();
      suggestAbortRef.current = null;
    }
  }

  function clearSuggestPanelState() {
    setSuggestOpen(false);
    setSuggestItems([]);
    setSuggestLoading(false);
    setSuggestError(null);
    setSuggestHighlightIndex(-1);
  }

  function closeSuggestPanel() {
    invalidateSuggestRequest();
    clearSuggestPanelState();
  }

  function openSuggestPanel() {
    setSuggestOpen(true);
  }

  async function fetchSuggest(keyword: string) {
    const reqId = suggestReqIdRef.current + 1;
    suggestReqIdRef.current = reqId;

    if (suggestAbortRef.current) suggestAbortRef.current.abort();
    const controller = new AbortController();
    suggestAbortRef.current = controller;

    setSuggestOpen(true);
    setSuggestLoading(true);
    setSuggestError(null);
    setSuggestHighlightIndex(-1);

    try {
      const json = await fetchEdgeSuggestApi({
        q: keyword,
        limit: SUGGEST_LIMIT,
        relation,
        source_db: sourceDb,
        signal: controller.signal,
      });

      if (reqId !== suggestReqIdRef.current) return;
      setSuggestItems(Array.isArray(json.items) ? json.items : []);
      setSuggestError(null);
      setSuggestOpen(true);
    } catch (e: unknown) {
      if (controller.signal.aborted) return;
      if (reqId !== suggestReqIdRef.current) return;
      const msg = e instanceof Error ? e.message : String(e);
      console.warn("edge suggest error:", msg);
      setSuggestItems([]);
      setSuggestError("候选请求失败（不影响搜索）");
      setSuggestOpen(true);
    } finally {
      if (reqId === suggestReqIdRef.current) setSuggestLoading(false);
    }
  }

  function selectSuggestCandidate(item: EdgeSearchItem) {
    suppressNextSuggestRef.current = true;
    onSelect(item);
    closeSuggestPanel();
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      if (!suggestOpen || suggestItems.length === 0) return;
      e.preventDefault();
      setSuggestHighlightIndex((prev) => (prev < 0 ? 0 : (prev + 1) % suggestItems.length));
      return;
    }

    if (e.key === "ArrowUp") {
      if (!suggestOpen || suggestItems.length === 0) return;
      e.preventDefault();
      setSuggestHighlightIndex((prev) => {
        if (prev < 0) return suggestItems.length - 1;
        return prev <= 0 ? suggestItems.length - 1 : prev - 1;
      });
      return;
    }

    if (e.key === "Enter") {
      if (suggestOpen && suggestItems.length > 0) {
        e.preventDefault();
        const idx = suggestHighlightIndex >= 0 ? suggestHighlightIndex : 0;
        const item = suggestItems[idx];
        if (item) selectSuggestCandidate(item);
        return;
      }
      closeSuggestPanel();
      onSearch();
      return;
    }

    if (e.key === "Escape" && suggestOpen) {
      e.preventDefault();
      closeSuggestPanel();
    }
  }

  function onInputChange(value: string) {
    onQueryChange(value);
  }

  useEffect(() => {
    const keyword = q.trim();
    const prev = prevSuggestDepsRef.current;
    const qChanged = prev.q !== keyword;
    const filterChanged = prev.relation !== relation || prev.sourceDb !== sourceDb;

    prevSuggestDepsRef.current = { q: keyword, relation, sourceDb };

    if (suppressNextSuggestRef.current) {
      suppressNextSuggestRef.current = false;
      return;
    }

    if (keyword.length < MIN_CHARS) {
      closeSuggestPanel();
      return;
    }

    if (filterChanged && !suggestOpen && !qChanged) return;
    if (!qChanged && !filterChanged) return;

    const timer = window.setTimeout(() => {
      void fetchSuggest(keyword);
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [q, relation, sourceDb, suggestOpen]);

  useEffect(() => {
    if (!suggestOpen) return;
    const onDocMouseDown = (e: MouseEvent) => {
      const el = suggestWrapRef.current;
      if (el && !el.contains(e.target as Node)) closeSuggestPanel();
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => {
      document.removeEventListener("mousedown", onDocMouseDown);
    };
  }, [suggestOpen]);

  useEffect(() => {
    return () => {
      invalidateSuggestRequest();
    };
  }, []);

  return {
    suggestOpen,
    suggestItems,
    suggestLoading,
    suggestError,
    suggestHighlightIndex,
    suggestWrapRef,
    onInputChange,
    onKeyDown,
    setSuggestHighlightIndex,
    openSuggestPanel,
    closeSuggestPanel,
    selectSuggestCandidate,
  };
}
