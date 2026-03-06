import { useCallback, useEffect, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";

import { relationTypes as relationTypesApi } from "../api/kg";
import { useRawIdSuggest } from "../hooks/useRawIdSuggest";
import { useSuggest } from "../hooks/useSuggest";
import type {
  EntityTypeItem,
  GraphDiscoveryEntityFacetItem,
  GraphDiscoveryRelationFacetItem,
  RelationTypeItem,
  RawIdSuggestItem,
  SuggestItem,
} from "../types/kg";
import { parseApiError } from "../utils/httpError";
import { relationDisplay } from "../utils/kg";

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

type DiscoveryPanelProps = {
  seeds: SuggestItem[];
  query: DiscoveryQueryState;
  runtime: DiscoveryRuntimeState;
  entityTypeOptions: EntityTypeItem[];
  resultFacets: {
    entityTypes: GraphDiscoveryEntityFacetItem[];
    relationTypes: GraphDiscoveryRelationFacetItem[];
  } | null;
  loading: boolean;
  onAddSeed: (item: SuggestItem) => void;
  onRemoveSeed: (vid: number) => void;
  onClearSeeds: () => void;
  onUpdateQuery: (patch: Partial<DiscoveryQueryState>) => void;
  onUpdateRuntime: (patch: Partial<DiscoveryRuntimeState>) => void;
  onRun: () => void;
  onNotice: (level: "error" | "warn" | "info", message: string) => void;
};

const RELATION_TYPES_PAGE_SIZE = 100;

function CheckboxList({
  items,
  checked,
  renderLabel,
  onToggle,
  onSelectAll,
  onClear,
  emptyText,
}: {
  items: string[];
  checked: Set<string>;
  renderLabel: (key: string) => string;
  onToggle: (key: string) => void;
  onSelectAll: () => void;
  onClear: () => void;
  emptyText: string;
}) {
  return (
    <div style={{ display: "grid", gap: 8 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button onClick={onSelectAll} style={{ padding: "6px 8px", fontSize: 12 }}>
          全选
        </button>
        <button onClick={onClear} style={{ padding: "6px 8px", fontSize: 12 }}>
          清空
        </button>
      </div>
      <div
        style={{
          maxHeight: 180,
          overflow: "auto",
          border: "1px solid #eee",
          borderRadius: 8,
          background: "#fff",
          padding: 8,
          display: "grid",
          gap: 6,
        }}
      >
        {items.length === 0 ? (
          <div style={{ fontSize: 12, color: "#666" }}>{emptyText}</div>
        ) : (
          items.map((key) => (
            <label key={key} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12, cursor: "pointer" }}>
              <input type="checkbox" checked={checked.has(key)} onChange={() => onToggle(key)} />
              <span>{renderLabel(key)}</span>
            </label>
          ))
        )}
      </div>
    </div>
  );
}

export function DiscoveryPanel({
  seeds,
  query,
  runtime,
  entityTypeOptions,
  resultFacets,
  loading,
  onAddSeed,
  onRemoveSeed,
  onClearSeeds,
  onUpdateQuery,
  onUpdateRuntime,
  onRun,
  onNotice,
}: DiscoveryPanelProps) {
  const [nameQ, setNameQ] = useState("");
  const [rawIdQ, setRawIdQ] = useState("");
  const [seedEntityType, setSeedEntityType] = useState("");

  const [relationCatalogItems, setRelationCatalogItems] = useState<RelationTypeItem[]>([]);
  const [relationCatalogQuery, setRelationCatalogQuery] = useState("");
  const [relationCatalogLoading, setRelationCatalogLoading] = useState(false);
  const [relationCatalogHasMore, setRelationCatalogHasMore] = useState(false);
  const [relationCatalogNextOffset, setRelationCatalogNextOffset] = useState<number | null>(0);

  const queryEntityTypeSet = useMemo(() => new Set(query.allowedEntityTypes), [query.allowedEntityTypes]);
  const queryRelationTypeSet = useMemo(() => new Set(query.allowedRelationTypes), [query.allowedRelationTypes]);
  const runtimeEntityTypeSet = useMemo(() => new Set(runtime.entityTypes), [runtime.entityTypes]);
  const runtimeRelationTypeSet = useMemo(() => new Set(runtime.relationTypes), [runtime.relationTypes]);

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
    selectSuggestCandidate,
  } = useSuggest({
    q: nameQ,
    entityType: seedEntityType,
    source: "",
    onSelect: (item) => {
      onAddSeed(item);
      setNameQ("");
      setRawIdQ("");
    },
    onQueryChange: setNameQ,
    onSearch: () => {},
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
    selectSuggestCandidate: selectRawIdSuggestCandidate,
  } = useRawIdSuggest({
    q: rawIdQ,
    entityType: seedEntityType,
    source: "",
    onSelect: (item: RawIdSuggestItem) => {
      onAddSeed({
        vid: item.vid,
        label: item.label || item.entity_raw_id,
        entity_type: item.entity_type,
        source: item.source,
      });
      setNameQ("");
      setRawIdQ("");
    },
    onQueryChange: setRawIdQ,
    onSearch: () => {},
  });

  useEffect(() => {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => {
      setRelationCatalogLoading(true);
      void relationTypesApi({
        q: relationCatalogQuery,
        limit: RELATION_TYPES_PAGE_SIZE,
        offset: 0,
        signal: controller.signal,
      })
        .then((resp) => {
          setRelationCatalogItems(resp.items);
          setRelationCatalogHasMore(resp.has_more);
          setRelationCatalogNextOffset(resp.next_offset);
        })
        .catch((e: unknown) => {
          if (e instanceof Error && e.name === "AbortError") return;
          const parsed = parseApiError(e);
          onNotice("warn", `relation metadata 加载失败：${parsed.message}`);
        })
        .finally(() => {
          if (!controller.signal.aborted) setRelationCatalogLoading(false);
        });
    }, 180);

    return () => {
      controller.abort();
      window.clearTimeout(timeoutId);
    };
  }, [onNotice, relationCatalogQuery]);

  const handleLoadMoreRelationTypes = useCallback(async () => {
    if (relationCatalogLoading) return;
    if (!relationCatalogHasMore || relationCatalogNextOffset == null) return;
    setRelationCatalogLoading(true);
    try {
      const resp = await relationTypesApi({
        q: relationCatalogQuery,
        limit: RELATION_TYPES_PAGE_SIZE,
        offset: relationCatalogNextOffset,
      });
      setRelationCatalogItems((prev) => {
        const merged = new Map<string, RelationTypeItem>();
        for (const item of prev) merged.set(item.relation_type, item);
        for (const item of resp.items) merged.set(item.relation_type, item);
        return Array.from(merged.values());
      });
      setRelationCatalogHasMore(resp.has_more);
      setRelationCatalogNextOffset(resp.next_offset);
    } catch (e: unknown) {
      const parsed = parseApiError(e);
      onNotice("warn", `relation metadata 加载失败：${parsed.message}`);
    } finally {
      setRelationCatalogLoading(false);
    }
  }, [onNotice, relationCatalogHasMore, relationCatalogLoading, relationCatalogNextOffset, relationCatalogQuery]);

  function toggleArrayValue(list: string[], value: string) {
    const key = String(value || "").trim();
    if (!key) return list;
    const next = new Set(list);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return Array.from(next).sort((a, b) => a.localeCompare(b));
  }

  function handleNameKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    onKeyDown(e);
    if (e.key === "Enter" && suggestItems[suggestHighlightIndex]) {
      e.preventDefault();
      selectSuggestCandidate(suggestItems[suggestHighlightIndex]);
    }
  }

  function handleRawIdKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    onRawIdKeyDown(e);
    if (e.key === "Enter" && rawIdSuggestItems[rawIdSuggestHighlightIndex]) {
      e.preventDefault();
      selectRawIdSuggestCandidate(rawIdSuggestItems[rawIdSuggestHighlightIndex]);
    }
  }

  const queryEntityTypeItems = useMemo(
    () => entityTypeOptions.map((item) => item.entity_type),
    [entityTypeOptions]
  );
  const queryRelationTypeItems = useMemo(
    () => relationCatalogItems.map((item) => item.relation_type),
    [relationCatalogItems]
  );

  return (
    <div style={{ padding: 16, display: "grid", gap: 14 }}>
      <div>
        <h3 style={{ margin: 0 }}>统一关系发现</h3>
        <div style={{ marginTop: 6, fontSize: 12, color: "#666" }}>
          添加 1 个或多个 seed，按实体/关系类型做查询前过滤，生成主题关系图。
        </div>
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 10 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>Seed 节点</div>

        <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
          <span>seed entity_type（可选）</span>
          <select value={seedEntityType} onChange={(e) => setSeedEntityType(e.target.value)} style={{ padding: 8 }}>
            <option value="">全部</option>
            {entityTypeOptions.map((opt) => (
              <option key={opt.entity_type} value={opt.entity_type}>
                {opt.entity_type} ({opt.count})
              </option>
            ))}
          </select>
        </label>

        <div ref={suggestWrapRef} style={{ position: "relative" }}>
          <input
            value={nameQ}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleNameKeyDown}
            placeholder="按 entity_name 搜索 seed"
            style={{ width: "100%", padding: 8 }}
          />
          {suggestOpen ? (
            <div style={{ position: "absolute", left: 0, right: 0, top: "calc(100% + 6px)", zIndex: 30, border: "1px solid #e5e6eb", borderRadius: 8, background: "#fff", boxShadow: "0 8px 24px rgba(0,0,0,0.12)", maxHeight: 240, overflow: "auto" }}>
              {suggestLoading ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
              ) : suggestError ? (
                <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选加载失败</div>
              ) : suggestItems.length === 0 ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选</div>
              ) : (
                suggestItems.map((item, idx) => (
                  <div
                    key={`${item.vid}-${item.label}-${idx}`}
                    onMouseEnter={() => setSuggestHighlightIndex(idx)}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectSuggestCandidate(item)}
                    style={{ padding: "8px 10px", cursor: "pointer", background: idx === suggestHighlightIndex ? "#e6f4ff" : "#fff" }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{item.label}</div>
                    <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                      vid={item.vid}
                      {item.entity_type ? ` | ${item.entity_type}` : ""}
                      {item.source ? ` | ${item.source}` : ""}
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : null}
        </div>

        <div ref={rawIdSuggestWrapRef} style={{ position: "relative" }}>
          <input
            value={rawIdQ}
            onChange={(e) => onRawIdInputChange(e.target.value)}
            onKeyDown={handleRawIdKeyDown}
            placeholder="按 entity_raw_id 搜索 seed"
            style={{ width: "100%", padding: 8 }}
          />
          {rawIdSuggestOpen ? (
            <div style={{ position: "absolute", left: 0, right: 0, top: "calc(100% + 6px)", zIndex: 29, border: "1px solid #e5e6eb", borderRadius: 8, background: "#fff", boxShadow: "0 8px 24px rgba(0,0,0,0.12)", maxHeight: 240, overflow: "auto" }}>
              {rawIdSuggestLoading ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>加载中…</div>
              ) : rawIdSuggestError ? (
                <div style={{ padding: 10, fontSize: 13, color: "#d4380d" }}>候选加载失败</div>
              ) : rawIdSuggestItems.length === 0 ? (
                <div style={{ padding: 10, fontSize: 13, color: "#666" }}>无匹配候选</div>
              ) : (
                rawIdSuggestItems.map((item, idx) => (
                  <div
                    key={`${item.vid}-${item.entity_raw_id}-${idx}`}
                    onMouseEnter={() => setRawIdSuggestHighlightIndex(idx)}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => selectRawIdSuggestCandidate(item)}
                    style={{ padding: "8px 10px", cursor: "pointer", background: idx === rawIdSuggestHighlightIndex ? "#e6f4ff" : "#fff" }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 600 }}>{item.entity_raw_id}</div>
                    <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                      {item.label || "(无名称)"} | vid={item.vid}
                      {item.entity_type ? ` | ${item.entity_type}` : ""}
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : null}
        </div>

        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={onClearSeeds} disabled={loading || seeds.length === 0} style={{ padding: "6px 10px", fontSize: 12 }}>
            清空 Seed
          </button>
          <div style={{ fontSize: 12, color: "#666", alignSelf: "center" }}>已选 {seeds.length}</div>
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          {seeds.length === 0 ? (
            <div style={{ fontSize: 12, color: "#666" }}>尚未添加 seed 节点</div>
          ) : (
            seeds.map((seed) => (
              <div key={seed.vid} style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", border: "1px solid #f0f0f0", borderRadius: 8, padding: 8, background: "#fafafa" }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{seed.label}</div>
                  <div style={{ fontSize: 12, color: "#666", marginTop: 2 }}>
                    vid={seed.vid}
                    {seed.entity_type ? ` | ${seed.entity_type}` : ""}
                    {seed.source ? ` | ${seed.source}` : ""}
                  </div>
                </div>
                <button onClick={() => onRemoveSeed(seed.vid)} style={{ padding: "6px 8px", fontSize: 12 }}>
                  删除
                </button>
              </div>
            ))
          )}
        </div>
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>查询前配置</div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>allowed_entity_types</div>
          <CheckboxList
            items={queryEntityTypeItems}
            checked={queryEntityTypeSet}
            renderLabel={(key) => {
              const found = entityTypeOptions.find((item) => item.entity_type === key);
              return found ? `${key} (${found.count})` : key;
            }}
            onToggle={(key) => onUpdateQuery({ allowedEntityTypes: toggleArrayValue(query.allowedEntityTypes, key) })}
            onSelectAll={() => onUpdateQuery({ allowedEntityTypes: [...queryEntityTypeItems] })}
            onClear={() => onUpdateQuery({ allowedEntityTypes: [] })}
            emptyText="暂无 entity_type metadata"
          />
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <div style={{ fontSize: 12, fontWeight: 600 }}>allowed_relation_types</div>
            <button
              onClick={() => {
                void handleLoadMoreRelationTypes();
              }}
              disabled={relationCatalogLoading || !relationCatalogHasMore}
              style={{ padding: "6px 8px", fontSize: 12 }}
            >
              {relationCatalogHasMore ? "加载更多" : "已无更多"}
            </button>
          </div>
          <input
            value={relationCatalogQuery}
            onChange={(e) => setRelationCatalogQuery(e.target.value)}
            placeholder="搜索 relation metadata"
            style={{ width: "100%", padding: 8 }}
          />
          <CheckboxList
            items={queryRelationTypeItems}
            checked={queryRelationTypeSet}
            renderLabel={(key) => {
              const found = relationCatalogItems.find((item) => item.relation_type === key);
              const display = relationDisplay(key) || key;
              return found ? `${display} (${found.count})` : display;
            }}
            onToggle={(key) => onUpdateQuery({ allowedRelationTypes: toggleArrayValue(query.allowedRelationTypes, key) })}
            onSelectAll={() => onUpdateQuery({ allowedRelationTypes: [...queryRelationTypeItems] })}
            onClear={() => onUpdateQuery({ allowedRelationTypes: [] })}
            emptyText={relationCatalogLoading ? "relation metadata 加载中…" : "暂无 relation metadata"}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>max_nodes</span>
            <input type="number" min={10} max={1000} value={query.maxNodes} onChange={(e) => onUpdateQuery({ maxNodes: Number(e.target.value) || 0 })} style={{ padding: 8 }} />
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>max_edges</span>
            <input type="number" min={10} max={5000} value={query.maxEdges} onChange={(e) => onUpdateQuery({ maxEdges: Number(e.target.value) || 0 })} style={{ padding: 8 }} />
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>top_k_per_type</span>
            <input type="number" min={1} max={100} value={query.topKPerType} onChange={(e) => onUpdateQuery({ topKPerType: Number(e.target.value) || 0 })} style={{ padding: 8 }} />
          </label>
          <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
            <span>hop</span>
            <select value={query.hop} onChange={(e) => onUpdateQuery({ hop: Number(e.target.value) || 1 })} style={{ padding: 8 }}>
              <option value={1}>1</option>
            </select>
          </label>
        </div>

        <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 12 }}>
          <input
            type="checkbox"
            checked={query.includeCandidateCandidateEdges}
            onChange={(e) => onUpdateQuery({ includeCandidateCandidateEdges: e.target.checked })}
          />
          include_candidate_candidate_edges
        </label>

        <label style={{ display: "inline-flex", gap: 8, alignItems: "center", fontSize: 12 }}>
          <input
            type="checkbox"
            checked={query.includeSeedSeedEdges}
            onChange={(e) => onUpdateQuery({ includeSeedSeedEdges: e.target.checked })}
          />
          include_seed_seed_edges
        </label>

        <button onClick={onRun} disabled={loading || seeds.length === 0} style={{ padding: "10px 12px" }}>
          {loading ? "生成中…" : "生成主题关系图"}
        </button>
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, display: "grid", gap: 12 }}>
        <div style={{ fontSize: 13, fontWeight: 700 }}>查询后二次过滤</div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>entity type facets</div>
          <CheckboxList
            items={(resultFacets?.entityTypes || []).map((item) => item.entity_type)}
            checked={runtimeEntityTypeSet}
            renderLabel={(key) => {
              const found = resultFacets?.entityTypes.find((item) => item.entity_type === key);
              return found ? `${key} (${found.count})` : key;
            }}
            onToggle={(key) => onUpdateRuntime({ entityTypes: toggleArrayValue(runtime.entityTypes, key) })}
            onSelectAll={() => onUpdateRuntime({ entityTypes: (resultFacets?.entityTypes || []).map((item) => item.entity_type) })}
            onClear={() => onUpdateRuntime({ entityTypes: [] })}
            emptyText="运行 discovery 后显示"
          />
        </div>

        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 12, fontWeight: 600 }}>relation type facets</div>
          <CheckboxList
            items={(resultFacets?.relationTypes || []).map((item) => item.relation_type)}
            checked={runtimeRelationTypeSet}
            renderLabel={(key) => {
              const found = resultFacets?.relationTypes.find((item) => item.relation_type === key);
              const display = relationDisplay(key) || key;
              return found ? `${display} (${found.count})` : display;
            }}
            onToggle={(key) => onUpdateRuntime({ relationTypes: toggleArrayValue(runtime.relationTypes, key) })}
            onSelectAll={() => onUpdateRuntime({ relationTypes: (resultFacets?.relationTypes || []).map((item) => item.relation_type) })}
            onClear={() => onUpdateRuntime({ relationTypes: [] })}
            emptyText="运行 discovery 后显示"
          />
        </div>
      </div>
    </div>
  );
}
