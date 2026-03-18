import type { ImportObjectType, ImportPropertyMapping, ImportSource, ImportTargetMapping } from "./types/import";

export const VERTEX_PROPERTY_FIELDS = [
  "entity_type",
  "entity_name",
  "entity_raw_id",
  "description",
  "source",
  "synonyms",
  "version",
  "updated_at",
  "updated_by",
];

export const EDGE_PROPERTY_FIELDS = [
  "edge_kind",
  "relation",
  "source",
  "evidence",
  "score",
  "version",
  "updated_at",
  "updated_by",
];

function aliasLookup(source: ImportSource) {
  return new Map(source.alias_hints.map((item) => [item.source_column, item.logical_field]));
}

function identityMappingForSource(source: ImportSource, objectType: ImportObjectType) {
  const lookup = aliasLookup(source);
  if (objectType === "tag") {
    const idColumn = source.columns.find((column) => lookup.get(column) === "ID") || "";
    return { id_column: idColumn };
  }
  return {
    src_column: source.columns.find((column) => lookup.get(column) === "srcVID") || "",
    dst_column: source.columns.find((column) => lookup.get(column) === "dstVID") || "",
    rank_column: source.columns.find((column) => lookup.get(column) === "rank") || "",
  };
}

function propertyMappingsForSource(source: ImportSource, objectType: ImportObjectType, identityColumns: Set<string>) {
  const lookup = aliasLookup(source);
  const fixedFields = new Set(objectType === "tag" ? VERTEX_PROPERTY_FIELDS : EDGE_PROPERTY_FIELDS);
  return source.columns
    .filter((column) => !identityColumns.has(column))
    .map(
      (column): ImportPropertyMapping => {
        const logicalField = lookup.get(column);
        return {
          source_column: column,
          target_field: logicalField && fixedFields.has(logicalField) ? logicalField : column,
          logical_field: logicalField || undefined,
        };
      }
    );
}

export function suggestTargetFromSource(source: ImportSource, objectType?: ImportObjectType): ImportTargetMapping {
  const nextObjectType = objectType || source.recommended_object_type || (source.inferred_kind === "edge" ? "edge_type" : "tag");
  const identity_mapping = identityMappingForSource(source, nextObjectType);
  const identityColumns = new Set(Object.values(identity_mapping).filter((value): value is string => Boolean(value)));
  return {
    object_type: nextObjectType,
    object_name: nextObjectType === "tag" ? "Entity" : "REL2",
    source_id: source.source_id,
    identity_mapping,
    property_mappings: propertyMappingsForSource(source, nextObjectType, identityColumns),
    row_selector: null,
    target_options: nextObjectType === "edge_type" && source.default_edge_kind ? { edge_kind: source.default_edge_kind } : {},
  };
}
