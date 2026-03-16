from typing import Any, Dict

from app.models.search_models import CandidateNode
from app.schemas.discovery import DiscoveryEntityCandidatesRequest
from app.schemas.search import SearchRequest
from app.services.search_v2 import service as search_v2_service

_DEFAULT_PAGE = 1
_DEFAULT_PAGE_SIZE = 100
_MAX_PAGE_SIZE = 100


def _build_search_request(req: DiscoveryEntityCandidatesRequest) -> SearchRequest:
    return SearchRequest(
        q=str(req.q or ""),
        search_in_name=bool(req.search_in_name),
        search_in_description=bool(req.search_in_description),
        search_in_type=bool(req.search_in_type),
        search_in_raw_id=bool(req.search_in_raw_id),
        include_edges=False,
        entity_type=req.entity_type,
        source=req.source,
        entity_raw_id=req.entity_raw_id,
        entity_raw_id_mode=req.entity_raw_id_mode,
    )


def _to_candidate_item_payload(node: CandidateNode) -> Dict[str, Any]:
    snippet = node.description or ""
    if snippet and len(snippet) > 160:
        snippet = snippet[:160] + "…"

    return {
        "id": int(node.vid),
        "vid": int(node.vid),
        "label": str(node.label or ""),
        "entity_type": str(node.entity_type or ""),
        "raw_id": str(node.raw_id or ""),
        "source": str(node.source or ""),
        "score": None if node.score is None else round(float(node.score), 6),
        "snippet": snippet,
        "description": str(node.description or ""),
    }


def entity_candidates(req: DiscoveryEntityCandidatesRequest) -> Dict[str, Any]:
    page = max(_DEFAULT_PAGE, int(req.page or _DEFAULT_PAGE))
    page_size = max(1, min(int(req.page_size or _DEFAULT_PAGE_SIZE), _MAX_PAGE_SIZE))
    offset = (page - 1) * page_size

    result = search_v2_service.search_candidates_page(
        _build_search_request(req),
        offset=offset,
        limit=page_size,
    )
    nodes = result.get("nodes") or []
    has_more = bool(result.get("has_more"))
    meta = result.get("meta") or {}

    return {
        "items": [_to_candidate_item_payload(node) for node in nodes],
        "page": page,
        "page_size": page_size,
        "returned": len(nodes),
        "has_more": has_more,
        "next_page": page + 1 if has_more else None,
        "space_meta": result.get("space_meta"),
        "meta": meta,
    }
