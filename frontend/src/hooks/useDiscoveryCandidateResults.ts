import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { discoveryEntityCandidates as discoveryEntityCandidatesApi } from "../api/kg";
import type {
  DiscoveryEntityCandidateItem,
  DiscoveryEntityCandidateQueryState,
  DiscoveryEntityCandidatesResp,
} from "../types/kg";
import { parseApiError } from "../utils/httpError";

const PREVIEW_PAGE_SIZE = 10;
const FULL_LIST_PAGE_SIZE = 100;
const PREVIEW_DEBOUNCE_MS = 250;
const MIN_PREVIEW_QUERY_LEN = 2;

export type DiscoveryCandidatePreviewState = {
  items: DiscoveryEntityCandidateItem[];
  open: boolean;
  loading: boolean;
  error: string | null;
  highlightIndex: number;
};

export type DiscoveryCandidateResultState = DiscoveryEntityCandidatesResp & {
  loading: boolean;
  loadingMore: boolean;
  error: string | null;
};

const EMPTY_RESULT: DiscoveryCandidateResultState = {
  items: [],
  page: 1,
  page_size: FULL_LIST_PAGE_SIZE,
  returned: 0,
  has_more: false,
  next_page: null,
  meta: {},
  loading: false,
  loadingMore: false,
  error: null,
};

const EMPTY_PREVIEW: DiscoveryCandidatePreviewState = {
  items: [],
  open: false,
  loading: false,
  error: null,
  highlightIndex: -1,
};

function buildRequest(
  query: DiscoveryEntityCandidateQueryState,
  page: number,
  pageSize: number
) {
  return {
    q: query.q,
    page,
    page_size: pageSize,
    search_in_name: query.searchInName,
    search_in_description: query.searchInDescription,
    search_in_type: query.searchInType,
    search_in_raw_id: query.searchInRawId,
    entity_type: query.entityType || null,
    source: query.source || null,
    entity_raw_id: query.entityRawId || null,
    entity_raw_id_mode: query.entityRawIdMode,
  };
}

function candidateKey(item: DiscoveryEntityCandidateItem) {
  return Number(item.vid || item.id);
}

export function useDiscoveryCandidateResults({
  query,
  onError,
}: {
  query: DiscoveryEntityCandidateQueryState;
  onError: (message: string) => void;
}) {
  const [preview, setPreview] = useState<DiscoveryCandidatePreviewState>(EMPTY_PREVIEW);
  const [result, setResult] = useState<DiscoveryCandidateResultState>(EMPTY_RESULT);
  const [committedQuery, setCommittedQuery] = useState<DiscoveryEntityCandidateQueryState | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  const previewAbortRef = useRef<AbortController | null>(null);
  const resultAbortRef = useRef<AbortController | null>(null);

  const closePreview = useCallback(() => {
    previewAbortRef.current?.abort();
    previewAbortRef.current = null;
    setPreview((prev) => ({
      ...prev,
      items: [],
      open: false,
      loading: false,
      error: null,
      highlightIndex: -1,
    }));
  }, []);

  const setPreviewHighlightIndex = useCallback((index: number) => {
    setPreview((prev) => ({
      ...prev,
      highlightIndex: index,
    }));
  }, []);

  useEffect(() => {
    const keyword = query.q.trim();
    if (keyword.length < MIN_PREVIEW_QUERY_LEN) {
      closePreview();
      return;
    }

    const timer = window.setTimeout(() => {
      previewAbortRef.current?.abort();
      const controller = new AbortController();
      previewAbortRef.current = controller;

      setPreview((prev) => ({
        ...prev,
        open: true,
        loading: true,
        error: null,
        highlightIndex: -1,
      }));

      void discoveryEntityCandidatesApi({
        ...buildRequest(query, 1, PREVIEW_PAGE_SIZE),
        signal: controller.signal,
      })
        .then((resp) => {
          if (controller.signal.aborted) return;
          setPreview({
            items: resp.items,
            open: true,
            loading: false,
            error: null,
            highlightIndex: resp.items.length > 0 ? 0 : -1,
          });
        })
        .catch((e: unknown) => {
          if (controller.signal.aborted) return;
          const parsed = parseApiError(e);
          setPreview({
            items: [],
            open: true,
            loading: false,
            error: parsed.message || "候选预览失败",
            highlightIndex: -1,
          });
        });
    }, PREVIEW_DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [closePreview, query]);

  useEffect(() => {
    return () => {
      previewAbortRef.current?.abort();
      resultAbortRef.current?.abort();
    };
  }, []);

  const runSearch = useCallback(
    async (options?: { append?: boolean; page?: number; queryOverride?: DiscoveryEntityCandidateQueryState }) => {
      const append = options?.append ?? false;
      const nextQuery = options?.queryOverride ?? (append ? committedQuery : query);
      if (!nextQuery) return;

      const qTrimmed = nextQuery.q.trim();
      const rawIdTrimmed = nextQuery.entityRawId.trim();
      if (!qTrimmed && !rawIdTrimmed) {
        setResult((prev) => ({
          ...prev,
          items: [],
          page: 1,
          returned: 0,
          has_more: false,
          next_page: null,
          loading: false,
          loadingMore: false,
          error: "请输入搜索关键词或 entity_raw_id",
        }));
        if (!append) setSelectedIds([]);
        closePreview();
        return;
      }

      const page = Math.max(1, Number(options?.page || (append ? result.next_page || 1 : 1)));
      resultAbortRef.current?.abort();
      const controller = new AbortController();
      resultAbortRef.current = controller;

      setResult((prev) => ({
        ...prev,
        loading: !append,
        loadingMore: append,
        error: null,
        ...(!append
          ? {
              items: [],
              page: 1,
              returned: 0,
              has_more: false,
              next_page: null,
              meta: {},
            }
          : {}),
      }));
      closePreview();

      if (!append) {
        setCommittedQuery({ ...nextQuery });
        setSelectedIds([]);
      }

      try {
        const resp = await discoveryEntityCandidatesApi({
          ...buildRequest(nextQuery, page, FULL_LIST_PAGE_SIZE),
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setResult((prev) => {
          const mergedItems = append
            ? (() => {
                const merged = new Map<number, DiscoveryEntityCandidateItem>();
                for (const item of prev.items) merged.set(candidateKey(item), item);
                for (const item of resp.items) merged.set(candidateKey(item), item);
                return Array.from(merged.values());
              })()
            : resp.items;
          return {
            ...resp,
            items: mergedItems,
            loading: false,
            loadingMore: false,
            error: null,
          };
        });
      } catch (e: unknown) {
        if (controller.signal.aborted) return;
        const parsed = parseApiError(e);
        setResult((prev) => ({
          ...prev,
          loading: false,
          loadingMore: false,
          error: parsed.message || "候选搜索失败",
        }));
        onError(parsed.message || "候选搜索失败");
      }
    },
    [closePreview, committedQuery, onError, query, result.next_page]
  );

  const loadMore = useCallback(async () => {
    if (result.loading || result.loadingMore) return;
    if (!result.has_more || result.next_page == null) return;
    await runSearch({
      append: true,
      page: result.next_page,
      queryOverride: committedQuery || query,
    });
  }, [committedQuery, query, result.has_more, result.loading, result.loadingMore, result.next_page, runSearch]);

  const toggleSelected = useCallback((id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  }, []);

  const clearSelected = useCallback(() => {
    setSelectedIds([]);
  }, []);

  const removeSelected = useCallback((ids: number[]) => {
    if (ids.length === 0) return;
    const removeSet = new Set(ids);
    setSelectedIds((prev) => prev.filter((id) => !removeSet.has(id)));
  }, []);

  const patchCandidate = useCallback((vid: number, patch: Partial<DiscoveryEntityCandidateItem>) => {
    setPreview((prev) => ({
      ...prev,
      items: prev.items.map((item) => (candidateKey(item) === vid ? { ...item, ...patch } : item)),
    }));
    setResult((prev) => ({
      ...prev,
      items: prev.items.map((item) => (candidateKey(item) === vid ? { ...item, ...patch } : item)),
    }));
  }, []);

  const selectedIdSet = useMemo(() => new Set<number>(selectedIds), [selectedIds]);

  return {
    preview,
    result,
    committedQuery,
    selectedIds,
    selectedIdSet,
    setPreviewHighlightIndex,
    closePreview,
    runSearch,
    loadMore,
    toggleSelected,
    clearSelected,
    removeSelected,
    patchCandidate,
  };
}
