import { CreateSpaceInlinePanel } from "./CreateSpaceInlinePanel";
import { SpaceSwitcher } from "./SpaceSwitcher";
import type { CreateSpaceResp, CurrentSpaceResp, SpaceSummary } from "../../space/types/space";

type SpaceActionSummary = {
  title: string;
  message: string;
};

type ImportSpaceContextBarProps = {
  currentSpace: string;
  current: SpaceSummary | null;
  resolvedCurrent: CurrentSpaceResp | null;
  spaces: SpaceSummary[];
  loading: boolean;
  error: string | null;
  spaceSwitching: boolean;
  spaceSwitchPhase: string;
  defaultSpaceName: string;
  createOpen: boolean;
  createSubmitting: boolean;
  createError: string | null;
  actionSummary: SpaceActionSummary | null;
  onDismissActionSummary: () => void;
  onSelectSpace: (spaceName: string) => void;
  onOpenCreate: () => void;
  onCloseCreate: () => void;
  onRefresh: () => void;
  onCreateSpace: (payload: {
    space_name: string;
    display_name: string;
    description: string;
    template_type: "entity_rel2_default";
    created_by: string;
  }) => Promise<CreateSpaceResp>;
};

function statusTone(status: string | undefined) {
  if (status === "ready") return { bg: "#eefbf1", color: "#166534" };
  if (status === "failed") return { bg: "#fff1f0", color: "#a61d24" };
  return { bg: "#fff7e6", color: "#ad6800" };
}

function detailValue(value?: string | null) {
  const text = String(value || "").trim();
  return text || "-";
}

export function ImportSpaceContextBar({
  currentSpace,
  current,
  resolvedCurrent,
  spaces,
  loading,
  error,
  spaceSwitching,
  spaceSwitchPhase,
  defaultSpaceName,
  createOpen,
  createSubmitting,
  createError,
  actionSummary,
  onDismissActionSummary,
  onSelectSpace,
  onOpenCreate,
  onCloseCreate,
  onRefresh,
  onCreateSpace,
}: ImportSpaceContextBarProps) {
  const canClassifySpace = !!currentSpace && !!defaultSpaceName;
  const isDefaultSpace = canClassifySpace && currentSpace === defaultSpaceName;
  const isTemplateTestSpace =
    canClassifySpace && !!current && current.space_name !== defaultSpaceName && current.template_type === "entity_rel2_default";
  const statusStyle = statusTone(current?.status || resolvedCurrent?.registry_status || "");

  return (
    <section
      style={{
        borderRadius: 26,
        background: "linear-gradient(135deg, rgba(85, 56, 30, 0.95), rgba(129, 88, 45, 0.88))",
        color: "#fff7ed",
        padding: 24,
        display: "grid",
        gap: 16,
        boxShadow: "0 24px 80px rgba(94, 63, 32, 0.18)",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ display: "grid", gap: 8 }}>
          <div style={{ fontSize: 13, letterSpacing: "0.18em", textTransform: "uppercase", opacity: 0.8 }}>Import Workspace</div>
          <div style={{ fontSize: 32, fontWeight: 700, lineHeight: 1.1 }}>选择 Space 后再导入</div>
          <div style={{ maxWidth: 860, fontSize: 14, color: "rgba(255,247,237,0.88)" }}>
            当前主流程已经收口为：选择或创建 current space，上传 CSV，冻结 draft / compiled plan / job snapshot，然后在该 space 中查看图谱。
          </div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <SpaceSwitcher
            currentSpace={currentSpace}
            spaces={spaces}
            loading={loading}
            switching={spaceSwitching}
            onSelect={onSelectSpace}
          />
          <button onClick={onRefresh} style={{ padding: "10px 14px", borderRadius: 12, border: "none", background: "#f6dfb4", color: "#51371d" }}>
            Refresh
          </button>
          <button onClick={onOpenCreate} style={{ padding: "10px 14px", borderRadius: 12, border: "none", background: "#fff7ed", color: "#51371d" }}>
            Create New Space
          </button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 12 }}>
        <div style={{ padding: 14, borderRadius: 16, background: "rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: 12, opacity: 0.76 }}>current space</div>
          <strong style={{ display: "block", marginTop: 6, fontSize: 18 }}>{detailValue(currentSpace)}</strong>
          <div style={{ fontSize: 12, marginTop: 8, color: "rgba(255,247,237,0.82)" }}>source={resolvedCurrent?.source || "header"}</div>
        </div>
        <div style={{ padding: 14, borderRadius: 16, background: "rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: 12, opacity: 0.76 }}>display_name</div>
          <strong style={{ display: "block", marginTop: 6, fontSize: 18 }}>{detailValue(current?.display_name || current?.space_name)}</strong>
        </div>
        <div style={{ padding: 14, borderRadius: 16, background: "rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: 12, opacity: 0.76 }}>template_type</div>
          <strong style={{ display: "block", marginTop: 6, fontSize: 18 }}>{detailValue(current?.template_type)}</strong>
        </div>
        <div style={{ padding: 14, borderRadius: 16, background: "rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: 12, opacity: 0.76 }}>integration_scope</div>
          <strong style={{ display: "block", marginTop: 6, fontSize: 18 }}>{detailValue(current?.integration_scope)}</strong>
        </div>
        <div style={{ padding: 14, borderRadius: 16, background: "rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: 12, opacity: 0.76 }}>status</div>
          <strong
            style={{
              display: "inline-flex",
              marginTop: 6,
              padding: "4px 10px",
              borderRadius: 999,
              background: statusStyle.bg,
              color: statusStyle.color,
              fontSize: 14,
            }}
          >
            {detailValue(current?.status || resolvedCurrent?.registry_status)}
          </strong>
        </div>
        <div style={{ padding: 14, borderRadius: 16, background: "rgba(255,255,255,0.12)" }}>
          <div style={{ fontSize: 12, opacity: 0.76 }}>index_status</div>
          <strong style={{ display: "block", marginTop: 6, fontSize: 18 }}>
            {detailValue(current?.index_status?.status || resolvedCurrent?.index_status?.status)}
          </strong>
          <div style={{ fontSize: 12, marginTop: 8, color: "rgba(255,247,237,0.82)" }}>
            canonical_docs={current?.index_status?.doc_count ?? resolvedCurrent?.index_status?.doc_count ?? 0}
          </div>
        </div>
      </div>

      {error ? <div style={{ padding: 12, borderRadius: 14, background: "#fff1f0", color: "#a61d24", fontSize: 13 }}>{error}</div> : null}

      {spaceSwitching ? (
        <div style={{ padding: 12, borderRadius: 14, background: "#fff7e6", color: "#ad6800", fontSize: 13 }}>
          current space switching: {spaceSwitchPhase}
        </div>
      ) : null}

      {actionSummary ? (
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", padding: 14, borderRadius: 16, background: "#eefbf1", color: "#166534" }}>
          <div style={{ display: "grid", gap: 4 }}>
            <strong>{actionSummary.title}</strong>
            <div style={{ fontSize: 13 }}>{actionSummary.message}</div>
          </div>
          <button onClick={onDismissActionSummary} style={{ padding: "8px 12px" }}>
            Dismiss
          </button>
        </div>
      ) : null}

      {isDefaultSpace ? (
        <div style={{ padding: 12, borderRadius: 14, background: "#fff7e6", color: "#ad6800", fontSize: 13 }}>
          You are importing into the default project space. Create a new test space if you want isolated testing.
        </div>
      ) : null}

      {isTemplateTestSpace ? (
        <div style={{ padding: 12, borderRadius: 14, background: "#eefbf1", color: "#166534", fontSize: 13 }}>
          You are importing into an isolated template-based space.
        </div>
      ) : null}

      {canClassifySpace && !isDefaultSpace ? (
        <div style={{ padding: 12, borderRadius: 14, background: "#fff7e6", color: "#ad6800", fontSize: 13 }}>
          候选搜索链路在所有 ready current space 下都应可用；图结果丰富度仍取决于该 space 的图规模、关系密度与预算裁剪。
        </div>
      ) : null}

      {createOpen ? (
        <CreateSpaceInlinePanel
          open={createOpen}
          submitting={createSubmitting}
          error={createError}
          onClose={onCloseCreate}
          onSubmit={onCreateSpace}
        />
      ) : null}
    </section>
  );
}
