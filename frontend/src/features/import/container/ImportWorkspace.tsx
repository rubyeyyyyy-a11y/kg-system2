import { useEffect, useMemo, useRef, useState } from "react";

import type { CurrentSpaceResp, SpaceSummary } from "../../space/types/space";
import { useCreateSpace } from "../../space/hooks/useCreateSpace";
import { useCurrentSpace } from "../../space/hooks/useCurrentSpace";
import { BatchPanel } from "../components/BatchPanel";
import { ImportFlowPanels } from "../components/ImportFlowPanels";
import { ImportSpaceContextBar } from "../components/ImportSpaceContextBar";
import { ImportWorkspaceSidebar } from "../components/ImportWorkspaceSidebar";
import { JobPanel } from "../components/JobPanel";
import { useCleanupJobs } from "../hooks/useCleanupJobs";
import { useImportBatches } from "../hooks/useImportBatches";
import { useImportCleanupFlow } from "../hooks/useImportCleanupFlow";
import { useImportDraftFlow } from "../hooks/useImportDraftFlow";
import { useImportJobActions } from "../hooks/useImportJobActions";
import { useImportJobs } from "../hooks/useImportJobs";
import { useImportWorkspaceSelection } from "../hooks/useImportWorkspaceSelection";

type ImportWorkspaceProps = {
  onNotice: (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;
  spaces: SpaceSummary[];
  resolvedCurrent: CurrentSpaceResp | null;
  loadingSpaces: boolean;
  spacesError: string | null;
  refreshSpaces: () => Promise<void>;
  spaceSwitching: boolean;
  spaceSwitchPhase: string;
};

const SURFACE = "#f5efe4";
const VALIDATE_FIXED_NOTE =
  "Validate 现在按 target 使用各自 source 校验 identity/property/schema，不再共享第一份文件 columns。";
const INTEGRATION_FIXED_NOTE =
  "Import success does not automatically mean the data enters current search, discovery, or graph primary flows. Check integration level and integration warnings.";
const SPACE_SWITCH_NOTE =
  "Switching current space changes where draft validation, compiled plan freeze, job submission, metadata refresh, and entity ES sync will land.";

function formatTs(ts?: number | null) {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString();
}

function integrationLabel(level?: string | null) {
  if (level === "fully_integrated") return "fully integrated";
  if (level === "partially_integrated") return "partially integrated";
  if (level === "import_only") return "import-only";
  return "-";
}

export function ImportWorkspace({
  onNotice,
  spaces,
  resolvedCurrent,
  loadingSpaces,
  spacesError,
  refreshSpaces,
  spaceSwitching,
  spaceSwitchPhase,
}: ImportWorkspaceProps) {
  const { currentSpace, setCurrentSpace } = useCurrentSpace();
  const { createSpace, submitting: creatingSpace, error: createSpaceError } = useCreateSpace();
  const [createdBy, setCreatedBy] = useState("import_workspace");
  const [createPanelOpen, setCreatePanelOpen] = useState(false);
  const [spaceActionSummary, setSpaceActionSummary] = useState<{ title: string; message: string } | null>(null);
  const { jobs, loading: jobsLoading, reload: reloadJobs } = useImportJobs(true);
  const { batches, loading: batchesLoading, reload: reloadBatches } = useImportBatches(true);
  const { cleanupJobs, loading: cleanupJobsLoading, reload: reloadCleanupJobs } = useCleanupJobs(true);
  const selection = useImportWorkspaceSelection({ jobs, batches });
  const effectiveCurrentSpace = currentSpace || resolvedCurrent?.space_name || "";
  const selectedSpace = useMemo(
    () => spaces.find((item) => item.space_name === effectiveCurrentSpace) || null,
    [effectiveCurrentSpace, spaces]
  );
  const defaultSpaceName = useMemo(() => {
    const fromRegistry = spaces.find((item) => item.created_by === "system");
    if (fromRegistry) return fromRegistry.space_name;
    if (resolvedCurrent?.source === "default") return resolvedCurrent.space_name;
    return "";
  }, [resolvedCurrent, spaces]);
  const currentSpaceStatus = selectedSpace?.status || resolvedCurrent?.registry_status || "-";
  const currentTemplateType = selectedSpace?.template_type || "-";
  const currentIntegrationScope = selectedSpace?.integration_scope || "-";
  const importBlockedReason =
    currentSpaceStatus === "ready"
      ? ""
      : currentSpaceStatus === "provisioning"
        ? `当前 space ${effectiveCurrentSpace || "-"} 仍在 provisioning，暂时不能执行 import。`
        : currentSpaceStatus === "failed"
          ? `当前 space ${effectiveCurrentSpace || "-"} provisioning 失败，暂时不能执行 import。`
          : `当前 space ${effectiveCurrentSpace || "-"} 尚未 ready，暂时不能执行 import。`;
  const canRunImportFlow = !!effectiveCurrentSpace && currentSpaceStatus === "ready";
  const lastSpaceRef = useRef("");

  function ensureReady(actionLabel: string) {
    if (canRunImportFlow) return true;
    onNotice({ level: "warn", message: `${actionLabel}已阻止：${importBlockedReason}` });
    return false;
  }

  const draftFlow = useImportDraftFlow({ ensureReady, onNotice });
  const cleanupFlow = useImportCleanupFlow({
    batches,
    createdBy,
    onNotice,
    reloadBatches,
    reloadCleanupJobs,
    selectedBatchIds: selection.selectedBatchIds,
    setJobsTab: selection.setJobsTab,
  });
  const jobActions = useImportJobActions({
    createdBy,
    draft: draftFlow.draft,
    ensureReady,
    onNotice,
    onSelectJob: selection.setSelectedJobId,
    reloadBatches,
    reloadJobs,
  });

  useEffect(() => {
    if (!effectiveCurrentSpace) return;
    if (lastSpaceRef.current && lastSpaceRef.current !== effectiveCurrentSpace) {
      draftFlow.clearSpaceBoundState();
      selection.clearSpaceBoundState();
      cleanupFlow.clearCleanupPreview();
      onNotice({
        level: "info",
        message: `current space 已切换到 ${effectiveCurrentSpace}。请重新 preview / validate，再提交新的 import job。`,
      });
    }
    lastSpaceRef.current = effectiveCurrentSpace;
  }, [cleanupFlow, draftFlow, effectiveCurrentSpace, onNotice, selection]);

  function handleSelectSpace(spaceName: string) {
    if (!spaceName || spaceName === effectiveCurrentSpace) return;
    setCurrentSpace(spaceName);
    setCreatePanelOpen(false);
    setSpaceActionSummary({
      title: `Current space switched to ${spaceName}`,
      message: "Current-space switch coordinator is refreshing readiness and index status. Re-run preview and validate before submitting a new job.",
    });
  }

  async function handleCreateSpace(payload: {
    space_name: string;
    display_name: string;
    description: string;
    template_type: "entity_rel2_default";
    created_by: string;
  }) {
    const resp = await createSpace(payload, { autoSelect: true });
    setCreatePanelOpen(false);
    setSpaceActionSummary({
      title: `Space ${resp.space.space_name} is ready and selected`,
      message: "Next step: upload CSV in this Import Workspace. The current-space switch coordinator will refresh readiness and index status for the new space automatically.",
    });
    onNotice({
      level: "info",
      message: `space ${resp.space.space_name} 已创建并自动切换，下一步请上传 CSV。`,
    });
    return resp;
  }

  function handleRefresh() {
    void refreshSpaces();
    void reloadJobs();
    void reloadBatches();
    void reloadCleanupJobs();
  }

  return (
    <div
      style={{
        minHeight: "100dvh",
        overflow: "auto",
        background:
          "radial-gradient(circle at top left, rgba(202, 171, 114, 0.35), transparent 28%), linear-gradient(180deg, #f9f4ec 0%, #f0e7da 100%)",
        color: "#3d2d1f",
      }}
    >
      <div style={{ maxWidth: 1480, margin: "0 auto", padding: "28px 24px 48px", display: "grid", gap: 18 }}>
        <div style={{ position: "sticky", top: 12, zIndex: 20 }}>
          <ImportSpaceContextBar
            currentSpace={effectiveCurrentSpace}
            current={selectedSpace}
            resolvedCurrent={resolvedCurrent}
            spaces={spaces}
            loading={loadingSpaces}
            error={createSpaceError || spacesError}
            spaceSwitching={spaceSwitching}
            spaceSwitchPhase={spaceSwitchPhase}
            defaultSpaceName={defaultSpaceName}
            createOpen={createPanelOpen}
            createSubmitting={creatingSpace}
            createError={createSpaceError}
            actionSummary={spaceActionSummary}
            onDismissActionSummary={() => setSpaceActionSummary(null)}
            onSelectSpace={handleSelectSpace}
            onOpenCreate={() => setCreatePanelOpen(true)}
            onCloseCreate={() => setCreatePanelOpen(false)}
            onRefresh={handleRefresh}
            onCreateSpace={handleCreateSpace}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.35fr) minmax(360px, 460px)", gap: 18 }}>
          <ImportFlowPanels
            canRunImportFlow={canRunImportFlow}
            compiledPlan={draftFlow.compiledPlan}
            createdBy={createdBy}
            currentIntegrationScope={currentIntegrationScope}
            currentSpaceStatus={currentSpaceStatus}
            draft={draftFlow.draft}
            draftTotalBytes={draftFlow.draftTotalBytes}
            effectiveCurrentSpace={effectiveCurrentSpace}
            files={draftFlow.files}
            importBlockedReason={importBlockedReason}
            onAddTarget={draftFlow.addTarget}
            onCreatedByChange={setCreatedBy}
            onPreview={() => {
              void draftFlow.handlePreview();
            }}
            onRemoveTarget={draftFlow.removeTarget}
            onSaveDraft={() => {
              void draftFlow.handleSaveDraft();
            }}
            onSchemaPlan={() => {
              void draftFlow.handleSchemaPlan();
            }}
            onSubmitJob={() => {
              void jobActions.handleSubmitJob();
            }}
            onUpdateTarget={draftFlow.updateTarget}
            onUpload={(fileList) => {
              void draftFlow.handleUpload(fileList);
            }}
            onValidate={() => {
              void draftFlow.handleValidate();
            }}
            schemaObjects={draftFlow.schemaObjects}
            schemaPlan={draftFlow.schemaPlan}
            sources={draftFlow.sources}
            spaceSwitchNote={SPACE_SWITCH_NOTE}
            submittingJob={jobActions.submitting}
            surface={SURFACE}
            targets={draftFlow.targets}
            validateFixedNote={VALIDATE_FIXED_NOTE}
            integrationFixedNote={INTEGRATION_FIXED_NOTE}
            workspaceMode={draftFlow.workspaceMode}
            onWorkspaceModeChange={draftFlow.setWorkspaceMode}
          />

          <ImportWorkspaceSidebar
            compiledPlan={draftFlow.compiledPlan}
            currentTemplateType={currentTemplateType}
            draft={draftFlow.draft}
            draftTotalBytes={draftFlow.draftTotalBytes}
            effectiveCurrentSpace={effectiveCurrentSpace}
            integrationWarnings={draftFlow.integrationWarnings}
            jobLogs={selection.jobLogs}
            preview={draftFlow.preview}
            schemaWarnings={draftFlow.schemaWarnings}
            selectedJobId={selection.selectedJobId}
            sources={draftFlow.sources}
            targetsCount={draftFlow.targets.length}
            workspaceMode={draftFlow.workspaceMode}
            formatTs={formatTs}
            integrationLabel={integrationLabel}
          />
        </div>

        <section style={{ borderRadius: 24, background: "#fffaf1", padding: 20, border: "1px solid rgba(76, 56, 36, 0.12)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <strong>4. Operations</strong>
              <button
                data-testid="import-tab-jobs"
                onClick={() => selection.setJobsTab("jobs")}
                style={{ background: selection.jobsTab === "jobs" ? "#fff3dc" : "#fff" }}
              >
                Jobs
              </button>
              <button
                data-testid="import-tab-batches"
                onClick={() => selection.setJobsTab("batches")}
                style={{ background: selection.jobsTab === "batches" ? "#fff3dc" : "#fff" }}
              >
                Batches
              </button>
            </div>
            <div style={{ fontSize: 12, color: "#7d6b57" }}>
              {selection.jobsTab === "jobs"
                ? `${jobsLoading ? "jobs loading..." : `jobs=${jobs.length}`}`
                : `${batchesLoading ? "batches loading..." : `batches=${batches.length}`} | cleanup_jobs=${cleanupJobs.length}`}{" "}
              | space={effectiveCurrentSpace || "-"}
            </div>
          </div>
          {selection.jobsTab === "jobs" ? (
            <JobPanel
              jobs={jobs}
              selectedJobId={selection.selectedJobId}
              onSelect={selection.setSelectedJobId}
              onCancel={(jobId) => {
                void jobActions.handleCancelJob(jobId);
              }}
              onDownloadFailedRows={(jobId) => {
                void jobActions.handleDownloadFailedRows(jobId);
              }}
              onDownloadArtifact={(jobId, artifactName) => {
                void jobActions.handleDownloadArtifact(jobId, artifactName);
              }}
            />
          ) : (
            <BatchPanel
              batches={batches}
              selectedBatchId={selection.selectedBatchId}
              selectedBatchItems={selection.selectedBatchItems}
              selectedBatchIds={selection.selectedBatchIds}
              cleanupJobs={cleanupJobs}
              cleanupLoading={cleanupJobsLoading || cleanupFlow.submitting}
              cleanupPlanPreview={cleanupFlow.cleanupPlanPreview}
              cleanupPlanLoading={cleanupFlow.previewLoading}
              onSelectBatch={selection.setSelectedBatchId}
              onToggleBatch={selection.toggleBatchSelection}
              onPreviewCleanupPlan={(scope) => {
                void cleanupFlow.handlePreviewCleanup(scope);
              }}
              onConfirmCleanup={(scope) => {
                void cleanupFlow.handleConfirmCleanup(scope);
              }}
              onQuickCleanup={(scope) => {
                void cleanupFlow.handleQuickCleanup(scope);
              }}
              onDownloadCleanupArtifact={(cleanupJobId, artifactName) => {
                void cleanupFlow.handleDownloadCleanupArtifact(cleanupJobId, artifactName);
              }}
            />
          )}
        </section>
      </div>
    </div>
  );
}
