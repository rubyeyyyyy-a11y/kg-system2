import { useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { FixedSizeList } from "react-window";
import type { RelPreset } from "../../hooks/useRelationFilter";
import type { RelationTypeItem } from "../../types/kg";
import { getRelationGroupKey, normalizeText, relationDisplay, uniqueStrings } from "../../utils/relation";

type MatchMode = "display" | "raw" | "both";
type SortMode = "count" | "alpha" | "selected";

type RelationFilterPanelProps = {
  relationCatalogItems: RelationTypeItem[];
  relationCatalogLoading: boolean;
  relationCatalogHasMore: boolean;
  relationCatalogMatchedTotal: number;
  relationCatalogQuery: string;
  draftRelations: string[];
  appliedRelations: string[];
  relationCountMap: Map<string, number>;
  previewActive: boolean;
  previewEdgeTotal: number;
  onRelationCatalogQueryChange: (next: string) => void;
  onRelationCatalogLoadMore: () => void;
  onClose: () => void;
  onToggleDraftRelation: (raw: string) => void;
  onClearDraft: () => void;
  onRestoreApplied: () => void;
  onInvertCurrentList: (currentList: string[]) => void;
  onPreviewOnlyApply: () => void;
  onExitPreview: () => void;
  onApplyAndReload: () => void;
  presets: RelPreset[];
  activePresetId: string;
  onSelectPreset: (presetId: string) => void;
  onSavePreset: (name: string) => void;
  onRenamePreset: (presetId: string, name: string) => void;
  onDeletePreset: (presetId: string) => void;
  estimateKeepEdges: (relations: string[]) => number;
};

type RelationItem = {
  raw: string;
  display: string;
  count: number;
  selected: boolean;
  groupKey: string;
};

type RowData = {
  items: RelationItem[];
  draftSet: Set<string>;
  onToggleDraftRelation: (raw: string) => void;
};

const ROW_HEIGHT = 56;
const LIST_HEIGHT = 420;
const SYSTEM_PRESET_ID = "__all__";

function RelationRow({
  index,
  style,
  data,
}: {
  index: number;
  style: CSSProperties;
  data: RowData;
}) {
  const item = data.items[index];
  if (!item) return null;
  const checked = data.draftSet.has(item.raw);
  return (
    <div
      style={{
        ...style,
        boxSizing: "border-box",
        borderBottom: "1px solid #f2f2f2",
        padding: "8px 10px",
        display: "grid",
        gridTemplateColumns: "24px minmax(0,1fr) auto",
        alignItems: "center",
        gap: 8,
      }}
      title={item.raw}
    >
      <input type="checkbox" checked={checked} onChange={() => data.onToggleDraftRelation(item.raw)} />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {item.display}
        </div>
        <div style={{ fontSize: 11, color: "#777", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {item.raw}
        </div>
      </div>
      <div style={{ fontSize: 12, color: "#444", minWidth: 34, textAlign: "right" }}>{item.count}</div>
    </div>
  );
}

export function RelationFilterPanel({
  relationCatalogItems,
  relationCatalogLoading,
  relationCatalogHasMore,
  relationCatalogMatchedTotal,
  relationCatalogQuery,
  draftRelations,
  appliedRelations,
  relationCountMap,
  previewActive,
  previewEdgeTotal,
  onRelationCatalogQueryChange,
  onRelationCatalogLoadMore,
  onClose,
  onToggleDraftRelation,
  onClearDraft,
  onRestoreApplied,
  onInvertCurrentList,
  onPreviewOnlyApply,
  onExitPreview,
  onApplyAndReload,
  presets,
  activePresetId,
  onSelectPreset,
  onSavePreset,
  onRenamePreset,
  onDeletePreset,
  estimateKeepEdges,
}: RelationFilterPanelProps) {
  const [scopeCurrentOnly, setScopeCurrentOnly] = useState(true);
  const [matchMode, setMatchMode] = useState<MatchMode>("both");
  const [sortMode, setSortMode] = useState<SortMode>("count");
  const [activeGroupKey, setActiveGroupKey] = useState<string>("");
  const [collapsedByGroup, setCollapsedByGroup] = useState<Record<string, boolean>>({});

  const draftSet = useMemo(() => new Set(draftRelations), [draftRelations]);
  const relationCatalogCountMap = useMemo(() => {
    const next = new Map<string, number>();
    for (const item of relationCatalogItems) {
      const raw = String(item.relation_type || "").trim();
      if (!raw) continue;
      next.set(raw, Number(item.count) || 0);
    }
    return next;
  }, [relationCatalogItems]);

  const baseRelations = useMemo(() => {
    const fromGraph = Array.from(relationCountMap.keys());
    const fromCatalog = relationCatalogItems.map((item) => item.relation_type);
    const merged = uniqueStrings([...fromCatalog, ...fromGraph, ...draftRelations, ...appliedRelations]);
    if (!scopeCurrentOnly) return merged;
    const currentSet = new Set(fromGraph);
    return merged.filter((raw) => currentSet.has(raw));
  }, [relationCatalogItems, relationCountMap, draftRelations, appliedRelations, scopeCurrentOnly]);

  const filteredSortedItems = useMemo(() => {
    const kw = normalizeText(relationCatalogQuery);
    const out: RelationItem[] = [];
    for (const raw of baseRelations) {
      const display = relationDisplay(raw) || raw;
      const rawNorm = normalizeText(raw);
      const displayNorm = normalizeText(display);
      const matched =
        !kw ||
        (matchMode === "display" && displayNorm.includes(kw)) ||
        (matchMode === "raw" && rawNorm.includes(kw)) ||
        (matchMode === "both" && (displayNorm.includes(kw) || rawNorm.includes(kw)));
      if (!matched) continue;
      out.push({
        raw,
        display,
        count: relationCountMap.get(raw) || relationCatalogCountMap.get(raw) || 0,
        selected: draftSet.has(raw),
        groupKey: getRelationGroupKey(display),
      });
    }

    out.sort((a, b) => {
      if (sortMode === "count") {
        if (b.count !== a.count) return b.count - a.count;
        return a.display.localeCompare(b.display);
      }
      if (sortMode === "selected") {
        if (a.selected !== b.selected) return a.selected ? -1 : 1;
        if (b.count !== a.count) return b.count - a.count;
        return a.display.localeCompare(b.display);
      }
      return a.display.localeCompare(b.display);
    });

    return out;
  }, [baseRelations, draftSet, matchMode, relationCatalogCountMap, relationCatalogQuery, relationCountMap, sortMode]);

  const groupedItems = useMemo(() => {
    const m = new Map<string, RelationItem[]>();
    for (const item of filteredSortedItems) {
      const key = item.groupKey || "Other";
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(item);
    }
    return m;
  }, [filteredSortedItems]);

  const groupEntries = useMemo(() => {
    return Array.from(groupedItems.entries())
      .map(([groupKey, items]) => ({
        groupKey,
        total: items.length,
        selected: items.filter((x) => x.selected).length,
      }))
      .sort((a, b) => {
        if (b.selected !== a.selected) return b.selected - a.selected;
        if (b.total !== a.total) return b.total - a.total;
        return a.groupKey.localeCompare(b.groupKey);
      });
  }, [groupedItems]);

  const effectiveActiveGroupKey =
    groupEntries.some((x) => x.groupKey === activeGroupKey) ? activeGroupKey : (groupEntries[0]?.groupKey ?? "");
  const activeGroupCollapsed = !!collapsedByGroup[effectiveActiveGroupKey];
  const rightItems = useMemo(() => {
    if (!effectiveActiveGroupKey || activeGroupCollapsed) return [];
    return groupedItems.get(effectiveActiveGroupKey) || [];
  }, [activeGroupCollapsed, effectiveActiveGroupKey, groupedItems]);

  const rowData = useMemo<RowData>(
    () => ({
      items: rightItems,
      draftSet,
      onToggleDraftRelation,
    }),
    [rightItems, draftSet, onToggleDraftRelation]
  );

  const selectedChipItems = useMemo(() => {
    return draftRelations.map((raw) => ({
      raw,
      display: relationDisplay(raw) || raw,
    }));
  }, [draftRelations]);

  const currentListRawRelations = useMemo(() => rightItems.map((x) => x.raw), [rightItems]);
  const keepEdges = estimateKeepEdges(draftRelations);
  const changePct = previewEdgeTotal > 0 ? ((keepEdges - previewEdgeTotal) / previewEdgeTotal) * 100 : 0;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 100,
        background: "rgba(0,0,0,0.24)",
        display: "grid",
        placeItems: "center",
      }}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          width: "min(1200px, calc(100vw - 48px))",
          height: "min(88vh, 860px)",
          background: "#fff",
          borderRadius: 12,
          border: "1px solid #e8e8e8",
          boxShadow: "0 16px 48px rgba(0,0,0,0.2)",
          display: "grid",
          gridTemplateRows: "auto auto minmax(0,1fr) auto",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            padding: 12,
            borderBottom: "1px solid #eee",
            display: "grid",
            gap: 10,
            background: "#fafafa",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ fontSize: 15, fontWeight: 700 }}>筛选关系（数据层）</div>
            <button onClick={onClose} style={{ padding: "6px 10px", fontSize: 12 }}>
              关闭
            </button>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "minmax(220px,1fr) auto auto auto", gap: 8 }}>
            <input
              value={relationCatalogQuery}
              onChange={(e) => onRelationCatalogQueryChange(e.target.value)}
              placeholder="搜索 relation（支持 display/raw）"
              style={{ padding: 8, minWidth: 0 }}
            />
            <label style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <input type="checkbox" checked={scopeCurrentOnly} onChange={(e) => setScopeCurrentOnly(e.target.checked)} />
              仅当前图出现
            </label>
            <select value={matchMode} onChange={(e) => setMatchMode(e.target.value as MatchMode)} style={{ padding: 8 }}>
              <option value="display">匹配显示名</option>
              <option value="raw">匹配原始名</option>
              <option value="both">匹配两者</option>
            </select>
            <select value={sortMode} onChange={(e) => setSortMode(e.target.value as SortMode)} style={{ padding: 8 }}>
              <option value="count">按出现次数</option>
              <option value="alpha">按字母排序</option>
              <option value="selected">已选优先</option>
            </select>
          </div>
        </div>

        <div style={{ padding: 10, borderBottom: "1px solid #eee", display: "grid", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={onClearDraft} style={{ padding: "6px 8px", fontSize: 12 }}>
              清空已选
            </button>
            <button onClick={onRestoreApplied} style={{ padding: "6px 8px", fontSize: 12 }}>
              恢复已应用
            </button>
            <button
              onClick={() => onInvertCurrentList(currentListRawRelations)}
              style={{ padding: "6px 8px", fontSize: 12 }}
              disabled={currentListRawRelations.length === 0}
            >
              反选当前列表
            </button>
            <div style={{ marginLeft: "auto", fontSize: 12, color: "#666", alignSelf: "center" }}>
              已选 {draftRelations.length} 项 | metadata 匹配 {relationCatalogMatchedTotal} 项
            </div>
          </div>

          <div
            style={{
              border: "1px solid #f0f0f0",
              borderRadius: 8,
              padding: 8,
              maxHeight: 84,
              overflow: "auto",
              display: "flex",
              gap: 6,
              flexWrap: "wrap",
            }}
          >
            {selectedChipItems.length === 0 ? (
              <span style={{ fontSize: 12, color: "#777" }}>当前未选择任何关系（等价于全部）</span>
            ) : (
              selectedChipItems.map((chip) => (
                <button
                  key={chip.raw}
                  onClick={() => onToggleDraftRelation(chip.raw)}
                  style={{
                    padding: "3px 8px",
                    fontSize: 12,
                    borderRadius: 999,
                    border: "1px solid #d9d9d9",
                    background: "#fff",
                    cursor: "pointer",
                  }}
                  title={`移除: ${chip.raw}`}
                >
                  {chip.display} ×
                </button>
              ))
            )}
          </div>
        </div>

        <div style={{ minHeight: 0, display: "grid", gridTemplateColumns: "280px minmax(0,1fr)", gap: 10, padding: 10 }}>
          <div
            style={{
              border: "1px solid #eee",
              borderRadius: 8,
              overflow: "auto",
              padding: 8,
              display: "grid",
              gap: 6,
              alignContent: "start",
            }}
          >
            {groupEntries.length === 0 ? (
              <div style={{ fontSize: 12, color: "#777", padding: 4 }}>无匹配分组</div>
            ) : (
              groupEntries.map((g) => {
                const collapsed = !!collapsedByGroup[g.groupKey];
                const active = g.groupKey === effectiveActiveGroupKey;
                return (
                  <div
                    key={g.groupKey}
                    style={{
                      border: active ? "1px solid #91caff" : "1px solid #f0f0f0",
                      borderRadius: 8,
                      padding: 8,
                      background: active ? "#f0f8ff" : "#fff",
                    }}
                  >
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <button
                        onClick={() =>
                          setCollapsedByGroup((prev) => ({
                            ...prev,
                            [g.groupKey]: !collapsed,
                          }))
                        }
                        style={{ padding: "2px 6px", fontSize: 11 }}
                        title={collapsed ? "展开分组" : "折叠分组"}
                      >
                        {collapsed ? "▶" : "▼"}
                      </button>
                      <button
                        onClick={() => setActiveGroupKey(g.groupKey)}
                        style={{
                          padding: "2px 6px",
                          fontSize: 12,
                          border: "1px solid #ddd",
                          borderRadius: 6,
                          background: active ? "#e6f4ff" : "#fff",
                        }}
                      >
                        {g.groupKey}
                      </button>
                      <span style={{ marginLeft: "auto", fontSize: 12, color: "#666" }}>
                        {g.selected}/{g.total}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div style={{ border: "1px solid #eee", borderRadius: 8, overflow: "hidden", display: "grid", gridTemplateRows: "auto 1fr" }}>
            <div style={{ padding: "8px 10px", borderBottom: "1px solid #eee", fontSize: 12, color: "#666" }}>
              当前分组：{effectiveActiveGroupKey || "-"} | 右侧项数：{rightItems.length}
            </div>
            <div style={{ minHeight: 0 }}>
              {rightItems.length === 0 ? (
                <div style={{ padding: 10, fontSize: 12, color: "#777" }}>无可展示关系</div>
              ) : (
                <FixedSizeList<RowData>
                  width="100%"
                  height={LIST_HEIGHT}
                  itemCount={rightItems.length}
                  itemSize={ROW_HEIGHT}
                  itemData={rowData}
                >
                  {RelationRow}
                </FixedSizeList>
              )}
            </div>
            <div style={{ padding: "8px 10px", borderTop: "1px solid #eee", display: "flex", gap: 8, alignItems: "center" }}>
              <div style={{ fontSize: 12, color: "#666" }}>
                {relationCatalogLoading ? "metadata 加载中…" : `已加载 metadata ${relationCatalogItems.length} 项`}
              </div>
              <button
                onClick={onRelationCatalogLoadMore}
                disabled={relationCatalogLoading || !relationCatalogHasMore}
                style={{ marginLeft: "auto", padding: "6px 8px", fontSize: 12 }}
              >
                {relationCatalogHasMore ? "加载更多" : "已无更多"}
              </button>
            </div>
          </div>
        </div>

        <div
          style={{
            padding: 10,
            borderTop: "1px solid #eee",
            background: "#fafafa",
            display: "grid",
            gap: 10,
          }}
        >
          <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto auto", gap: 8 }}>
            <select value={activePresetId} onChange={(e) => onSelectPreset(e.target.value)} style={{ padding: 8, minWidth: 0 }}>
              {presets.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <button
              onClick={() => {
                const name = window.prompt("请输入 preset 名称");
                if (name) onSavePreset(name);
              }}
              style={{ padding: "8px 10px", fontSize: 12 }}
            >
              保存当前为 preset
            </button>
            <button
              onClick={() => {
                if (activePresetId === SYSTEM_PRESET_ID) return;
                const current = presets.find((p) => p.id === activePresetId);
                const name = window.prompt("请输入新名称", current?.name || "");
                if (name) onRenamePreset(activePresetId, name);
              }}
              style={{ padding: "8px 10px", fontSize: 12 }}
              disabled={activePresetId === SYSTEM_PRESET_ID}
            >
              重命名
            </button>
            <button
              onClick={() => {
                if (activePresetId === SYSTEM_PRESET_ID) return;
                if (!window.confirm("确认删除该 preset？")) return;
                onDeletePreset(activePresetId);
              }}
              style={{ padding: "8px 10px", fontSize: 12 }}
              disabled={activePresetId === SYSTEM_PRESET_ID}
            >
              删除
            </button>
          </div>

          <div style={{ fontSize: 12, color: "#555" }}>
            当前边数 E={previewEdgeTotal} / 勾选后预计保留边数 E_keep={keepEdges} / 变化{" "}
            <strong>{changePct >= 0 ? "+" : ""}{changePct.toFixed(1)}%</strong>
          </div>

          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
            {previewActive ? (
              <button onClick={onExitPreview} style={{ padding: "8px 12px", fontSize: 12 }}>
                退出预览（恢复已应用）
              </button>
            ) : null}
            <button onClick={onClose} style={{ padding: "8px 12px", fontSize: 12 }}>
              取消
            </button>
            <button onClick={onPreviewOnlyApply} style={{ padding: "8px 12px", fontSize: 12 }}>
              仅预览应用（不重载）
            </button>
            <button onClick={onApplyAndReload} style={{ padding: "8px 12px", fontSize: 12 }}>
              应用并重载
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
