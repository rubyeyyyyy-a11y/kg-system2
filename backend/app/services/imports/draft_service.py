import time

from app.object_meta import import_rules
from app.core.space_context import get_current_space
from fastapi import UploadFile
from app.services.imports import file_store, source_service, validation_service
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import DraftSource, ImportDraft, ImportTargetConfig

_DRAFT_SOURCE_SAMPLE_ROWS = 20


async def save_upload(file: UploadFile):
    return await file_store.save_upload(file)


def _build_sources(payload: dict, existing: ImportDraft | None) -> list[DraftSource]:
    raw_sources = list(payload.get("sources") or [])
    if raw_sources:
        file_ids = [str(item.get("file_id") or "") for item in raw_sources if str(item.get("file_id") or "").strip()]
        if file_ids:
            return source_service.build_sources(file_ids, sample_rows=_DRAFT_SOURCE_SAMPLE_ROWS)
    file_ids = list(payload.get("file_ids") or [])
    if file_ids:
        return source_service.build_sources(file_ids, sample_rows=_DRAFT_SOURCE_SAMPLE_ROWS)
    if existing and existing.sources:
        return list(existing.sources)
    if existing and existing.file_ids:
        return source_service.build_sources(list(existing.file_ids), sample_rows=_DRAFT_SOURCE_SAMPLE_ROWS)
    return []


def _normalize_mapping(
    *,
    raw_mapping: list[dict],
    sources: list[DraftSource],
    discriminator_column: str | None,
) -> list[ImportTargetConfig]:
    first_source_id = sources[0].source_id if sources else ""
    sources_by_id = {source.source_id: source for source in sources}
    normalized: list[ImportTargetConfig] = []
    for item in raw_mapping:
        payload = dict(item)
        if not payload.get("source_id"):
            payload["source_id"] = first_source_id
        if discriminator_column and not payload.get("row_selector") and payload.get("discriminator_value"):
            payload["row_selector"] = {
                "column": discriminator_column,
                "equals": payload.get("discriminator_value"),
            }
        target = ImportTargetConfig.model_validate(payload)
        source = sources_by_id.get(target.source_id)
        if source is not None:
            target = import_rules.apply_target_import_rules(source=source, target=target)
        normalized.append(target)
    return normalized


def _status_for_draft(*, sources: list[DraftSource], mapping: list[ImportTargetConfig]) -> str:
    if mapping:
        return "mapped"
    if sources:
        return "preview_ready"
    return "files_uploaded"


def _normalize_existing_draft(draft: ImportDraft) -> ImportDraft:
    sources = list(draft.sources)
    if not sources and draft.file_ids:
        sources = source_service.build_sources(list(draft.file_ids), sample_rows=_DRAFT_SOURCE_SAMPLE_ROWS)
    if sources:
        draft.sources = sources
        draft.file_ids = [source.file_id for source in sources]
    if draft.mapping:
        draft.mapping = _normalize_mapping(raw_mapping=[item.model_dump() for item in draft.mapping], sources=sources, discriminator_column=None)
    return draft


def upsert_draft(payload: dict) -> ImportDraft:
    now = int(time.time())
    draft_id = str(payload.get("draft_id") or file_store.new_id("draft"))
    current_space = get_current_space()
    existing = None
    try:
        existing = _normalize_existing_draft(file_store.load_draft(draft_id))
    except Exception:
        existing = None

    sources = _build_sources(payload, existing)
    file_ids = [source.file_id for source in sources]
    if len(file_ids) > file_store.MAX_DRAFT_FILES:
        raise_import_http_error(
            status_code=422,
            error_code="IMPORT_DRAFT_FILE_LIMIT_EXCEEDED",
            message=f"draft file count exceeds max {file_store.MAX_DRAFT_FILES}",
            field="file_ids",
            extra={"max_draft_files": file_store.MAX_DRAFT_FILES},
        )
    total_size_bytes = file_store.sum_file_sizes(file_ids)
    if total_size_bytes > file_store.MAX_DRAFT_TOTAL_BYTES:
        raise_import_http_error(
            status_code=422,
            error_code="IMPORT_DRAFT_TOTAL_SIZE_EXCEEDED",
            message=f"draft total size exceeds max {file_store.MAX_DRAFT_TOTAL_BYTES} bytes",
            field="file_ids",
            extra={
                "max_draft_total_bytes": file_store.MAX_DRAFT_TOTAL_BYTES,
                "draft_total_bytes": total_size_bytes,
            },
        )
    existing_space_name = str(existing.space_name or current_space) if existing else current_space
    if existing is not None and existing_space_name != current_space:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_DRAFT_NOT_FOUND",
            message=f"draft `{draft_id}` not found in current space `{current_space}`",
            field="draft_id",
        )

    raw_mapping = payload.get("mapping")
    if raw_mapping is None and existing is not None:
        raw_mapping = [item.model_dump() for item in existing.mapping]
    discriminator_column = str(payload.get("discriminator_column") or "").strip() or None
    mapping = _normalize_mapping(raw_mapping=list(raw_mapping or []), sources=sources, discriminator_column=discriminator_column)
    workspace_mode = payload.get("workspace_mode") or payload.get("mode") or (existing.workspace_mode if existing else "vertex")
    draft = ImportDraft(
        draft_id=draft_id,
        space_name=existing_space_name,
        status=_status_for_draft(sources=sources, mapping=mapping),
        workspace_mode=workspace_mode,
        file_ids=file_ids,
        sources=sources,
        mapping=mapping,
        update_strategy=payload.get("update_strategy") or (existing.update_strategy if existing else {}),
        schema_options=payload.get("schema_options") or (existing.schema_options if existing else {}),
        postprocess_options=payload.get("postprocess_options") or (existing.postprocess_options if existing else {}),
        created_at=existing.created_at if existing else now,
        updated_at=now,
        validation=None,
    )
    file_store.save_draft(draft)
    return draft


def get_draft(draft_id: str) -> ImportDraft:
    try:
        draft = _normalize_existing_draft(file_store.load_draft(draft_id))
    except Exception:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_DRAFT_NOT_FOUND",
            message=f"draft `{draft_id}` not found",
            field="draft_id",
        )
    if str(draft.space_name or get_current_space()) != get_current_space():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_DRAFT_NOT_FOUND",
            message=f"draft `{draft_id}` not found",
            field="draft_id",
        )
    if not draft.space_name:
        draft.space_name = get_current_space()
    file_store.save_draft(draft)
    return draft


def validate_and_persist(draft_id: str) -> ImportDraft:
    draft = get_draft(draft_id)
    validation = validation_service.validate_draft(draft)
    draft.validation = validation
    draft.status = "validated" if validation.passed else "mapped"
    draft.updated_at = int(time.time())
    file_store.save_draft(draft)
    return draft
