from typing import Optional

from fastapi import APIRouter

from app.schemas.edge import EdgeSearchRequest, EdgeSearchResp, EdgeSuggestResp
from app.schemas.search import EntityTypeItem, RawIdSuggestResp, SearchRequest, SuggestResp
from app.services import edge_search_service, search_service

router = APIRouter(prefix="/api")


@router.post("/search")
def search(req: SearchRequest):
    return search_service.search(req)


@router.get("/entity_types", response_model=list[EntityTypeItem])
def entity_types():
    return search_service.entity_types()


@router.get("/suggest", response_model=SuggestResp)
def suggest(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
):
    return search_service.suggest(q=q, limit=limit, entity_type=entity_type, source=source)


@router.get("/suggest_raw_id", response_model=RawIdSuggestResp)
def suggest_raw_id(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
):
    return search_service.suggest_raw_id(q=q, limit=limit, entity_type=entity_type, source=source)


@router.get("/edge_suggest", response_model=EdgeSuggestResp)
def edge_suggest(
    q: str,
    limit: int = 12,
    relation: Optional[str] = None,
    source_db: Optional[str] = None,
):
    return edge_search_service.edge_suggest(
        q=q,
        limit=limit,
        relation=relation,
        source_db=source_db,
    )


@router.post("/edge_search", response_model=EdgeSearchResp)
def edge_search(req: EdgeSearchRequest):
    return edge_search_service.edge_search(req)
