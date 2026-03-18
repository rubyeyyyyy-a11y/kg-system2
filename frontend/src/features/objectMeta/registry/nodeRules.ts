import type { ObjectMetaFieldRule, ObjectMetaGroupRule } from "./commonRules";
import { fallbackFieldRule } from "./commonRules";

export const nodeGroups: ObjectMetaGroupRule[] = [
  { key: "basic", title: "基础信息", order: 10 },
  { key: "text", title: "文本信息", order: 20 },
  { key: "other", title: "其他属性", order: 30 },
  { key: "system", title: "系统信息", order: 40 },
  { key: "advanced", title: "高级属性", order: 50 },
];

export const nodeFieldRules: Record<string, ObjectMetaFieldRule> = {
  vid: { name: "vid", label: "VID", group: "basic", order: 10, maxLen: 64, multiline: false, readOnly: true },
  entity_name: { name: "entity_name", label: "名称", group: "basic", order: 20, maxLen: 256, multiline: false },
  entity_type: {
    name: "entity_type",
    label: "实体类型",
    group: "basic",
    order: 30,
    maxLen: 128,
    multiline: false,
    highRisk: true,
  },
  entity_raw_id: {
    name: "entity_raw_id",
    label: "原始 ID",
    group: "basic",
    order: 40,
    maxLen: 256,
    multiline: false,
    readOnly: true,
  },
  source: { name: "source", label: "来源", group: "basic", order: 50, maxLen: 256, multiline: false },
  hop_level: { name: "hop_level", label: "Hop Level", group: "basic", order: 60, maxLen: 64, multiline: false, readOnly: true },
  description: {
    name: "description",
    label: "描述",
    group: "text",
    order: 70,
    maxLen: 4096,
    multiline: true,
    longText: { previewChars: 240 },
  },
  synonyms: {
    name: "synonyms",
    label: "同义词",
    group: "text",
    order: 80,
    maxLen: 4096,
    multiline: true,
    longText: { previewChars: 240 },
  },
  version: { name: "version", label: "Version", group: "system", order: 90, maxLen: 32, multiline: false, readOnly: true },
  updated_at: { name: "updated_at", label: "Updated At", group: "system", order: 100, maxLen: 32, multiline: false, readOnly: true },
  updated_by: { name: "updated_by", label: "Updated By", group: "system", order: 110, maxLen: 64, multiline: false, readOnly: true },
};

export const nodeDefaultFieldOrder = [
  "entity_name",
  "entity_type",
  "vid",
  "entity_raw_id",
  "source",
  "hop_level",
  "description",
  "synonyms",
  "version",
  "updated_at",
  "updated_by",
];

export function getNodeFieldRule(name: string): ObjectMetaFieldRule {
  return nodeFieldRules[name] || fallbackFieldRule("node", name);
}
