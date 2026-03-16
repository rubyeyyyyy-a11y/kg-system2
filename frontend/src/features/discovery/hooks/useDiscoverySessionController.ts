import { useCallback, useRef, useState } from "react";

import { useDiscoveryCandidateResults } from "../../../hooks/useDiscoveryCandidateResults";
import { useDiscoveryCandidateSearch } from "../../../hooks/useDiscoveryCandidateSearch";
import { useDiscoverySeeds } from "../../../hooks/useDiscoverySeeds";
import type { GraphDiscoveryResp } from "../../../types/kg";

type DiscoveryRequest = {
  seed_vids: number[];
  allowed_entity_types: string[];
  allowed_relation_types: string[];
  max_nodes: number;
  max_edges: number;
  top_k_per_type: number;
  include_candidate_candidate_edges: boolean;
  include_seed_seed_edges: boolean;
  hop: number;
  ranking_mode: "v1" | "layered_multiseed";
};

type DiscoveryQueryState = {
  allowedEntityTypes: string[];
  allowedRelationTypes: string[];
  maxNodes: number;
  maxEdges: number;
  topKPerType: number;
  includeCandidateCandidateEdges: boolean;
  includeSeedSeedEdges: boolean;
  hop: number;
};

type DiscoveryRuntimeState = {
  entityTypes: string[];
  relationTypes: string[];
};

const DEFAULT_DISCOVERY_QUERY: DiscoveryQueryState = {
  allowedEntityTypes: [],
  allowedRelationTypes: [],
  maxNodes: 90,
  maxEdges: 140,
  topKPerType: 12,
  includeCandidateCandidateEdges: true,
  includeSeedSeedEdges: false,
  hop: 3,
};

export function useDiscoverySessionController({
  currentSpaceName,
  spaceScopeKey,
  onError,
}: {
  currentSpaceName: string;
  spaceScopeKey: string;
  onError: (message: string) => void;
}) {
  const discoveryAbortRef = useRef<AbortController | null>(null);
  const [loadingDiscovery, setLoadingDiscovery] = useState(false);
  const [lastDiscoveryRequest, setLastDiscoveryRequest] = useState<DiscoveryRequest | null>(null);
  const discoverySeedsState = useDiscoverySeeds();
  const [discoveryResult, setDiscoveryResult] = useState<GraphDiscoveryResp | null>(null);
  const discoveryCandidateSearch = useDiscoveryCandidateSearch();
  const discoveryCandidateResults = useDiscoveryCandidateResults({
    query: discoveryCandidateSearch.query,
    spaceName: currentSpaceName,
    scopeKey: spaceScopeKey,
    onError: (message) => onError(`候选搜索失败：${message}`),
  });
  const [discoveryQuery, setDiscoveryQuery] = useState<DiscoveryQueryState>(DEFAULT_DISCOVERY_QUERY);
  const [discoveryRuntimeFilters, setDiscoveryRuntimeFilters] = useState<DiscoveryRuntimeState>({
    entityTypes: [],
    relationTypes: [],
  });
  const [discoveryExpandFilters, setDiscoveryExpandFilters] = useState<DiscoveryRuntimeState>({
    entityTypes: [],
    relationTypes: [],
  });
  const [discoveryRenderedPanelCollapsed, setDiscoveryRenderedPanelCollapsed] = useState(true);
  const [discoveryDroppedPanelCollapsed, setDiscoveryDroppedPanelCollapsed] = useState(false);

  const resetForSpaceChange = useCallback(() => {
    discoveryAbortRef.current?.abort();
    discoveryAbortRef.current = null;
    setLoadingDiscovery(false);
    setLastDiscoveryRequest(null);
    setDiscoveryResult(null);
    discoverySeedsState.clear();
    discoveryCandidateSearch.resetQuery();
    discoveryCandidateSearch.setAdvancedOpen(false);
    discoveryCandidateResults.reset();
    setDiscoveryQuery(DEFAULT_DISCOVERY_QUERY);
    setDiscoveryRuntimeFilters({ entityTypes: [], relationTypes: [] });
    setDiscoveryExpandFilters({ entityTypes: [], relationTypes: [] });
    setDiscoveryRenderedPanelCollapsed(true);
    setDiscoveryDroppedPanelCollapsed(false);
  }, [discoveryCandidateResults, discoveryCandidateSearch, discoverySeedsState]);

  return {
    discoveryAbortRef,
    loadingDiscovery,
    setLoadingDiscovery,
    lastDiscoveryRequest,
    setLastDiscoveryRequest,
    discoverySeedsState,
    discoveryResult,
    setDiscoveryResult,
    discoveryCandidateSearch,
    discoveryCandidateResults,
    discoveryQuery,
    setDiscoveryQuery,
    discoveryRuntimeFilters,
    setDiscoveryRuntimeFilters,
    discoveryExpandFilters,
    setDiscoveryExpandFilters,
    discoveryRenderedPanelCollapsed,
    setDiscoveryRenderedPanelCollapsed,
    discoveryDroppedPanelCollapsed,
    setDiscoveryDroppedPanelCollapsed,
    resetForSpaceChange,
  };
}
