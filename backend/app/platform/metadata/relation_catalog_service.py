import logging
from typing import Any, Callable, Dict

from app.services import metadata_service

logger = logging.getLogger(__name__)


def query_relation_types(
    *,
    q: str = "",
    limit: int = 100,
    offset: int = 0,
    query_relation_types_fn: Callable[..., Dict[str, Any]] = metadata_service.query_relation_types,
    logger_instance: logging.Logger = logger,
) -> Dict[str, Any]:
    try:
        return query_relation_types_fn(q=q, limit=limit, offset=offset)
    except Exception as exc:
        logger_instance.warning("relation_types metadata fallback: %s", exc)
        safe_limit = max(1, min(int(limit or 100), 200))
        safe_offset = max(0, int(offset or 0))
        return {
            "items": [],
            "q": str(q or "").strip().lower(),
            "limit": safe_limit,
            "offset": safe_offset,
            "next_offset": None,
            "has_more": False,
            "matched_total": 0,
        }
