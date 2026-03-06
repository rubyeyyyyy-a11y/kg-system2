import { useCallback, useEffect, useMemo, useState } from "react";

import { edgeDetail as edgeDetailApi, editableFields as editableFieldsApi, nodeDetail as nodeDetailApi } from "../api/kg";
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

function FormField({
  spec,
  value,
  disabled,
  onChange,
}: {
  spec: EditableFieldSpec;
  value: string;
  disabled?: boolean;
  onChange: (next: string) => void;
}) {
  const counterText = `${value.length}/${spec.maxLen}`;
  return (
    <label style={{ display: "grid", gap: 4, fontSize: 12, color: "#444" }}>
      <span>
        {spec.name} {spec.required ? "*" : ""} <span style={{ color: "#888" }}>({counterText})</span>
      </span>
      {spec.multiline ? (
        <textarea
          value={value}
          disabled={disabled}
          rows={4}
          maxLength={spec.maxLen}
          onChange={(e) => onChange(e.target.value)}
          style={{ width: "100%", padding: 8, resize: "vertical" }}
        />
      ) : (
        <input
          value={value}
          disabled={disabled}
          maxLength={spec.maxLen}
          onChange={(e) => onChange(e.target.value)}
          style={{ width: "100%", padding: 8 }}
        />
      )}
    </label>
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
  const [schemaLoading, setSchemaLoading] = useState(false);
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

  const [selectedNodeSet, setSelectedNodeSet] = useState<Record<string, string>>({});
  const [selectedEdgeSet, setSelectedEdgeSet] = useState<Record<string, string>>({});

  const [directNodeVid, setDirectNodeVid] = useState("");
  const [directNodeDetail, setDirectNodeDetail] = useState<NodeDetailResp | null>(null);
  const [directNodeSet, setDirectNodeSet] = useState<Record<string, string>>({});
  const [directNodeLoading, setDirectNodeLoading] = useState(false);

  const [directEdgeSrc, setDirectEdgeSrc] = useState("");
  const [directEdgeDst, setDirectEdgeDst] = useState("");
  const [directEdgeRank, setDirectEdgeRank] = useState("");
  const [directEdgeDetail, setDirectEdgeDetail] = useState<EdgeDetailResp | null>(null);
  const [directEdgeSet, setDirectEdgeSet] = useState<Record<string, string>>({});
  const [directEdgeLoading, setDirectEdgeLoading] = useState(false);

  const nodeSpecs = useMemo(() => schema?.entity?.fields ?? EMPTY_EDITABLE_FIELDS, [schema]);
  const edgeSpecs = useMemo(() => schema?.edge?.fields ?? EMPTY_EDITABLE_FIELDS, [schema]);

  useEffect(() => {
    let cancelled = false;
    async function loadSchema() {
      setSchemaLoading(true);
      setSchemaError(null);
      try {
        const resp = await editableFieldsApi();
        if (cancelled) return;
        setSchema(resp);
      } catch (e: unknown) {
        if (cancelled) return;
        const parsed = parseHttpError(e);
        setSchemaError(parsed.message);
      } finally {
        if (!cancelled) setSchemaLoading(false);
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

  useEffect(() => {
    if (sel.kind !== "node" || !nodeDetail) {
      setSelectedNodeSet({});
      return;
    }
    const next: Record<string, string> = {};
    for (const spec of nodeSpecs) {
      const raw = (nodeDetail as Record<string, unknown>)[spec.name];
      next[spec.name] = typeof raw === "string" ? raw : "";
    }
    setSelectedNodeSet(next);
  }, [sel, nodeDetail, nodeSpecs]);

  useEffect(() => {
    if (sel.kind !== "edge" || !edgeDetail) {
      setSelectedEdgeSet({});
      return;
    }
    const next: Record<string, string> = {};
    for (const spec of edgeSpecs) {
      const raw = (edgeDetail as Record<string, unknown>)[spec.name === "source" ? "source_db" : spec.name];
      next[spec.name] = typeof raw === "string" ? raw : "";
    }
    setSelectedEdgeSet(next);
  }, [sel, edgeDetail, edgeSpecs]);

  const selectedNodeVersion = sel.kind === "node" ? nodeDetail?.version ?? null : null;
  const selectedEdgeVersion = sel.kind === "edge" ? edgeDetail?.version ?? null : null;
  const actorTrimmed = (saveUpdatedBy || "").trim();
  const actorInvalid = actorTrimmed.length === 0 || actorTrimmed.length > 64;
  const actorError = actorTrimmed.length === 0 ? "updated_by 必填" : actorTrimmed.length > 64 ? "updated_by 不能超过 64 个字符" : "";

  const finalizeActor = useCallback((): string => {
    const actor = actorTrimmed;
    if (!actor) throw new Error("updated_by 必填");
    if (actor.length > 64) throw new Error("updated_by 不能超过 64 个字符");
    if (setAsDefault) setDefaultUpdatedBy(actor);
    return actor;
  }, [actorTrimmed, setAsDefault]);

  const saveSelectedNode = useCallback(async () => {
    if (sel.kind !== "node" || selectedNodeVersion == null) return;
    setSaveLoading(true);
    setError(null);
    setNotice(null);
    try {
      const actor = finalizeActor();
      const resp = await onSaveNodeEdit(sel.vid, selectedNodeSet, selectedNodeVersion, actor);
      setNotice(`保存成功，version=${resp.version}`);
      await onReloadNodeDetail(sel.vid);
    } catch (e: unknown) {
      const parsed = parseHttpError(e);
      setError(parsed.status === 409 ? `版本冲突：${parsed.message}` : parsed.message);
    } finally {
      setSaveLoading(false);
    }
  }, [finalizeActor, onReloadNodeDetail, onSaveNodeEdit, sel, selectedNodeSet, selectedNodeVersion]);

  const saveSelectedEdge = useCallback(async () => {
    if (sel.kind !== "edge" || selectedEdgeVersion == null) return;
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
      const resp = await onSaveEdgeEdit(identity, selectedEdgeSet, selectedEdgeVersion, actor);
      setNotice(`保存成功，version=${resp.version}`);
      await onReloadEdgeDetail(identity);
    } catch (e: unknown) {
      const parsed = parseHttpError(e);
      setError(parsed.status === 409 ? `版本冲突：${parsed.message}` : parsed.message);
    } finally {
      setSaveLoading(false);
    }
  }, [finalizeActor, onReloadEdgeDetail, onSaveEdgeEdit, sel, selectedEdgeSet, selectedEdgeVersion]);

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
      const next: Record<string, string> = {};
      for (const spec of nodeSpecs) {
        const raw = (detail as Record<string, unknown>)[spec.name];
        next[spec.name] = typeof raw === "string" ? raw : "";
      }
      setDirectNodeSet(next);
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
      const next: Record<string, string> = {};
      for (const spec of edgeSpecs) {
        const raw = (detail as Record<string, unknown>)[spec.name === "source" ? "source_db" : spec.name];
        next[spec.name] = typeof raw === "string" ? raw : "";
      }
      setDirectEdgeSet(next);
    } catch (e: unknown) {
      setError(parseHttpError(e).message);
    } finally {
      setDirectEdgeLoading(false);
    }
  }

  async function saveDirectNode() {
    if (!directNodeDetail) return;
    setSaveLoading(true);
    setError(null);
    setNotice(null);
    try {
      const actor = finalizeActor();
      const resp = await onSaveNodeEdit(directNodeDetail.vid, directNodeSet, directNodeDetail.version, actor);
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
      const resp = await onSaveEdgeEdit(identity, directEdgeSet, directEdgeDetail.version, actor);
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
        <input value={defaultUpdatedBy} onChange={(e) => setDefaultUpdatedBy(e.target.value)} style={{ padding: 8 }} />
      </label>
      <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
        <span>本次保存（可临时覆盖）</span>
        <input value={saveUpdatedBy} onChange={(e) => setSaveUpdatedBy(e.target.value)} style={{ padding: 8 }} />
      </label>
      {actorError ? <div style={{ fontSize: 12, color: "#d4380d" }}>{actorError}</div> : null}
      <label style={{ fontSize: 12 }}>
        <input type="checkbox" checked={setAsDefault} onChange={(e) => setSetAsDefault(e.target.checked)} /> 保存时设为默认
      </label>
    </div>
  );

  const renderSelectedEditor = useMemo(() => {
    if (sel.kind === "none") return <div style={{ fontSize: 12, color: "#666" }}>请先选中节点或边再编辑。</div>;
    if (schemaLoading) return <div style={{ fontSize: 12, color: "#666" }}>加载可编辑字段中…</div>;
    if (schemaError) return <div style={{ fontSize: 12, color: "#d4380d" }}>字段 schema 加载失败：{schemaError}</div>;

    if (sel.kind === "node") {
      const canSave = !saveLoading && !detailLoading && nodeDetail != null && selectedNodeVersion != null && !actorInvalid;
      return (
        <div style={{ display: "grid", gap: 10 }}>
          <div style={{ fontSize: 12, color: "#666" }}>
            Node vid={sel.vid} | current_version={selectedNodeVersion ?? "-"} | updated_by={nodeDetail?.updated_by || "-"}
          </div>
          {nodeSpecs.map((spec) => (
            <FormField
              key={spec.name}
              spec={spec}
              value={selectedNodeSet[spec.name] || ""}
              disabled={!canSave}
              onChange={(next) => setSelectedNodeSet((prev) => ({ ...prev, [spec.name]: next }))}
            />
          ))}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => void onReloadNodeDetail(sel.vid)} disabled={detailLoading} style={{ padding: "6px 10px" }}>
              重新加载详情
            </button>
            <button onClick={() => void saveSelectedNode()} disabled={!canSave} style={{ padding: "6px 10px" }}>
              {saveLoading ? "保存中…" : "保存节点"}
            </button>
          </div>
        </div>
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
      <div style={{ display: "grid", gap: 10 }}>
        <div style={{ fontSize: 12, color: "#666" }}>
          Edge {identity.edge_type} {identity.src}{"->"}{identity.dst}@{identity.rank} | current_version=
          {selectedEdgeVersion ?? "-"} | updated_by={edgeDetail?.updated_by || "-"}
        </div>
        {edgeSpecs.map((spec) => (
          <FormField
            key={spec.name}
            spec={spec}
            value={selectedEdgeSet[spec.name] || ""}
            disabled={!canSave}
            onChange={(next) => setSelectedEdgeSet((prev) => ({ ...prev, [spec.name]: next }))}
          />
        ))}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button onClick={() => void onReloadEdgeDetail(identity)} disabled={detailLoading} style={{ padding: "6px 10px" }}>
            重新加载详情
          </button>
          <button onClick={() => void saveSelectedEdge()} disabled={!canSave} style={{ padding: "6px 10px" }}>
            {saveLoading ? "保存中…" : "保存边"}
          </button>
        </div>
      </div>
    );
  }, [
    actorInvalid,
    detailLoading,
    edgeDetail,
    edgeSpecs,
    nodeDetail,
    nodeSpecs,
    onReloadEdgeDetail,
    onReloadNodeDetail,
    saveLoading,
    schemaError,
    schemaLoading,
    sel,
    selectedEdgeSet,
    selectedEdgeVersion,
    selectedNodeSet,
    selectedNodeVersion,
    saveSelectedEdge,
    saveSelectedNode,
  ]);

  const renderDirectEditor = (
    <div style={{ display: "grid", gap: 14 }}>
      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 10, display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600 }}>直接编辑 Node</div>
        <div style={{ display: "flex", gap: 8 }}>
          <input value={directNodeVid} onChange={(e) => setDirectNodeVid(e.target.value)} placeholder="vid" style={{ padding: 8, flex: 1 }} />
          <button onClick={() => void loadDirectNode()} disabled={directNodeLoading} style={{ padding: "8px 12px" }}>
            {directNodeLoading ? "加载中…" : "加载"}
          </button>
        </div>
        <div style={{ fontSize: 12, color: "#666" }}>current_version={directNodeDetail?.version ?? "-"}</div>
        {directNodeDetail ? (
          <div style={{ display: "grid", gap: 8 }}>
            {nodeSpecs.map((spec) => (
              <FormField
                key={`direct-node-${spec.name}`}
                spec={spec}
                value={directNodeSet[spec.name] || ""}
                onChange={(next) => setDirectNodeSet((prev) => ({ ...prev, [spec.name]: next }))}
              />
            ))}
            <button onClick={() => void saveDirectNode()} disabled={saveLoading || actorInvalid} style={{ padding: "6px 10px" }}>
              {saveLoading ? "保存中…" : "保存节点"}
            </button>
          </div>
        ) : null}
      </div>

      <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 10, display: "grid", gap: 8 }}>
        <div style={{ fontWeight: 600 }}>直接编辑 Edge</div>
        <div style={{ display: "grid", gap: 8 }}>
          <input value={directEdgeSrc} onChange={(e) => setDirectEdgeSrc(e.target.value)} placeholder="src" style={{ padding: 8 }} />
          <input value={directEdgeDst} onChange={(e) => setDirectEdgeDst(e.target.value)} placeholder="dst" style={{ padding: 8 }} />
          <input value={directEdgeRank} onChange={(e) => setDirectEdgeRank(e.target.value)} placeholder="rank" style={{ padding: 8 }} />
          <button onClick={() => void loadDirectEdge()} disabled={directEdgeLoading} style={{ padding: "8px 12px" }}>
            {directEdgeLoading ? "加载中…" : "加载"}
          </button>
        </div>
        <div style={{ fontSize: 12, color: "#666" }}>current_version={directEdgeDetail?.version ?? "-"}</div>
        {directEdgeDetail ? (
          <div style={{ display: "grid", gap: 8 }}>
            {edgeSpecs.map((spec) => (
              <FormField
                key={`direct-edge-${spec.name}`}
                spec={spec}
                value={directEdgeSet[spec.name] || ""}
                onChange={(next) => setDirectEdgeSet((prev) => ({ ...prev, [spec.name]: next }))}
              />
            ))}
            <button onClick={() => void saveDirectEdge()} disabled={saveLoading || actorInvalid} style={{ padding: "6px 10px" }}>
              {saveLoading ? "保存中…" : "保存边"}
            </button>
          </div>
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
