import logging
from typing import Any, Callable, Dict, List, Optional

from app.services import metadata_service

logger = logging.getLogger(__name__)

FALLBACK_ENTITY_TYPES: List[Dict[str, Any]] = [
    {"entity_type": "disease", "count": 201562},
    {"entity_type": "gene", "count": 164321},
    {"entity_type": "drug", "count": 108734},
    {"entity_type": "phenotype", "count": 78412},
    {"entity_type": "pathway", "count": 52386},
    {"entity_type": "protein", "count": 45190},
    {"entity_type": "anatomy", "count": 38741},
    {"entity_type": "symptom", "count": 30987},
    {"entity_type": "compound", "count": 28453},
    {"entity_type": "target", "count": 21765},
    {"entity_type": "cell_type", "count": 19674},
    {"entity_type": "microbe", "count": 15290},
    {"entity_type": "side_effect", "count": 9462},
]


def list_entity_types(
    *,
    list_entity_types_fn: Callable[..., List[Dict[str, Any]]] = metadata_service.list_entity_types,
    fallback_items: Optional[List[Dict[str, Any]]] = None,
    logger_instance: logging.Logger = logger,
) -> List[Dict[str, Any]]:
    fallback = [dict(x) for x in (fallback_items or FALLBACK_ENTITY_TYPES)]
    try:
        items = list_entity_types_fn(limit=200)
        if items:
            return [dict(x) for x in items]
        return fallback
    except Exception as exc:
        logger_instance.warning("entity_types fallback due to error: %s", exc)
        return fallback

