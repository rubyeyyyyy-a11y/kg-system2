import type { NodeBrief, NodeDetailResp } from "../../../types/kg";
import { useDetailLayout } from "../hooks/useDetailLayout";
import { useNormalizedNodeDetail } from "../hooks/useNormalizedDetail";
import { DetailField } from "./DetailField";
import { DetailSection } from "./DetailSection";
import { RawJsonDebugSection } from "./RawJsonDebugSection";

export function NodeDetailView({
  detail,
  selectedNodeBrief,
  hopLevel,
  detailLoading,
}: {
  detail: NodeDetailResp | null;
  selectedNodeBrief: NodeBrief | null;
  hopLevel?: number | string | null;
  detailLoading?: boolean;
}) {
  const normalized = useNormalizedNodeDetail({ detail, selectedNodeBrief, hopLevel });
  const layout = useDetailLayout(normalized);

  return (
    <div data-testid="selected-node-detail" style={{ display: "grid", gap: 10 }}>
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
