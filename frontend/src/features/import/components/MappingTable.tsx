import type {
  ImportObjectType,
  ImportPropertyMapping,
  ImportSchemaObject,
  ImportSource,
  ImportTargetMapping,
} from "../types/import";

type MappingTableProps = {
  target: ImportTargetMapping;
  sources: ImportSource[];
  schemaObjects: ImportSchemaObject[];
  onChange: (next: ImportTargetMapping) => void;
  onRemove?: () => void;
};

const VERTEX_PROPERTY_FIELDS = ["entity_name", "entity_type", "entity_raw_id", "description", "source"];
const EDGE_PROPERTY_FIELDS = ["relation", "source", "evidence", "score"];

function sourceForTarget(target: ImportTargetMapping, sources: ImportSource[]) {
  return sources.find((item) => item.source_id === target.source_id) || null;
}

function propertyOptions(target: ImportTargetMapping, schemaObjects: ImportSchemaObject[]) {
  const builtin = target.object_type === "tag" ? VERTEX_PROPERTY_FIELDS : EDGE_PROPERTY_FIELDS;
  const schemaObject = schemaObjects.find((item) => item.object_type === target.object_type && item.name === target.object_name);
  const extra = (schemaObject?.properties || []).map((item) => item.name);
  return Array.from(new Set([...builtin, ...extra]));
}

function nextSourceDefaults(source: ImportSource | null, objectType: ImportObjectType) {
  const columns = source?.columns || [];
  const initialProperties: ImportPropertyMapping[] = [];
  if (objectType === "tag") {
    for (const column of columns) {
      if (column === "VID" || column === "ID") continue;
      initialProperties.push({ source_column: column, target_field: column });
    }
    return { identity_mapping: { id_column: columns.find((item) => item === "VID" || item === "ID") || "" }, property_mappings: initialProperties };
  }
  for (const column of columns) {
    if (column === "SRC_VID" || column === "DST_VID" || column === "rank") continue;
    initialProperties.push({ source_column: column, target_field: column });
  }
  return {
    identity_mapping: {
      src_column: columns.find((item) => item === "SRC_VID" || item === "srcVID") || "",
      dst_column: columns.find((item) => item === "DST_VID" || item === "dstVID") || "",
      rank_column: columns.find((item) => item === "rank") || "",
    },
    property_mappings: initialProperties,
  };
}

export function MappingTable({ target, sources, schemaObjects, onChange, onRemove }: MappingTableProps) {
  const source = sourceForTarget(target, sources);
  const propertyFieldOptions = propertyOptions(target, schemaObjects);

  return (
    <div
      style={{
        border: "1px solid rgba(76, 56, 36, 0.14)",
        borderRadius: 18,
        padding: 16,
        background: "#fffdf8",
        display: "grid",
        gap: 12,
      }}
    >
      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr 1fr auto" }}>
        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#6c5b47" }}>对象类型</span>
          <select
            value={target.object_type}
            onChange={(event) => {
              const objectType = event.target.value as ImportObjectType;
              const nextDefaults = nextSourceDefaults(source, objectType);
              onChange({
                ...target,
                object_type: objectType,
                object_name: objectType === "tag" ? "Entity" : "REL2",
                identity_mapping: nextDefaults.identity_mapping,
                property_mappings: nextDefaults.property_mappings,
              });
            }}
          >
            <option value="tag">tag</option>
            <option value="edge_type">edge_type</option>
          </select>
        </label>
        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#6c5b47" }}>对象名</span>
          <input value={target.object_name} onChange={(event) => onChange({ ...target, object_name: event.target.value })} />
        </label>
        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ fontSize: 12, color: "#6c5b47" }}>绑定 Source</span>
          <select
            value={target.source_id}
            onChange={(event) => {
              const nextSource = sources.find((item) => item.source_id === event.target.value) || null;
              const nextDefaults = nextSourceDefaults(nextSource, target.object_type);
              onChange({
                ...target,
                source_id: event.target.value,
                identity_mapping: nextDefaults.identity_mapping,
                property_mappings: nextDefaults.property_mappings,
              });
            }}
          >
            {sources.map((item) => (
              <option key={item.source_id} value={item.source_id}>
                {item.filename}
              </option>
            ))}
          </select>
        </label>
        {onRemove ? (
          <button onClick={onRemove} style={{ alignSelf: "end", background: "#fff1f0", borderColor: "#ffccc7" }}>
            删除目标
          </button>
        ) : (
          <div />
        )}
      </div>

      {source ? (
        <div style={{ display: "grid", gap: 10, fontSize: 13, color: "#5b4b38" }}>
          <div>
            source={source.filename} | kind={source.inferred_kind} | columns={source.columns.join(", ")}
          </div>
          {target.object_type === "tag" ? (
            <label style={{ display: "grid", gap: 6 }}>
              <span style={{ fontSize: 12, color: "#6c5b47" }}>identity.id_column</span>
              <select
                value={target.identity_mapping.id_column || ""}
                onChange={(event) => onChange({ ...target, identity_mapping: { id_column: event.target.value } })}
              >
                <option value="">未绑定</option>
                {source.columns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr 1fr" }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span style={{ fontSize: 12, color: "#6c5b47" }}>identity.src_column</span>
                <select
                  value={target.identity_mapping.src_column || ""}
                  onChange={(event) =>
                    onChange({
                      ...target,
                      identity_mapping: { ...target.identity_mapping, src_column: event.target.value },
                    })
                  }
                >
                  <option value="">未绑定</option>
                  {source.columns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ display: "grid", gap: 6 }}>
                <span style={{ fontSize: 12, color: "#6c5b47" }}>identity.dst_column</span>
                <select
                  value={target.identity_mapping.dst_column || ""}
                  onChange={(event) =>
                    onChange({
                      ...target,
                      identity_mapping: { ...target.identity_mapping, dst_column: event.target.value },
                    })
                  }
                >
                  <option value="">未绑定</option>
                  {source.columns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </label>
              <label style={{ display: "grid", gap: 6 }}>
                <span style={{ fontSize: 12, color: "#6c5b47" }}>identity.rank_column</span>
                <select
                  value={target.identity_mapping.rank_column || ""}
                  onChange={(event) =>
                    onChange({
                      ...target,
                      identity_mapping: { ...target.identity_mapping, rank_column: event.target.value },
                    })
                  }
                >
                  <option value="">system generated</option>
                  {source.columns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f6efe4" }}>
                  <th style={{ textAlign: "left", padding: 8 }}>Source 列</th>
                  <th style={{ textAlign: "left", padding: 8 }}>属性字段</th>
                </tr>
              </thead>
              <tbody>
                {source.columns.map((column) => {
                  const row = target.property_mappings.find((item) => item.source_column === column) || {
                    source_column: column,
                    target_field: "",
                  };
                  const isIdentityColumn =
                    column === target.identity_mapping.id_column ||
                    column === target.identity_mapping.src_column ||
                    column === target.identity_mapping.dst_column ||
                    column === target.identity_mapping.rank_column;
                  return (
                    <tr key={column} style={{ borderTop: "1px solid #f0e6d8" }}>
                      <td style={{ padding: 8 }}>{column}</td>
                      <td style={{ padding: 8 }}>
                        <select
                          value={isIdentityColumn ? "" : row.target_field}
                          disabled={isIdentityColumn}
                          onChange={(event) => {
                            const nextValue = event.target.value;
                            const nextMappings = target.property_mappings.filter((item) => item.source_column !== column);
                            if (nextValue) nextMappings.push({ source_column: column, target_field: nextValue });
                            onChange({ ...target, property_mappings: nextMappings });
                          }}
                        >
                          <option value="">{isIdentityColumn ? "identity 占用" : "忽略"}</option>
                          {propertyFieldOptions.map((fieldName) => (
                            <option key={fieldName} value={fieldName}>
                              {fieldName}
                            </option>
                          ))}
                          {!propertyFieldOptions.includes(column) ? (
                            <option value={column}>{column}</option>
                          ) : null}
                        </select>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 13, color: "#7d6b57" }}>请选择一个 source。</div>
      )}
    </div>
  );
}
