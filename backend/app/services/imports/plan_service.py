import time

from app.services.imports import mapping_service, schema_service
from app.services.imports.models import CompiledImportPlan, ImportDraft


def compile_plan(draft: ImportDraft, *, all_columns: list[str]) -> tuple[CompiledImportPlan, list[str], list[str]]:
    schema = schema_service.introspect_schema()
    schema_plan, schema_warnings, integration_warnings = schema_service.build_schema_plan(
        schema=schema,
        mapping=draft.mapping,
        all_columns=all_columns,
        schema_options=draft.schema_options,
    )
    targets = []
    warnings = list(schema_warnings)
    schema_lookup = {
        ("tag", item["name"]): item for item in schema.get("tags", [])
    } | {
        ("edge_type", item["name"]): item for item in schema.get("edge_types", [])
    }
    for target in draft.mapping:
        compiled = mapping_service.compile_target(
            target=target, schema_object=schema_lookup.get((target.object_type, target.object_name))
        )
        warnings.extend(compiled.warnings)
        targets.append(compiled)
    levels = {item.integration_level for item in targets}
    if levels == {"fully_integrated"}:
        integration_level = "fully_integrated"
    elif "fully_integrated" in levels or "partially_integrated" in levels:
        integration_level = "partially_integrated"
    else:
        integration_level = "import_only"
    plan = CompiledImportPlan(
        plan_id=f"plan_{int(time.time())}",
        mode=draft.mode,
        file_ids=list(draft.file_ids),
        discriminator_column=draft.discriminator_column,
        targets=targets,
        schema_create_plan=schema_plan,
        update_strategy=draft.update_strategy,
        rank_generation_strategy="system_generated"
        if any(
            "rank" not in {field_mapping.target_field for field_mapping in item.field_mappings}
            for item in draft.mapping
            if item.object_type == "edge_type"
        )
        else "preserve_input",
        postprocess_options=draft.postprocess_options,
        warnings=warnings,
        integration_level=integration_level,
    )
    return plan, warnings, integration_warnings
