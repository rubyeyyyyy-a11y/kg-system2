from fastapi import APIRouter

from app.schemas.detail import EdgeDetailRequest
from app.services import detail_service

router = APIRouter(prefix="/api")


@router.get("/node/{vid}")
def node_detail(vid: int):
    return detail_service.node_detail(vid)


@router.post("/edge_detail")
def edge_detail(req: EdgeDetailRequest):
    return detail_service.edge_detail(req)
