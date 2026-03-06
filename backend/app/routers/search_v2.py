from typing import Optional

from fastapi import APIRouter

from app.schemas.search import RawIdSuggestResp, SearchRequest, SuggestResp
from app.services.search_v2 import service as search_v2_service

router = APIRouter(prefix="/api/v2")


@router.post("/search")
def search(req: SearchRequest):
    return search_v2_service.search(req)


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

