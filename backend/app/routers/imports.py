from pathlib import Path

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.core.space_context import get_current_space
from app.schemas.imports import (
    ImportDraftResp,
    ImportDraftUpsertRequest,
    ImportDraftValidationResp,
    ImportFileUploadResp,
    ImportJobCreateRequest,
    ImportJobLogsResp,
    ImportJobResp,
    ImportPostprocessReconcileRequest,
    ImportPostprocessReconcileResp,
    ImportPreviewRequest,
    ImportPreviewResp,
    ImportSchemaPlanRequest,
    ImportSchemaPlanResp,
    ImportSchemaResp,
)
from app.services.imports import (
    draft_service,
    executor_service,
    file_store,
    job_service,
    postprocess_reconcile_service,
    preview_service,
    schema_service,
    source_service,
)
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import ImportTargetConfig, SchemaOptions
from app.services.spaces import validation_service

router = APIRouter(prefix="/api/import")


def _require_ready_import_space() -> str:
    space_name = get_current_space()
    validation_service.ensure_space_ready(space_name)
    return space_name


@router.post("/files", response_model=ImportFileUploadResp)
async def upload_file(file: UploadFile = File(...)):
    _require_ready_import_space()
    record = await file_store.save_upload(file)
    return record.model_dump()


@router.post("/preview", response_model=ImportPreviewResp)
def import_preview(req: ImportPreviewRequest):
    _require_ready_import_space()
    return preview_service.build_preview(
        file_ids=req.file_ids,
        sample_rows=req.sample_rows,
        mode_hint=req.mode_hint,
    )


@router.get("/schema", response_model=ImportSchemaResp)
def import_schema():
    return schema_service.introspect_schema()


@router.post("/schema/plan", response_model=ImportSchemaPlanResp)
def import_schema_plan(req: ImportSchemaPlanRequest):
    _require_ready_import_space()
    sources = (
        [item.model_dump() for item in req.sources]
        if req.sources
        else [item.model_dump() for item in source_service.build_sources(req.file_ids, sample_rows=file_store.MAX_SAMPLE_ROWS)]
    )
    source_models = {item["source_id"]: item for item in sources}
    mapping_payload = []
    for item in req.mapping:
        payload = item.model_dump()
        if not payload.get("source_id") and sources:
            payload["source_id"] = sources[0]["source_id"]
        mapping_payload.append(payload)
    schema = schema_service.introspect_schema()
    schema_plan, warnings, integration_warnings = schema_service.build_schema_plan(
        schema=schema,
        mapping=[ImportTargetConfig.model_validate(item) for item in mapping_payload],
        sources_by_id={key: source_service.build_source_snapshot(value["file_id"], sample_rows=file_store.MAX_SAMPLE_ROWS) for key, value in source_models.items()},
        schema_options=SchemaOptions.model_validate(req.schema_options.model_dump()),
    )
    return {
        "schema_create_plan": [item.model_dump() for item in schema_plan],
        "warnings": warnings,
        "integration_warnings": integration_warnings,
    }


@router.post("/drafts", response_model=ImportDraftResp)
def upsert_import_draft(req: ImportDraftUpsertRequest):
    _require_ready_import_space()
    draft = draft_service.upsert_draft(req.model_dump())
    return draft.model_dump()


@router.get("/drafts/{draft_id}", response_model=ImportDraftResp)
def get_import_draft(draft_id: str):
    _require_ready_import_space()
    return draft_service.get_draft(draft_id).model_dump()


@router.post("/drafts/{draft_id}/validate", response_model=ImportDraftValidationResp)
def validate_import_draft(draft_id: str):
    _require_ready_import_space()
    draft = draft_service.validate_and_persist(draft_id)
    return draft.validation.model_dump()


@router.post("/jobs", response_model=ImportJobResp)
def create_import_job(req: ImportJobCreateRequest):
    _require_ready_import_space()
    state = job_service.create_job(draft_id=req.draft_id, created_by=req.created_by)
    executor_service.ensure_worker_running()
    return state.model_dump()


@router.post("/reconcile", response_model=ImportPostprocessReconcileResp)
def reconcile_import_postprocess(req: ImportPostprocessReconcileRequest):
    _require_ready_import_space()
    result = postprocess_reconcile_service.reconcile_postprocess(
        space_name=req.space_name,
        job_id=req.job_id,
        actor=req.actor,
        refresh_metadata=req.refresh_metadata,
        sync_scope=req.sync_scope,
    )
    return result


@router.get("/jobs", response_model=list[ImportJobResp])
def list_import_jobs():
    return [item.model_dump() for item in job_service.list_jobs()]


@router.get("/jobs/{job_id}", response_model=ImportJobResp)
def get_import_job(job_id: str):
    return job_service.get_job(job_id).model_dump()


@router.get("/jobs/{job_id}/logs", response_model=ImportJobLogsResp)
def get_import_job_logs(job_id: str):
    job_service.get_job(job_id)
    return {"job_id": job_id, "lines": file_store.load_job_log_lines(job_id)}


@router.get("/jobs/{job_id}/failed_rows")
def download_failed_rows(job_id: str):
    state = job_service.get_job(job_id)
    path = Path(state.failed_rows_path or "")
    if not path.exists():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_FAILED_ROWS_NOT_FOUND",
            message="failed_rows artifact not found for this job",
            field="job_id",
        )
    return FileResponse(path, filename=path.name, media_type="text/csv")


@router.get("/jobs/{job_id}/artifacts/{artifact_name}")
def download_job_artifact(job_id: str, artifact_name: str):
    state = job_service.get_job(job_id)
    artifact = next((item for item in state.artifacts if item.filename == artifact_name), None)
    if artifact is None:
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_ARTIFACT_NOT_FOUND",
            message=f"artifact `{artifact_name}` not found for job `{job_id}`",
            field="artifact_name",
        )
    path = Path(artifact.path)
    if not path.exists():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_ARTIFACT_NOT_FOUND",
            message=f"artifact `{artifact_name}` not found for job `{job_id}`",
            field="artifact_name",
        )
    media_type = "application/json" if artifact.kind == "summary" else "text/csv"
    return FileResponse(path, filename=artifact.filename, media_type=media_type)


@router.post("/jobs/{job_id}/cancel", response_model=ImportJobResp)
def cancel_import_job(job_id: str):
    return job_service.cancel_job(job_id).model_dump()
