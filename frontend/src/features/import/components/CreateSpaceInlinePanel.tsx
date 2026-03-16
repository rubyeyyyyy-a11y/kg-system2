import { useState } from "react";

import type { CreateSpaceResp } from "../../space/types/space";

type CreateSpaceInlinePanelProps = {
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

const FIXED_PROMISES = [
  "This is a template-compatible space.",
  "Only Entity / REL2 / EntityTypeStat / RelationTypeStat are currently promised.",
  "Import success does not mean arbitrary schemas automatically enter current search, discovery, or graph primary flows.",
];

export function CreateSpaceInlinePanel({ open, submitting, error, onClose, onSubmit }: CreateSpaceInlinePanelProps) {
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
    <section
      style={{
        borderRadius: 22,
        background: "linear-gradient(180deg, rgba(255, 248, 238, 0.98), rgba(246, 236, 220, 0.98))",
        border: "1px solid rgba(110, 80, 46, 0.14)",
        padding: 18,
        display: "grid",
        gap: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div style={{ display: "grid", gap: 4 }}>
          <strong style={{ fontSize: 16 }}>Create Template Space</strong>
          <div style={{ fontSize: 13, color: "#6c5b47", maxWidth: 760 }}>
            Provision a managed `entity_rel2_default` space inside the current import flow. Creation stays in the spaces subdomain; the
            Import Workspace only collects the main user entry.
          </div>
        </div>
        <button onClick={onClose} disabled={submitting} style={{ padding: "8px 12px" }}>
          Collapse
        </button>
      </div>

      <div style={{ display: "grid", gap: 10 }}>
        {FIXED_PROMISES.map((item) => (
          <div key={item} style={{ padding: 10, borderRadius: 12, background: "#fff7e0", color: "#8c4b11", fontSize: 13 }}>
            {item}
          </div>
        ))}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
        <label style={{ display: "grid", gap: 6, fontSize: 12 }}>
          <span>space_name</span>
          <input value={spaceName} onChange={(event) => setSpaceName(event.target.value)} placeholder="test_space_a" />
        </label>
        <label style={{ display: "grid", gap: 6, fontSize: 12 }}>
          <span>display_name</span>
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Test Space A" />
        </label>
        <label style={{ display: "grid", gap: 6, fontSize: 12 }}>
          <span>created_by</span>
          <input value={createdBy} onChange={(event) => setCreatedBy(event.target.value)} />
        </label>
        <label style={{ display: "grid", gap: 6, fontSize: 12 }}>
          <span>template_type</span>
          <input value="entity_rel2_default" disabled />
        </label>
      </div>

      <label style={{ display: "grid", gap: 6, fontSize: 12 }}>
        <span>description</span>
        <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} />
      </label>

      {error ? <div style={{ padding: 10, borderRadius: 12, background: "#fff1f0", color: "#a61d24", fontSize: 13 }}>{error}</div> : null}

      <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, flexWrap: "wrap" }}>
        <button onClick={onClose} disabled={submitting} style={{ padding: "10px 14px" }}>
          Cancel
        </button>
        <button onClick={() => void handleSubmit()} disabled={submitting || !spaceName.trim()} style={{ padding: "10px 14px" }}>
          {submitting ? "Creating..." : "Create and Switch"}
        </button>
      </div>
    </section>
  );
}
