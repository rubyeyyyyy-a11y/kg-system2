from typing import Any

from app.config import settings
from app.db.nebula_client import execute_ngql_safe
from app.services.common import vw
from app.services.imports.models import (
    ImportTargetConfig,
    IntegrationLevel,
    SchemaObject,
    SchemaObjectPlan,
    SchemaOptions,
    SchemaProperty,
    SchemaPropertyPlan,
)

SYSTEM_VERTEX_PROPS = [
    SchemaPropertyPlan(name="version", type="int64", exists=False),
    SchemaPropertyPlan(name="updated_at", type="int64", exists=False),
    SchemaPropertyPlan(name="updated_by", type="string", exists=False),
]
SYSTEM_EDGE_PROPS = [
    SchemaPropertyPlan(name="version", type="int64", exists=False),
    SchemaPropertyPlan(name="updated_at", type="int64", exists=False),
    SchemaPropertyPlan(name="updated_by", type="string", exists=False),
]


def _column_values(result: Any, candidates: list[str]) -> list[Any]:
    for candidate in candidates:
        try:
            values = result.column_values(candidate)
            if values is not None:
                return list(values)
        except Exception:
            continue
    return []


def _describe_object(object_type: str, name: str) -> list[SchemaProperty]:
    stmt = "TAG" if object_type == "tag" else "EDGE"
    result = execute_ngql_safe(f"DESCRIBE {stmt} `{name}`;")
    fields = _column_values(result, ["Field", "field", "Name", "name"])
    types = _column_values(result, ["Type", "type"])
    nulls = _column_values(result, ["Null", "null"])
    props: list[SchemaProperty] = []
    for idx, field in enumerate(fields):
        field_name = str(vw(field) or "").strip()
        if not field_name:
            continue
        nullable_text = str(vw(nulls[idx]) or "YES").strip().upper() if idx < len(nulls) else "YES"
        props.append(
            SchemaProperty(
                name=field_name,
                type=str(vw(types[idx]) or "string") if idx < len(types) else "string",
                nullable=nullable_text != "NO",
            )
        )
    return props


def introspect_schema() -> dict[str, list[dict[str, Any]]]:
    tags_res = execute_ngql_safe("SHOW TAGS;")
    edges_res = execute_ngql_safe("SHOW EDGES;")
    tags = []
    edges = []
    for value in _column_values(tags_res, ["Name", "name", "Tag"]):
        tag_name = str(vw(value) or "").strip()
        if tag_name:
            tags.append(SchemaObject(object_type="tag", name=tag_name, properties=_describe_object("tag", tag_name)))
    for value in _column_values(edges_res, ["Name", "name", "Edge"]):
        edge_name = str(vw(value) or "").strip()
        if edge_name:
            edges.append(
                SchemaObject(object_type="edge_type", name=edge_name, properties=_describe_object("edge_type", edge_name))
            )
    return {
        "tags": [item.model_dump() for item in sorted(tags, key=lambda item: item.name)],
        "edge_types": [item.model_dump() for item in sorted(edges, key=lambda item: item.name)],
    }


def integration_level_for_target(*, object_type: str, object_name: str) -> IntegrationLevel:
    if object_type == "tag" and object_name == "Entity":
        return "fully_integrated"
    if object_type == "edge_type" and object_name == settings.edge_type:
        return "partially_integrated"
    return "import_only"


def integration_warnings_for_target(*, object_type: str, object_name: str, object_exists: bool) -> list[str]:
    level = integration_level_for_target(object_type=object_type, object_name=object_name)
    warnings: list[str] = []
    if level == "fully_integrated":
        return warnings
    if object_type == "tag":
        warnings.append(
            f"tag `{object_name}` {'already exists but' if object_exists else 'will be created and'} does not automatically join current search/discovery/graph primary flows"
        )
    else:
        warnings.append(
            f"edge type `{object_name}` {'already exists but' if object_exists else 'will be created and'} is import-compatible only; ES/search remains entity-only"
        )
    return warnings


def _object_lookup(schema: dict[str, list[dict[str, Any]]], object_type: str, object_name: str) -> dict[str, Any] | None:
    key = "tags" if object_type == "tag" else "edge_types"
    for item in schema.get(key, []):
        if str(item.get("name") or "") == object_name:
            return item
    return None


def default_property_type(field_name: str) -> str:
    name = str(field_name or "").strip()
    if name in {"version", "updated_at"}:
        return "int64"
    if name == "score":
        return "double"
    return "string"


def build_schema_plan(
    *,
    schema: dict[str, list[dict[str, Any]]],
    mapping: list[ImportTargetConfig],
    all_columns: list[str],
    schema_options: SchemaOptions,
) -> tuple[list[SchemaObjectPlan], list[str], list[str]]:
    plans: list[SchemaObjectPlan] = []
    warnings: list[str] = []
    integration_warnings: list[str] = []
    for target in mapping:
        existing = _object_lookup(schema, target.object_type, target.object_name)
        exists = existing is not None
        if not exists and not schema_options.allow_create_object:
            warnings.append(f"{target.object_type} `{target.object_name}` does not exist and create is disabled")
        existing_props = {str(item.get("name") or ""): item for item in (existing or {}).get("properties", [])}
        mapped_columns = {item.source_column for item in target.field_mappings}
        add_properties: list[SchemaPropertyPlan] = []
        for item in target.field_mappings:
            prop_name = item.target_field
            if prop_name in {"ID", "srcVID", "dstVID", "rank"}:
                continue
            prop_exists = prop_name in existing_props
            if exists and not prop_exists and not schema_options.allow_add_properties:
                warnings.append(
                    f"{target.object_type} `{target.object_name}` missing property `{prop_name}` and add-property is disabled"
                )
            prop_type = str(existing_props.get(prop_name, {}).get("type") or default_property_type(prop_name))
            add_properties.append(
                SchemaPropertyPlan(
                    name=prop_name,
                    type=prop_type,
                    exists=prop_exists,
                    source_column=item.source_column,
                )
            )
        system_props = SYSTEM_VERTEX_PROPS if target.object_type == "tag" else SYSTEM_EDGE_PROPS
        for system_prop in system_props:
            if system_prop.name in existing_props:
                continue
            add_properties.append(system_prop.model_copy())
        object_integration_warnings = integration_warnings_for_target(
            object_type=target.object_type, object_name=target.object_name, object_exists=exists
        )
        integration_warnings.extend(object_integration_warnings)
        ignored_columns = [column for column in all_columns if column not in mapped_columns]
        plans.append(
            SchemaObjectPlan(
                object_type=target.object_type,
                object_name=target.object_name,
                object_exists=exists,
                add_object=not exists,
                add_properties=[item for item in add_properties if not item.exists],
                ignored_columns=ignored_columns,
                integration_warnings=object_integration_warnings,
            )
        )
    return plans, warnings, integration_warnings


def apply_schema_plan(schema_plan: list[SchemaObjectPlan]) -> None:
    for object_plan in schema_plan:
        target = f"`{object_plan.object_name}`"
        if object_plan.add_object:
            if object_plan.object_type == "tag":
                props = ", ".join(f"`{item.name}` {item.type}" for item in object_plan.add_properties)
                execute_ngql_safe(f"CREATE TAG IF NOT EXISTS {target}({props});" if props else f"CREATE TAG IF NOT EXISTS {target}();")
            else:
                props = ", ".join(f"`{item.name}` {item.type}" for item in object_plan.add_properties)
                execute_ngql_safe(
                    f"CREATE EDGE IF NOT EXISTS {target}({props});" if props else f"CREATE EDGE IF NOT EXISTS {target}();"
                )
            continue
        if not object_plan.add_properties:
            continue
        props = ", ".join(f"`{item.name}` {item.type}" for item in object_plan.add_properties)
        if object_plan.object_type == "tag":
            execute_ngql_safe(f"ALTER TAG {target} ADD ({props});")
        else:
            execute_ngql_safe(f"ALTER EDGE {target} ADD ({props});")
