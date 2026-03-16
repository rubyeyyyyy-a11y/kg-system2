import hashlib
import re
from typing import Iterable

from app.services.imports import file_store
from app.services.imports.models import (
    DraftSource,
    IdentityMapping,
    ImportTargetConfig,
    ObjectType,
    PropertyMapping,
    SourceAliasHint,
)

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")

LOGICAL_ALIAS_RULES: dict[str, set[str]] = {
    "ID": {"id", "vid"},
    "srcVID": {"srcvid", "src_vid", "subject_our_defined_id"},
    "dstVID": {"dstvid", "dst_vid", "object_our_defined_id"},
    "rank": {"rank"},
    "relation": {"relation"},
    "source": {"source"},
    "evidence": {"evidence", "pmid", "relation_detail"},
    "score": {"score"},
    "entity_name": {"entity_name"},
    "entity_type": {"entity_type"},
    "entity_raw_id": {"entity_raw_id"},
    "description": {"description"},
}

VERTEX_PROPERTY_FIELDS = {"entity_name", "entity_type", "entity_raw_id", "description", "source"}
EDGE_PROPERTY_FIELDS = {"relation", "source", "evidence", "score"}
VERTEX_IDENTITY_FIELDS = {"ID"}
EDGE_IDENTITY_FIELDS = {"srcVID", "dstVID", "rank"}


def normalize_token(value: str) -> str:
    return _NORMALIZE_RE.sub("", str(value or "").strip().lower())


def source_id_for_file(file_id: str) -> str:
    digest = hashlib.sha1(str(file_id).encode("utf-8")).hexdigest()[:12]
    return f"source_{digest}"


def header_hash(columns: Iterable[str]) -> str:
    joined = "\x1f".join(str(column or "") for column in columns)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def logical_field_for_column(column: str) -> str | None:
    token = normalize_token(column)
    for logical_field, aliases in LOGICAL_ALIAS_RULES.items():
        if token in {normalize_token(alias) for alias in aliases}:
            return logical_field
    return None


def alias_hints(columns: Iterable[str]) -> list[SourceAliasHint]:
    hints: list[SourceAliasHint] = []
    for column in columns:
        logical_field = logical_field_for_column(column)
        if logical_field:
            hints.append(SourceAliasHint(source_column=str(column), logical_field=logical_field))
    return hints


def infer_kind(columns: Iterable[str]) -> str:
    logical_fields = {hint.logical_field for hint in alias_hints(columns)}
    vertex_identity = bool(logical_fields & VERTEX_IDENTITY_FIELDS)
    edge_identity = bool(logical_fields & {"srcVID", "dstVID"})
    vertex_props = len(logical_fields & {"entity_name", "entity_type", "entity_raw_id", "description"})
    edge_props = len(logical_fields & {"relation", "evidence", "score"})
    if vertex_identity and edge_identity:
        return "mixed"
    if edge_identity or edge_props:
        return "edge"
    if vertex_identity or vertex_props:
        return "vertex"
    return "unknown"


def recommended_object_type(inferred_kind: str) -> ObjectType | None:
    if inferred_kind == "vertex":
        return "tag"
    if inferred_kind == "edge":
        return "edge_type"
    return None


def preview_hints(source: DraftSource) -> list[str]:
    hints: list[str] = []
    for hint in source.alias_hints:
        hints.append(f"column `{hint.source_column}` matched logical field `{hint.logical_field}`")
    return hints


def build_source_snapshot(file_id: str, *, sample_rows: int) -> DraftSource:
    columns, sample, record, sample_capped = file_store.read_csv_sample(file_id, sample_rows)
    inferred_kind = infer_kind(columns)
    warnings: list[str] = []
    if sample_rows > file_store.MAX_SAMPLE_ROWS:
        warnings.append(f"sample_rows capped at {file_store.MAX_SAMPLE_ROWS}")
    if sample_capped:
        warnings.append(f"preview limited to the first {min(sample_rows, file_store.MAX_SAMPLE_ROWS)} rows")
    return DraftSource(
        source_id=source_id_for_file(file_id),
        file_id=file_id,
        filename=record.original_name,
        columns=columns,
        sample_rows=sample,
        header_hash=header_hash(columns),
        inferred_kind=inferred_kind,
        warnings=warnings,
        alias_hints=alias_hints(columns),
        recommended_object_type=recommended_object_type(inferred_kind),
    )


def build_sources(file_ids: list[str], *, sample_rows: int) -> list[DraftSource]:
    return [build_source_snapshot(file_id, sample_rows=sample_rows) for file_id in file_ids]


def suggest_target_mappings(*, source: DraftSource, object_type: ObjectType) -> tuple[IdentityMapping, list[PropertyMapping]]:
    identity = IdentityMapping()
    properties: list[PropertyMapping] = []
    for column in source.columns:
        logical_field = logical_field_for_column(column)
        if object_type == "tag":
            if logical_field == "ID":
                identity.id_column = column
                continue
            if logical_field in VERTEX_PROPERTY_FIELDS:
                properties.append(PropertyMapping(source_column=column, target_field=logical_field, logical_field=logical_field))
                continue
        else:
            if logical_field == "srcVID":
                identity.src_column = column
                continue
            if logical_field == "dstVID":
                identity.dst_column = column
                continue
            if logical_field == "rank":
                identity.rank_column = column
                continue
            if logical_field in EDGE_PROPERTY_FIELDS:
                properties.append(PropertyMapping(source_column=column, target_field=logical_field, logical_field=logical_field))
                continue
        if logical_field and logical_field not in {"ID", "srcVID", "dstVID", "rank"}:
            properties.append(PropertyMapping(source_column=column, target_field=logical_field, logical_field=logical_field))
        elif not logical_field:
            properties.append(PropertyMapping(source_column=column, target_field=column))
    return identity, properties


def build_default_target(*, source: DraftSource, object_type: ObjectType, object_name: str) -> ImportTargetConfig:
    identity_mapping, property_mappings = suggest_target_mappings(source=source, object_type=object_type)
    return ImportTargetConfig(
        object_type=object_type,
        object_name=object_name,
        source_id=source.source_id,
        identity_mapping=identity_mapping,
        property_mappings=property_mappings,
    )


def validate_source_kind_hint(*, object_type: ObjectType, inferred_kind: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if inferred_kind == "unknown":
        warnings.append("source kind could not be inferred from aliases; validate will rely on explicit mappings")
        return errors, warnings
    if inferred_kind == "mixed":
        warnings.append("mixed source means single-file row split; ensure row_selector is configured when sharing this source")
        return errors, warnings
    if inferred_kind == "vertex" and object_type == "edge_type":
        errors.append("edge target is bound to a vertex-like source")
    if inferred_kind == "edge" and object_type == "tag":
        errors.append("tag target is bound to an edge-like source")
    return errors, warnings


def missing_identity_hints(*, object_type: ObjectType, source: DraftSource) -> list[str]:
    hints: list[str] = []
    matched = {hint.logical_field: hint.source_column for hint in source.alias_hints}
    if object_type == "tag" and "ID" in matched:
        hints.append(f"suggest mapping `{matched['ID']}` -> vertex id")
    if object_type == "edge_type":
        if "srcVID" in matched:
            hints.append(f"suggest mapping `{matched['srcVID']}` -> edge srcVID")
        if "dstVID" in matched:
            hints.append(f"suggest mapping `{matched['dstVID']}` -> edge dstVID")
        if "rank" in matched:
            hints.append(f"suggest mapping `{matched['rank']}` -> edge rank")
    return hints
