import type { EditLayoutField } from "../hooks/useEditLayout";

export function EditField({
  field,
  value,
  disabled,
  onChange,
}: {
  field: EditLayoutField;
  value: string;
  disabled?: boolean;
  onChange: (next: string) => void;
}) {
  const readOnly = Boolean(field.readOnly);
  const counterText = `${value.length}/${field.maxLen}`;

  if (readOnly) {
    return (
      <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#444" }}>
        <span>{field.label}</span>
        <div
          data-testid={`edit-field-${field.name}`}
          style={{ padding: 8, border: "1px solid #eee", borderRadius: 6, background: "#fafafa", color: value ? "#222" : "#999" }}
        >
          {value || "-"}
        </div>
      </label>
    );
  }

  return (
    <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#444" }}>
      <span>
        {field.label}
        {field.highRisk ? <span style={{ color: "#d46b08" }}>（高风险）</span> : null}
        <span style={{ color: "#888" }}> ({counterText})</span>
      </span>
      {field.multiline ? (
        <textarea
          data-testid={`edit-field-${field.name}`}
          value={value}
          disabled={disabled}
          rows={4}
          maxLength={field.maxLen}
          onChange={(event) => onChange(event.target.value)}
          style={{ width: "100%", padding: 8, resize: "vertical" }}
        />
      ) : (
        <input
          data-testid={`edit-field-${field.name}`}
          value={value}
          disabled={disabled}
          maxLength={field.maxLen}
          onChange={(event) => onChange(event.target.value)}
          style={{ width: "100%", padding: 8 }}
        />
      )}
    </label>
  );
}
