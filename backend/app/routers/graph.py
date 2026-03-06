from fastapi import APIRouter, Query

from app.schemas.discovery import GraphDiscoveryRequest, GraphDiscoveryResp
from app.schemas.graph import (
    ExpandResp,
    ExpandRequest,
    MultiEntityGraphApplyPathsRequest,
    MultiEntityGraphRequest,
    MultiEntityGraphResp,
    RelationTypesResp,
    SubgraphResp,
    SubgraphRequest,
)
from app.services import graph_discovery_service, graph_service

router = APIRouter(prefix="/api")


@router.post("/subgraph", response_model=SubgraphResp)
def subgraph(req: SubgraphRequest):
    return graph_service.subgraph(req)


@router.post("/expand", response_model=ExpandResp)
def expand(req: ExpandRequest):
    return graph_service.expand(req)


@router.get("/relation_types", response_model=RelationTypesResp)
def relation_types(
    q: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return graph_service.relation_types(q=q, limit=limit, offset=offset)


@router.post("/multi_entity_graph", response_model=MultiEntityGraphResp)
def multi_entity_graph(req: MultiEntityGraphRequest):
    return graph_service.multi_entity_graph(req)


@router.post("/multi_entity_graph_apply_paths", response_model=MultiEntityGraphResp)
def multi_entity_graph_apply_paths(req: MultiEntityGraphApplyPathsRequest):
    return graph_service.multi_entity_graph_apply_paths(req)


@router.post("/graph/discovery", response_model=GraphDiscoveryResp)
def graph_discovery(req: GraphDiscoveryRequest):
    return graph_discovery_service.discovery(req)
