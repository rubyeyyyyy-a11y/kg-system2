from fastapi import APIRouter

from app.schemas.graph import (
    ExpandRequest,
    MultiEntityGraphApplyPathsRequest,
    MultiEntityGraphRequest,
    MultiEntityGraphResp,
    SubgraphRequest,
)
from app.services import graph_service

router = APIRouter(prefix="/api")


@router.post("/subgraph")
def subgraph(req: SubgraphRequest):
    return graph_service.subgraph(req)


@router.post("/expand")
def expand(req: ExpandRequest):
    return graph_service.expand(req)


@router.get("/relation_types")
def relation_types():
    return graph_service.relation_types()


@router.post("/multi_entity_graph", response_model=MultiEntityGraphResp)
def multi_entity_graph(req: MultiEntityGraphRequest):
    return graph_service.multi_entity_graph(req)


@router.post("/multi_entity_graph_apply_paths", response_model=MultiEntityGraphResp)
def multi_entity_graph_apply_paths(req: MultiEntityGraphApplyPathsRequest):
    return graph_service.multi_entity_graph_apply_paths(req)
