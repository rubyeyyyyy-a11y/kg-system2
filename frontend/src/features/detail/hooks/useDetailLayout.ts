import { useMemo } from "react";

import { edgeDefaultFieldOrder, edgeGroups, getEdgeFieldRule } from "../../objectMeta/registry/edgeRules";
import {
  isMeaningfulValue,
  sortFieldRules,
  type ObjectMetaFieldRule,
  type ObjectMetaGroupRule,
  type ObjectMetaKind,
} from "../../objectMeta/registry/commonRules";
import { nodeDefaultFieldOrder, nodeGroups, getNodeFieldRule } from "../../objectMeta/registry/nodeRules";
import type { NormalizedDetail } from "../utils/normalizeDetail";

export type DetailLayoutField = ObjectMetaFieldRule & {
  value: unknown;
};

export type DetailLayoutSection = {
  key: string;
  title: string;
  fields: DetailLayoutField[];
};

function getRule(kind: ObjectMetaKind, fieldName: string, edgeKind?: string): ObjectMetaFieldRule {
  return kind === "node" ? getNodeFieldRule(fieldName) : getEdgeFieldRule(fieldName, edgeKind);
}

function getGroups(kind: ObjectMetaKind): ObjectMetaGroupRule[] {
  return kind === "node" ? nodeGroups : edgeGroups;
}

function getFieldOrder(kind: ObjectMetaKind): string[] {
  return kind === "node" ? nodeDefaultFieldOrder : edgeDefaultFieldOrder;
}

function buildFields(kind: ObjectMetaKind, detail: NormalizedDetail): DetailLayoutField[] {
  const fields = Object.entries(detail.allFields)
    .filter(([, value]) => isMeaningfulValue(value))
    .map(([fieldName, value]) => ({
      ...getRule(kind, fieldName, detail.edgeKind),
      value,
    }));
  return sortFieldRules(fields, getGroups(kind), getFieldOrder(kind));
}

export function useDetailLayout(detail: NormalizedDetail) {
  return useMemo(() => {
    const kind = detail.objectType;
    const fields = buildFields(kind, detail);
    const systemFieldNames = new Set(["version", "updated_at", "updated_by"]);
    const titleFieldNames = new Set(kind === "node" ? ["entity_name"] : ["edge_kind"]);
    const fixedFieldNames = new Set(
      kind === "node"
        ? ["vid", "entity_type", "entity_raw_id", "source", "hop_level"]
        : ["src", "dst", "rank", "edge_type", "relation", "source"],
    );

    const basicFields = fields.filter((field) => fixedFieldNames.has(field.name));
    const systemFields = fields.filter((field) => systemFieldNames.has(field.name));
    const longTextFields = fields.filter(
      (field) =>
        !systemFieldNames.has(field.name) &&
        !fixedFieldNames.has(field.name) &&
        !titleFieldNames.has(field.name) &&
        (Boolean(field.longText) || (typeof field.value === "string" && field.value.trim().length > 240)),
    );
    const longTextNames = new Set(longTextFields.map((field) => field.name));
    const dynamicFields = fields.filter(
      (field) =>
        !systemFieldNames.has(field.name) &&
        !fixedFieldNames.has(field.name) &&
        !titleFieldNames.has(field.name) &&
        !longTextNames.has(field.name),
    );

    const sections: DetailLayoutSection[] = [];
    if (basicFields.length > 0) {
      sections.push({
        key: kind === "node" ? "basic" : "connection",
        title: kind === "node" ? "基础信息" : "连接信息",
        fields: basicFields,
      });
    }
    if (dynamicFields.length > 0) {
      sections.push({
        key: kind === "node" ? "business" : "dynamic",
        title: kind === "node" ? "业务属性" : "动态属性",
        fields: dynamicFields,
      });
    }
    if (longTextFields.length > 0) {
      sections.push({
        key: "long-text",
        title: kind === "node" ? "描述" : "证据",
        fields: longTextFields,
      });
    }
    if (systemFields.length > 0) {
      sections.push({
        key: "system",
        title: "编辑信息",
        fields: systemFields,
      });
    }

    return {
      title: detail.title,
      sections,
    };
  }, [detail]);
}
