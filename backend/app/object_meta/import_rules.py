from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any, Iterable

from app.services.imports.models import DraftSource, IdentityMapping, ImportTargetConfig, ObjectType, PropertyMapping

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_GENERIC_EDGE_KIND_TOKENS = {
    "",
    "csv",
    "data",
    "dataset",
    "edge",
    "edges",
    "file",
    "graph",
    "import",
    "imports",
    "rel",
    "rel2",
    "relation",
    "relations",
}

LOGICAL_ALIAS_RULES: dict[str, set[str]] = {
    "ID": {"id", "vid"},
    "srcVID": {"srcvid", "src_vid", "subject_our_defined_id"},
    "dstVID": {"dstvid", "dst_vid", "object_our_defined_id"},
    "rank": {"rank"},
    "edge_kind": {"edge_kind", "edgekind", "semantic_edge_kind", "semanticedgekind"},
    "relation": {"relation"},
    "source": {"source", "source_db"},
    "evidence": {"evidence"},
    "score": {"score"},
    "entity_name": {"entity_name"},
    "entity_type": {"entity_type"},
    "entity_raw_id": {"entity_raw_id"},
    "description": {"description"},
    "synonyms": {"synonyms", "synonym"},
    "version": {"version"},
    "updated_at": {"updated_at"},
    "updated_by": {"updated_by"},
}

VERTEX_FIXED_PROPERTY_FIELDS = (
    "entity_type",
    "entity_name",
    "entity_raw_id",
    "description",
    "source",
    "synonyms",
)
EDGE_FIXED_PROPERTY_FIELDS = (
    "relation",
    "source",
    "evidence",
    "score",
    "version",
    "updated_at",
    "updated_by",
)
VERTEX_IDENTITY_FIELDS = ("ID",)
EDGE_IDENTITY_FIELDS = ("srcVID", "dstVID", "rank")


def normalize_token(value: str) -> str:
    return _NORMALIZE_RE.sub("", str(value or "").strip().lower())


def logical_field_for_column(column: str) -> str | None:
    token = normalize_token(column)
    for logical_field, aliases in LOGICAL_ALIAS_RULES.items():
        if token in {normalize_token(alias) for alias in aliases}:
            return logical_field
    return None


def alias_hints(columns: Iterable[str]) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    for column in columns:
        logical_field = logical_field_for_column(str(column))
        if logical_field:
            hints.append({"source_column": str(column), "logical_field": logical_field})
    return hints


def inferred_default_edge_kind(*, filename: str) -> str | None:
    path = PurePath(str(filename or "").strip())
    candidates = list(path.parts[:-1]) + [path.stem] if path.name else list(path.parts)
    for candidate in reversed(candidates):
        token = normalize_token(candidate)
        if token and token not in _GENERIC_EDGE_KIND_TOKENS:
            return token
    return None


def _alias_map(columns: Iterable[str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for column in columns:
        logical_field = logical_field_for_column(str(column))
        if logical_field and logical_field not in resolved:
            resolved[logical_field] = str(column)
    return resolved


def _target_options_with_defaults(*, source: DraftSource, object_type: ObjectType, target_options: dict[str, Any] | None) -> dict[str, Any]:
    resolved = dict(target_options or {})
    if object_type == "edge_type" and not str(resolved.get("edge_kind") or "").strip():
        default_edge_kind = str(source.default_edge_kind or "").strip()
        if default_edge_kind:
            resolved["edge_kind"] = default_edge_kind
    return resolved


def suggest_target_mappings(
    *,
    source: DraftSource,
    object_type: ObjectType,
    target_options: dict[str, Any] | None = None,
) -> tuple[IdentityMapping, list[PropertyMapping], dict[str, Any]]:
    alias_map = _alias_map(source.columns)
    identity = IdentityMapping()
    properties: list[PropertyMapping] = []
    effective_target_options = _target_options_with_defaults(
        source=source,
        object_type=object_type,
        target_options=target_options,
    )
    if object_type == "tag":
        identity.id_column = alias_map.get("ID")
        fixed_fields = set(VERTEX_FIXED_PROPERTY_FIELDS)
        identity_columns = {identity.id_column} - {None}
    else:
        identity.src_column = alias_map.get("srcVID")
        identity.dst_column = alias_map.get("dstVID")
        identity.rank_column = alias_map.get("rank")
        fixed_fields = set(EDGE_FIXED_PROPERTY_FIELDS) | {"edge_kind"}
        identity_columns = {identity.src_column, identity.dst_column, identity.rank_column} - {None}
    for column in source.columns:
        if column in identity_columns:
            continue
        logical_field = logical_field_for_column(column)
        target_field = logical_field if logical_field in fixed_fields else str(column)
        properties.append(
            PropertyMapping(
                source_column=str(column),
                target_field=target_field,
                logical_field=logical_field,
            )
        )
    return identity, properties, effective_target_options


def build_default_target(*, source: DraftSource, object_type: ObjectType, object_name: str) -> ImportTargetConfig:
    identity_mapping, property_mappings, target_options = suggest_target_mappings(source=source, object_type=object_type)
    return ImportTargetConfig(
        object_type=object_type,
        object_name=object_name,
        source_id=source.source_id,
        identity_mapping=identity_mapping,
        property_mappings=property_mappings,
        target_options=target_options,
    )


def _edge_kind_resolution(
    *,
    source: DraftSource,
    target: ImportTargetConfig,
) -> tuple[PropertyMapping | None, dict[str, Any] | None]:
    if target.object_type != "edge_type":
        return None, None
    for item in target.property_mappings:
        if str(item.target_field or "").strip() == "edge_kind":
            return None, {
                "mode": "existing_mapping",
                "source_column": str(item.source_column or "").strip() or None,
                "default_value": str(item.default_value or "").strip() or None,
            }

    alias_map = _alias_map(source.columns)
    explicit_edge_kind_column = alias_map.get("edge_kind")
    configured_edge_kind_column = str(target.target_options.get("edge_kind_column") or "").strip()
    if explicit_edge_kind_column:
        return (
            PropertyMapping(
                source_column=explicit_edge_kind_column,
                target_field="edge_kind",
                logical_field="edge_kind",
            ),
            {"mode": "source_column", "source": "edge_kind_column", "source_column": explicit_edge_kind_column},
        )
    if configured_edge_kind_column and configured_edge_kind_column in set(source.columns):
        return (
            PropertyMapping(
                source_column=configured_edge_kind_column,
                target_field="edge_kind",
                logical_field="edge_kind",
            ),
            {"mode": "source_column", "source": "target_options.edge_kind_column", "source_column": configured_edge_kind_column},
        )

    default_edge_kind = str(target.target_options.get("edge_kind") or target.target_options.get("edge_kind_default") or "").strip()
    if default_edge_kind:
        return (
            PropertyMapping(
                source_column="",
                target_field="edge_kind",
                logical_field="edge_kind",
                default_value=default_edge_kind,
            ),
            {"mode": "default_value", "source": "target_options.edge_kind", "value": default_edge_kind},
        )

    relation_column = alias_map.get("relation")
    if relation_column:
        return (
            PropertyMapping(
                source_column=relation_column,
                target_field="edge_kind",
                logical_field="edge_kind",
            ),
            {"mode": "source_column", "source": "relation_column_fallback", "source_column": relation_column},
        )

    return None, None


def apply_target_import_rules(*, source: DraftSource, target: ImportTargetConfig) -> ImportTargetConfig:
    next_target = target.model_copy(deep=True)
    next_target.target_options = _target_options_with_defaults(
        source=source,
        object_type=next_target.object_type,
        target_options=next_target.target_options,
    )
    mapping, resolution = _edge_kind_resolution(source=source, target=next_target)
    if mapping is not None:
        next_target.property_mappings.append(mapping)
    if resolution is not None:
        next_target.target_options["edge_kind_resolution"] = resolution
    return next_target
