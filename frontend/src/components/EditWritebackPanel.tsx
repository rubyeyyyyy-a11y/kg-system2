import { useCallback, useEffect, useMemo, useState } from "react";

import { edgeDetail as edgeDetailApi, editableFields as editableFieldsApi, nodeDetail as nodeDetailApi } from "../api/kg";
import { DynamicEditForm } from "../features/edit/components/DynamicEditForm";
import { useEditDraft } from "../features/edit/hooks/useEditDraft";
import { useEditLayout } from "../features/edit/hooks/useEditLayout";
import { normalizeEdgeDetail, normalizeNodeDetail } from "../features/detail/utils/normalizeDetail";
import type {
  EdgeDetailResp,
  EdgePatchResp,
  EditableFieldSpec,
  EditableFieldsResp,
  NodeDetailResp,
  NodePatchResp,
  Sel,
} from "../types/kg";

const UPDATED_BY_KEY = "kg.updated_by";
const EDGE_TYPE_DEFAULT = "REL2";
const EMPTY_EDITABLE_FIELDS: EditableFieldSpec[] = [];

type EdgeIdentity = { edge_type: string; src: number; dst: number; rank: string };

type EditWritebackPanelProps = {
  mode: "edit" | "direct";
  sel: Sel;
  nodeDetail: NodeDetailResp | null;
  edgeDetail: EdgeDetailResp | null;
  detailLoading: boolean;
  onReloadNodeDetail: (vid: number) => Promise<void>;
  onReloadEdgeDetail: (identity: EdgeIdentity) => Promise<void>;
  onSaveNodeEdit: (
    vid: number,
    setFields: Record<string, string>,
    expectedVersion: number,
    updatedBy: string
  ) => Promise<NodePatchResp>;
  onSaveEdgeEdit: (
    identity: EdgeIdentity,
    setFields: Record<string, string>,
    expectedVersion: number,
    updatedBy: string
  ) => Promise<EdgePatchResp>;
};

function parseHttpError(err: unknown): { status: number | null; message: string } {
  const raw = err instanceof Error ? err.message : String(err);
  const m = raw.match(/^HTTP\s+(\d+):\s*([\s\S]*)$/);
  if (!m) return { status: null, message: raw };
  const status = Number(m[1]);
  const body = (m[2] || "").trim();
  try {
    const json = JSON.parse(body);
    if (typeof json?.detail === "string") return { status, message: json.detail };
    if (json?.detail?.message) {
      const field = json?.detail?.field ? `[${String(json.detail.field)}] ` : "";
      return { status, message: `${field}${String(json.detail.message)}` };
    }
    if (json?.message) return { status, message: String(json.message) };
    return { status, message: body || raw };
  } catch {
    return { status, message: body || raw };
  }
}

function buildPatchSet(
  sections: ReturnType<typeof useEditLayout>,
  draft: Record<string, string>,
): Record<string, string> {
  const out: Record<string, string> = {};
  sections.forEach((section) => {
    section.fields.forEach((field) => {
      if (field.readOnly) return;
      const nextValue = draft[field.name] || "";
      if (nextValue === field.value) return;
      out[field.name] = nextValue;
    });
  });
  return out;
}

function EditorBlock({
  title,
  subtitle,
  sections,
  draft,
  disabled,
  onChange,
  onReload,
  onSave,
  saveLabel,
  reloadLabel = "重新加载详情",
  reloadTestId,
  saveTestId,
}: {
  title: string;
  subtitle: string;
  sections: ReturnType<typeof useEditLayout>;
  draft: Record<string, string>;
  disabled?: boolean;
  onChange: (fieldName: string, next: string) => void;
  onReload?: () => void;
  onSave: () => void;
  saveLabel: string;
  reloadLabel?: string;
  reloadTestId?: string;
  saveTestId?: string;
}) {
  return (
    <div style={{ display: "grid", gap: 10 }}>
      <div style={{ fontSize: 12, color: "#666" }}>{title}</div>
      <div style={{ fontSize: 12, color: "#666" }}>{subtitle}</div>
      <DynamicEditForm
        sections={sections}
        draft={draft}
        disabled={disabled}
        onChange={onChange}
      />
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {onReload ? (
          <button data-testid={reloadTestId} onClick={onReload} disabled={disabled} style={{ padding: "6px 10px" }}>
            {reloadLabel}
          </button>
        ) : null}
        <button data-testid={saveTestId} onClick={onSave} disabled={disabled} style={{ padding: "6px 10px" }}>
          {saveLabel}
        </button>
      </div>
    </div>
  );
}

export function EditWritebackPanel({
  mode,
  sel,
  nodeDetail,
  edgeDetail,
  detailLoading,
  onReloadNodeDetail,
  onReloadEdgeDetail,
  onSaveNodeEdit,
  onSaveEdgeEdit,
}: EditWritebackPanelProps) {
  const [schema, setSchema] = useState<EditableFieldsResp | null>(null);
  const [schemaError, setSchemaError] = useState<string | null>(null);

  const [defaultUpdatedBy, setDefaultUpdatedBy] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(UPDATED_BY_KEY) || "";
  });
  const [saveUpdatedBy, setSaveUpdatedBy] = useState<string>(() => {
    if (typeof window === "undefined") return "";
    return window.localStorage.getItem(UPDATED_BY_KEY) || "";
  });
  const [setAsDefault, setSetAsDefault] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [directNodeVid, setDirectNodeVid] = useState("");
  const [directNodeDetail, setDirectNodeDetail] = useState<NodeDetailResp | null>(null);
  const [directNodeLoading, setDirectNodeLoading] = useState(false);

  const [directEdgeSrc, setDirectEdgeSrc] = useState("");
  const [directEdgeDst, setDirectEdgeDst] = useState("");
  const [directEdgeRank, setDirectEdgeRank] = useState("");
  const [directEdgeDetail, setDirectEdgeDetail] = useState<EdgeDetailResp | null>(null);
  const [directEdgeLoading, setDirectEdgeLoading] = useState(false);

  const nodeMetadataFields = useMemo(() => schema?.entity?.fields ?? EMPTY_EDITABLE_FIELDS, [schema]);
  const edgeMetadataFields = useMemo(() => schema?.edge?.fields ?? EMPTY_EDITABLE_FIELDS, [schema]);

  useEffect(() => {
    let cancelled = false;
    async function loadSchema() {
      try {
        const resp = await editableFieldsApi();
        if (cancelled) return;
        setSchema(resp);
      } catch (e: unknown) {
        if (cancelled) return;
        setSchemaError(parseHttpError(e).message);
      }
    }
    void loadSchema();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(UPDATED_BY_KEY, defaultUpdatedBy);
  }, [defaultUpdatedBy]);

  useEffect(() => {
    setSaveUpdatedBy(defaultUpdatedBy);
  }, [defaultUpdatedBy]);

  const selectedNodeNormalized = useMemo(
    () => normalizeNodeDetail({ detail: sel.kind === "node" ? nodeDetail : null, selectedNodeBrief: null, hopLevel: null }),
    [nodeDetail, sel.kind],
  );
  const selectedEdgeNormalized = useMemo(
    () =>
      normalizeEdgeDetail({
        detail: sel.kind === "edge" ? edgeDetail : null,
        selection: sel.kind === "edge" ? sel : null,
      }),
    [edgeDetail, sel],
  );
  const directNodeNormalized = useMemo(
    () => normalizeNodeDetail({ detail: directNodeDetail, selectedNodeBrief: null, hopLevel: null }),
    [directNodeDetail],
  );
  const directEdgeNormalized = useMemo(
    () =>
      normalizeEdgeDetail({
        detail: directEdgeDetail,
        selection:
          directEdgeDetail == null
            ? null
            : {
                kind: "edge",
                src: directEdgeDetail.src,
                dst: directEdgeDetail.dst,
                rank: directEdgeDetail.rank,
                edge_type: directEdgeDetail.edge_type,
                relation: directEdgeDetail.relation || "",
                source: "external_detail",
                source_db: directEdgeDetail.source_db,
              },
      }),
    [directEdgeDetail],
  );

  const selectedNodeSections = useEditLayout({ kind: "node", detail: selectedNodeNormalized, metadataFields: nodeMetadataFields });
  const selectedEdgeSections = useEditLayout({ kind: "edge", detail: selectedEdgeNormalized, metadataFields: edgeMetadataFields });
  const directNodeSections = useEditLayout({ kind: "node", detail: directNodeNormalized, metadataFields: nodeMetadataFields });
  const directEdgeSections = useEditLayout({ kind: "edge", detail: directEdgeNormalized, metadataFields: edgeMetadataFields });

  const { draft: selectedNodeDraft, setDraft: setSelectedNodeDraft } = useEditDraft(
    sel.kind === "node" ? `node:${sel.vid}:${nodeDetail?.version ?? "none"}` : "node:none",
    selectedNodeSections,
  );
  const { draft: selectedEdgeDraft, setDraft: setSelectedEdgeDraft } = useEditDraft(
    sel.kind === "edge" ? `edge:${sel.src}:${sel.dst}:${sel.rank}:${edgeDetail?.version ?? "none"}` : "edge:none",
    selectedEdgeSections,
  );
  const { draft: directNodeDraft, setDraft: setDirectNodeDraft } = useEditDraft(
    directNodeDetail ? `direct-node:${directNodeDetail.vid}:${directNodeDetail.version}` : "direct-node:none",
    directNodeSections,
  );
  const { draft: directEdgeDraft, setDraft: setDirectEdgeDraft } = useEditDraft(
    directEdgeDetail
      ? `direct-edge:${directEdgeDetail.src}:${directEdgeDetail.dst}:${directEdgeDetail.rank}:${directEdgeDetail.version}`
      : "direct-edge:none",
    directEdgeSections,
  );

  const selectedNodeVersion = sel.kind === "node" ? nodeDetail?.version ?? null : null;
  const selectedEdgeVersion = sel.kind === "edge" ? edgeDetail?.version ?? null : null;
  const actorTrimmed = (saveUpdatedBy || "").trim();
  const actorInvalid = actorTrimmed.length === 0 || actorTrimmed.length > 64;
  const actorError =
    actorTrimmed.length === 0 ? "updated_by 必填" : actorTrimmed.length > 64 ? "updated_by 不能超过 64 个字符" : "";

  const finalizeActor = useCallback((): string => {
    const actor = actorTrimmed;
    if (!actor) throw new Error("updated_by 必填");
    if (actor.length > 64) throw new Error("updated_by 不能超过 64 个字符");
    if (setAsDefault) setDefaultUpdatedBy(actor);
    return actor;
  }, [actorTrimmed, setAsDefault]);

  const saveSelectedNode = useCallback(async () => {
    if (sel.kind !== "node" || selectedNodeVersion == null) return;
    const setFields = buildPatchSet(selectedNodeSections, selectedNodeDraft);
    if (Object.keys(setFields).length === 0) {
      setNotice("没有可保存的变更");
      setError(null);
      return;
    }
    setSaveLoading(true);
    setError(null);
    setNotice(null);
    try {
      const actor = finalizeActor();
      const resp = await onSaveNodeEdit(sel.vid, setFields, selectedNodeVersion, actor);
      setNotice(`保存成功，version=${resp.version}`);
      await onReloadNodeDetail(sel.vid);
    } catch (e: unknown) {
      const parsed = parseHttpError(e);
      setError(parsed.status === 409 ? `版本冲突：${parsed.message}` : parsed.message);
    } finally {
      setSaveLoading(false);
    }
  }, [
    finalizeActor,
    onReloadNodeDetail,
    onSaveNodeEdit,
    sel,
    selectedNodeDraft,
    selectedNodeSections,
    selectedNodeVersion,
  ]);

  const saveSelectedEdge = useCallback(async () => {
    if (sel.kind !== "edge" || selectedEdgeVersion == null) return;
    const setFields = buildPatchSet(selectedEdgeSections, selectedEdgeDraft);
    if (Object.keys(setFields).length === 0) {
      setNotice("没有可保存的变更");
      setError(null);
      return;
    }
    setSaveLoading(true);
    setError(null);
    setNotice(null);
    try {
      const actor = finalizeActor();
      const identity: EdgeIdentity = {
        edge_type: sel.edge_type || EDGE_TYPE_DEFAULT,
        src: sel.src,
        dst: sel.dst,
        rank: sel.rank,
      };
      const resp = await onSaveEdgeEdit(identity, setFields, selectedEdgeVersion, actor);
      setNotice(`保存成功，version=${resp.version}`);
      await onReloadEdgeDetail(identity);
    } catch (e: unknown) {
      const parsed = parseHttpError(e);
      setError(parsed.status === 409 ? `版本冲突：${parsed.message}` : parsed.message);
    } finally {
      setSaveLoading(false);
    }
  }, [
    finalizeActor,
    onReloadEdgeDetail,
    onSaveEdgeEdit,
    sel,
    selectedEdgeDraft,
    selectedEdgeSections,
    selectedEdgeVersion,
  ]);

  async function loadDirectNode() {
    const vid = Number(directNodeVid);
    if (!Number.isFinite(vid)) {
      setError("vid 必须是数字");
      return;
    }
    setDirectNodeLoading(true);
    setError(null);
    try {
      const detail = await nodeDetailApi(vid);
      setDirectNodeDetail(detail);
    } catch (e: unknown) {
      setError(parseHttpError(e).message);
    } finally {
      setDirectNodeLoading(false);
    }
  }

  async function loadDirectEdge() {
    const src = Number(directEdgeSrc);
    const dst = Number(directEdgeDst);
    const rank = String(directEdgeRank || "").trim();
    if (!Number.isFinite(src) || !Number.isFinite(dst) || !rank) {
      setError("src/dst/rank 必填且格式正确");
      return;
    }
    setDirectEdgeLoading(true);
    setError(null);
    try {
      const detail = await edgeDetailApi({
        edge_type: EDGE_TYPE_DEFAULT,
        src,
        dst,
        rank,
      });
      setDirectEdgeDetail(detail);
    } catch (e: unknown) {
      setError(parseHttpError(e).message);
    } finally {
      setDirectEdgeLoading(false);
    }
  }

  async function saveDirectNode() {
    if (!directNodeDetail) return;
    const setFields = buildPatchSet(directNodeSections, directNodeDraft);
    if (Object.keys(setFields).length === 0) {
      setNotice("没有可保存的变更");
      setError(null);
      return;
    }
    setSaveLoading(true);
    setError(null);
    setNotice(null);
    try {
      const actor = finalizeActor();
      const resp = await onSaveNodeEdit(directNodeDetail.vid, setFields, directNodeDetail.version, actor);
      setNotice(`节点保存成功，version=${resp.version}`);
      const refreshed = await nodeDetailApi(directNodeDetail.vid);
      setDirectNodeDetail(refreshed);
    } catch (e: unknown) {
      const parsed = parseHttpError(e);
      setError(parsed.status === 409 ? `版本冲突：${parsed.message}` : parsed.message);
    } finally {
      setSaveLoading(false);
    }
  }

  async function saveDirectEdge() {
    if (!directEdgeDetail) return;
    const setFields = buildPatchSet(directEdgeSections, directEdgeDraft);
    if (Object.keys(setFields).length === 0) {
      setNotice("没有可保存的变更");
      setError(null);
      return;
    }
    setSaveLoading(true);
    setError(null);
    setNotice(null);
    try {
      const actor = finalizeActor();
      const identity: EdgeIdentity = {
        edge_type: directEdgeDetail.edge_type || EDGE_TYPE_DEFAULT,
        src: directEdgeDetail.src,
        dst: directEdgeDetail.dst,
        rank: directEdgeDetail.rank,
      };
      const resp = await onSaveEdgeEdit(identity, setFields, directEdgeDetail.version, actor);
      setNotice(`边保存成功，version=${resp.version}`);
      const refreshed = await edgeDetailApi(identity);
      setDirectEdgeDetail(refreshed);
    } catch (e: unknown) {
      const parsed = parseHttpError(e);
      setError(parsed.status === 409 ? `版本冲突：${parsed.message}` : parsed.message);
    } finally {
      setSaveLoading(false);
    }
  }

  const renderActor = (
    <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 10, display: "grid", gap: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 13 }}>操作者（updated_by）</div>
      <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
        <span>全局默认（localStorage: {UPDATED_BY_KEY}）</span>
        <input
          data-testid="edit-default-updated-by-input"
          value={defaultUpdatedBy}
          onChange={(e) => setDefaultUpdatedBy(e.target.value)}
          style={{ padding: 8 }}
        />
      </label>
      <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
        <span>本次保存（可临时覆盖）</span>
        <input
          data-testid="edit-save-updated-by-input"
          value={saveUpdatedBy}
          onChange={(e) => setSaveUpdatedBy(e.target.value)}
          style={{ padding: 8 }}
        />
      </label>
      {actorError ? <div style={{ fontSize: 12, color: "#d4380d" }}>{actorError}</div> : null}
      <label style={{ fontSize: 12 }}>
        <input type="checkbox" checked={setAsDefault} onChange={(e) => setSetAsDefault(e.target.checked)} /> 保存时设为默认
      </label>
      {schemaError ? <div style={{ fontSize: 12, color: "#d46b08" }}>metadata 字段补充加载失败：{schemaError}</div> : null}
    </div>
  );

  const renderSelectedEditor = useMemo(() => {
    if (sel.kind === "none") return <div style={{ fontSize: 12, color: "#666" }}>请先选中节点或边再编辑。</div>;

    if (sel.kind === "node") {
      const canSave = !saveLoading && !detailLoading && nodeDetail != null && selectedNodeVersion != null && !actorInvalid;
      return (
        <EditorBlock
          title={`Node vid=${sel.vid}`}
          subtitle={`current_version=${selectedNodeVersion ?? "-"} | updated_by=${nodeDetail?.updated_by || "-"}`}
          sections={selectedNodeSections}
          draft={selectedNodeDraft}
          disabled={!canSave}
          onChange={(fieldName, next) => setSelectedNodeDraft((prev) => ({ ...prev, [fieldName]: next }))}
          onReload={() => void onReloadNodeDetail(sel.vid)}
          onSave={() => void saveSelectedNode()}
          reloadTestId="selected-node-reload-button"
          saveTestId="selected-node-save-button"
          saveLabel={saveLoading ? "保存中…" : "保存节点"}
        />
      );
    }

    const canSave = !saveLoading && !detailLoading && edgeDetail != null && selectedEdgeVersion != null && !actorInvalid;
    const identity: EdgeIdentity = {
      edge_type: sel.edge_type || EDGE_TYPE_DEFAULT,
      src: sel.src,
      dst: sel.dst,
      rank: sel.rank,
    };
    return (
      <EditorBlock
        title={`Edge ${identity.edge_type} ${identity.src}->${identity.dst}@${identity.rank}`}
        subtitle={`current_version=${selectedEdgeVersion ?? "-"} | updated_by=${edgeDetail?.updated_by || "-"}`}
        sections={selectedEdgeSections}
        draft={selectedEdgeDraft}
        disabled={!canSave}
        onChange={(fieldName, next) => setSelectedEdgeDraft((prev) => ({ ...prev, [fieldName]: next }))}
        onReload={() => void onReloadEdgeDetail(identity)}
        onSave={() => void saveSelectedEdge()}
        reloadTestId="selected-edge-reload-button"
        saveTestId="selected-edge-save-button"
        saveLabel={saveLoading ? "保存中…" : "保存边"}
      />
    );
  }, [
    actorInvalid,
    detailLoading,
    edgeDetail,
    nodeDetail,
    onReloadEdgeDetail,
    onReloadNodeDetail,
    saveLoading,
    saveSelectedEdge,
    saveSelectedNode,
    sel,
    selectedEdgeDraft,
    selectedEdgeSections,
    selectedEdgeVersion,
    selectedNodeDraft,
    selectedNodeSections,
    selectedNodeVersion,
    setSelectedEdgeDraft,
    setSelectedNodeDraft,
  ]);

  const renderDirectEditor = (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 10, display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600 }}>直接编辑 Node</div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            data-testid="direct-node-vid-input"
            value={directNodeVid}
            onChange={(e) => setDirectNodeVid(e.target.value)}
            placeholder="vid"
            style={{ padding: 8, flex: 1 }}
          />
          <button data-testid="direct-node-load-button" onClick={() => void loadDirectNode()} disabled={directNodeLoading} style={{ padding: "8px 12px" }}>
            {directNodeLoading ? "加载中…" : "加载"}
          </button>
        </div>
        {directNodeDetail ? (
          <EditorBlock
            title={`Node vid=${directNodeDetail.vid}`}
            subtitle={`current_version=${directNodeDetail.version ?? "-"} | updated_by=${directNodeDetail.updated_by || "-"}`}
            sections={directNodeSections}
            draft={directNodeDraft}
            disabled={saveLoading || actorInvalid}
            onChange={(fieldName, next) => setDirectNodeDraft((prev) => ({ ...prev, [fieldName]: next }))}
            onSave={() => void saveDirectNode()}
            saveTestId="direct-node-save-button"
            saveLabel={saveLoading ? "保存中…" : "保存节点"}
          />
        ) : null}
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 10, display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600 }}>直接编辑 Edge</div>
        <div style={{ display: "grid", gap: 8 }}>
          <input data-testid="direct-edge-src-input" value={directEdgeSrc} onChange={(e) => setDirectEdgeSrc(e.target.value)} placeholder="src" style={{ padding: 8 }} />
          <input data-testid="direct-edge-dst-input" value={directEdgeDst} onChange={(e) => setDirectEdgeDst(e.target.value)} placeholder="dst" style={{ padding: 8 }} />
          <input data-testid="direct-edge-rank-input" value={directEdgeRank} onChange={(e) => setDirectEdgeRank(e.target.value)} placeholder="rank" style={{ padding: 8 }} />
          <button data-testid="direct-edge-load-button" onClick={() => void loadDirectEdge()} disabled={directEdgeLoading} style={{ padding: "8px 12px" }}>
            {directEdgeLoading ? "加载中…" : "加载"}
          </button>
        </div>
        {directEdgeDetail ? (
          <EditorBlock
            title={`Edge ${directEdgeDetail.edge_type} ${directEdgeDetail.src}->${directEdgeDetail.dst}@${directEdgeDetail.rank}`}
            subtitle={`current_version=${directEdgeDetail.version ?? "-"} | updated_by=${directEdgeDetail.updated_by || "-"}`}
            sections={directEdgeSections}
            draft={directEdgeDraft}
            disabled={saveLoading || actorInvalid}
            onChange={(fieldName, next) => setDirectEdgeDraft((prev) => ({ ...prev, [fieldName]: next }))}
            onSave={() => void saveDirectEdge()}
            saveTestId="direct-edge-save-button"
            saveLabel={saveLoading ? "保存中…" : "保存边"}
          />
        ) : null}
      </div>
    </div>
  );

  return (
    <div style={{ display: "grid", gap: 10 }}>
      {renderActor}
      {notice ? <div style={{ fontSize: 12, color: "#389e0d" }}>{notice}</div> : null}
      {error ? <div style={{ fontSize: 12, color: "#d4380d" }}>{error}</div> : null}
      {mode === "edit" ? renderSelectedEditor : renderDirectEditor}
    </div>
  );
}
