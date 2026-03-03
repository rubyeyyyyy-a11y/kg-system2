from fastapi import APIRouter

from app.schemas.detail import EdgeDetailRequest, EdgeDetailResp, EdgeUpdateRequest
from app.services import detail_service

router = APIRouter(prefix="/api")


@router.get("/node/{vid}")
def node_detail(vid: int):
    return detail_service.node_detail(vid)


@router.post("/edge_detail", response_model=EdgeDetailResp)
def edge_detail(req: EdgeDetailRequest):
    return detail_service.edge_detail(req)


@router.post("/edge_update", response_model=EdgeDetailResp)
def edge_update(req: EdgeUpdateRequest):
    return detail_service.edge_update(req)
