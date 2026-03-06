from fastapi import APIRouter

from app.schemas.detail import EdgeDetailRequest, EdgeDetailResp, NodeDetailResp
from app.services import detail_service

router = APIRouter(prefix="/api")


@router.get("/node/{vid}", response_model=NodeDetailResp)
def node_detail(vid: int):
    return detail_service.node_detail(vid)


@router.get("/node_detail", response_model=NodeDetailResp)
def node_detail_alias(vid: int):
    return detail_service.node_detail(vid)


@router.post("/edge_detail", response_model=EdgeDetailResp)
def edge_detail(req: EdgeDetailRequest):
    return detail_service.edge_detail(req)
