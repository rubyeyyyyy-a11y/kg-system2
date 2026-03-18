from __future__ import annotations

from app.config import settings
from app.services.imports import source_service


def build_system_managed_draft_payload(
    *,
    file_id: str,
    contract_kind: str,
    space_name: str,
) -> dict:
    source = source_service.build_source_snapshot(file_id, sample_rows=20)
    if contract_kind == "entity_csv":
        mapping = [source_service.build_default_target(source=source, object_type="tag", object_name="Entity").model_dump()]
        workspace_mode = "vertex"
    elif contract_kind == "rel2_csv":
        mapping = [
            source_service.build_default_target(source=source, object_type="edge_type", object_name=settings.edge_type).model_dump()
        ]
        workspace_mode = "edge"
    else:
        raise ValueError(f"unsupported contract_kind `{contract_kind}`")

    return {
        "space_name": space_name,
        "workspace_mode": workspace_mode,
        "file_ids": [file_id],
        "sources": [source.model_dump()],
        "mapping": mapping,
        "update_strategy": {
            "mode": "merge_partial",
            "create_if_missing": True,
            "update_existing": True,
        },
        "schema_options": {
            "allow_create_object": True,
            "allow_add_properties": True,
        },
        "postprocess_options": {
            "refresh_metadata": True,
            "sync_entity_es": True,
        },
    }
