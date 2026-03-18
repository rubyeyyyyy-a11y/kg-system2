import { useMemo } from "react";

import type { EditableFieldSpec } from "../../../types/kg";
import { edgeDefaultFieldOrder, edgeGroups, getEdgeFieldRule } from "../../objectMeta/registry/edgeRules";
import { canonicalizeFieldName, sortFieldRules, type ObjectMetaFieldRule } from "../../objectMeta/registry/commonRules";
import { nodeDefaultFieldOrder, nodeGroups, getNodeFieldRule } from "../../objectMeta/registry/nodeRules";
import type { NormalizedDetail } from "../../detail/utils/normalizeDetail";

export type EditLayoutField = ObjectMetaFieldRule & {
  value: string;
};

export type EditLayoutSection = {
  key: string;
  title: string;
  fields: EditLayoutField[];
};

function normalizeFieldValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  return String(value);
}

function buildMetadataFields(kind: "node" | "edge", metadataFields: EditableFieldSpec[]): ObjectMetaFieldRule[] {
  return metadataFields.map((spec, index) => {
    const name = canonicalizeFieldName(kind, spec.name);
    const baseRule = kind === "node" ? getNodeFieldRule(name) : getEdgeFieldRule(name);
    return {
      ...baseRule,
      name,
      maxLen: spec.maxLen || baseRule.maxLen,
      multiline: spec.multiline || baseRule.multiline,
      order: baseRule.order + index,
    };
  });
}

export function useEditLayout(params: {
  kind: "node" | "edge";
  detail: NormalizedDetail;
  metadataFields: EditableFieldSpec[];
}) {
  const { detail, kind, metadataFields } = params;

  return useMemo(() => {
    const baseFields = kind === "node" ? Object.keys(getNodeRuleMap()) : Object.keys(getEdgeRuleMap());
    const currentFields = Object.keys(detail.allFields);
    const metadataRuleFields = buildMetadataFields(kind, metadataFields);
    const allFieldNames = Array.from(new Set([...baseFields, ...currentFields, ...metadataRuleFields.map((rule) => rule.name)]));
    const allRules = allFieldNames.map((fieldName) =>
      kind === "node"
        ? { ...getNodeFieldRule(fieldName), value: normalizeFieldValue(detail.allFields[fieldName]) }
        : { ...getEdgeFieldRule(fieldName, detail.edgeKind), value: normalizeFieldValue(detail.allFields[fieldName]) },
    );
    metadataRuleFields.forEach((rule) => {
      const target = allRules.find((item) => item.name === rule.name);
      if (target) {
        target.maxLen = rule.maxLen;
        target.multiline = rule.multiline;
      }
    });

    const sorted = sortFieldRules(allRules, kind === "node" ? nodeGroups : edgeGroups, kind === "node" ? nodeDefaultFieldOrder : edgeDefaultFieldOrder);

    const sections: EditLayoutSection[] = [];
    if (kind === "node") {
      const basicNames = new Set(["vid", "entity_name", "entity_type", "entity_raw_id", "source", "hop_level"]);
      const textNames = new Set(["description", "synonyms"]);
      const systemNames = new Set(["version", "updated_at", "updated_by"]);
      sections.push({
        key: "basic",
        title: "基础信息",
        fields: sorted.filter((field) => basicNames.has(field.name)),
      });
      sections.push({
        key: "text",
        title: "文本信息",
        fields: sorted.filter((field) => textNames.has(field.name)),
      });
      sections.push({
        key: "other",
        title: "其他属性",
        fields: sorted.filter((field) => !basicNames.has(field.name) && !textNames.has(field.name) && !systemNames.has(field.name)),
      });
      sections.push({
        key: "system",
        title: "系统信息",
        fields: sorted.filter((field) => systemNames.has(field.name)),
      });
    } else {
      const connectionNames = new Set(["src", "dst", "rank", "edge_type"]);
      const commonNames = new Set(["edge_kind", "relation", "source", "evidence"]);
      const systemNames = new Set(["version", "updated_at", "updated_by"]);
      sections.push({
        key: "connection",
        title: "连接信息",
        fields: sorted.filter((field) => connectionNames.has(field.name)),
      });
      sections.push({
        key: "common",
        title: "公共属性",
        fields: sorted.filter((field) => commonNames.has(field.name)),
      });
      sections.push({
        key: "other",
        title: "其他属性",
        fields: sorted.filter((field) => !connectionNames.has(field.name) && !commonNames.has(field.name) && !systemNames.has(field.name)),
      });
      sections.push({
        key: "system",
        title: "系统信息",
        fields: sorted.filter((field) => systemNames.has(field.name)),
      });
    }

    return sections.filter((section) => section.fields.length > 0);
  }, [detail, kind, metadataFields]);
}

function getNodeRuleMap() {
  return {
    vid: getNodeFieldRule("vid"),
    entity_name: getNodeFieldRule("entity_name"),
    entity_type: getNodeFieldRule("entity_type"),
    entity_raw_id: getNodeFieldRule("entity_raw_id"),
    source: getNodeFieldRule("source"),
    hop_level: getNodeFieldRule("hop_level"),
    description: getNodeFieldRule("description"),
    synonyms: getNodeFieldRule("synonyms"),
    version: getNodeFieldRule("version"),
    updated_at: getNodeFieldRule("updated_at"),
    updated_by: getNodeFieldRule("updated_by"),
  };
}

function getEdgeRuleMap() {
  return {
    edge_kind: getEdgeFieldRule("edge_kind"),
    src: getEdgeFieldRule("src"),
    dst: getEdgeFieldRule("dst"),
    rank: getEdgeFieldRule("rank"),
    edge_type: getEdgeFieldRule("edge_type"),
    relation: getEdgeFieldRule("relation"),
    source: getEdgeFieldRule("source"),
    evidence: getEdgeFieldRule("evidence"),
    version: getEdgeFieldRule("version"),
    updated_at: getEdgeFieldRule("updated_at"),
    updated_by: getEdgeFieldRule("updated_by"),
  };
}
