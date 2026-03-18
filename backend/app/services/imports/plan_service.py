import time

from app.object_meta import import_rules
from app.services.imports import mapping_service, schema_service
from app.services.imports.models import CompiledImportPlan, ImportDraft
from app.services.spaces import registry_service, template_service


def compile_plan(draft: ImportDraft) -> tuple[CompiledImportPlan, list[str], list[str]]:
    space_summary = registry_service.get_space(draft.space_name) or registry_service.register_default_space()
    template_meta = template_service.template_summary(space_summary.template_type)
    schema = schema_service.introspect_schema(space_name=draft.space_name)
    sources_by_id = {source.source_id: source for source in draft.sources}
    schema_plan, schema_warnings, integration_warnings = schema_service.build_schema_plan(
        schema=schema,
        mapping=draft.mapping,
        sources_by_id=sources_by_id,
        schema_options=draft.schema_options,
    )
    warnings = list(schema_warnings)
    schema_lookup = {("tag", item["name"]): item for item in schema.get("tags", [])} | {
        ("edge_type", item["name"]): item for item in schema.get("edge_types", [])
    }
    ordered_targets = sorted(draft.mapping, key=lambda item: 0 if item.object_type == "tag" else 1)
    targets = []
    for target in ordered_targets:
        source = sources_by_id.get(target.source_id)
        if source is None and len(draft.sources) == 1:
            source = draft.sources[0]
            target.source_id = source.source_id
        if source is None:
            raise KeyError(f"missing source for target {target.target_id}")
        target = import_rules.apply_target_import_rules(source=source, target=target)
        compiled = mapping_service.compile_target(
            target=target,
            source_columns=source.columns,
            source_file_id=source.file_id,
            source_filename=source.filename,
            inferred_source_kind=source.inferred_kind,
            schema_object=schema_lookup.get((target.object_type, target.object_name)),
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
        space_name=draft.space_name,
        template_type=template_meta["template_type"],
        integration_scope=space_summary.integration_scope,
        workspace_mode=draft.workspace_mode,
        file_ids=[source.file_id for source in draft.sources],
        sources=draft.sources,
        targets=targets,
        schema_create_plan=schema_plan,
        update_strategy=draft.update_strategy,
        rank_generation_strategy="system_generated"
        if any(item.object_type == "edge_type" and not item.identity_mapping.rank_column for item in draft.mapping)
        else "preserve_input",
        postprocess_options=draft.postprocess_options,
        warnings=warnings,
        integration_level=integration_level,
    )
    return plan, warnings, integration_warnings
