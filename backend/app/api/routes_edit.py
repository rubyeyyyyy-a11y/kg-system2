from fastapi import APIRouter

from app.schemas.edit import EdgePatchRequest, EdgePatchResp, EditableFieldsResp, NodePatchRequest, NodePatchResp
from app.services import edit_service

router = APIRouter(prefix="/api")


@router.get("/schema/editable_fields", response_model=EditableFieldsResp)
def schema_editable_fields():
    return edit_service.editable_fields()


@router.patch("/node/{vid}", response_model=NodePatchResp)
def patch_node(vid: int, req: NodePatchRequest):
    return edit_service.patch_node(vid=vid, req=req)


@router.patch("/edge", response_model=EdgePatchResp)
def patch_edge(req: EdgePatchRequest):
    return edit_service.patch_edge(req=req)
