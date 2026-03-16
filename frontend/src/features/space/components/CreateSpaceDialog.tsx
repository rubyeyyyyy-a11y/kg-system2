import { useState } from "react";

import type { CreateSpaceResp } from "../types/space";

type CreateSpaceDialogProps = {
  open: boolean;
  submitting: boolean;
  error: string | null;
  onClose: () => void;
  onSubmit: (payload: {
    space_name: string;
    display_name: string;
    description: string;
    template_type: "entity_rel2_default";
    created_by: string;
  }) => Promise<CreateSpaceResp>;
};

export function CreateSpaceDialog({ open, submitting, error, onClose, onSubmit }: CreateSpaceDialogProps) {
  const [spaceName, setSpaceName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [description, setDescription] = useState("");
  const [createdBy, setCreatedBy] = useState("internal_user");

  if (!open) return null;

  async function handleSubmit() {
    await onSubmit({
      space_name: spaceName.trim(),
      display_name: displayName.trim() || spaceName.trim(),
      description: description.trim(),
      template_type: "entity_rel2_default",
      created_by: createdBy.trim(),
    });
    setSpaceName("");
    setDisplayName("");
    setDescription("");
    setCreatedBy("internal_user");
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.28)",
        display: "grid",
        placeItems: "center",
        zIndex: 1200,
      }}
    >
      <div style={{ width: "min(560px, calc(100vw - 32px))", background: "#fff", borderRadius: 12, padding: 16, display: "grid", gap: 10 }}>
        <div style={{ fontSize: 16, fontWeight: 700 }}>创建模板 Space</div>
        <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
          <span>space_name</span>
          <input value={spaceName} onChange={(e) => setSpaceName(e.target.value)} placeholder="test_space_a" />
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
          <span>display_name</span>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Test Space A" />
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
          <span>description</span>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
          <span>template_type</span>
          <input value="entity_rel2_default" disabled />
        </label>
        <label style={{ display: "grid", gap: 4, fontSize: 12 }}>
          <span>created_by</span>
          <input value={createdBy} onChange={(e) => setCreatedBy(e.target.value)} />
        </label>
        {error ? <div style={{ fontSize: 12, color: "#a8071a" }}>{error}</div> : null}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} disabled={submitting} style={{ padding: "8px 12px" }}>
            关闭
          </button>
          <button onClick={() => void handleSubmit()} disabled={submitting || !spaceName.trim()} style={{ padding: "8px 12px" }}>
            {submitting ? "创建中..." : "创建并切换"}
          </button>
        </div>
      </div>
    </div>
  );
}
