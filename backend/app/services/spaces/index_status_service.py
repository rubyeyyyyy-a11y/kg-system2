from __future__ import annotations

from typing import Any

from app.clients.es_client import ElasticsearchClient
from app.services import metadata_service
from app.services.search_v2 import indexing_service
from app.services.spaces import registry_service
from app.services.spaces.models import SpaceIndexStatus


def classify_index_status(
    *,
    dry_run: bool,
    fail_count: int,
    verify_result: dict[str, Any] | None,
    nebula_count: int | None = None,
    es_doc_count: int | None = None,
) -> tuple[str, str]:
    if int(fail_count) > 0:
        return "failed", "bulk upsert reported failed documents"

    verified_doc_count = int((verify_result or {}).get("doc_count") or 0)
    resolved_es_doc_count = int(es_doc_count if es_doc_count is not None else verified_doc_count)
    resolved_nebula_count = None if nebula_count is None else int(nebula_count)

    if verify_result is not None and verified_doc_count <= 0 and (resolved_nebula_count or 0) <= 0:
        return "verified_empty", "space is ready but currently has no entity documents"

    if verify_result is not None and not bool(verify_result.get("ok")):
        reasons: list[str] = []
        if not bool(verify_result.get("sample_ids_ok", True)):
            reasons.append("sample_ids_mismatch")
        if not bool(verify_result.get("sample_space_ok", True)):
            reasons.append("sample_space_mismatch")
        if not bool(verify_result.get("sample_query_ok", True)):
            reasons.append("sample_query_failed")
        if not reasons:
            reasons.append("verification_failed")
        return "failed", ",".join(reasons)

    if resolved_nebula_count is not None and resolved_nebula_count > 0 and resolved_es_doc_count < resolved_nebula_count:
        note = (
            f"canonical coverage is partial: es_doc_count={resolved_es_doc_count} "
            f"below nebula_entity_count={resolved_nebula_count}"
        )
        return "verified_partial", note

    if dry_run:
        if (resolved_nebula_count or 0) <= 0 and resolved_es_doc_count <= 0:
            return "verified_empty", "dry-run confirms the ready space is currently empty"
        return "verified_partial", "dry-run scanned the space but skipped ES write and verification"

    if verify_result is None:
        if resolved_es_doc_count <= 0 and (resolved_nebula_count or 0) <= 0:
            return "verified_empty", "ready space currently has no entity documents"
        if resolved_es_doc_count > 0:
            return "verified_partial", "backfill completed without verify; treat coverage as partial until verification runs"
        return "verified_empty", "ready space currently has no canonical entity documents"

    return "verified_nonempty", "space documents match the canonical ES contract"


def build_index_status_payload(
    *,
    status: str,
    note: str,
    doc_count: int | None,
    nebula_entity_count: int | None,
    coverage_pct: float | None,
) -> SpaceIndexStatus | None:
    if status not in {"verified_nonempty", "verified_empty", "verified_partial", "failed"}:
        return None
    return SpaceIndexStatus(
        status=status,
        doc_count=int(doc_count or 0),
        nebula_entity_count=None if nebula_entity_count is None else int(nebula_entity_count),
        coverage_pct=None if coverage_pct is None else round(float(coverage_pct), 2),
        note=str(note or ""),
        updated_at=registry_service._now_iso(),
    )


def build_completion_snapshot(
    *,
    status: str,
    nebula_entity_count: int | None,
    es_doc_count: int | None,
    coverage_pct: float | None,
) -> dict[str, Any]:
    resolved_es_doc_count = int(es_doc_count or 0)
    resolved_nebula_count = None if nebula_entity_count is None else int(nebula_entity_count)
    remaining_docs = None
    if resolved_nebula_count is not None:
        remaining_docs = max(resolved_nebula_count - resolved_es_doc_count, 0)

    full_completion = False
    if status == "verified_empty":
        full_completion = (resolved_nebula_count or 0) <= 0 and resolved_es_doc_count <= 0
    elif status == "verified_nonempty":
        if resolved_nebula_count is None:
            full_completion = coverage_pct is not None and float(coverage_pct) >= 100.0
        else:
            full_completion = resolved_es_doc_count >= resolved_nebula_count and (
                coverage_pct is None or float(coverage_pct) >= 100.0
            )

    return {
        "full_completion": full_completion,
        "remaining_docs": remaining_docs,
        "completion_standard": "canonical_es_doc_count must reach nebula_entity_count with verified canonical samples",
    }


def persist_index_status(space_name: str, payload: SpaceIndexStatus | None) -> SpaceIndexStatus | None:
    if payload is None:
        return None
    summary = registry_service.get_space(space_name)
    if summary is None:
        return payload
    registry_service.update_space(space_name, index_status=payload)
    return payload


def update_index_status_from_summary(space_name: str, summary: dict[str, Any]) -> SpaceIndexStatus | None:
    payload = build_index_status_payload(
        status=str(summary.get("status") or ""),
        note=str(summary.get("note") or ""),
        doc_count=int(summary.get("es_doc_count") or 0),
        nebula_entity_count=summary.get("nebula_entity_count"),
        coverage_pct=summary.get("coverage_pct"),
    )
    return persist_index_status(space_name, payload)


def mark_space_empty_ready(space_name: str, *, note: str = "ready managed space with no entity documents yet") -> SpaceIndexStatus | None:
    payload = build_index_status_payload(
        status="verified_empty",
        note=note,
        doc_count=0,
        nebula_entity_count=0,
        coverage_pct=100.0,
    )
    return persist_index_status(space_name, payload)


def refresh_space_index_status(
    space_name: str,
    *,
    es_client: ElasticsearchClient | None = None,
    index_name: str | None = None,
) -> dict[str, Any]:
    summary = calculate_space_index_status_summary(
        space_name,
        es_client=es_client,
        index_name=index_name,
    )
    payload = persist_index_status(
        space_name,
        build_index_status_payload(
            status=summary["status"],
            note=summary["note"],
            doc_count=summary["es_doc_count"],
            nebula_entity_count=summary["nebula_entity_count"],
            coverage_pct=summary["coverage_pct"],
        ),
    )
    return {
        **summary,
        "index_status": payload.model_dump() if payload is not None else None,
    }


def calculate_space_index_status_summary(
    space_name: str,
    *,
    es_client: ElasticsearchClient | None = None,
    index_name: str | None = None,
) -> dict[str, Any]:
    client = es_client or ElasticsearchClient(index=index_name)
    nebula_count_result = resolve_entity_count(space_name)
    nebula_count = int(nebula_count_result["count"] or 0)
    verify_result = indexing_service.verify_space(space_name, es_client=client, index_name=index_name)
    es_doc_count = int(verify_result.get("doc_count") or 0)
    coverage_pct = 100.0 if nebula_count <= 0 else round((float(es_doc_count) / float(nebula_count)) * 100.0, 2)
    status, note = classify_index_status(
        dry_run=False,
        fail_count=0,
        verify_result=verify_result,
        nebula_count=nebula_count,
        es_doc_count=es_doc_count,
    )
    return {
        "space_name": space_name,
        "status": status,
        "note": note,
        "es_doc_count": es_doc_count,
        "nebula_entity_count": nebula_count,
        "nebula_count_source": nebula_count_result["source"],
        "nebula_count_error": nebula_count_result["error"],
        "coverage_pct": coverage_pct,
        "verify": verify_result,
        **build_completion_snapshot(
            status=status,
            nebula_entity_count=nebula_count,
            es_doc_count=es_doc_count,
            coverage_pct=coverage_pct,
        ),
    }


def resolve_entity_count(space_name: str) -> dict[str, Any]:
    try:
        result = indexing_service.count_entities(space_name)
        return {
            "space_name": space_name,
            "count": int(result["count"]),
            "source": "nebula_match",
            "took_ms": float(result["took_ms"]),
            "error": None,
        }
    except Exception as exc:
        primary_error = str(exc)

    try:
        entity_type_items = metadata_service.list_entity_types(limit=5000, space_name=space_name)
        return {
            "space_name": space_name,
            "count": sum(max(0, int(item.get("count") or 0)) for item in entity_type_items),
            "source": "metadata_stats",
            "took_ms": 0.0,
            "error": primary_error,
        }
    except Exception as fallback_exc:
        return {
            "space_name": space_name,
            "count": None,
            "source": "unavailable",
            "took_ms": 0.0,
            "error": f"{primary_error}; metadata_stats_fallback={fallback_exc}",
        }
