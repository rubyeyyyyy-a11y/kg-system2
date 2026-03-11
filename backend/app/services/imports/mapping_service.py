from app.services.imports.models import CompiledTargetPlan, ImportTargetConfig
from app.services.imports import schema_service


VERTEX_IDENTITY_FIELDS = ["ID"]
EDGE_IDENTITY_FIELDS = ["srcVID", "dstVID", "rank"]
VERTEX_UPDATE_FORBIDDEN = {"entity_raw_id", "version", "updated_at", "updated_by"}
EDGE_UPDATE_FORBIDDEN = {"srcVID", "dstVID", "rank", "version", "updated_at", "updated_by"}


def compile_target(
    *,
    target: ImportTargetConfig,
    schema_object: dict | None,
) -> CompiledTargetPlan:
    field_mappings = {item.source_column: item.target_field for item in target.field_mappings}
    property_types = {
        str(prop.get("name") or ""): str(prop.get("type") or schema_service.default_property_type(str(prop.get("name") or "")))
        for prop in (schema_object or {}).get("properties", [])
        if str(prop.get("name") or "")
    }
    for mapped_field in field_mappings.values():
        if mapped_field in {"ID", "srcVID", "dstVID", "rank"}:
            continue
        property_types.setdefault(mapped_field, schema_service.default_property_type(mapped_field))
    identity_fields = VERTEX_IDENTITY_FIELDS if target.object_type == "tag" else EDGE_IDENTITY_FIELDS
    update_forbidden = VERTEX_UPDATE_FORBIDDEN if target.object_type == "tag" else EDGE_UPDATE_FORBIDDEN
    update_fields = [field for field in field_mappings.values() if field not in set(identity_fields) | update_forbidden]
    create_fields = [field for field in field_mappings.values() if field not in {"version", "updated_at", "updated_by"}]
    warnings: list[str] = []
    if target.object_type == "tag" and "entity_raw_id" in field_mappings.values():
        warnings.append("entity_raw_id will be written on create but never overwrite existing vertices")
    if target.object_type == "edge_type" and "rank" not in field_mappings.values():
        warnings.append("rank not mapped; system-generated rank will be used")
    return CompiledTargetPlan(
        object_type=target.object_type,
        object_name=target.object_name,
        discriminator_value=target.discriminator_value,
        field_mappings=field_mappings,
        property_types=property_types,
        identity_fields=identity_fields,
        update_fields=update_fields,
        create_fields=create_fields,
        integration_level=schema_service.integration_level_for_target(
            object_type=target.object_type, object_name=target.object_name
        ),
        warnings=warnings,
    )
