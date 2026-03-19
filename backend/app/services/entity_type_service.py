from typing import Any

from app.services import metadata_service

FALLBACK_ENTITY_TYPES: list[dict[str, Any]] = [
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


def list_entity_types() -> list[dict[str, Any]]:
    try:
        items = metadata_service.list_entity_types(limit=200)
    except Exception:
        items = []
    if items:
        return [dict(item) for item in items]
    return [dict(item) for item in FALLBACK_ENTITY_TYPES]
