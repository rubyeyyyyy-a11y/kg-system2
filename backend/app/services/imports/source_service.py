import hashlib
from typing import Iterable

from app.object_meta import import_rules
from app.services.imports import file_store
from app.services.imports.models import (
    DraftSource,
    IdentityMapping,
    ImportTargetConfig,
    ObjectType,
    PropertyMapping,
    SourceAliasHint,
)

VERTEX_PROPERTY_FIELDS = set(import_rules.VERTEX_FIXED_PROPERTY_FIELDS)
EDGE_PROPERTY_FIELDS = set(import_rules.EDGE_FIXED_PROPERTY_FIELDS) | {"edge_kind"}
VERTEX_IDENTITY_FIELDS = set(import_rules.VERTEX_IDENTITY_FIELDS)
EDGE_IDENTITY_FIELDS = set(import_rules.EDGE_IDENTITY_FIELDS)
MAX_SOURCE_SAMPLE_ROWS = file_store.MAX_SAMPLE_ROWS


def normalize_token(value: str) -> str:
    return import_rules.normalize_token(value)


def source_id_for_file(file_id: str) -> str:
    digest = hashlib.sha1(str(file_id).encode("utf-8")).hexdigest()[:12]
    return f"source_{digest}"


def header_hash(columns: Iterable[str]) -> str:
    joined = "\x1f".join(str(column or "") for column in columns)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def logical_field_for_column(column: str) -> str | None:
    return import_rules.logical_field_for_column(column)


def alias_hints(columns: Iterable[str]) -> list[SourceAliasHint]:
    return [SourceAliasHint.model_validate(item) for item in import_rules.alias_hints(columns)]


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
    if source.default_edge_kind:
        hints.append(f"edge kind default inferred as `{source.default_edge_kind}` from source context")
    return hints


def build_source_snapshot(file_id: str, *, sample_rows: int) -> DraftSource:
    columns, sample, record, sample_capped = file_store.read_csv_sample(file_id, sample_rows)
    inferred_kind = infer_kind(columns)
    warnings: list[str] = []
    if sample_rows > MAX_SOURCE_SAMPLE_ROWS:
        warnings.append(f"sample_rows capped at {MAX_SOURCE_SAMPLE_ROWS}")
    if sample_capped:
        warnings.append(f"preview limited to the first {min(sample_rows, MAX_SOURCE_SAMPLE_ROWS)} rows")
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
        default_edge_kind=import_rules.inferred_default_edge_kind(filename=record.original_name),
    )


def build_sources(file_ids: list[str], *, sample_rows: int) -> list[DraftSource]:
    return [build_source_snapshot(file_id, sample_rows=sample_rows) for file_id in file_ids]


def suggest_target_mappings(*, source: DraftSource, object_type: ObjectType) -> tuple[IdentityMapping, list[PropertyMapping]]:
    identity, properties, _target_options = import_rules.suggest_target_mappings(source=source, object_type=object_type)
    return identity, properties


def build_default_target(*, source: DraftSource, object_type: ObjectType, object_name: str) -> ImportTargetConfig:
    return import_rules.build_default_target(source=source, object_type=object_type, object_name=object_name)


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
