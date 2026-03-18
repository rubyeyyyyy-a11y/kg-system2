import { ExpandableText } from "./ExpandableText";
import { formatValue } from "../utils/formatValue";
import type { DetailLayoutField } from "../hooks/useDetailLayout";

export function DetailField({ field }: { field: DetailLayoutField }) {
  const longText = Boolean(field.longText) || (typeof field.value === "string" && field.value.trim().length > 240);
  const showLabel = field.name !== "description";
  return (
    <div style={{ display: "grid", gap: 4 }}>
      {showLabel ? <div style={{ fontSize: 11, color: "#888", textTransform: "uppercase" }}>{field.label}</div> : null}
      <div style={{ fontSize: 12, color: "#222" }}>
        {longText && typeof field.value === "string" ? (
          <ExpandableText
            text={field.value}
            previewChars={field.longText?.previewChars ?? 240}
            testId={`detail-expand-${field.name}`}
          />
        ) : (
          <span style={{ wordBreak: "break-word", whiteSpace: "pre-wrap" }}>{formatValue(field.name, field.value)}</span>
        )}
      </div>
    </div>
  );
}
