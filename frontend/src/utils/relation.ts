export function relationDisplay(raw?: string): string {
  const s = String(raw || "").trim();
  if (!s) return "";
  return s.split("|")[0].trim();
}

export function normalizeText(value: string): string {
  return value.trim().toLowerCase();
}

export function getRelationGroupKey(displayName: string): string {
  const normalized = String(displayName || "").trim();
  if (!normalized) return "Other";
  const token = normalized.split(/[|:_\s]+/).find((x) => x.trim().length > 0);
  return token || "Other";
}

export function uniqueStrings(values: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const v of values) {
    const raw = String(v || "").trim();
    if (!raw || seen.has(raw)) continue;
    seen.add(raw);
    out.push(raw);
  }
  return out;
}
