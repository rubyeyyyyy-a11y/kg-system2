import type { ReactNode } from "react";

export function EditSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 10, display: "grid", gap: 10 }}>
      <div style={{ fontWeight: 600, fontSize: 13 }}>{title}</div>
      <div style={{ display: "grid", gap: 8 }}>{children}</div>
    </div>
  );
}
