import type { EdgeDetailResp, Sel } from "../../../types/kg";
import { useDetailLayout } from "../hooks/useDetailLayout";
import { useNormalizedEdgeDetail } from "../hooks/useNormalizedDetail";
import { DetailField } from "./DetailField";
import { DetailSection } from "./DetailSection";
import { RawJsonDebugSection } from "./RawJsonDebugSection";

export function EdgeDetailView({
  detail,
  selection,
  detailLoading,
}: {
  detail: EdgeDetailResp | null;
  selection: Extract<Sel, { kind: "edge" }> | null;
  detailLoading?: boolean;
}) {
  const normalized = useNormalizedEdgeDetail({ detail, selection });
  const layout = useDetailLayout(normalized);

  return (
    <div data-testid="selected-edge-detail" style={{ display: "grid", gap: 10 }}>
      <div>
        <div style={{ fontWeight: 700 }}>{layout.title.primary}</div>
        <div style={{ fontSize: 12, color: "#666" }}>{layout.title.secondary || "-"}</div>
      </div>

      {detailLoading ? <div style={{ fontSize: 12, color: "#666" }}>加载详情中…</div> : null}

      {layout.sections.map((section) => (
        <DetailSection key={section.key} title={section.title}>
          {section.fields.map((field) => (
            <DetailField key={field.name} field={field} />
          ))}
        </DetailSection>
      ))}

      <RawJsonDebugSection payload={detail ?? { props: normalized.props, ...normalized.allFields }} />
    </div>
  );
}
