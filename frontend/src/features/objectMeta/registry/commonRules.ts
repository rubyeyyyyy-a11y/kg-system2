export type ObjectMetaKind = "node" | "edge";

export type ObjectMetaGroupRule = {
  key: string;
  title: string;
  order: number;
};

export type ObjectMetaLongTextRule = {
  previewChars: number;
};

export type ObjectMetaFieldRule = {
  name: string;
  label: string;
  group: string;
  order: number;
  maxLen: number;
  multiline: boolean;
  readOnly?: boolean;
  highRisk?: boolean;
  aliases?: string[];
  longText?: ObjectMetaLongTextRule;
};

export const DEFAULT_FIELD_MAX_LEN = 4096;

export function titleizeFieldName(name: string): string {
  return String(name || "")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function isMeaningfulValue(value: unknown): boolean {
  if (value == null) return false;
  if (typeof value === "string") return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value as Record<string, unknown>).length > 0;
  return true;
}

export function canonicalizeFieldName(kind: ObjectMetaKind, fieldName: string): string {
  const key = String(fieldName || "").trim();
  if (!key) return "";
  if (kind === "edge" && key === "source_db") return "source";
  return key;
}

export function sortFieldRules<T extends ObjectMetaFieldRule>(
  rules: T[],
  groups: ObjectMetaGroupRule[],
  fieldNames: string[],
): T[] {
  const groupOrder = new Map(groups.map((group) => [group.key, group.order]));
  const fieldOrder = new Map(fieldNames.map((fieldName, index) => [fieldName, index]));
  return [...rules].sort((left, right) => {
    const groupDelta = (groupOrder.get(left.group) ?? 999) - (groupOrder.get(right.group) ?? 999);
    if (groupDelta !== 0) return groupDelta;
    const explicitDelta = (fieldOrder.get(left.name) ?? 9999) - (fieldOrder.get(right.name) ?? 9999);
    if (explicitDelta !== 0) return explicitDelta;
    const orderDelta = left.order - right.order;
    if (orderDelta !== 0) return orderDelta;
    return left.name.localeCompare(right.name);
  });
}

export function fallbackFieldRule(kind: ObjectMetaKind, name: string): ObjectMetaFieldRule {
  return {
    name,
    label: titleizeFieldName(name),
    group: kind === "node" ? "other" : "other",
    order: 9000,
    maxLen: DEFAULT_FIELD_MAX_LEN,
    multiline: true,
  };
}
