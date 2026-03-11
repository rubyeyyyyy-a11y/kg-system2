import time

from app.services.imports.errors import raise_import_http_error
from app.services.imports import file_store, validation_service
from app.services.imports.models import ImportDraft


def upsert_draft(payload: dict) -> ImportDraft:
    now = int(time.time())
    draft_id = str(payload.get("draft_id") or file_store.new_id("draft"))
    existing = None
    try:
        existing = file_store.load_draft(draft_id)
    except Exception:
        existing = None
    status = "files_uploaded"
    if payload.get("mapping"):
        status = "mapped"
    elif payload.get("file_ids"):
        status = "preview_ready"
    validation = existing.validation if existing else None
    next_file_ids = list(payload.get("file_ids") or (existing.file_ids if existing else []))
    if len(next_file_ids) > file_store.MAX_DRAFT_FILES:
        raise_import_http_error(
            status_code=422,
            error_code="IMPORT_DRAFT_FILE_LIMIT_EXCEEDED",
            message=f"draft file count exceeds max {file_store.MAX_DRAFT_FILES}",
            field="file_ids",
            extra={"max_draft_files": file_store.MAX_DRAFT_FILES},
        )
    draft = ImportDraft(
        draft_id=draft_id,
        status=status,
        mode=payload.get("mode") or (existing.mode if existing else "vertex"),
        file_ids=next_file_ids,
        discriminator_column=payload.get("discriminator_column"),
        mapping=payload.get("mapping") or [],
        update_strategy=payload.get("update_strategy") or {},
        schema_options=payload.get("schema_options") or {},
        postprocess_options=payload.get("postprocess_options") or {},
        created_at=existing.created_at if existing else now,
        updated_at=now,
        validation=None,
    )
    file_store.save_draft(draft)
    return draft


def get_draft(draft_id: str) -> ImportDraft:
    try:
        return file_store.load_draft(draft_id)
    except Exception:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_DRAFT_NOT_FOUND",
            message=f"draft `{draft_id}` not found",
            field="draft_id",
        )


def validate_and_persist(draft_id: str) -> ImportDraft:
    draft = get_draft(draft_id)
    validation = validation_service.validate_draft(draft)
    draft.validation = validation
    draft.status = "validated" if validation.passed else "mapped"
    draft.updated_at = int(time.time())
    file_store.save_draft(draft)
    return draft
