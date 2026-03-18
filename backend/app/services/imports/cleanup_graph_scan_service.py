import os
from typing import Any

from app.clients.nebula_client import NebulaClient
from app.config import settings

_LIVE_SCAN_MAX_EDGES = max(0, int(os.getenv("IMPORT_CLEANUP_LIVE_SCAN_MAX_EDGES", "200000")))
_LIVE_SCAN_SAMPLE_LIMIT = max(1, int(os.getenv("IMPORT_CLEANUP_LIVE_SCAN_SAMPLE_LIMIT", "20")))


def _relation_key_from_edge(edge: dict[str, Any]) -> tuple[str, int, int, int]:
    return (
        str(edge.get("edge_type") or settings.edge_type or "REL2"),
        int(edge.get("src_vid") or 0),
        int(edge.get("dst_vid") or 0),
        int(edge.get("rank") or 0),
    )


def check_entity_live_references(
    *,
    space_id: str,
    vid: int,
    excluding_relation_keys: set[tuple[str, int, int, int]] | None = None,
    edge_type: str | None = None,
) -> dict[str, Any]:
    normalized_vid = int(vid)
    if normalized_vid <= 0:
        return {
            "vid": normalized_vid,
            "has_blockers": False,
            "live_blocking_edges": [],
            "live_blocking_count": 0,
            "scan_note": "invalid vid skipped from live graph scan",
            "truncated": False,
            "warning": None,
            "scanned_incident_edge_count": 0,
            "excluded_by_plan_count": 0,
            "scan_edge_type": str(edge_type or settings.edge_type or "REL2"),
            "took_ms": 0.0,
        }
    client = NebulaClient(space_name=space_id)
    incident_edges, took_ms = client.fetch_incident_edges(
        normalized_vid,
        edge_type=edge_type or settings.edge_type,
        limit=_LIVE_SCAN_MAX_EDGES if _LIVE_SCAN_MAX_EDGES > 0 else None,
        space_name=space_id,
    )
    excluding = set(excluding_relation_keys or set())
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, int]] = set()
    excluded_count = 0
    for edge in incident_edges:
        key = _relation_key_from_edge(edge)
        if key in seen:
            continue
        seen.add(key)
        if key in excluding:
            excluded_count += 1
            continue
        deduped.append(
            {
                "edge_type": key[0],
                "src_vid": key[1],
                "dst_vid": key[2],
                "rank": key[3],
                "relation": str(edge.get("relation") or ""),
            }
        )
    truncated = bool(_LIVE_SCAN_MAX_EDGES > 0 and len(incident_edges) >= _LIVE_SCAN_MAX_EDGES)
    warning = None
    if truncated:
        warning = (
            f"incident edge scan may be truncated at max_edges={_LIVE_SCAN_MAX_EDGES}; "
            "cleanup should be retried with a higher limit for strict verification"
        )
    scan_note = (
        f"live scan checks incident `{str(edge_type or settings.edge_type or 'REL2')}` edges in Nebula, "
        "then excludes edges planned for deletion by relation key (edge_type/src_vid/dst_vid/rank)"
    )
    return {
        "vid": normalized_vid,
        "has_blockers": len(deduped) > 0,
        "live_blocking_edges": deduped[:_LIVE_SCAN_SAMPLE_LIMIT],
        "live_blocking_count": len(deduped),
        "scan_note": scan_note,
        "truncated": truncated,
        "warning": warning,
        "scanned_incident_edge_count": len(seen),
        "excluded_by_plan_count": excluded_count,
        "scan_edge_type": str(edge_type or settings.edge_type or "REL2"),
        "took_ms": round(float(took_ms), 3),
    }
