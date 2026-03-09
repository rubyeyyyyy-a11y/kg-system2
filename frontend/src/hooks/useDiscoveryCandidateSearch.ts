import { useCallback, useState } from "react";

import type { DiscoveryEntityCandidateQueryState } from "../types/kg";

export const DEFAULT_DISCOVERY_CANDIDATE_QUERY: DiscoveryEntityCandidateQueryState = {
  q: "",
  searchInName: true,
  searchInDescription: true,
  searchInType: false,
  searchInRawId: false,
  entityType: "",
  source: "",
  entityRawId: "",
  entityRawIdMode: "contains",
};

export function useDiscoveryCandidateSearch(initial?: Partial<DiscoveryEntityCandidateQueryState>) {
  const [query, setQuery] = useState<DiscoveryEntityCandidateQueryState>({
    ...DEFAULT_DISCOVERY_CANDIDATE_QUERY,
    ...initial,
  });
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const updateQuery = useCallback((patch: Partial<DiscoveryEntityCandidateQueryState>) => {
    setQuery((prev) => ({
      ...prev,
      ...patch,
    }));
  }, []);

  const resetQuery = useCallback(() => {
    setQuery(DEFAULT_DISCOVERY_CANDIDATE_QUERY);
  }, []);

  const toggleAdvancedOpen = useCallback(() => {
    setAdvancedOpen((prev) => !prev);
  }, []);

  return {
    query,
    setQuery,
    updateQuery,
    resetQuery,
    advancedOpen,
    setAdvancedOpen,
    toggleAdvancedOpen,
    canSearch: Boolean(query.q.trim() || query.entityRawId.trim()),
  };
}
