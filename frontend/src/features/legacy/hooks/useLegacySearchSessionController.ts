import { useCallback, useRef, useState } from "react";

import { useEdgeSuggest } from "../../../hooks/useEdgeSuggest";
import { useRawIdSuggest } from "../../../hooks/useRawIdSuggest";
import { useSuggest } from "../../../hooks/useSuggest";
import type {
  EdgeSearchItem,
  EdgeSearchResp,
  PairPathCandidate,
  RawIdSuggestItem,
  SearchResp,
  SuggestItem,
} from "../../../types/kg";

const EMPTY_SPACE_META = {
  space_name: "",
  graph_status: "unavailable" as const,
  search_status: "unavailable" as const,
  coverage_pct: null,
  index_status: null,
};

type MultiGraphParams = {
  selectedEntities: SuggestItem[];
  directOnly: boolean;
  explainPaths: boolean;
  k: 2 | 3;
};

type MultiGraphRequest = {
  vids: number[];
  direct_only: boolean;
  explain_paths: boolean;
  k: 2 | 3;
  relations: string[];
  max_nodes: number;
  max_edges: number;
  per_pair_path_limit: number;
  ignore_direction: boolean;
};

type LegacyWorkspaceSession =
  | {
      kind: "single";
      rootVid: number;
      hop: number;
      relations: string[];
    }
  | {
      kind: "multi";
      params: MultiGraphParams;
      relations: string[];
    }
  | null;

export function useLegacySearchSessionController({
  currentSpaceName,
  spaceScopeKey,
  onSearch,
  onEdgeSearch,
  onSelectNameSuggest,
  onSelectRawIdSuggest,
  onSelectEdgeSuggest,
}: {
  currentSpaceName: string;
  spaceScopeKey: string;
  onSearch: () => void;
  onEdgeSearch: () => void;
  onSelectNameSuggest?: (item: SuggestItem) => void;
  onSelectRawIdSuggest?: (item: RawIdSuggestItem) => void;
  onSelectEdgeSuggest?: (item: EdgeSearchItem) => void;
}) {
  const [q, setQ] = useState("");
  const [searchName, setSearchName] = useState(true);
  const [searchDesc, setSearchDesc] = useState(false);
  const [entityType, setEntityType] = useState("");
  const [entityRawId, setEntityRawId] = useState("");
  const [source, setSource] = useState("");
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchData, setSearchData] = useState<SearchResp>({
    nodes: [],
    edges: [],
    total_candidates: 0,
    space_meta: EMPTY_SPACE_META,
  });
  const [searchSelectedVid, setSearchSelectedVid] = useState<number | null>(null);

  const [edgeQ, setEdgeQ] = useState("");
  const [edgeSearchInRelation, setEdgeSearchInRelation] = useState(true);
  const [edgeSearchInProps, setEdgeSearchInProps] = useState(true);
  const [edgeSearchSourceDb, setEdgeSearchSourceDb] = useState("");
  const [edgeSearchRelation, setEdgeSearchRelation] = useState("");
  const [loadingEdgeSearch, setLoadingEdgeSearch] = useState(false);
  const [edgeSearchData, setEdgeSearchData] = useState<EdgeSearchResp>({ edges: [], total_candidates: 0 });
  const [edgeSearchNotice, setEdgeSearchNotice] = useState<string | null>(null);
  const [pendingEdgeLocate, setPendingEdgeLocate] = useState<EdgeSearchItem | null>(null);

  const [loadingMultiGraph, setLoadingMultiGraph] = useState(false);
  const [loadingApplyPathChoice, setLoadingApplyPathChoice] = useState(false);
  const [legacyWorkspaceSession, setLegacyWorkspaceSession] = useState<LegacyWorkspaceSession>(null);
  const [lastMultiGraphParams, setLastMultiGraphParams] = useState<MultiGraphParams | null>(null);
  const [lastMultiGraphRequest, setLastMultiGraphRequest] = useState<MultiGraphRequest | null>(null);
  const [pathCandidates, setPathCandidates] = useState<PairPathCandidate[]>([]);
  const [chosenPathByPair, setChosenPathByPair] = useState<Record<string, number>>({});
  const [appliedExtraPaths, setAppliedExtraPaths] = useState<Record<string, number[]>>({});

  const searchAbortRef = useRef<AbortController | null>(null);
  const edgeSearchAbortRef = useRef<AbortController | null>(null);
  const multiGraphAbortRef = useRef<AbortController | null>(null);
  const applyPathAbortRef = useRef<AbortController | null>(null);

  const {
    suggestOpen,
    suggestItems,
    suggestLoading,
    suggestError,
    suggestHighlightIndex,
    suggestWrapRef,
    onInputChange,
    onKeyDown,
    setSuggestHighlightIndex,
    closeSuggestPanel,
    selectSuggestCandidate,
  } = useSuggest({
    q,
    entityType,
    source,
    spaceName: currentSpaceName,
    scopeKey: spaceScopeKey,
    onSelect: (item) => {
      setQ(item.label);
      onSelectNameSuggest?.(item);
    },
    onQueryChange: setQ,
    onSearch,
  });

  const {
    suggestOpen: rawIdSuggestOpen,
    suggestItems: rawIdSuggestItems,
    suggestLoading: rawIdSuggestLoading,
    suggestError: rawIdSuggestError,
    suggestHighlightIndex: rawIdSuggestHighlightIndex,
    suggestWrapRef: rawIdSuggestWrapRef,
    onInputChange: onRawIdInputChange,
    onKeyDown: onRawIdKeyDown,
    setSuggestHighlightIndex: setRawIdSuggestHighlightIndex,
    closeSuggestPanel: closeRawIdSuggestPanel,
    selectSuggestCandidate: selectRawIdSuggestCandidate,
  } = useRawIdSuggest({
    q: entityRawId,
    entityType,
    source,
    spaceName: currentSpaceName,
    scopeKey: spaceScopeKey,
    onSelect: (item: RawIdSuggestItem) => {
      setEntityRawId(item.entity_raw_id);
      if (item.label) setQ(item.label);
      onSelectRawIdSuggest?.(item);
    },
    onQueryChange: setEntityRawId,
    onSearch,
  });

  const {
    suggestOpen: edgeSuggestOpen,
    suggestItems: edgeSuggestItems,
    suggestLoading: edgeSuggestLoading,
    suggestError: edgeSuggestError,
    suggestHighlightIndex: edgeSuggestHighlightIndex,
    suggestWrapRef: edgeSuggestWrapRef,
    onInputChange: onEdgeInputChange,
    onKeyDown: onEdgeKeyDown,
    setSuggestHighlightIndex: setEdgeSuggestHighlightIndex,
    closeSuggestPanel: closeEdgeSuggestPanel,
    selectSuggestCandidate: selectEdgeSuggestCandidate,
  } = useEdgeSuggest({
    q: edgeQ,
    relation: edgeSearchRelation,
    sourceDb: edgeSearchSourceDb,
    spaceName: currentSpaceName,
    scopeKey: spaceScopeKey,
    onSelect: (item) => {
      setEdgeQ(item.relation);
      onSelectEdgeSuggest?.(item);
    },
    onQueryChange: setEdgeQ,
    onSearch: onEdgeSearch,
  });

  const clearMultiPathState = useCallback(() => {
    setPathCandidates([]);
    setChosenPathByPair({});
    setAppliedExtraPaths({});
  }, []);

  const abortSpaceScopedRequests = useCallback(() => {
    searchAbortRef.current?.abort();
    searchAbortRef.current = null;
    edgeSearchAbortRef.current?.abort();
    edgeSearchAbortRef.current = null;
    multiGraphAbortRef.current?.abort();
    multiGraphAbortRef.current = null;
    applyPathAbortRef.current?.abort();
    applyPathAbortRef.current = null;
  }, []);

  const resetForSpaceChange = useCallback(
    (nextSpace: string) => {
      abortSpaceScopedRequests();
      closeSuggestPanel();
      closeRawIdSuggestPanel();
      closeEdgeSuggestPanel();
      setLoadingSearch(false);
      setSearchData({ nodes: [], edges: [], total_candidates: 0, space_meta: { ...EMPTY_SPACE_META, space_name: nextSpace } });
      setSearchSelectedVid(null);
      setQ("");
      setSearchName(true);
      setSearchDesc(false);
      setEntityType("");
      setEntityRawId("");
      setSource("");
      setEdgeQ("");
      setEdgeSearchInRelation(true);
      setEdgeSearchInProps(true);
      setEdgeSearchSourceDb("");
      setEdgeSearchRelation("");
      setEdgeSearchData({ edges: [], total_candidates: 0 });
      setEdgeSearchNotice(null);
      setPendingEdgeLocate(null);
      setLoadingMultiGraph(false);
      setLoadingApplyPathChoice(false);
      setLegacyWorkspaceSession(null);
      setLastMultiGraphParams(null);
      setLastMultiGraphRequest(null);
      clearMultiPathState();
    },
    [abortSpaceScopedRequests, clearMultiPathState, closeEdgeSuggestPanel, closeRawIdSuggestPanel, closeSuggestPanel]
  );

  return {
    q,
    setQ,
    searchName,
    setSearchName,
    searchDesc,
    setSearchDesc,
    entityType,
    setEntityType,
    entityRawId,
    setEntityRawId,
    source,
    setSource,
    loadingSearch,
    setLoadingSearch,
    searchData,
    setSearchData,
    searchSelectedVid,
    setSearchSelectedVid,
    edgeQ,
    setEdgeQ,
    edgeSearchInRelation,
    setEdgeSearchInRelation,
    edgeSearchInProps,
    setEdgeSearchInProps,
    edgeSearchSourceDb,
    setEdgeSearchSourceDb,
    edgeSearchRelation,
    setEdgeSearchRelation,
    loadingEdgeSearch,
    setLoadingEdgeSearch,
    edgeSearchData,
    setEdgeSearchData,
    edgeSearchNotice,
    setEdgeSearchNotice,
    pendingEdgeLocate,
    setPendingEdgeLocate,
    loadingMultiGraph,
    setLoadingMultiGraph,
    loadingApplyPathChoice,
    setLoadingApplyPathChoice,
    legacyWorkspaceSession,
    setLegacyWorkspaceSession,
    lastMultiGraphParams,
    setLastMultiGraphParams,
    lastMultiGraphRequest,
    setLastMultiGraphRequest,
    pathCandidates,
    setPathCandidates,
    chosenPathByPair,
    setChosenPathByPair,
    appliedExtraPaths,
    setAppliedExtraPaths,
    searchAbortRef,
    edgeSearchAbortRef,
    multiGraphAbortRef,
    applyPathAbortRef,
    suggestOpen,
    suggestItems,
    suggestLoading,
    suggestError,
    suggestHighlightIndex,
    suggestWrapRef,
    onInputChange,
    onKeyDown,
    setSuggestHighlightIndex,
    closeSuggestPanel,
    selectSuggestCandidate,
    rawIdSuggestOpen,
    rawIdSuggestItems,
    rawIdSuggestLoading,
    rawIdSuggestError,
    rawIdSuggestHighlightIndex,
    rawIdSuggestWrapRef,
    onRawIdInputChange,
    onRawIdKeyDown,
    setRawIdSuggestHighlightIndex,
    closeRawIdSuggestPanel,
    selectRawIdSuggestCandidate,
    edgeSuggestOpen,
    edgeSuggestItems,
    edgeSuggestLoading,
    edgeSuggestError,
    edgeSuggestHighlightIndex,
    edgeSuggestWrapRef,
    onEdgeInputChange,
    onEdgeKeyDown,
    setEdgeSuggestHighlightIndex,
    closeEdgeSuggestPanel,
    selectEdgeSuggestCandidate,
    clearMultiPathState,
    abortSpaceScopedRequests,
    resetForSpaceChange,
  };
}
