from app.services.imports import schema_service
from app.services.imports.models import CompiledTargetPlan, ImportTargetConfig

VERTEX_IDENTITY_FIELDS = ["ID"]
EDGE_IDENTITY_FIELDS = ["srcVID", "dstVID", "rank"]
VERTEX_UPDATE_FORBIDDEN = {"entity_raw_id", "version", "updated_at", "updated_by"}
EDGE_UPDATE_FORBIDDEN = {"srcVID", "dstVID", "rank", "version", "updated_at", "updated_by"}


def compile_target(
    *,
    target: ImportTargetConfig,
    source_columns: list[str],
    source_file_id: str,
    source_filename: str,
    inferred_source_kind: str,
    schema_object: dict | None,
) -> CompiledTargetPlan:
    property_types = {
        str(prop.get("name") or ""): str(prop.get("type") or schema_service.default_property_type(str(prop.get("name") or "")))
        for prop in (schema_object or {}).get("properties", [])
        if str(prop.get("name") or "")
    }
    for mapped_prop in target.property_mappings:
        property_types.setdefault(mapped_prop.target_field, schema_service.default_property_type(mapped_prop.target_field))

    identity_fields = VERTEX_IDENTITY_FIELDS if target.object_type == "tag" else EDGE_IDENTITY_FIELDS
    update_forbidden = VERTEX_UPDATE_FORBIDDEN if target.object_type == "tag" else EDGE_UPDATE_FORBIDDEN
    mapped_property_fields = [item.target_field for item in target.property_mappings if item.target_field]
    update_fields = [field for field in mapped_property_fields if field not in update_forbidden]
    create_fields = [field for field in mapped_property_fields if field not in {"version", "updated_at", "updated_by"}]

    warnings: list[str] = []
    if target.object_type == "tag" and any(item.target_field == "entity_raw_id" for item in target.property_mappings):
        warnings.append("entity_raw_id will be written on create but never overwrite existing vertices")
    if target.object_type == "edge_type" and not target.identity_mapping.rank_column:
        warnings.append("rank not mapped; system-generated rank will be used")

    return CompiledTargetPlan(
        target_id=target.target_id,
        object_type=target.object_type,
        object_name=target.object_name,
        source_id=target.source_id,
        source_file_id=source_file_id,
        source_filename=source_filename,
        source_columns=list(source_columns),
        inferred_source_kind=inferred_source_kind,
        identity_mapping=target.identity_mapping,
        property_mappings=target.property_mappings,
        row_selector=target.row_selector,
        property_types=property_types,
        identity_fields=identity_fields,
        update_fields=update_fields,
        create_fields=create_fields,
        integration_level=schema_service.integration_level_for_target(
            object_type=target.object_type, object_name=target.object_name
        ),
        warnings=warnings,
    )
