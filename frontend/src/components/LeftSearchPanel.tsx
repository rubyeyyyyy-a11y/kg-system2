import { useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, KeyboardEvent, RefObject, SetStateAction } from "react";
import { search as searchApi } from "../api/kg";
import { useSuggest } from "../hooks/useSuggest";
import { useRawIdSuggest } from "../hooks/useRawIdSuggest";
import type {
  EdgeSearchItem,
  EdgeSearchResp,
  EntityTypeItem,
  PairPathCandidate,
  RawIdSuggestItem,
  SearchResp,
  SuggestItem,
} from "../types/kg";
import { pairKey, relationDisplay } from "../utils/kg";

type MultiGenerateParams = {
  selectedEntities: SuggestItem[];
  directOnly: boolean;
  explainPaths: boolean;
  k: 2 | 3;
};

type LeftSearchPanelProps = {
  q: string;
  onQChange: (value: string) => void;
  loadingSearch: boolean;
  onSearch: () => void;
  onSearchInputKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  suggestWrapRef: RefObject<HTMLDivElement | null>;
  suggestOpen: boolean;
  suggestLoading: boolean;
  suggestError: string | null;
  suggestItems: SuggestItem[];
  suggestHighlightIndex: number;
  setSuggestHighlightIndex: Dispatch<SetStateAction<number>>;
  onSelectSuggestItem: (item: SuggestItem) => void;
  searchName: boolean;
  setSearchName: (value: boolean) => void;
  searchDesc: boolean;
  setSearchDesc: (value: boolean) => void;
  entityType: string;
  setEntityType: (value: string) => void;
  entityTypeOptions: EntityTypeItem[];
  entityTypeFallbackUsed: boolean;
  source: string;
  setSource: (value: string) => void;
  entityRawId: string;
  onRawIdChange: (value: string) => void;
  onRawIdInputKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  rawIdSuggestWrapRef: RefObject<HTMLDivElement | null>;
  rawIdSuggestOpen: boolean;
  rawIdSuggestLoading: boolean;
  rawIdSuggestError: string | null;
  rawIdSuggestItems: RawIdSuggestItem[];
  rawIdSuggestHighlightIndex: number;
  setRawIdSuggestHighlightIndex: Dispatch<SetStateAction<number>>;
  onSelectRawIdSuggestItem: (item: RawIdSuggestItem) => void;
  searchData: SearchResp;
  rootVid: number | null;
  onLoadSubgraph: (vid: number) => void;

  edgeQ: string;
  onEdgeQChange: (value: string) => void;
  edgeSearchLoading: boolean;
  onEdgeSearch: () => void;
  onEdgeSearchInputKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void;
  edgeSuggestWrapRef: RefObject<HTMLDivElement | null>;
  edgeSuggestOpen: boolean;
  edgeSuggestLoading: boolean;
  edgeSuggestError: string | null;
  edgeSuggestItems: EdgeSearchItem[];
  edgeSuggestHighlightIndex: number;
  setEdgeSuggestHighlightIndex: Dispatch<SetStateAction<number>>;
  onSelectEdgeSuggestItem: (item: EdgeSearchItem) => void;
  edgeSearchInRelation: boolean;
  setEdgeSearchInRelation: (value: boolean) => void;
  edgeSearchInProps: boolean;
  setEdgeSearchInProps: (value: boolean) => void;
  edgeSearchSourceDb: string;
  setEdgeSearchSourceDb: (value: string) => void;
  edgeSearchRelation: string;
  setEdgeSearchRelation: (value: string) => void;
  edgeSearchData: EdgeSearchResp;
  onSelectEdgeSearchItem: (item: EdgeSearchItem) => void;
  edgeSearchNotice: string | null;

  loadingMultiGraph: boolean;
  onGenerateMultiGraph: (params: MultiGenerateParams) => void;
  showPathCandidates: boolean;
  pathCandidates: PairPathCandidate[];
  chosenPathByPair: Record<string, number>;
  onChoosePathForPair: (u: number, v: number, chosenIndex: number) => void;
  onApplyPathForPair: (u: number, v: number) => void;
  pathApplyLoading: boolean;
  resolveEntityLabel: (vid: number) => string;
  appliedExtraPaths: Record<string, number[]>;
  onAppendPathForPair: (u: number, v: number) => void;
};

type MultiSlot = {
  slotId: string;
  selected: SuggestItem | null;
};

type MultiEntitySlotInputProps = {
  index: number;
  selected: SuggestItem | null;
  entityTypeOptions: EntityTypeItem[];
  canRemove: boolean;
  onRemove: () => void;
  onSelectedChange: (item: SuggestItem | null) => void;
  resetToken: number;
};

function MultiEntitySlotInput({
  index,
  selected,
  entityTypeOptions,
  canRemove,
  onRemove,
  onSelectedChange,
  resetToken,
}: MultiEntitySlotInputProps) {
  const [entityType, setEntityType] = useState("");
  const [nameQ, setNameQ] = useState("");
  const [rawIdQ, setRawIdQ] = useState("");
  const [slotSearchLoading, setSlotSearchLoading] = useState(false);
  const [slotSearchError, setSlotSearchError] = useState<string | null>(null);
  const [slotSearchItems, setSlotSearchItems] = useState<SuggestItem[]>([]);
  const didMountRef = useRef(false);

  async function runSlotSearch() {
    const qTrimmed = nameQ.trim();
    const rawIdTrimmed = rawIdQ.trim();
    if (!qTrimmed && !rawIdTrimmed) {
      setSlotSearchItems([]);
      setSlotSearchError(null);
      return;
    }

    const useRawId = !!rawIdTrimmed;
    setSlotSearchLoading(true);
    setSlotSearchError(null);
    try {
      const json = await searchApi({
        q: useRawId ? "" : nameQ,
        search_in_name: useRawId ? false : true,
        search_in_description: useRawId ? false : true,
        entity_type: entityType || null,
        source: null,
        entity_raw_id: rawIdTrimmed || null,
        entity_raw_id_mode: "contains",
      });
      const items: SuggestItem[] = (json.nodes || []).map((n) => ({
        vid: n.id,
        label: n.label,
        entity_type: n.entity_type,
        source: n.source,
        score: n.score,
      }));
      setSlotSearchItems(items);
      setSlotSearchError(null);
    } catch (e: unknown) {
      setSlotSearchItems([]);
      setSlotSearchError(e instanceof Error ? e.message : String(e));
    } finally {
      setSlotSearchLoading(false);
    }
  }

  const {
    suggestOpen: nameSuggestOpen,
    suggestItems: nameSuggestItems,
    suggestLoading: nameSuggestLoading,
    suggestError: nameSuggestError,
    suggestHighlightIndex: nameSuggestHighlightIndex,
    suggestWrapRef: nameSuggestWrapRef,
    onInputChange: onNameInputChange,
    onKeyDown: onNameInputKeyDown,
    setSuggestHighlightIndex: setNameSuggestHighlightIndex,
    closeSuggestPanel: closeNameSuggestPanel,
    selectSuggestCandidate: selectNameSuggestCandidate,
  } = useSuggest({
    q: nameQ,
    entityType,
    source: "",
    onSelect: (item) => {
      setNameQ(item.label);
      onSelectedChange(item);
    },
    onQueryChange: setNameQ,
    onSearch: () => {
      void runSlotSearch();
    },
  });

  const {
    suggestOpen: rawIdSuggestOpen,
    suggestItems: rawIdSuggestItems,
    suggestLoading: rawIdSuggestLoading,
    suggestError: rawIdSuggestError,
    suggestHighlightIndex: rawIdSuggestHighlightIndex,
    suggestWrapRef: rawIdSuggestWrapRef,
    onInputChange: onRawIdInputChange,
    onKeyDown: onRawIdInputKeyDown,
    setSuggestHighlightIndex: setRawIdSuggestHighlightIndex,
    closeSuggestPanel: closeRawIdSuggestPanel,
    selectSuggestCandidate: selectRawIdSuggestCandidate,
  } = useRawIdSuggest({
    q: rawIdQ,
    entityType,
    source: "",
    onSelect: (item) => {
      setRawIdQ(item.entity_raw_id);
      setNameQ(item.label || "");
      onSelectedChange({
        vid: item.vid,
        label: item.label || item.entity_raw_id,
        entity_type: item.entity_type,
        source: item.source,
      });
    },
    onQueryChange: setRawIdQ,
    onSearch: () => {
      void runSlotSearch();
    },
  });

  useEffect(() => {
    if (!selected) return;
    setNameQ(selected.label);
  }, [selected]);

  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true;
      return;
    }
    onSelectedChange(null);
    setEntityType("");
    setNameQ("");
    setRawIdQ("");
    setSlotSearchItems([]);
    setSlotSearchError(null);
    closeNameSuggestPanel();
    closeRawIdSuggestPanel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetToken]);

  function clearSelection() {
    onSelectedChange(null);
    setNameQ("");
    setRawIdQ("");
    setSlotSearchItems([]);
    setSlotSearchError(null);
    closeNameSuggestPanel();
    closeRawIdSuggestPanel();
  }

  return (
    <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 10, display: "grid", gap: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>实体栏位 #{index + 1}</div>
        <button onClick={onRemove} disabled={!canRemove} style={{ padding: "4px 8px", fontSize: 12 }}>
          删除
        </button>
      </div>

      <div style={{ display: "grid", gap: 8 }}>
        <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#444" }}>
          <span>entity_type</span>
          <select
            style={{ width: "100%", padding: 8 }}
            value={entityType}
            disabled={!!selected}
            onChange={(e) => setEntityType(e.target.value)}
          >
            <option value="">全部</option>
            {entityTypeOptions.map((opt) => (
              <option key={opt.entity_type} value={opt.entity_type}>
                {opt.entity_type} ({opt.count})
              </option>
            ))}
          </select>
        </label>

        <div ref={rawIdSuggestWrapRef} style={{ position: "relative" }}>
          <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#444" }}>
            <span>entity_raw_id</span>
            <input
              style={{ width: "100%", padding: 8 }}
              placeholder="按 entity_raw_id 搜索（contains）"
              value={rawIdQ}
              disabled={!!selected}
              onChange={(e) => onRawIdInputChange(e.target.value)}
              onKeyDown={onRawIdInputKeyDown}
            />
          </label>

          {rawIdSuggestOpen && !selected ? (
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: "calc(100% + 6px)",
                zIndex: 31,
                border: "1px solid #e5e6eb",
                borderRadius: 8,
                background: "#fff",
                boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                maxHeight: 280,
                overflow: "auto",
              }}
            >
              {rawIdSuggestLoading ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
              ) : rawIdSuggestError ? (
                <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选请求失败（不影响搜索）</div>
              ) : rawIdSuggestItems.length === 0 ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选（继续输入以缩小范围）</div>
              ) : (
                rawIdSuggestItems.map((item, idx) => {
                  const active = idx === rawIdSuggestHighlightIndex;
                  return (
                    <div
                      key={`${item.vid}-${item.entity_raw_id}-${idx}`}
                      onMouseEnter={() => setRawIdSuggestHighlightIndex(idx)}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => selectRawIdSuggestCandidate(item)}
                      style={{
                        padding: "8px 10px",
                        cursor: "pointer",
                        borderBottom: idx === rawIdSuggestItems.length - 1 ? "none" : "1px solid #f0f0f0",
                        background: active ? "#e6f4ff" : "#fff",
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>{item.entity_raw_id}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                        {item.label || "(无名称)"}
                        {item.entity_type ? ` | ${item.entity_type}` : ""}
                        {item.source ? ` | ${item.source}` : ""}
                        {` | vid=${item.vid}`}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          ) : null}
        </div>

        <div ref={nameSuggestWrapRef} style={{ position: "relative" }}>
          <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#444" }}>
            <span>entity_name</span>
            <input
              style={{ width: "100%", padding: 8 }}
              placeholder="输入实体名称并点击候选锁定"
              value={nameQ}
              disabled={!!selected}
              onChange={(e) => onNameInputChange(e.target.value)}
              onKeyDown={onNameInputKeyDown}
            />
          </label>

          {nameSuggestOpen && !selected ? (
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: "calc(100% + 6px)",
                zIndex: 30,
                border: "1px solid #e5e6eb",
                borderRadius: 8,
                background: "#fff",
                boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                maxHeight: 280,
                overflow: "auto",
              }}
            >
              {nameSuggestLoading ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
              ) : nameSuggestError ? (
                <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选请求失败（不影响搜索）</div>
              ) : nameSuggestItems.length === 0 ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选（继续输入以缩小范围）</div>
              ) : (
                nameSuggestItems.map((item, idx) => {
                  const active = idx === nameSuggestHighlightIndex;
                  return (
                    <div
                      key={`${item.vid}-${item.label}-${idx}`}
                      onMouseEnter={() => setNameSuggestHighlightIndex(idx)}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => selectNameSuggestCandidate(item)}
                      style={{
                        padding: "8px 10px",
                        cursor: "pointer",
                        borderBottom: idx === nameSuggestItems.length - 1 ? "none" : "1px solid #f0f0f0",
                        background: active ? "#e6f4ff" : "#fff",
                      }}
                    >
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>{item.label}</div>
                      <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                        vid={item.vid}
                        {item.entity_type ? ` | ${item.entity_type}` : ""}
                        {item.source ? ` | ${item.source}` : ""}
                        {typeof item.score === "number" ? ` | score=${item.score}` : ""}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          ) : null}
        </div>
      </div>

      {selected ? (
        <div
          style={{
            border: "1px solid #f0f0f0",
            borderRadius: 8,
            padding: 8,
            display: "flex",
            justifyContent: "space-between",
            gap: 8,
            alignItems: "center",
            background: "#fafafa",
          }}
        >
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {selected.label}
            </div>
            <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
              id={selected.vid}
              {selected.entity_type ? ` | ${selected.entity_type}` : ""}
              {selected.source ? ` | ${selected.source}` : ""}
            </div>
          </div>
          <button
            onClick={clearSelection}
            style={{ padding: "6px 8px", fontSize: 12 }}
          >
            取消选择
          </button>
        </div>
      ) : (
        <div style={{ fontSize: 12, color: "#666" }}>未选择实体</div>
      )}

      {!selected ? (
        <div style={{ display: "grid", gap: 6 }}>
          <button
            onClick={() => {
              void runSlotSearch();
            }}
            disabled={slotSearchLoading}
            style={{ padding: "6px 10px", fontSize: 12 }}
          >
            {slotSearchLoading ? "搜索中…" : "搜索候选"}
          </button>
          {slotSearchError ? (
            <div style={{ fontSize: 12, color: "#d4380d" }}>搜索失败：{slotSearchError}</div>
          ) : null}
          {slotSearchItems.length > 0 ? (
            <div
              style={{
                border: "1px solid #f0f0f0",
                borderRadius: 8,
                maxHeight: 180,
                overflow: "auto",
              }}
            >
              {slotSearchItems.map((item, idx) => (
                <div
                  key={`${item.vid}-${idx}`}
                  onClick={() => onSelectedChange(item)}
                  style={{
                    padding: "8px 10px",
                    cursor: "pointer",
                    borderBottom: idx === slotSearchItems.length - 1 ? "none" : "1px solid #f5f5f5",
                  }}
                >
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{item.label}</div>
                  <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                    vid={item.vid}
                    {item.entity_type ? ` | ${item.entity_type}` : ""}
                    {item.source ? ` | ${item.source}` : ""}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

    </div>
  );
}

const MAX_SLOTS = 8;

export function LeftSearchPanel({
  q,
  onQChange,
  loadingSearch,
  onSearch,
  onSearchInputKeyDown,
  suggestWrapRef,
  suggestOpen,
  suggestLoading,
  suggestError,
  suggestItems,
  suggestHighlightIndex,
  setSuggestHighlightIndex,
  onSelectSuggestItem,
  searchName,
  setSearchName,
  searchDesc,
  setSearchDesc,
  entityType,
  setEntityType,
  entityTypeOptions,
  entityTypeFallbackUsed,
  source,
  setSource,
  entityRawId,
  onRawIdChange,
  onRawIdInputKeyDown,
  rawIdSuggestWrapRef,
  rawIdSuggestOpen,
  rawIdSuggestLoading,
  rawIdSuggestError,
  rawIdSuggestItems,
  rawIdSuggestHighlightIndex,
  setRawIdSuggestHighlightIndex,
  onSelectRawIdSuggestItem,
  searchData,
  rootVid,
  onLoadSubgraph,
  edgeQ,
  onEdgeQChange,
  edgeSearchLoading,
  onEdgeSearch,
  onEdgeSearchInputKeyDown,
  edgeSuggestWrapRef,
  edgeSuggestOpen,
  edgeSuggestLoading,
  edgeSuggestError,
  edgeSuggestItems,
  edgeSuggestHighlightIndex,
  setEdgeSuggestHighlightIndex,
  onSelectEdgeSuggestItem,
  edgeSearchInRelation,
  setEdgeSearchInRelation,
  edgeSearchInProps,
  setEdgeSearchInProps,
  edgeSearchSourceDb,
  setEdgeSearchSourceDb,
  edgeSearchRelation,
  setEdgeSearchRelation,
  edgeSearchData,
  onSelectEdgeSearchItem,
  edgeSearchNotice,
  loadingMultiGraph,
  onGenerateMultiGraph,
  showPathCandidates,
  pathCandidates,
  chosenPathByPair,
  onChoosePathForPair,
  onApplyPathForPair,
  pathApplyLoading,
  resolveEntityLabel,
  appliedExtraPaths,
  onAppendPathForPair,
}: LeftSearchPanelProps) {
  const [activeTab, setActiveTab] = useState<"node" | "edge">("node");
  const [nodeMode, setNodeMode] = useState<"single" | "multi">("single");

  const [multiSlots, setMultiSlots] = useState<MultiSlot[]>([
    { slotId: "slot-1", selected: null },
    { slotId: "slot-2", selected: null },
  ]);
  const [nextSlotId, setNextSlotId] = useState(3);
  const [slotResetToken, setSlotResetToken] = useState(0);

  const [multiDirectOnly, setMultiDirectOnly] = useState(true);
  const [multiExplainPaths, setMultiExplainPaths] = useState(false);
  const [multiExplainK, setMultiExplainK] = useState<2 | 3>(2);

  const selectedEntities = useMemo(() => {
    const seen = new Set<number>();
    const arr: SuggestItem[] = [];
    for (const s of multiSlots) {
      if (!s.selected) continue;
      if (seen.has(s.selected.vid)) continue;
      seen.add(s.selected.vid);
      arr.push(s.selected);
    }
    return arr;
  }, [multiSlots]);

  useEffect(() => {
    if (!multiExplainPaths || !multiDirectOnly) return;
    setMultiDirectOnly(false);
  }, [multiExplainPaths, multiDirectOnly]);

  const canGenerateMultiGraph = selectedEntities.length >= 2 && !loadingMultiGraph;

  function updateSlotSelection(slotId: string, item: SuggestItem | null) {
    setMultiSlots((prev) => prev.map((s) => (s.slotId === slotId ? { ...s, selected: item } : s)));
  }

  function removeSlot(slotId: string) {
    setMultiSlots((prev) => {
      if (prev.length <= 2) return prev;
      return prev.filter((s) => s.slotId !== slotId);
    });
  }

  function addSlot() {
    setMultiSlots((prev) => {
      if (prev.length >= MAX_SLOTS) return prev;
      return [...prev, { slotId: `slot-${nextSlotId}`, selected: null }];
    });
    setNextSlotId((v) => v + 1);
  }

  function clearAllSlots() {
    setMultiSlots((prev) => prev.map((s) => ({ ...s, selected: null })));
    setSlotResetToken((t) => t + 1);
  }

  return (
    <div style={{ padding: 16 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => setActiveTab("node")}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid #d9d9d9",
            background: activeTab === "node" ? "#e6f4ff" : "#fff",
            cursor: "pointer",
            fontWeight: activeTab === "node" ? 700 : 500,
          }}
        >
          实体检索
        </button>
        <button
          onClick={() => setActiveTab("edge")}
          style={{
            padding: "8px 12px",
            borderRadius: 8,
            border: "1px solid #d9d9d9",
            background: activeTab === "edge" ? "#e6f4ff" : "#fff",
            cursor: "pointer",
            fontWeight: activeTab === "edge" ? 700 : 500,
          }}
        >
          边检索
        </button>
      </div>

      {activeTab === "node" ? (
        <>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button
              onClick={() => setNodeMode("single")}
              style={{
                padding: "6px 10px",
                borderRadius: 8,
                border: "1px solid #d9d9d9",
                background: nodeMode === "single" ? "#fffbe6" : "#fff",
                cursor: "pointer",
                fontWeight: nodeMode === "single" ? 700 : 500,
                fontSize: 12,
              }}
            >
              单实体检索
            </button>
            <button
              onClick={() => setNodeMode("multi")}
              style={{
                padding: "6px 10px",
                borderRadius: 8,
                border: "1px solid #d9d9d9",
                background: nodeMode === "multi" ? "#fffbe6" : "#fff",
                cursor: "pointer",
                fontWeight: nodeMode === "multi" ? 700 : 500,
                fontSize: 12,
              }}
            >
              多实体关系
            </button>
          </div>

          {nodeMode === "single" ? (
            <>
              <h3 style={{ margin: "12px 0 0 0" }}>实体检索（Top100）</h3>

              <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
                <div ref={suggestWrapRef} style={{ position: "relative" }}>
                  <div style={{ display: "flex", gap: 8 }}>
                    <input
                      style={{ flex: 1, padding: 8 }}
                      placeholder="按 entity_name 搜索（模糊）"
                      value={q}
                      onChange={(e) => onQChange(e.target.value)}
                      onKeyDown={onSearchInputKeyDown}
                    />
                    <button onClick={onSearch} disabled={loadingSearch} style={{ padding: "8px 12px" }}>
                      {loadingSearch ? "搜索中…" : "搜索"}
                    </button>
                  </div>

                  {suggestOpen && (
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        right: 0,
                        top: "calc(100% + 6px)",
                        zIndex: 30,
                        border: "1px solid #e5e6eb",
                        borderRadius: 8,
                        background: "#fff",
                        boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                        maxHeight: 360,
                        overflow: "auto",
                      }}
                    >
                      {suggestLoading ? (
                        <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
                      ) : suggestError ? (
                        <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选请求失败（不影响搜索）</div>
                      ) : suggestItems.length === 0 ? (
                        <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选（继续输入以缩小范围）</div>
                      ) : (
                        suggestItems.map((item, idx) => {
                          const active = idx === suggestHighlightIndex;
                          return (
                            <div
                              key={`${item.vid}-${item.label}-${idx}`}
                              onMouseEnter={() => setSuggestHighlightIndex(idx)}
                              onMouseDown={(e) => e.preventDefault()}
                              onClick={() => onSelectSuggestItem(item)}
                              style={{
                                padding: "8px 10px",
                                cursor: "pointer",
                                borderBottom: idx === suggestItems.length - 1 ? "none" : "1px solid #f0f0f0",
                                background: active ? "#e6f4ff" : "#fff",
                              }}
                            >
                              <div style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>{item.label}</div>
                              <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                                vid={item.vid}
                                {item.entity_type ? ` | ${item.entity_type}` : ""}
                                {item.source ? ` | ${item.source}` : ""}
                                {typeof item.score === "number" ? ` | score=${item.score}` : ""}
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  )}
                </div>

                <div ref={rawIdSuggestWrapRef} style={{ position: "relative" }}>
                  <input
                    style={{ width: "100%", padding: 8 }}
                    placeholder="按 entity_raw_id 搜索（contains）"
                    value={entityRawId}
                    onChange={(e) => onRawIdChange(e.target.value)}
                    onKeyDown={onRawIdInputKeyDown}
                  />

                  {rawIdSuggestOpen ? (
                    <div
                      style={{
                        position: "absolute",
                        left: 0,
                        right: 0,
                        top: "calc(100% + 6px)",
                        zIndex: 29,
                        border: "1px solid #e5e6eb",
                        borderRadius: 8,
                        background: "#fff",
                        boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                        maxHeight: 360,
                        overflow: "auto",
                      }}
                    >
                      {rawIdSuggestLoading ? (
                        <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
                      ) : rawIdSuggestError ? (
                        <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选请求失败（不影响搜索）</div>
                      ) : rawIdSuggestItems.length === 0 ? (
                        <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选（继续输入以缩小范围）</div>
                      ) : (
                        rawIdSuggestItems.map((item, idx) => {
                          const active = idx === rawIdSuggestHighlightIndex;
                          return (
                            <div
                              key={`${item.vid}-${item.entity_raw_id}-${idx}`}
                              onMouseEnter={() => setRawIdSuggestHighlightIndex(idx)}
                              onMouseDown={(e) => e.preventDefault()}
                              onClick={() => onSelectRawIdSuggestItem(item)}
                              style={{
                                padding: "8px 10px",
                                cursor: "pointer",
                                borderBottom: idx === rawIdSuggestItems.length - 1 ? "none" : "1px solid #f0f0f0",
                                background: active ? "#e6f4ff" : "#fff",
                              }}
                            >
                              <div style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>{item.entity_raw_id}</div>
                              <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                                {item.label || "(无名称)"}
                                {item.entity_type ? ` | ${item.entity_type}` : ""}
                                {item.source ? ` | ${item.source}` : ""}
                                {` | vid=${item.vid}`}
                              </div>
                            </div>
                          );
                        })
                      )}
                    </div>
                  ) : null}
                </div>
              </div>

              <div style={{ marginTop: 10, display: "grid", gap: 6, fontSize: 13 }}>
                <label>
                  <input type="checkbox" checked={searchName} onChange={(e) => setSearchName(e.target.checked)} /> 搜索
                  entity_name
                </label>
                <label>
                  <input type="checkbox" checked={searchDesc} onChange={(e) => setSearchDesc(e.target.checked)} /> 搜索
                  description
                </label>
              </div>

              <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13, color: "#444" }}>entity_type：</span>
                  <span style={{ fontSize: 13, color: "#222" }}>（{entityType || "全部"}）</span>
                  <select
                    style={{ padding: 8, minWidth: 180 }}
                    value={entityType}
                    onChange={(e) => setEntityType(e.target.value)}
                  >
                    <option value="">全部</option>
                    {entityTypeOptions.map((opt) => (
                      <option key={opt.entity_type} value={opt.entity_type}>
                        {opt.entity_type} ({opt.count})
                      </option>
                    ))}
                  </select>
                </div>
                <input
                  style={{ padding: 8 }}
                  placeholder="过滤 source（可选，如 UMLS）"
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                />
              </div>
              {entityTypeFallbackUsed ? (
                <div style={{ marginTop: 4, color: "#999", fontSize: 12 }}>
                  entity_type 列表获取失败，使用内置列表
                </div>
              ) : null}

              <div style={{ marginTop: 10, color: "#666", fontSize: 12 }}>
                候选数量：{searchData.total_candidates}（返回 Top100）
              </div>
              <hr style={{ margin: "12px 0" }} />

              <div style={{ display: "grid", gap: 10 }}>
                {searchData.nodes.map((n) => (
                  <div
                    key={n.id}
                    style={{
                      padding: 10,
                      border: rootVid === n.id ? "1px solid #333" : "1px solid #f0f0f0",
                      borderRadius: 8,
                      cursor: "pointer",
                    }}
                    onClick={() => onLoadSubgraph(n.id)}
                    title="点击切换为该实体的子图"
                  >
                    <div style={{ fontWeight: 600 }}>{n.label}</div>
                    <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                      id={n.id} | {n.entity_type} | {n.source} | score={n.score}
                    </div>
                    {n.snippet ? <div style={{ fontSize: 12, marginTop: 6 }}>{n.snippet}</div> : null}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <>
              <h3 style={{ margin: "12px 0 0 0" }}>多实体关系</h3>

              <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button onClick={addSlot} disabled={multiSlots.length >= MAX_SLOTS || loadingMultiGraph} style={{ padding: "6px 10px", fontSize: 12 }}>
                  + 添加实体
                </button>
                <button onClick={clearAllSlots} disabled={loadingMultiGraph} style={{ padding: "6px 10px", fontSize: 12 }}>
                  清空全部
                </button>
                <div style={{ fontSize: 12, color: "#666", alignSelf: "center" }}>
                  已选 {selectedEntities.length} / {multiSlots.length}（去重后）
                </div>
              </div>

              <div style={{ marginTop: 10, display: "grid", gap: 8, fontSize: 13 }}>
                <label>
                  <input
                    type="checkbox"
                    checked={multiDirectOnly}
                    disabled={multiExplainPaths}
                    onChange={(e) => setMultiDirectOnly(e.target.checked)}
                  />{" "}
                  仅显示直接关系（默认；启用路径解释时自动关闭）
                </label>
                <label>
                  <input
                    type="checkbox"
                    checked={multiExplainPaths}
                    onChange={(e) => setMultiExplainPaths(e.target.checked)}
                  />{" "}
                  启用路径解释（k-hop）
                </label>
                {multiExplainPaths ? (
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                    <span>k</span>
                    <select value={multiExplainK} onChange={(e) => setMultiExplainK(Number(e.target.value) as 2 | 3)}>
                      <option value={2}>2</option>
                      <option value={3}>3</option>
                    </select>
                    <span style={{ color: "#666" }}>默认渲染 1 条最短路径，其它候选可切换</span>
                  </div>
                ) : null}
              </div>

              <button
                style={{ marginTop: 10, padding: "8px 12px" }}
                disabled={!canGenerateMultiGraph}
                onClick={() =>
                  onGenerateMultiGraph({
                    selectedEntities,
                    directOnly: multiExplainPaths ? false : multiDirectOnly,
                    explainPaths: multiExplainPaths,
                    k: multiExplainK,
                  })
                }
              >
                {loadingMultiGraph ? "生成中…" : "生成关系图"}
              </button>

              <div style={{ marginTop: 6, color: "#666", fontSize: 12 }}>
                默认只画直接边。启用路径解释后仅默认渲染 1 条最短路径，其他路径可在候选面板中按 pair 选择并替换。
              </div>

              <hr style={{ margin: "12px 0" }} />

              <div style={{ display: "grid", gap: 10 }}>
                {multiSlots.map((slot, idx) => (
                  <MultiEntitySlotInput
                    key={slot.slotId}
                    index={idx}
                    selected={slot.selected}
                    entityTypeOptions={entityTypeOptions}
                    canRemove={multiSlots.length > 2}
                    onRemove={() => removeSlot(slot.slotId)}
                    onSelectedChange={(item) => updateSlotSelection(slot.slotId, item)}
                    resetToken={slotResetToken}
                  />
                ))}
              </div>

              {showPathCandidates ? (
                <>
                  <hr style={{ margin: "12px 0" }} />
                  <div style={{ display: "grid", gap: 8 }}>
                    <div style={{ fontSize: 14, fontWeight: 700 }}>路径解释候选（按 pair）</div>
                    {pathCandidates.length === 0 ? (
                      <div style={{ fontSize: 12, color: "#666" }}>当前结果没有可切换的候选路径。</div>
                    ) : (
                      pathCandidates.map((pair) => {
                        const key = pairKey(pair.u, pair.v);
                        const selectedIndexRaw = chosenPathByPair[key];
                        const selectedIndex =
                          Number.isFinite(selectedIndexRaw) &&
                          selectedIndexRaw >= 0 &&
                          selectedIndexRaw < pair.candidates.length
                            ? selectedIndexRaw
                            : pair.candidates.length > 0
                              ? 0
                              : -1;
                        const selectedCandidate =
                          selectedIndex >= 0 ? pair.candidates[selectedIndex] : undefined;
                        const appended = appliedExtraPaths[key] || [];
                        const selectedAlreadyAppended = selectedIndex >= 0 && appended.includes(selectedIndex);

                        return (
                          <div
                            key={`${pair.u}-${pair.v}`}
                            style={{
                              border: "1px solid #f0f0f0",
                              borderRadius: 8,
                              padding: 10,
                              display: "grid",
                              gap: 8,
                            }}
                          >
                            <div style={{ fontSize: 13, fontWeight: 600 }}>
                              {resolveEntityLabel(pair.u)} ({pair.u}) ↔ {resolveEntityLabel(pair.v)} ({pair.v})
                            </div>

                            {pair.has_direct ? (
                              <div style={{ fontSize: 12, color: "#666" }}>已存在 direct edge，当前以直接边为主。</div>
                            ) : null}

                            {pair.candidates.length === 0 ? (
                              <div style={{ fontSize: 12, color: "#666" }}>
                                {pair.has_direct ? "无额外候选路径" : "k-hop 内无可用路径"}
                              </div>
                            ) : (
                              <>
                                <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                                  <select
                                    value={selectedIndex}
                                    onChange={(e) => onChoosePathForPair(pair.u, pair.v, Number(e.target.value))}
                                    style={{ padding: "4px 8px", maxWidth: "100%" }}
                                  >
                                    {pair.candidates.map((c, idx) => (
                                      <option key={c.path_id || `${pair.u}-${pair.v}-${idx}`} value={idx}>
                                        候选 #{idx + 1} | length={c.length}
                                        {typeof c.score === "number" ? ` | score=${c.score}` : ""}
                                      </option>
                                    ))}
                                  </select>
                                  <button
                                    onClick={() => onApplyPathForPair(pair.u, pair.v)}
                                    disabled={loadingMultiGraph || pathApplyLoading}
                                    style={{ padding: "6px 10px", fontSize: 12 }}
                                  >
                                    {pathApplyLoading ? "应用中…" : "应用该路径（替换）"}
                                  </button>
                                  <button
                                    onClick={() => onAppendPathForPair(pair.u, pair.v)}
                                    disabled={loadingMultiGraph || pathApplyLoading || selectedAlreadyAppended}
                                    style={{ padding: "6px 10px", fontSize: 12 }}
                                  >
                                    {selectedAlreadyAppended ? "已追加" : "追加该路径"}
                                  </button>
                                </div>
                                <div style={{ fontSize: 12, color: "#666" }}>
                                  {selectedCandidate?.summary ||
                                    `nodes: ${(selectedCandidate?.nodes || []).join(" -> ")}`}
                                </div>
                                {appended.length > 0 ? (
                                  <div style={{ fontSize: 12, color: "#666" }}>
                                    已追加候选：{appended.map((x) => `#${x + 1}`).join(", ")}
                                  </div>
                                ) : null}
                              </>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                </>
              ) : null}
            </>
          )}
        </>
      ) : (
        <>
          <h3 style={{ margin: "12px 0 0 0" }}>边检索（Top100）</h3>

          <div ref={edgeSuggestWrapRef} style={{ marginTop: 12, position: "relative" }}>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                style={{ flex: 1, padding: 8 }}
                placeholder="关键词（模糊）"
                value={edgeQ}
                onChange={(e) => onEdgeQChange(e.target.value)}
                onKeyDown={onEdgeSearchInputKeyDown}
              />
              <button onClick={onEdgeSearch} disabled={edgeSearchLoading} style={{ padding: "8px 12px" }}>
                {edgeSearchLoading ? "搜索中…" : "搜索"}
              </button>
            </div>

            {edgeSuggestOpen && (
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  top: "calc(100% + 6px)",
                  zIndex: 30,
                  border: "1px solid #e5e6eb",
                  borderRadius: 8,
                  background: "#fff",
                  boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
                  maxHeight: 360,
                  overflow: "auto",
                }}
              >
                {edgeSuggestLoading ? (
                  <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
                ) : edgeSuggestError ? (
                  <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选请求失败（不影响搜索）</div>
                ) : edgeSuggestItems.length === 0 ? (
                  <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选（继续输入以缩小范围）</div>
                ) : (
                  edgeSuggestItems.map((item, idx) => {
                    const active = idx === edgeSuggestHighlightIndex;
                    return (
                      <div
                        key={`${item.src}-${item.dst}-${item.rank || "0"}-${item.relation}-${item.source_db || ""}-${idx}`}
                        onMouseEnter={() => setEdgeSuggestHighlightIndex(idx)}
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => onSelectEdgeSuggestItem(item)}
                        style={{
                          padding: "8px 10px",
                          cursor: "pointer",
                          borderBottom: idx === edgeSuggestItems.length - 1 ? "none" : "1px solid #f0f0f0",
                          background: active ? "#e6f4ff" : "#fff",
                        }}
                      >
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#222" }}>
                          {relationDisplay(item.relation) || item.relation}
                        </div>
                        <div style={{ marginTop: 4, fontSize: 12, color: "#666" }}>
                          {(item.src_label || item.src) + ` (${item.src})`} → {(item.dst_label || item.dst) + ` (${item.dst})`}
                          {` | ${item.edge_type || "REL2"} | rank=${item.rank ?? "0"}`}
                          {item.source_db ? ` | ${item.source_db}` : ""}
                          {typeof item.score === "number" ? ` | score=${item.score}` : ""}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>

          <div style={{ marginTop: 10, display: "grid", gap: 6, fontSize: 13 }}>
            <label>
              <input
                type="checkbox"
                checked={edgeSearchInRelation}
                onChange={(e) => setEdgeSearchInRelation(e.target.checked)}
              />{" "}
              搜索 relation
            </label>
            <label>
              <input type="checkbox" checked={edgeSearchInProps} onChange={(e) => setEdgeSearchInProps(e.target.checked)} />{" "}
              搜索 props
            </label>
          </div>

          <div style={{ marginTop: 10, display: "grid", gap: 8 }}>
            <input
              style={{ padding: 8 }}
              placeholder="过滤 source_db（可选，如 UMLS）"
              value={edgeSearchSourceDb}
              onChange={(e) => setEdgeSearchSourceDb(e.target.value)}
            />
            <input
              style={{ padding: 8 }}
              placeholder="过滤 relation（可选）"
              value={edgeSearchRelation}
              onChange={(e) => setEdgeSearchRelation(e.target.value)}
            />
          </div>

          <div style={{ marginTop: 10, color: "#666", fontSize: 12 }}>候选数量：{edgeSearchData.total_candidates}（返回 Top100）</div>
          {edgeSearchNotice ? (
            <div style={{ marginTop: 8, color: "#d4380d", fontSize: 12 }}>{edgeSearchNotice}</div>
          ) : null}
          <hr style={{ margin: "12px 0" }} />

          <div style={{ display: "grid", gap: 10 }}>
            {edgeSearchData.edges.map((e, idx) => (
              <div
                key={`${e.src}-${e.dst}-${e.rank || "0"}-${e.relation}-${e.source_db || ""}-${idx}`}
                style={{
                  padding: 10,
                  border: "1px solid #f0f0f0",
                  borderRadius: 8,
                  cursor: "pointer",
                }}
                onClick={() => onSelectEdgeSearchItem(e)}
                title="点击定位该边并打开边详情"
              >
                <div style={{ fontWeight: 600 }}>{relationDisplay(e.relation) || e.relation}</div>
                <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                  {(e.src_label || e.src) + ` (${e.src})`} → {(e.dst_label || e.dst) + ` (${e.dst})`}
                  {` | ${e.edge_type || "REL2"} | rank=${e.rank ?? "0"}`}
                  {e.source_db ? ` | ${e.source_db}` : ""}
                  {typeof e.score === "number" ? ` | score=${e.score}` : ""}
                </div>
                {e.snippet ? <div style={{ fontSize: 12, marginTop: 6 }}>{e.snippet}</div> : null}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
