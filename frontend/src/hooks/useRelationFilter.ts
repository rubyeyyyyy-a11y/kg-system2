import { useCallback, useEffect, useMemo, useState } from "react";
import type { EdgeBrief, NodeBrief } from "../types/kg";
import { uniqueStrings } from "../utils/relation";

export type RelPreset = {
  id: string;
  name: string;
  relations: string[];
  updatedAt: number;
};

type UseRelationFilterParams = {
  appliedRelations: string[];
  graphNodes: NodeBrief[];
  graphEdges: EdgeBrief[];
  rootVid: number | null;
};

type UseRelationFilterResult = {
  open: boolean;
  appliedRelations: string[];
  draftRelations: string[];
  relationCountMap: Map<string, number>;
  previewActive: boolean;
  previewRelations: string[];
  previewNodes: NodeBrief[];
  previewEdges: EdgeBrief[];
  previewEdgeTotal: number;
  openPanel: () => void;
  closePanel: () => void;
  setDraftRelations: (next: string[]) => void;
  toggleDraftRelation: (raw: string) => void;
  clearDraft: () => void;
  restoreDraftFromApplied: () => void;
  invertDraftByRelations: (relationsInList: string[]) => void;
  enterPreview: () => void;
  exitPreview: () => void;
  commitDraftAsApplied: () => string[];
  estimateKeepEdges: (candidateRelations: string[]) => number;
  presets: RelPreset[];
  activePresetId: string;
  selectPreset: (presetId: string) => void;
  savePreset: (name: string) => void;
  renamePreset: (presetId: string, name: string) => void;
  deletePreset: (presetId: string) => void;
};

const PRESETS_KEY = "kg:relPresets";
const ACTIVE_PRESET_KEY = "kg:relPresetActiveId";
const SYSTEM_PRESET_ID_ALL = "__all__";
const SYSTEM_PRESET_UPDATED_AT = 0;

function readPresetsFromStorage(): RelPreset[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(PRESETS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as RelPreset[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((x) => x && typeof x.id === "string" && typeof x.name === "string")
      .map((x) => ({
        id: x.id,
        name: x.name,
        relations: uniqueStrings(Array.isArray(x.relations) ? x.relations : []),
        updatedAt: Number(x.updatedAt) || Date.now(),
      }));
  } catch {
    return [];
  }
}

function readPresetActiveId(): string {
  if (typeof window === "undefined") return SYSTEM_PRESET_ID_ALL;
  return window.localStorage.getItem(ACTIVE_PRESET_KEY) || SYSTEM_PRESET_ID_ALL;
}

function makePresetId(): string {
  return `rp_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export function useRelationFilter({
  appliedRelations,
  graphNodes,
  graphEdges,
  rootVid,
}: UseRelationFilterParams): UseRelationFilterResult {
  const [open, setOpen] = useState(false);
  const [draftRelations, setDraftRelationsState] = useState<string[]>(() => uniqueStrings(appliedRelations));

  const [previewActive, setPreviewActive] = useState(false);
  const [previewRelations, setPreviewRelations] = useState<string[]>([]);

  const [customPresets, setCustomPresets] = useState<RelPreset[]>(() => readPresetsFromStorage());
  const [activePresetId, setActivePresetId] = useState<string>(() => readPresetActiveId());
  const appliedState = useMemo(() => uniqueStrings(appliedRelations), [appliedRelations]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(PRESETS_KEY, JSON.stringify(customPresets));
  }, [customPresets]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(ACTIVE_PRESET_KEY, activePresetId);
  }, [activePresetId]);

  const presets = useMemo(() => {
    const systemPreset: RelPreset = {
      id: SYSTEM_PRESET_ID_ALL,
      name: "全部（不筛选）",
      relations: [],
      updatedAt: SYSTEM_PRESET_UPDATED_AT,
    };
    const sortedCustom = [...customPresets].sort((a, b) => b.updatedAt - a.updatedAt);
    return [systemPreset, ...sortedCustom];
  }, [customPresets]);

  const relationCountMap = useMemo(() => {
    const m = new Map<string, number>();
    for (const e of graphEdges) {
      const raw = String(e.relation || "").trim();
      if (!raw) continue;
      m.set(raw, (m.get(raw) || 0) + 1);
    }
    return m;
  }, [graphEdges]);

  const previewEdgeTotal = graphEdges.length;

  const estimateKeepEdges = useCallback(
    (candidateRelations: string[]) => {
      const selected = uniqueStrings(candidateRelations);
      if (selected.length === 0) return previewEdgeTotal;
      const selectedSet = new Set(selected);
      let keep = 0;
      for (const raw of selectedSet) keep += relationCountMap.get(raw) || 0;
      return keep;
    },
    [previewEdgeTotal, relationCountMap]
  );

  const previewEdges = useMemo(() => {
    if (!previewActive) return graphEdges;
    if (previewRelations.length === 0) return graphEdges;
    const allow = new Set(previewRelations);
    return graphEdges.filter((e) => allow.has(String(e.relation || "").trim()));
  }, [graphEdges, previewActive, previewRelations]);

  const previewNodes = useMemo(() => {
    if (!previewActive) return graphNodes;
    if (previewRelations.length === 0) return graphNodes;
    const keepIds = new Set<number>();
    for (const e of previewEdges) {
      keepIds.add(Number(e.source));
      keepIds.add(Number(e.target));
    }
    if (rootVid != null) keepIds.add(rootVid);
    if (keepIds.size === 0) return [];
    return graphNodes.filter((n) => keepIds.has(n.id));
  }, [graphNodes, previewActive, previewRelations, previewEdges, rootVid]);

  function openPanel() {
    setDraftRelationsState(appliedState);
    setOpen(true);
  }

  function closePanel() {
    setOpen(false);
  }

  function setDraftRelations(next: string[]) {
    setDraftRelationsState(uniqueStrings(next));
  }

  function toggleDraftRelation(raw: string) {
    const key = String(raw || "").trim();
    if (!key) return;
    setDraftRelationsState((prev) => {
      const s = new Set(prev);
      if (s.has(key)) s.delete(key);
      else s.add(key);
      return Array.from(s);
    });
  }

  function clearDraft() {
    setDraftRelationsState([]);
  }

  function restoreDraftFromApplied() {
    setDraftRelationsState(appliedState);
  }

  function invertDraftByRelations(relationsInList: string[]) {
    const keys = uniqueStrings(relationsInList);
    if (keys.length === 0) return;
    setDraftRelationsState((prev) => {
      const s = new Set(prev);
      for (const raw of keys) {
        if (s.has(raw)) s.delete(raw);
        else s.add(raw);
      }
      return Array.from(s);
    });
  }

  function enterPreview() {
    setPreviewRelations(uniqueStrings(draftRelations));
    setPreviewActive(true);
  }

  function exitPreview() {
    setPreviewActive(false);
    setPreviewRelations([]);
  }

  function commitDraftAsApplied() {
    const next = uniqueStrings(draftRelations);
    setPreviewActive(false);
    setPreviewRelations([]);
    return next;
  }

  function selectPreset(presetId: string) {
    const target = presets.find((p) => p.id === presetId);
    if (!target) return;
    setActivePresetId(presetId);
    setDraftRelationsState(uniqueStrings(target.relations));
  }

  function savePreset(name: string) {
    const finalName = name.trim();
    if (!finalName) return;
    const created: RelPreset = {
      id: makePresetId(),
      name: finalName,
      relations: uniqueStrings(draftRelations),
      updatedAt: Date.now(),
    };
    setCustomPresets((prev) => [created, ...prev]);
    setActivePresetId(created.id);
  }

  function renamePreset(presetId: string, name: string) {
    const finalName = name.trim();
    if (!finalName || presetId === SYSTEM_PRESET_ID_ALL) return;
    setCustomPresets((prev) => prev.map((p) => (p.id === presetId ? { ...p, name: finalName } : p)));
  }

  function deletePreset(presetId: string) {
    if (presetId === SYSTEM_PRESET_ID_ALL) return;
    setCustomPresets((prev) => prev.filter((p) => p.id !== presetId));
    if (activePresetId === presetId) setActivePresetId(SYSTEM_PRESET_ID_ALL);
  }

  return {
    open,
    appliedRelations: appliedState,
    draftRelations,
    relationCountMap,
    previewActive,
    previewRelations,
    previewNodes,
    previewEdges,
    previewEdgeTotal,
    openPanel,
    closePanel,
    setDraftRelations,
    toggleDraftRelation,
    clearDraft,
    restoreDraftFromApplied,
    invertDraftByRelations,
    enterPreview,
    exitPreview,
    commitDraftAsApplied,
    estimateKeepEdges,
    presets,
    activePresetId,
    selectPreset,
    savePreset,
    renamePreset,
    deletePreset,
  };
}
