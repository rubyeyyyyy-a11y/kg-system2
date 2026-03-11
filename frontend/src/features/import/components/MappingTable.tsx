import type { ImportFieldMapping, ImportMode, ImportSchemaObject, ImportTargetMapping } from "../types/import";

type MappingTableProps = {
  mode: ImportMode;
  target: ImportTargetMapping;
  schemaObjects: ImportSchemaObject[];
  onChange: (next: ImportTargetMapping) => void;
  onRemove?: () => void;
};

const VERTEX_TARGET_FIELDS = ["ID", "entity_name", "entity_type", "entity_raw_id", "description", "source"];
const EDGE_TARGET_FIELDS = ["srcVID", "dstVID", "rank", "relation", "source", "evidence", "score"];

function optionsForTarget(target: ImportTargetMapping, schemaObjects: ImportSchemaObject[]) {
  const builtin = target.object_type === "tag" ? VERTEX_TARGET_FIELDS : EDGE_TARGET_FIELDS;
  const schemaObject = schemaObjects.find((item) => item.name === target.object_name);
  const extra = (schemaObject?.properties || []).map((item) => item.name);
  return Array.from(new Set([...builtin, ...extra]));
}

function updateFieldMappings(fieldMappings: ImportFieldMapping[], index: number, patch: Partial<ImportFieldMapping>) {
  return fieldMappings.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item));
}

export function MappingTable({ mode, target, schemaObjects, onChange, onRemove }: MappingTableProps) {
  const fieldOptions = optionsForTarget(target, schemaObjects);

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
            onChange={(event) => onChange({ ...target, object_type: event.target.value as ImportTargetMapping["object_type"] })}
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
          <span style={{ fontSize: 12, color: "#6c5b47" }}>{mode === "mixed" ? "discriminator 值" : "模式"}</span>
          <input
            value={target.discriminator_value || ""}
            disabled={mode !== "mixed"}
            placeholder={mode === "mixed" ? "例如 vertex / edge / relation_a" : "仅 mixed 模式可用"}
            onChange={(event) => onChange({ ...target, discriminator_value: event.target.value })}
          />
        </label>
        {onRemove ? (
          <button onClick={onRemove} style={{ alignSelf: "end", background: "#fff1f0", borderColor: "#ffccc7" }}>
            删除目标
          </button>
        ) : (
          <div />
        )}
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f6efe4" }}>
              <th style={{ textAlign: "left", padding: 8 }}>CSV 列</th>
              <th style={{ textAlign: "left", padding: 8 }}>映射到</th>
            </tr>
          </thead>
          <tbody>
            {target.field_mappings.map((mapping, index) => (
              <tr key={`${mapping.source_column}-${index}`} style={{ borderTop: "1px solid #f0e6d8" }}>
                <td style={{ padding: 8 }}>{mapping.source_column}</td>
                <td style={{ padding: 8 }}>
                  <select
                    value={mapping.target_field}
                    onChange={(event) =>
                      onChange({
                        ...target,
                        field_mappings: updateFieldMappings(target.field_mappings, index, {
                          target_field: event.target.value,
                        }),
                      })
                    }
                  >
                    <option value="">忽略</option>
                    {fieldOptions.map((fieldName) => (
                      <option key={fieldName} value={fieldName}>
                        {fieldName}
                      </option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
