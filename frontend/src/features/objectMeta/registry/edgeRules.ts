import type { ObjectMetaFieldRule, ObjectMetaGroupRule } from "./commonRules";
import { fallbackFieldRule } from "./commonRules";

export const edgeGroups: ObjectMetaGroupRule[] = [
  { key: "connection", title: "连接信息", order: 10 },
  { key: "common", title: "公共属性", order: 20 },
  { key: "other", title: "其他属性", order: 30 },
  { key: "system", title: "系统信息", order: 40 },
  { key: "advanced", title: "高级属性", order: 50 },
];

export const edgeFieldRules: Record<string, ObjectMetaFieldRule> = {
  edge_kind: { name: "edge_kind", label: "Edge Kind", group: "common", order: 10, maxLen: 128, multiline: false },
  src: { name: "src", label: "Source", group: "connection", order: 20, maxLen: 64, multiline: false, readOnly: true },
  dst: { name: "dst", label: "Destination", group: "connection", order: 30, maxLen: 64, multiline: false, readOnly: true },
  rank: { name: "rank", label: "Rank", group: "connection", order: 40, maxLen: 64, multiline: false, readOnly: true },
  edge_type: {
    name: "edge_type",
    label: "Physical Edge Type",
    group: "connection",
    order: 50,
    maxLen: 64,
    multiline: false,
    readOnly: true,
  },
  relation: {
    name: "relation",
    label: "关系类型",
    group: "common",
    order: 60,
    maxLen: 256,
    multiline: false,
    readOnly: true,
  },
  source: {
    name: "source",
    label: "来源",
    group: "common",
    order: 70,
    maxLen: 256,
    multiline: false,
    aliases: ["source_db"],
  },
  evidence: {
    name: "evidence",
    label: "证据",
    group: "common",
    order: 80,
    maxLen: 4096,
    multiline: true,
    longText: { previewChars: 240 },
  },
  version: { name: "version", label: "Version", group: "system", order: 90, maxLen: 32, multiline: false, readOnly: true },
  updated_at: { name: "updated_at", label: "Updated At", group: "system", order: 100, maxLen: 32, multiline: false, readOnly: true },
  updated_by: { name: "updated_by", label: "Updated By", group: "system", order: 110, maxLen: 64, multiline: false, readOnly: true },
};

export const edgeDefaultFieldOrder = [
  "edge_kind",
  "relation",
  "src",
  "dst",
  "rank",
  "edge_type",
  "source",
  "evidence",
  "version",
  "updated_at",
  "updated_by",
];

export const edgeKindFieldOverrides: Record<string, Record<string, ObjectMetaFieldRule>> = {};

export function getEdgeFieldRule(name: string, edgeKind?: string): ObjectMetaFieldRule {
  const override = edgeKind ? edgeKindFieldOverrides[String(edgeKind).trim().toLowerCase()] : undefined;
  return override?.[name] || edgeFieldRules[name] || fallbackFieldRule("edge", name);
}
