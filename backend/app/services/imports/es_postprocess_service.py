from typing import Any

from app.clients.es_client import ElasticsearchClient
from app.clients.nebula_client import NebulaClient
from app.services.common import normalize_raw_id, vw


def _build_doc(row: dict[str, Any]) -> dict[str, Any]:
    raw_id = str(row.get("raw_id") or "")
    raw_id_norm = normalize_raw_id(raw_id)
    entity_type = str(row.get("entity_type") or "")
    return {
        "vid": int(row["vid"]),
        "entity_name": str(row.get("label") or ""),
        "description": str(row.get("description") or ""),
        "entity_raw_id": raw_id,
        "entity_raw_id_text": raw_id,
        "raw_id_norm": raw_id_norm,
        "raw_id_norm_text": raw_id_norm,
        "entity_type": entity_type,
        "entity_type_text": entity_type,
        "source": str(row.get("source") or ""),
    }


def sync_entities(vids: list[int]) -> dict[str, Any]:
    unique_vids = sorted({int(vid) for vid in vids if int(vid) > 0})
    if not unique_vids:
        return {"skipped": True, "reason": "no_entity_vids"}
    nebula = NebulaClient()
    rows, _took_ms = nebula.fetch_entity_props(unique_vids)
    docs = [_build_doc(row) for row in rows]
    es = ElasticsearchClient()
    es.ensure_index()
    ok_count, fail_count, bulk_ms = es.bulk_upsert(docs)
    return {
        "skipped": False,
        "input_vids": len(unique_vids),
        "docs": len(docs),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "bulk_ms": bulk_ms,
    }
