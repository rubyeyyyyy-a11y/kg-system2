import type { ReactNode } from "react";

export function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ border: "1px solid #f0f0f0", borderRadius: 8, background: "#fff", padding: 10, display: "grid", gap: 10 }}>
      <div style={{ fontWeight: 600, fontSize: 13 }}>{title}</div>
      <div style={{ display: "grid", gap: 10 }}>{children}</div>
    </div>
  );
}
