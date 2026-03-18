export function formatValue(fieldName: string, value: unknown): string {
  if (value == null || value === "") return "-";
  if (fieldName === "updated_at") {
    const seconds = Number(value);
    if (Number.isFinite(seconds) && seconds > 0) {
      return `${new Date(seconds * 1000).toLocaleString("zh-CN")} (${seconds})`;
    }
  }
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}
