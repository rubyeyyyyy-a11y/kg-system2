from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.space_context import resolve_request_space
from app.schemas.spaces import CreateSpaceRequest, CreateSpaceResp, CurrentSpaceResp, SpaceSummaryResp
from app.services.spaces import provisioning_service, readiness_service, registry_service

router = APIRouter(prefix="/api/spaces")


@router.get("", response_model=list[SpaceSummaryResp])
def list_spaces():
    return [readiness_service.build_space_summary_payload(item) for item in registry_service.list_spaces()]


@router.get("/current", response_model=CurrentSpaceResp)
def current_space(request: Request):
    resolved = resolve_request_space(request)
    return readiness_service.build_current_space_payload(
        space_name=resolved.space_name,
        source=resolved.source,
        header_present=resolved.header_present,
        header_value=resolved.header_value,
        registry_status=resolved.registry_status,
    )


@router.get("/{space_name}", response_model=SpaceSummaryResp)
def get_space(space_name: str):
    space = registry_service.get_space(space_name)
    if space is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"error_code": "SPACE_NOT_FOUND", "message": f"space `{space_name}` not found"})
    return readiness_service.build_space_summary_payload(space)


@router.post("", response_model=CreateSpaceResp)
def create_space(req: CreateSpaceRequest):
    summary, warnings = provisioning_service.create_space(
        space_name=req.space_name,
        display_name=req.display_name,
        description=req.description,
        template_type=req.template_type,
        created_by=req.created_by,
    )
    return {
        "space": summary.model_dump(),
        "status": summary.status,
        "integration_scope": summary.integration_scope,
        "warnings": warnings,
    }
