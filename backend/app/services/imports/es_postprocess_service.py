from typing import Any

from app.clients.es_client import ElasticsearchClient
from app.core.space_context import get_current_space
from app.services.search_v2 import indexing_service
from app.services.spaces.index_status_service import (
    calculate_space_index_status_summary,
    update_index_status_from_summary,
)
from app.services.spaces import readiness_service, registry_service

_VERIFY_FETCH_BATCH_SIZE = 1000


def _verify_imported_entities_visible(
    vids: list[int],
    *,
    space_name: str,
    es_client: ElasticsearchClient | None = None,
) -> dict[str, Any]:
    client = es_client or ElasticsearchClient()
    unique_vids = sorted({int(vid) for vid in vids if int(vid) > 0})
    if not unique_vids:
        return {
            "ok": True,
            "expected_docs": 0,
            "found_docs": 0,
            "missing_vids": [],
            "sample_query_ok": True,
            "sample_hits": {},
        }

    rows = indexing_service.fetch_entity_rows(space_name, vids=unique_vids)
    nebula_vids = sorted({int(row["vid"]) for row in rows})
    missing_in_nebula = [vid for vid in unique_vids if vid not in set(nebula_vids)]
    expected_vids = nebula_vids
    docs: list[dict[str, Any]] = []
    fetch_ms = 0.0
    for offset in range(0, len(expected_vids), _VERIFY_FETCH_BATCH_SIZE):
        batch_docs, batch_fetch_ms = client.fetch_documents_by_ids(
            space_name,
            expected_vids[offset : offset + _VERIFY_FETCH_BATCH_SIZE],
        )
        docs.extend(batch_docs)
        fetch_ms += float(batch_fetch_ms)

    found_vids: set[int] = set()
    space_name_mismatch_vids: list[int] = []
    for doc in docs:
        source = doc.get("_source") or {}
        if not doc.get("found"):
            continue
        try:
            vid = int(source.get("vid"))
        except Exception:
            continue
        if str(source.get("space_name") or "") != space_name:
            space_name_mismatch_vids.append(vid)
            continue
        found_vids.add(vid)

    missing_vids = sorted({*missing_in_nebula, *[vid for vid in expected_vids if vid not in found_vids]})
    sample_query_ok = True
    sample_hits: dict[str, list[int]] = {}
    for row in rows[:3]:
        vid = int(row["vid"])
        raw_id = str(row.get("raw_id") or "")
        label = str(row.get("label") or "")
        matched_vids: list[int] = []
        if raw_id:
            raw_norm = indexing_service.normalize_raw_id(raw_id)
            if raw_norm:
                hits, _ = client.search_entity_vids_by_raw_id_norm(
                    raw_norm,
                    raw_id_original=raw_id,
                    mode="exact",
                    limit=5,
                    space_name=space_name,
                    entity_type=None,
                    source=None,
                )
                matched_vids = [int(hit_vid) for hit_vid, _score in hits]
                sample_hits[f"raw_id:{vid}"] = matched_vids
        if vid not in matched_vids and label:
            hits, _ = client.search_entity_vids(
                label,
                limit=5,
                offset=0,
                space_name=space_name,
                search_in_name=True,
                search_in_description=False,
                search_in_type=False,
                search_in_raw_id=False,
                entity_type=None,
                source=None,
            )
            matched_vids = [int(hit_vid) for hit_vid, _score in hits]
            sample_hits[f"label:{vid}"] = matched_vids
        if vid not in matched_vids:
            sample_query_ok = False

    return {
        "ok": len(missing_vids) <= 0 and len(space_name_mismatch_vids) <= 0 and sample_query_ok,
        "expected_docs": len(unique_vids),
        "found_docs": len(found_vids),
        "missing_vids": missing_vids,
        "missing_in_nebula": missing_in_nebula,
        "space_name_mismatch_vids": space_name_mismatch_vids,
        "sample_query_ok": sample_query_ok,
        "sample_hits": sample_hits,
        "fetch_ms": round(fetch_ms, 3),
    }


def sync_entities(vids: list[int], *, space_name: str | None = None) -> dict[str, Any]:
    resolved_space = str(space_name or get_current_space())
    return indexing_service.sync_entities(vids, space_name=resolved_space, refresh="wait_for")


def post_verify_index(vids: list[int], *, space_name: str | None = None) -> dict[str, Any]:
    resolved_space = str(space_name or get_current_space())
    try:
        imported_visibility = _verify_imported_entities_visible(vids, space_name=resolved_space)
    except Exception as exc:
        raise RuntimeError(f"verify_failed: {exc}") from exc

    try:
        index_status_summary = calculate_space_index_status_summary(resolved_space)
    except Exception as exc:
        raise RuntimeError(f"verify_failed: {exc}") from exc

    try:
        index_status_payload = update_index_status_from_summary(resolved_space, index_status_summary)
        index_status_summary["index_status"] = None if index_status_payload is None else index_status_payload.model_dump()
        space_meta = readiness_service.space_meta_payload_for_space(resolved_space)
    except Exception as exc:
        raise RuntimeError(f"registry_write_failed: {exc}") from exc

    index_status_snapshot = space_meta.get("index_status")
    verify_success = bool(imported_visibility["ok"]) and (
        bool((index_status_summary.get("verify") or {}).get("ok")) or index_status_summary["status"] == "verified_empty"
    )
    registry_index_status_written = index_status_snapshot is not None
    searchable = verify_success and registry_index_status_written
    note = str(index_status_summary.get("note") or "")
    if vids and not imported_visibility["ok"]:
        note = (
            "imported_docs_not_searchable "
            f"missing_vids={imported_visibility['missing_vids']} "
            f"missing_in_nebula={imported_visibility['missing_in_nebula']}"
        )
    failure_stage = None
    if not verify_success:
        failure_stage = "verify_failed"
    elif not registry_index_status_written:
        failure_stage = "registry_write_failed"
    completion_summary = {
        "nebula_write_success": True,
        "post_es_sync_success": True,
        "verify_success": verify_success,
        "registry_index_status_written": registry_index_status_written,
        "imported_docs_visible": bool(imported_visibility["ok"]),
        "searchable": searchable,
        "affected_entity_count": len(sorted({int(vid) for vid in vids if int(vid) > 0})),
        "search_status": space_meta.get("search_status"),
        "index_status": index_status_summary["status"],
        "coverage_pct": index_status_summary.get("coverage_pct"),
        "note": note,
        "completed_at": registry_service._now_iso(),
        "failure_stage": failure_stage,
    }
    return {
        "space_name": resolved_space,
        "space_meta": space_meta,
        "imported_visibility": imported_visibility,
        "index_status_snapshot": index_status_snapshot,
        "index_status_summary": index_status_summary,
        "completion_summary": completion_summary,
    }
