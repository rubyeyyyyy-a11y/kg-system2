from typing import Optional

from fastapi import APIRouter

from app.schemas.search import EntityTypeItem, RawIdSuggestResp, SearchRequest, SearchResp, SuggestResp
from app.platform.metadata import entity_catalog_service
from app.services import metadata_service
from app.services.search_v2 import service as search_v2_service

router = APIRouter(prefix="/api")


@router.post("/search", response_model=SearchResp)
def search(req: SearchRequest):
    return search_v2_service.search(req)


@router.get("/entity_types", response_model=list[EntityTypeItem])
def entity_types():
    return entity_catalog_service.list_entity_types(
        list_entity_types_fn=metadata_service.list_entity_types,
        fallback_items=entity_catalog_service.FALLBACK_ENTITY_TYPES,
    )


@router.get("/suggest", response_model=SuggestResp)
def suggest(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
):
    return search_v2_service.suggest(q=q, limit=limit, entity_type=entity_type, source=source)


@router.get("/suggest_raw_id", response_model=RawIdSuggestResp)
def suggest_raw_id(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
):
    return search_v2_service.suggest_raw_id(q=q, limit=limit, entity_type=entity_type, source=source)
