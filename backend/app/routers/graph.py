from fastapi import APIRouter, Query

from app.core.space_context import get_current_space
from app.schemas.discovery import (
    DiscoveryEntityCandidatesRequest,
    DiscoveryEntityCandidatesResp,
    GraphDiscoveryExpandRequest,
    GraphDiscoveryExpandResp,
    GraphDiscoveryRequest,
    GraphDiscoveryResp,
)
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
from app.services import discovery_entity_candidate_service, graph_discovery_expand_service, graph_discovery_service, graph_service
from app.services.spaces.template_service import DISCOVERY_WARNING
from app.services.spaces.readiness_service import current_space_meta_payload

router = APIRouter(prefix="/api")


def _apply_discovery_contract(payload: dict):
    request_space = get_current_space()
    space_meta = current_space_meta_payload()
    warnings = list(payload.get("warnings") or [])

    payload["request_space"] = request_space
    payload["space_meta"] = space_meta

    if str(space_meta.get("space_name") or "").strip() != str(request_space or "").strip():
        warnings.append(DISCOVERY_WARNING)

    if str(space_meta.get("graph_status") or "").strip() != "ready":
        warnings.append(DISCOVERY_WARNING)

    if warnings:
        payload["warnings"] = list(dict.fromkeys(warnings))
    else:
        payload["warnings"] = []

    return payload


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
    payload = graph_discovery_service.discovery(req)
    return _apply_discovery_contract(payload)


@router.post("/graph/discovery/expand", response_model=GraphDiscoveryExpandResp)
def graph_discovery_expand(req: GraphDiscoveryExpandRequest):
    payload = graph_discovery_expand_service.expand(req)
    return _apply_discovery_contract(payload)


@router.post("/discovery/entity_candidates", response_model=DiscoveryEntityCandidatesResp)
def discovery_entity_candidates(req: DiscoveryEntityCandidatesRequest):
    return discovery_entity_candidate_service.entity_candidates(req)
