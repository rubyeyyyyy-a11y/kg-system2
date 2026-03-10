import { useEffect, useMemo, useRef, useState } from "react";

import { graphDiscoveryExpand } from "../api/kg";
import type { CachedNodePosition, GraphRenderMutation } from "../graph/renderControl";
import { createGraphRenderMutation } from "../graph/renderControl";
import type {
  DiscoveryGraphSourceTag,
  DiscoveryNodeExpandUiState,
  EdgeBrief,
  GraphDiscoveryDroppedCandidate,
  GraphDiscoveryExpandResp,
  GraphDiscoveryResp,
  NodeBrief,
  NodeExpandSession,
} from "../types/kg";
import { edgeKey } from "../utils/kg";

export type DroppedNodeReason =
  | "dropped_by_budget"
  | "dropped_by_type_filter"
  | "dropped_by_relation_filter";

export type DroppedNodeRecord = {
  node: NodeBrief;
  reason: DroppedNodeReason;
  supportEdges: EdgeBrief[];
  sourceNodeId: number | null;
};

export type DiscoveryRenderCoverageItem = {
  key: string;
  count: number;
};

type CapabilityState = {
  expandable: boolean;
  terminal: boolean;
};

type ToggleExpandResult =
  | {
      action: "collapsed";
      firstNodeId: number | null;
      response: null;
    }
  | {
      action: "expanded";
      firstNodeId: number | null;
      response: GraphDiscoveryExpandResp;
    };

type TagMap = Record<string, DiscoveryGraphSourceTag[]>;

type UseDiscoveryGraphStateParams = {
  graphNodes: NodeBrief[];
  graphEdges: EdgeBrief[];
  maxNodes: number;
  maxEdges: number;
  seedNodeIds: Set<number>;
  onMergeGraphData: (params: { nodes?: NodeBrief[]; edges?: EdgeBrief[]; stats?: Record<string, unknown> | null }) => void;
  onNotice?: (level: "error" | "warn" | "info", message: string) => void;
};

function droppedReasonKey(reason: GraphDiscoveryDroppedCandidate["reason"]): DroppedNodeReason {
  if (reason === "type_filter") return "dropped_by_type_filter";
  if (reason === "relation_filter") return "dropped_by_relation_filter";
  return "dropped_by_budget";
}

function candidateToNode(candidate: GraphDiscoveryDroppedCandidate): NodeBrief {
  return {
    id: candidate.node_id,
    label: candidate.label,
    entity_type: candidate.entity_type,
    raw_id: candidate.raw_id,
    source: candidate.source,
    snippet: candidate.snippet,
    role: "candidate",
    layer: "supplement",
  };
}

function sortNodesByLabel<T extends { node?: NodeBrief; label?: string; id?: number }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const aLabel = String(a.node?.label || a.label || "");
    const bLabel = String(b.node?.label || b.label || "");
    const byLabel = aLabel.localeCompare(bLabel);
    if (byLabel !== 0) return byLabel;
    const aId = Number(a.node?.id ?? a.id ?? 0);
    const bId = Number(b.node?.id ?? b.id ?? 0);
    return aId - bId;
  });
}

function uniqueTags(tags: DiscoveryGraphSourceTag[]) {
  return Array.from(new Set(tags)).sort((a, b) => a.localeCompare(b));
}

function withAddedTag(map: TagMap, key: string, tag: DiscoveryGraphSourceTag): TagMap {
  const prev = map[key] || [];
  if (prev.includes(tag)) return map;
  return {
    ...map,
    [key]: uniqueTags([...prev, tag]),
  };
}

function withRemovedTag(map: TagMap, key: string, tag: DiscoveryGraphSourceTag): TagMap {
  const prev = map[key] || [];
  if (!prev.includes(tag)) return map;
  const nextTags = prev.filter((item) => item !== tag);
  if (nextTags.length <= 0) {
    const next = { ...map };
    delete next[key];
    return next;
  }
  return {
    ...map,
    [key]: nextTags,
  };
}

function buildExpandFingerprint(entityTypes: string[], relationTypes: string[]) {
  return JSON.stringify({
    entityTypes: [...entityTypes].sort((a, b) => a.localeCompare(b)),
    relationTypes: [...relationTypes].sort((a, b) => a.localeCompare(b)),
  });
}

function expandSourceTag(sourceNodeId: number): DiscoveryGraphSourceTag {
  return `expand:${String(sourceNodeId)}`;
}

function isTargetIncidentEdge(targetNodeId: number, edge: EdgeBrief, candidateNodeId?: number) {
  const incident = edge.source === targetNodeId || edge.target === targetNodeId;
  if (!incident) return false;
  if (candidateNodeId == null) return true;
  return (
    (edge.source === targetNodeId && edge.target === candidateNodeId) ||
    (edge.target === targetNodeId && edge.source === candidateNodeId)
  );
}

function mergeUniqueEdges(edges: EdgeBrief[]) {
  const next = new Map<string, EdgeBrief>();
  for (const edge of edges) next.set(edgeKey(edge), edge);
  return Array.from(next.values());
}

function areSetsEqual<T>(a: Set<T>, b: Set<T>) {
  if (a.size !== b.size) return false;
  for (const item of a) {
    if (!b.has(item)) return false;
  }
  return true;
}

export function useDiscoveryGraphState({
  graphNodes,
  graphEdges,
  maxNodes,
  maxEdges,
  seedNodeIds,
  onMergeGraphData,
  onNotice,
}: UseDiscoveryGraphStateParams) {
  const [nodeSourceTagMap, setNodeSourceTagMap] = useState<TagMap>({});
  const [edgeSourceTagMap, setEdgeSourceTagMap] = useState<TagMap>({});
  const [hiddenNodeIds, setHiddenNodeIds] = useState<Set<number>>(new Set());
  const [droppedNodeMap, setDroppedNodeMap] = useState<Record<string, DroppedNodeRecord>>({});
  const [droppedNodeSourceTagMap, setDroppedNodeSourceTagMap] = useState<TagMap>({});
  const [nodeCapabilityMap, setNodeCapabilityMap] = useState<Record<string, CapabilityState>>({});
  const [expandSessionMap, setExpandSessionMap] = useState<Record<string, NodeExpandSession>>({});
  const [expandingNodeIds, setExpandingNodeIds] = useState<Set<number>>(new Set());
  const [nodePositionCache] = useState<Record<string, CachedNodePosition>>({});
  const [selectedEntityTypeSet, setSelectedEntityTypeSet] = useState<Set<string>>(new Set());
  const [selectedRelationTypeSet, setSelectedRelationTypeSet] = useState<Set<string>>(new Set());
  const renderMutationSequenceRef = useRef(0);
  const [renderMutation, setRenderMutation] = useState<GraphRenderMutation>(() =>
    createGraphRenderMutation("discovery", "initial_discovery")
  );
  const previousAvailableEntityTypeSetRef = useRef<Set<string>>(new Set());
  const previousAvailableRelationTypeSetRef = useRef<Set<string>>(new Set());

  function commitRenderMutation(
    reason: GraphRenderMutation["reason"],
    patch?: Partial<Pick<GraphRenderMutation, "anchorNodeId" | "affectedNodeIds">>
  ) {
    renderMutationSequenceRef.current += 1;
    setRenderMutation(
      createGraphRenderMutation("discovery", reason, renderMutationSequenceRef.current, {
        anchorNodeId: patch?.anchorNodeId ?? null,
        affectedNodeIds: patch?.affectedNodeIds ?? [],
      })
    );
  }

  function syncNodePositions(
    positions: Record<string, { x: number; y: number }>,
    source: CachedNodePosition["source"] = "layout"
  ) {
    const updatedAt = Date.now();
    for (const [nodeId, position] of Object.entries(positions)) {
      if (!Number.isFinite(position.x) || !Number.isFinite(position.y)) continue;
      nodePositionCache[nodeId] = {
        x: position.x,
        y: position.y,
        source,
        updatedAt,
      };
    }
  }

  function requestRelayout(nodeIds?: string[]) {
    commitRenderMutation("user_relayout", {
      affectedNodeIds:
        nodeIds && nodeIds.length > 0 ? nodeIds : Array.from(renderedNodeIds).map((nodeId) => String(nodeId)),
    });
  }

  const graphEntityMap = useMemo(() => {
    const next = new Map<number, NodeBrief>();
    for (const node of graphNodes) next.set(node.id, node);
    return next;
  }, [graphNodes]);

  const edgeMap = useMemo(() => {
    const next = new Map<string, EdgeBrief>();
    for (const edge of graphEdges) next.set(edgeKey(edge), edge);
    return next;
  }, [graphEdges]);

  function nodeWithSourceTags(node: NodeBrief): NodeBrief {
    return {
      ...node,
      source_tags: [...(nodeSourceTagMap[String(node.id)] || [])],
    };
  }

  function edgeWithSourceTags(edge: EdgeBrief): EdgeBrief {
    return {
      ...edge,
      source_tags: [...(edgeSourceTagMap[edgeKey(edge)] || [])],
    };
  }

  const workingNodeIds = useMemo(() => {
    const next = new Set<number>();
    for (const [nodeId, tags] of Object.entries(nodeSourceTagMap)) {
      if ((tags || []).length <= 0) continue;
      const numericId = Number(nodeId);
      next.add(numericId);
    }
    return next;
  }, [nodeSourceTagMap]);

  const renderedNodeIds = useMemo(() => {
    const next = new Set<number>();
    for (const nodeId of workingNodeIds) {
      if (hiddenNodeIds.has(nodeId)) continue;
      next.add(nodeId);
    }
    return next;
  }, [hiddenNodeIds, workingNodeIds]);

  const workingEdgeKeys = useMemo(() => {
    const next = new Set<string>();
    for (const [key, tags] of Object.entries(edgeSourceTagMap)) {
      if ((tags || []).length <= 0) continue;
      const edge = edgeMap.get(key);
      if (!edge) continue;
      if (!workingNodeIds.has(edge.source) || !workingNodeIds.has(edge.target)) continue;
      next.add(key);
    }
    return next;
  }, [edgeMap, edgeSourceTagMap, workingNodeIds]);

  const renderedEdgeIds = useMemo(() => {
    const next = new Set<string>();
    for (const key of workingEdgeKeys) {
      const edge = edgeMap.get(key);
      if (!edge) continue;
      if (!renderedNodeIds.has(edge.source) || !renderedNodeIds.has(edge.target)) continue;
      next.add(key);
    }
    return next;
  }, [edgeMap, renderedNodeIds, workingEdgeKeys]);

  function upsertDroppedCandidates(candidates: GraphDiscoveryDroppedCandidate[], sourceTag: DiscoveryGraphSourceTag) {
    if (candidates.length <= 0) return;
    const droppedNodes = candidates.map(candidateToNode);
    const droppedEdges = candidates.flatMap((item) => item.support_edges || []);
    onMergeGraphData({ nodes: droppedNodes, edges: droppedEdges });

    setDroppedNodeMap((prev) => {
      const next = { ...prev };
      for (const item of candidates) {
        const nodeId = String(item.node_id);
        next[nodeId] = {
          node: candidateToNode(item),
          reason: droppedReasonKey(item.reason),
          supportEdges: item.support_edges || [],
          sourceNodeId: item.source_node_id == null ? null : Number(item.source_node_id),
        };
      }
      return next;
    });
    setDroppedNodeSourceTagMap((prev) => {
      let next = prev;
      for (const item of candidates) {
        next = withAddedTag(next, String(item.node_id), sourceTag);
      }
      return next;
    });
  }

  function initializeFromDiscovery(result: GraphDiscoveryResp) {
    const nextNodeSourceTags: TagMap = {};
    const nextEdgeSourceTags: TagMap = {};
    const nextDroppedMap: Record<string, DroppedNodeRecord> = {};
    const nextDroppedSourceTags: TagMap = {};

    for (const node of result.nodes || []) {
      nextNodeSourceTags[String(node.id)] = ["discovery_base"];
    }
    for (const edge of result.edges || []) {
      nextEdgeSourceTags[edgeKey(edge)] = ["discovery_base"];
    }
    for (const item of result.dropped_candidates || []) {
      nextDroppedMap[String(item.node_id)] = {
        node: candidateToNode(item),
        reason: droppedReasonKey(item.reason),
        supportEdges: item.support_edges || [],
        sourceNodeId: item.source_node_id == null ? null : Number(item.source_node_id),
      };
      nextDroppedSourceTags[String(item.node_id)] = ["discovery_base"];
    }

    setNodeSourceTagMap(nextNodeSourceTags);
    setEdgeSourceTagMap(nextEdgeSourceTags);
    setHiddenNodeIds(new Set());
    setDroppedNodeMap(nextDroppedMap);
    setDroppedNodeSourceTagMap(nextDroppedSourceTags);
    setExpandSessionMap({});
    setExpandingNodeIds(new Set());
    setNodeCapabilityMap(() => {
      const next: Record<string, CapabilityState> = {};
      for (const item of result.node_capabilities || []) {
        next[String(item.node_id)] = {
          expandable: Boolean(item.expandable),
          terminal: Boolean(item.terminal),
        };
      }
      return next;
    });
    commitRenderMutation("initial_discovery", {
      affectedNodeIds: (result.nodes || []).map((node) => String(node.id)),
    });
  }

  function resetState() {
    setNodeSourceTagMap({});
    setEdgeSourceTagMap({});
    setHiddenNodeIds(new Set());
    setDroppedNodeMap({});
    setDroppedNodeSourceTagMap({});
    setNodeCapabilityMap({});
    setExpandSessionMap({});
    setExpandingNodeIds(new Set());
    setSelectedEntityTypeSet(new Set());
    setSelectedRelationTypeSet(new Set());
    previousAvailableEntityTypeSetRef.current = new Set();
    previousAvailableRelationTypeSetRef.current = new Set();
  }

  function hideRenderedNode(nodeId: number) {
    if (seedNodeIds.has(nodeId)) {
      onNotice?.("warn", "Seed 节点不能执行普通取消渲染，请从 seed 列表删除后触发全局 discovery 重跑。");
      return false;
    }
    if (!renderedNodeIds.has(nodeId)) return false;
    setHiddenNodeIds((prev) => {
      const next = new Set(prev);
      next.add(nodeId);
      return next;
    });
    commitRenderMutation("hide_node", {
      anchorNodeId: String(nodeId),
      affectedNodeIds: [String(nodeId)],
    });
    return true;
  }

  function restoreHiddenNode(nodeId: number) {
    if (!hiddenNodeIds.has(nodeId)) return false;
    if (!graphEntityMap.has(nodeId)) {
      onNotice?.("error", "当前缓存中不存在该隐藏节点，无法恢复显示。");
      return false;
    }

    let nextNodeSourceTags = nodeSourceTagMap;
    nextNodeSourceTags = withAddedTag(nextNodeSourceTags, String(nodeId), "manual_restore");
    setNodeSourceTagMap(nextNodeSourceTags);

    const nextVisibleNodeIds = new Set(renderedNodeIds);
    nextVisibleNodeIds.add(nodeId);

    let nextEdgeSourceTags = edgeSourceTagMap;
    const connectableEdges = graphEdges.filter(
      (edge) =>
        (edge.source === nodeId || edge.target === nodeId) &&
        nextVisibleNodeIds.has(edge.source) &&
        nextVisibleNodeIds.has(edge.target)
    );
    for (const edge of connectableEdges) {
      nextEdgeSourceTags = withAddedTag(nextEdgeSourceTags, edgeKey(edge), "manual_restore");
    }
    setEdgeSourceTagMap(nextEdgeSourceTags);
    setHiddenNodeIds((prev) => {
      const next = new Set(prev);
      next.delete(nodeId);
      return next;
    });
    commitRenderMutation("restore_node", {
      anchorNodeId: String(nodeId),
      affectedNodeIds: [String(nodeId)],
    });
    return true;
  }

  function forceRenderDroppedNode(nodeId: number) {
    const dropped = droppedNodeMap[String(nodeId)];
    if (!dropped) return false;
    if (!graphEntityMap.has(nodeId)) {
      onMergeGraphData({ nodes: [dropped.node], edges: dropped.supportEdges });
    }

    const nodeAlreadyHeld = Boolean((nodeSourceTagMap[String(nodeId)] || []).length > 0);
    if (!nodeAlreadyHeld && renderedNodeIds.size >= maxNodes) {
      onNotice?.("warn", `当前已达到节点预算上限 ${maxNodes}，无法加入渲染。`);
      return false;
    }

    const nextVisibleNodeIds = new Set(renderedNodeIds);
    nextVisibleNodeIds.add(nodeId);
    const connectableEdges = dropped.supportEdges.filter((edge) => {
      const other = edge.source === nodeId ? edge.target : edge.source;
      return nextVisibleNodeIds.has(other);
    });
    if (connectableEdges.length <= 0) {
      onNotice?.("warn", "当前缓存中没有可连接到已渲染节点的合法边，无法加入渲染。");
      return false;
    }
    const heldConnectableEdges = connectableEdges.filter((edge) => Boolean((edgeSourceTagMap[edgeKey(edge)] || []).length));
    if (heldConnectableEdges.length <= 0 && renderedEdgeIds.size >= maxEdges) {
      onNotice?.("warn", `当前已达到边预算上限 ${maxEdges}，无法加入渲染。`);
      return false;
    }

    let nextNodeSourceTags = nodeSourceTagMap;
    nextNodeSourceTags = withAddedTag(nextNodeSourceTags, String(nodeId), "forced_render");
    setNodeSourceTagMap(nextNodeSourceTags);

    let nextEdgeSourceTags = edgeSourceTagMap;
    const edgeBudget = heldConnectableEdges.length > 0 ? connectableEdges.length : Math.max(1, maxEdges - renderedEdgeIds.size);
    for (const edge of connectableEdges.slice(0, edgeBudget)) {
      nextEdgeSourceTags = withAddedTag(nextEdgeSourceTags, edgeKey(edge), "forced_render");
    }
    setEdgeSourceTagMap(nextEdgeSourceTags);
    setHiddenNodeIds((prev) => {
      const next = new Set(prev);
      next.delete(nodeId);
      return next;
    });
    commitRenderMutation("force_render_dropped", {
      anchorNodeId: dropped.sourceNodeId != null ? String(dropped.sourceNodeId) : String(nodeId),
      affectedNodeIds: [String(nodeId)],
    });
    return true;
  }

  function getNodeExpandUiState(nodeId: number, requestFingerprint: string): DiscoveryNodeExpandUiState {
    if (expandingNodeIds.has(nodeId)) return "expanding";
    const session = expandSessionMap[String(nodeId)];
    if (session?.isExpanded) return "expanded";
    const capability = nodeCapabilityMap[String(nodeId)];
    if (capability?.terminal && (!session || session.requestFingerprint === requestFingerprint)) return "terminal";
    return "collapsed";
  }

  function collapseExpandSession(targetNodeId: number) {
    const session = expandSessionMap[String(targetNodeId)];
    if (!session?.isExpanded) return false;
    const sourceTag = expandSourceTag(targetNodeId);

    let nextNodeSourceTags = nodeSourceTagMap;
    for (const nodeId of session.addedNodeIds) {
      nextNodeSourceTags = withRemovedTag(nextNodeSourceTags, nodeId, sourceTag);
    }

    let nextEdgeSourceTags = edgeSourceTagMap;
    for (const key of session.addedEdgeIds) {
      nextEdgeSourceTags = withRemovedTag(nextEdgeSourceTags, key, sourceTag);
    }

    let nextDroppedSourceTags = droppedNodeSourceTagMap;
    for (const nodeId of session.droppedNodeIds) {
      nextDroppedSourceTags = withRemovedTag(nextDroppedSourceTags, nodeId, sourceTag);
    }

    const nextDroppedMap = { ...droppedNodeMap };
    for (const nodeId of session.droppedNodeIds) {
      if ((nextDroppedSourceTags[nodeId] || []).length > 0) continue;
      delete nextDroppedMap[nodeId];
    }

    const nextHiddenNodeIds = new Set(hiddenNodeIds);
    for (const nodeId of session.addedNodeIds) {
      if ((nextNodeSourceTags[nodeId] || []).length > 0) continue;
      nextHiddenNodeIds.delete(Number(nodeId));
    }

    setNodeSourceTagMap(nextNodeSourceTags);
    setEdgeSourceTagMap(nextEdgeSourceTags);
    setDroppedNodeSourceTagMap(nextDroppedSourceTags);
    setDroppedNodeMap(nextDroppedMap);
    setHiddenNodeIds(nextHiddenNodeIds);
    setExpandSessionMap((prev) => ({
      ...prev,
      [String(targetNodeId)]: {
        ...session,
        isExpanded: false,
        addedNodeIds: [],
        addedEdgeIds: [],
        },
    }));
    commitRenderMutation("collapse", {
      anchorNodeId: String(targetNodeId),
      affectedNodeIds: session.addedNodeIds,
    });
    return true;
  }

  async function toggleNodeExpand(params: {
    targetNodeId: number;
    allowedEntityTypes: string[];
    allowedRelationTypes: string[];
    expandMaxNewNodes: number;
    expandMaxNewEdges: number;
    expandTopKPerType: number;
  }): Promise<ToggleExpandResult> {
    const requestFingerprint = buildExpandFingerprint(params.allowedEntityTypes, params.allowedRelationTypes);
    const existingSession = expandSessionMap[String(params.targetNodeId)];
    if (existingSession?.isExpanded) {
      collapseExpandSession(params.targetNodeId);
      return {
        action: "collapsed",
        firstNodeId: params.targetNodeId,
        response: null,
      };
    }

    setExpandingNodeIds((prev) => {
      const next = new Set(prev);
      next.add(params.targetNodeId);
      return next;
    });

    try {
      const rawResp = await graphDiscoveryExpand({
        target_node_id: params.targetNodeId,
        rendered_node_ids: Array.from(renderedNodeIds),
        rendered_edge_ids: Array.from(renderedEdgeIds),
        allowed_entity_types: params.allowedEntityTypes,
        allowed_relation_types: params.allowedRelationTypes,
        expand_max_new_nodes: params.expandMaxNewNodes,
        expand_max_new_edges: params.expandMaxNewEdges,
        expand_top_k_per_type: params.expandTopKPerType,
        expand_max_hop: 1,
      });

      const sourceTag = expandSourceTag(params.targetNodeId);
      const incidentEdgePool = mergeUniqueEdges(
        [...(rawResp.new_edges || []), ...(rawResp.support_edges || [])].filter((edge) =>
          isTargetIncidentEdge(params.targetNodeId, edge)
        )
      );
      const validNodes: NodeBrief[] = [];
      const validEdgeKeys = new Set<string>();
      for (const node of rawResp.new_nodes || []) {
        const incidentEdges = incidentEdgePool.filter((edge) => isTargetIncidentEdge(params.targetNodeId, edge, node.id));
        if (incidentEdges.length <= 0) {
          console.warn("discovery expand dropped orphan node", {
            targetNodeId: params.targetNodeId,
            nodeId: node.id,
          });
          continue;
        }
        validNodes.push(node);
        for (const edge of incidentEdges) validEdgeKeys.add(edgeKey(edge));
      }
      const validResp: GraphDiscoveryExpandResp = {
        ...rawResp,
        new_nodes: validNodes,
        new_edges: (rawResp.new_edges || []).filter((edge) => validEdgeKeys.has(edgeKey(edge))),
        support_edges: (rawResp.support_edges || []).filter((edge) => validEdgeKeys.has(edgeKey(edge))),
      };

      upsertDroppedCandidates(validResp.dropped_candidates || [], sourceTag);
      onMergeGraphData({
        nodes: validResp.new_nodes,
        edges: mergeUniqueEdges([...validResp.new_edges, ...validResp.support_edges]),
      });

      let nextNodeSourceTags = nodeSourceTagMap;
      for (const node of validResp.new_nodes) {
        nextNodeSourceTags = withAddedTag(nextNodeSourceTags, String(node.id), sourceTag);
      }

      let nextEdgeSourceTags = edgeSourceTagMap;
      const taggedEdges = mergeUniqueEdges([...validResp.new_edges, ...validResp.support_edges]);
      for (const edge of taggedEdges) {
        nextEdgeSourceTags = withAddedTag(nextEdgeSourceTags, edgeKey(edge), sourceTag);
      }

      setNodeSourceTagMap(nextNodeSourceTags);
      setEdgeSourceTagMap(nextEdgeSourceTags);
      setNodeCapabilityMap((prev) => ({
        ...prev,
        [String(params.targetNodeId)]: {
          expandable: Boolean(validResp.has_more_candidates_after_filters),
          terminal: Boolean(validResp.terminal),
        },
      }));
      setExpandSessionMap((prev) => ({
        ...prev,
        [String(params.targetNodeId)]: {
          sourceNodeId: String(params.targetNodeId),
          isExpanded: validResp.new_nodes.length > 0 || taggedEdges.length > 0,
          requestFingerprint,
          addedNodeIds: validResp.new_nodes.map((node) => String(node.id)),
          addedEdgeIds: taggedEdges.map((edge) => edgeKey(edge)),
          droppedNodeIds: (validResp.dropped_candidates || []).map((item) => String(item.node_id)),
          filtersSnapshot: {
            entityTypes: [...params.allowedEntityTypes].sort((a, b) => a.localeCompare(b)),
            relationTypes: [...params.allowedRelationTypes].sort((a, b) => a.localeCompare(b)),
          },
        },
      }));
      commitRenderMutation("expand", {
        anchorNodeId: String(params.targetNodeId),
        affectedNodeIds: validResp.new_nodes.map((node) => String(node.id)),
      });

      const firstNode = validResp.new_nodes.find((node) => !hiddenNodeIds.has(node.id));
      return {
        action: "expanded",
        firstNodeId: firstNode?.id ?? params.targetNodeId,
        response: validResp,
      };
    } finally {
      setExpandingNodeIds((prev) => {
        const next = new Set(prev);
        next.delete(params.targetNodeId);
        return next;
      });
    }
  }

  async function probeNodeExpand(params: {
    targetNodeId: number;
    allowedEntityTypes: string[];
    allowedRelationTypes: string[];
    expandTopKPerType: number;
  }) {
    const resp = await graphDiscoveryExpand({
      target_node_id: params.targetNodeId,
      rendered_node_ids: Array.from(renderedNodeIds),
      rendered_edge_ids: Array.from(renderedEdgeIds),
      allowed_entity_types: params.allowedEntityTypes,
      allowed_relation_types: params.allowedRelationTypes,
      expand_max_new_nodes: 0,
      expand_max_new_edges: 0,
      expand_top_k_per_type: params.expandTopKPerType,
      expand_max_hop: 1,
    });

    setNodeCapabilityMap((prev) => ({
      ...prev,
      [String(params.targetNodeId)]: {
        expandable: Boolean(resp.has_more_candidates_after_filters),
        terminal: Boolean(resp.terminal),
      },
    }));
    return resp;
  }

  const renderedNodes = useMemo(
    () =>
      sortNodesByLabel(
        Array.from(renderedNodeIds)
          .map((nodeId) => graphEntityMap.get(nodeId))
          .filter((item): item is NodeBrief => Boolean(item))
          .map((item) => nodeWithSourceTags(item))
      ),
    [graphEntityMap, renderedNodeIds, nodeSourceTagMap]
  );

  const hiddenNodes = useMemo(
    () =>
      sortNodesByLabel(
        Array.from(hiddenNodeIds)
          .filter((nodeId) => Boolean((nodeSourceTagMap[String(nodeId)] || []).length))
          .map((nodeId) => graphEntityMap.get(nodeId))
          .filter((item): item is NodeBrief => Boolean(item))
          .map((item) => nodeWithSourceTags(item))
      ),
    [graphEntityMap, hiddenNodeIds, nodeSourceTagMap]
  );

  const droppedEntries = useMemo(
    () =>
      Object.entries(droppedNodeMap)
        .filter(([nodeId]) => {
          if ((droppedNodeSourceTagMap[nodeId] || []).length <= 0) return false;
          const numericId = Number(nodeId);
          return !renderedNodeIds.has(numericId) && !hiddenNodeIds.has(numericId);
        })
        .map(([, item]) => item),
    [droppedNodeMap, droppedNodeSourceTagMap, hiddenNodeIds, renderedNodeIds]
  );

  const droppedByBudget = useMemo(
    () => sortNodesByLabel(droppedEntries.filter((item) => item.reason === "dropped_by_budget")),
    [droppedEntries]
  );
  const droppedByTypeFilter = useMemo(
    () => sortNodesByLabel(droppedEntries.filter((item) => item.reason === "dropped_by_type_filter")),
    [droppedEntries]
  );
  const droppedByRelationFilter = useMemo(
    () => sortNodesByLabel(droppedEntries.filter((item) => item.reason === "dropped_by_relation_filter")),
    [droppedEntries]
  );

  const availableEntityTypes = useMemo(() => {
    const countMap = new Map<string, number>();
    for (const nodeId of workingNodeIds) {
      const node = graphEntityMap.get(nodeId);
      if (!node) continue;
      const typeKey = String(node.entity_type || "");
      countMap.set(typeKey, (countMap.get(typeKey) || 0) + 1);
    }
    return Array.from(countMap.entries())
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => a.key.localeCompare(b.key));
  }, [graphEntityMap, workingNodeIds]);

  const availableRelationTypes = useMemo(() => {
    const countMap = new Map<string, number>();
    for (const key of workingEdgeKeys) {
      const edge = edgeMap.get(key);
      if (!edge) continue;
      const relationKey = String(edge.relation || "");
      countMap.set(relationKey, (countMap.get(relationKey) || 0) + 1);
    }
    return Array.from(countMap.entries())
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => a.key.localeCompare(b.key));
  }, [edgeMap, workingEdgeKeys]);

  useEffect(() => {
    const previousAvailable = previousAvailableEntityTypeSetRef.current;
    const nextAvailable = new Set(availableEntityTypes.map((item) => item.key));
    setSelectedEntityTypeSet((prev) => {
      const next = new Set<string>();
      for (const item of availableEntityTypes) {
        if (!previousAvailable.has(item.key) || prev.has(item.key)) {
          next.add(item.key);
        }
      }
      return areSetsEqual(prev, next) ? prev : next;
    });
    previousAvailableEntityTypeSetRef.current = nextAvailable;
  }, [availableEntityTypes]);

  useEffect(() => {
    const previousAvailable = previousAvailableRelationTypeSetRef.current;
    const nextAvailable = new Set(availableRelationTypes.map((item) => item.key));
    setSelectedRelationTypeSet((prev) => {
      const next = new Set<string>();
      for (const item of availableRelationTypes) {
        if (!previousAvailable.has(item.key) || prev.has(item.key)) {
          next.add(item.key);
        }
      }
      return areSetsEqual(prev, next) ? prev : next;
    });
    previousAvailableRelationTypeSetRef.current = nextAvailable;
  }, [availableRelationTypes]);

  const visibleNodeIdSet = useMemo(() => {
    const next = new Set<number>();
    for (const nodeId of renderedNodeIds) {
      const node = graphEntityMap.get(nodeId);
      if (!node) continue;
      const typeKey = String(node.entity_type || "");
      if (!selectedEntityTypeSet.has(typeKey)) continue;
      next.add(nodeId);
    }
    return next;
  }, [graphEntityMap, renderedNodeIds, selectedEntityTypeSet]);

  const visibleEdgeKeySet = useMemo(() => {
    const next = new Set<string>();
    for (const key of workingEdgeKeys) {
      const edge = edgeMap.get(key);
      if (!edge) continue;
      const relationKey = String(edge.relation || "");
      if (!selectedRelationTypeSet.has(relationKey)) continue;
      if (!visibleNodeIdSet.has(edge.source) || !visibleNodeIdSet.has(edge.target)) continue;
      next.add(key);
    }
    return next;
  }, [edgeMap, selectedRelationTypeSet, visibleNodeIdSet, workingEdgeKeys]);

  function setSelectedEntityTypes(nextKeys: string[]) {
    const allowed = new Set(availableEntityTypes.map((item) => item.key));
    const next = new Set(nextKeys.filter((key) => allowed.has(key)).sort((a, b) => a.localeCompare(b)));
    if (!areSetsEqual(selectedEntityTypeSet, next)) {
      commitRenderMutation("entity_coverage_toggle");
    }
    setSelectedEntityTypeSet(next);
  }

  function setSelectedRelationTypes(nextKeys: string[]) {
    const allowed = new Set(availableRelationTypes.map((item) => item.key));
    const next = new Set(nextKeys.filter((key) => allowed.has(key)).sort((a, b) => a.localeCompare(b)));
    if (!areSetsEqual(selectedRelationTypeSet, next)) {
      commitRenderMutation("relation_coverage_toggle");
    }
    setSelectedRelationTypeSet(next);
  }

  const visibleGraphNodes = useMemo(
    () => graphNodes.filter((node) => visibleNodeIdSet.has(node.id)).map((node) => nodeWithSourceTags(node)),
    [graphNodes, nodeSourceTagMap, visibleNodeIdSet]
  );
  const visibleGraphEdges = useMemo(
    () =>
      graphEdges.filter((edge) => {
        const key = edgeKey(edge);
        return visibleEdgeKeySet.has(key);
      }).map((edge) => edgeWithSourceTags(edge)),
    [edgeSourceTagMap, graphEdges, visibleEdgeKeySet]
  );

  return {
    workingNodeIds,
    workingEdgeKeys,
    renderedNodeIds,
    renderedEdgeIds,
    hiddenNodeIds,
    droppedNodeMap,
    droppedNodeSourceTagMap,
    nodeCapabilityMap,
    seedNodeIds,
    nodePositionCache,
    graphEntityMap,
    edgeMap,
    expandSessionMap,
    buildExpandFingerprint,
    renderMutation,
    getNodeExpandUiState,
    initializeFromDiscovery,
    resetState,
    hideRenderedNode,
    restoreHiddenNode,
    forceRenderDroppedNode,
    probeNodeExpand,
    toggleNodeExpand,
    workingNodeCount: workingNodeIds.size,
    workingEdgeCount: workingEdgeKeys.size,
    availableEntityTypes,
    availableRelationTypes,
    selectedEntityTypes: Array.from(selectedEntityTypeSet).sort((a, b) => a.localeCompare(b)),
    selectedRelationTypes: Array.from(selectedRelationTypeSet).sort((a, b) => a.localeCompare(b)),
    selectedEntityTypeSet,
    selectedRelationTypeSet,
    setSelectedEntityTypes,
    setSelectedRelationTypes,
    syncNodePositions,
    requestRelayout,
    visibleNodeIdSet,
    visibleEdgeKeySet,
    visibleGraphNodes,
    visibleGraphEdges,
    renderedNodes,
    hiddenNodes,
    droppedGroups: {
      droppedByBudget,
      droppedByTypeFilter,
      droppedByRelationFilter,
    },
  };
}
