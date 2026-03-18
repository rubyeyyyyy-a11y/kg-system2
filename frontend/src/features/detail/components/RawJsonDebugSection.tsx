import { useEffect, useState } from "react";

export function RawJsonDebugSection({ payload }: { payload: unknown }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setOpen(false);
  }, [payload]);
  return (
    <div style={{ border: "1px solid #f0f0f0", borderRadius: 8, overflow: "hidden", background: "#fff" }}>
      <button
        data-testid="detail-raw-json-toggle"
        onClick={() => setOpen((value) => !value)}
        style={{
          width: "100%",
          textAlign: "left",
          border: "none",
          background: "#fafafa",
          padding: "10px 12px",
          cursor: "pointer",
          fontSize: 12,
          fontWeight: 600,
        }}
      >
        {open ? "▼" : "▶"} Raw JSON
      </button>
      {open ? (
        <div data-testid="detail-raw-json-content" style={{ borderTop: "1px solid #f0f0f0", padding: 10 }}>
          <pre style={{ fontSize: 12, whiteSpace: "pre-wrap", margin: 0 }}>{JSON.stringify(payload ?? {}, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}
