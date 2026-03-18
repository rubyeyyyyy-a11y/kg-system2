import { useEffect, useMemo, useState } from "react";

type ExpandableTextProps = {
  text: string;
  previewChars?: number;
  testId?: string;
};

export function ExpandableText({ text, previewChars = 240, testId }: ExpandableTextProps) {
  const [expanded, setExpanded] = useState(false);
  const trimmed = String(text || "").trim();
  useEffect(() => {
    setExpanded(false);
  }, [trimmed]);
  const summary = useMemo(() => {
    if (trimmed.length <= previewChars) return trimmed;
    return `${trimmed.slice(0, previewChars)}...`;
  }, [previewChars, trimmed]);
  const canToggle = summary !== trimmed;

  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", lineHeight: 1.5 }}>
        {expanded ? trimmed : summary || "-"}
      </div>
      {canToggle ? (
        <button
          data-testid={testId}
          onClick={() => setExpanded((value) => !value)}
          style={{ width: "fit-content", padding: "4px 8px", fontSize: 12 }}
        >
          {expanded ? "收起" : "展开详情"}
        </button>
      ) : null}
    </div>
  );
}
