from __future__ import annotations

from typing import Any

from app.core.space_context import get_current_space
from app.services.spaces import registry_service
from app.services.spaces.models import SpaceReadiness, SpaceSummary


def _graph_ready(summary: SpaceSummary | None) -> bool:
    if summary is None:
        return False
    return summary.status == "ready" and summary.internal_status == "ready"


def _derive_search_status(summary: SpaceSummary | None, *, graph_status: str) -> tuple[str, float | None, Any]:
    search_status = "unavailable"
    coverage_pct = None
    index_status = None

    if summary is not None and summary.index_status is not None:
        index_status = summary.index_status
        coverage_pct = index_status.coverage_pct

    if graph_status == "ready" and index_status is not None:
        raw_index_status = str(index_status.status or "").strip()
        if raw_index_status == "failed":
            search_status = "failed"
        elif raw_index_status == "verified_empty":
            search_status = "empty"
        elif raw_index_status == "verified_partial":
            search_status = "partial"
        elif raw_index_status == "verified_nonempty":
            if coverage_pct is not None and float(coverage_pct) < 100.0:
                search_status = "partial"
            else:
                search_status = "full"

    return search_status, coverage_pct, index_status


def derive_readiness(summary: SpaceSummary | None, *, space_name: str | None = None) -> SpaceReadiness:
    resolved_space = str(space_name or (summary.space_name if summary is not None else "")).strip()
    graph_status = "ready" if _graph_ready(summary) else "unavailable"
    search_status, coverage_pct, index_status = _derive_search_status(summary, graph_status=graph_status)

    return SpaceReadiness(
        space_name=resolved_space,
        graph_status=graph_status,
        search_status=search_status,
        coverage_pct=coverage_pct,
        index_status=index_status,
    )


def build_space_summary_payload(summary: SpaceSummary) -> dict[str, Any]:
    readiness = derive_readiness(summary)
    payload = summary.model_dump()
    payload.update(
        {
            "graph_status": readiness.graph_status,
            "search_status": readiness.search_status,
            "coverage_pct": readiness.coverage_pct,
        }
    )
    return payload


def build_space_meta_payload(readiness: SpaceReadiness) -> dict[str, Any]:
    return {
        "space_name": readiness.space_name,
        "graph_status": readiness.graph_status,
        "search_status": readiness.search_status,
        "coverage_pct": readiness.coverage_pct,
        "index_status": readiness.index_status.model_dump() if readiness.index_status is not None else None,
    }


def space_meta_for_space(space_name: str) -> SpaceReadiness:
    resolved_space = str(space_name or "").strip()
    return derive_readiness(registry_service.get_space(resolved_space), space_name=resolved_space)


def space_meta_payload_for_space(space_name: str) -> dict[str, Any]:
    return build_space_meta_payload(space_meta_for_space(space_name))


def build_current_space_payload(
    *,
    space_name: str,
    source: str,
    header_present: bool,
    header_value: str | None,
    registry_status: str | None,
) -> dict[str, Any]:
    summary = registry_service.get_space(space_name)
    readiness = derive_readiness(summary, space_name=space_name)
    return {
        "source": source,
        "header_present": header_present,
        "header_value": header_value,
        "registry_status": registry_status,
        **build_space_meta_payload(readiness),
    }


def current_space_meta() -> SpaceReadiness:
    space_name = get_current_space()
    return space_meta_for_space(space_name)


def current_space_meta_payload() -> dict[str, Any]:
    return build_space_meta_payload(current_space_meta())
