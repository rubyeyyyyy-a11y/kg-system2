from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.schemas.imports import (
    ImportDraftResp,
    ImportDraftUpsertRequest,
    ImportDraftValidationResp,
    ImportFileUploadResp,
    ImportJobCreateRequest,
    ImportJobLogsResp,
    ImportJobResp,
    ImportPreviewRequest,
    ImportPreviewResp,
    ImportSchemaPlanRequest,
    ImportSchemaPlanResp,
    ImportSchemaResp,
)
from app.services.imports import draft_service, executor_service, file_store, job_service, preview_service, schema_service
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import ImportTargetConfig, SchemaOptions

router = APIRouter(prefix="/api/import")


@router.post("/files", response_model=ImportFileUploadResp)
async def upload_file(file: UploadFile = File(...)):
    record = await file_store.save_upload(file)
    return record.model_dump()


@router.post("/preview", response_model=ImportPreviewResp)
def import_preview(req: ImportPreviewRequest):
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
    columns = []
    if req.file_ids:
        columns = file_store.read_csv_columns(req.file_ids[0])
    schema = schema_service.introspect_schema()
    schema_plan, warnings, integration_warnings = schema_service.build_schema_plan(
        schema=schema,
        mapping=[ImportTargetConfig.model_validate(item.model_dump()) for item in req.mapping],
        all_columns=columns,
        schema_options=SchemaOptions.model_validate(req.schema_options.model_dump()),
    )
    return {
        "schema_create_plan": [item.model_dump() for item in schema_plan],
        "warnings": warnings,
        "integration_warnings": integration_warnings,
    }


@router.post("/drafts", response_model=ImportDraftResp)
def upsert_import_draft(req: ImportDraftUpsertRequest):
    draft = draft_service.upsert_draft(req.model_dump())
    return draft.model_dump()


@router.get("/drafts/{draft_id}", response_model=ImportDraftResp)
def get_import_draft(draft_id: str):
    return draft_service.get_draft(draft_id).model_dump()


@router.post("/drafts/{draft_id}/validate", response_model=ImportDraftValidationResp)
def validate_import_draft(draft_id: str):
    draft = draft_service.validate_and_persist(draft_id)
    return draft.validation.model_dump()


@router.post("/jobs", response_model=ImportJobResp)
def create_import_job(req: ImportJobCreateRequest):
    state = job_service.create_job(draft_id=req.draft_id, created_by=req.created_by)
    executor_service.ensure_worker_running()
    return state.model_dump()


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
    job_service.get_job(job_id)
    path = file_store.job_failed_rows_path(job_id)
    if not path.exists():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_FAILED_ROWS_NOT_FOUND",
            message="failed_rows.csv not found for this job",
            field="job_id",
        )
    return FileResponse(path, filename=f"{job_id}_failed_rows.csv", media_type="text/csv")


@router.post("/jobs/{job_id}/cancel", response_model=ImportJobResp)
def cancel_import_job(job_id: str):
    return job_service.cancel_job(job_id).model_dump()
