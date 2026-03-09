import { useCallback, useState } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { DiscoveryEntityCandidateItem, EdgeDetailResp, NodeDetailResp, Sel } from "../types/kg";

type UseDiscoveryEntityDetailParams = {
  loadNodeDetail: (vid: number) => Promise<void> | void;
  setSel: Dispatch<SetStateAction<Sel>>;
  setNodeDetail: Dispatch<SetStateAction<NodeDetailResp | null>>;
  setEdgeDetail: Dispatch<SetStateAction<EdgeDetailResp | null>>;
  setSelectedEdgeGraphId: Dispatch<SetStateAction<string | null>>;
};

export function useDiscoveryEntityDetail({
  loadNodeDetail,
  setSel,
  setNodeDetail,
  setEdgeDetail,
  setSelectedEdgeGraphId,
}: UseDiscoveryEntityDetailParams) {
  const [selectedCandidateVid, setSelectedCandidateVid] = useState<number | null>(null);

  const viewCandidateDetail = useCallback(
    (item: DiscoveryEntityCandidateItem) => {
      const vid = Number(item.vid || item.id);
      setSelectedCandidateVid(vid);
      setSel({ kind: "node", vid });
      setEdgeDetail(null);
      setSelectedEdgeGraphId(null);
      setNodeDetail({
        vid,
        entity_name: item.label,
        entity_type: item.entity_type || "",
        source: item.source || "",
        description: item.description || "",
        entity_raw_id: item.raw_id || "",
        version: 0,
        updated_at: 0,
        updated_by: "",
        props: {},
      });
      void loadNodeDetail(vid);
    },
    [loadNodeDetail, setEdgeDetail, setNodeDetail, setSel, setSelectedEdgeGraphId]
  );

  return {
    selectedCandidateVid,
    viewCandidateDetail,
  };
}
