import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app import config as app_config
from app.clients import ElasticsearchClient
from app.clients.nebula_client import NebulaClient, NebulaConnectionError, NebulaQueryError, NebulaTimeoutError
from app.models import CandidateNode, SearchDiagnostics, SearchResultBundle
from app.platform.metadata import entity_catalog_service
from app.schemas.search import SearchRequest
from app.services.fallback_search import FallbackSearchEngine
from app.services import metadata_service
from app.services.common import esc, normalize_raw_id_for_suggest_prefix, vw

logger = logging.getLogger(__name__)

nebula_client = NebulaClient()
es_client = ElasticsearchClient()
fallback_engine = FallbackSearchEngine(nebula_client)

_ES_HEALTH_CACHE: Dict[str, Any] = {"ok": False, "reason": "cold", "at": 0.0, "ms": 0.0}
_ES_HEALTH_TTL_SEC = 3.0

FALLBACK_ENTITY_TYPES = entity_catalog_service.FALLBACK_ENTITY_TYPES


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _snippet(text: str, max_len: int = 160) -> str:
    value = text or ""
    if len(value) > max_len:
        return value[:max_len] + "…"
    return value


def _http_error(status_code: int, request_id: str, message: str) -> HTTPException:
    safe = (message or "").strip()
    return HTTPException(status_code=status_code, detail=f"request_id={request_id} {safe}")


def _es_health() -> Tuple[bool, float, str]:
    now = time.time()
    if now - float(_ES_HEALTH_CACHE.get("at") or 0.0) < _ES_HEALTH_TTL_SEC:
        return bool(_ES_HEALTH_CACHE.get("ok")), float(_ES_HEALTH_CACHE.get("ms") or 0.0), str(
            _ES_HEALTH_CACHE.get("reason") or ""
        )

    ok, took_ms, reason = es_client.healthcheck()
    _ES_HEALTH_CACHE.update({"ok": ok, "reason": reason, "at": now, "ms": took_ms})
    return ok, took_ms, reason


def _should_use_es(req: SearchRequest) -> bool:
    if not app_config.settings.es_enabled:
        return False
    if (req.entity_raw_id or "").strip():
        return False
    q = (req.q or "").strip()
    if len(q) < app_config.settings.search_min_query_len:
        return False
    return True


def _es_search(req: SearchRequest, request_id: str) -> Tuple[SearchResultBundle, float, float, str]:
    q = (req.q or "").strip()
    vids_scores, es_ms = es_client.search_entity_vids(
        q,
        limit=app_config.settings.es_topk,
        search_in_name=req.search_in_name,
        search_in_description=req.search_in_description,
        search_in_type=req.search_in_type,
        search_in_raw_id=req.search_in_raw_id,
        entity_type=req.entity_type,
        source=req.source,
    )
    if not vids_scores:
        return SearchResultBundle(reason="es_no_hits"), es_ms, 0.0, "es_no_hits"

    vids = [vid for vid, _ in vids_scores]
    rows, fetch_ms = nebula_client.fetch_entity_props(vids)
    row_map = {int(row["vid"]): row for row in rows}

    nodes: List[CandidateNode] = []
    for vid, score in vids_scores:
        row = row_map.get(int(vid))
        if row is None:
            continue
        nodes.append(
            CandidateNode(
                vid=int(row["vid"]),
                label=str(row.get("label") or ""),
                entity_type=str(row.get("entity_type") or ""),
                raw_id=str(row.get("raw_id") or ""),
                source=str(row.get("source") or ""),
                description=str(row.get("description") or ""),
                score=float(score),
            )
        )

    edges: List[Dict[str, Any]] = []
    if req.include_edges:
        edges, _ = nebula_client.fetch_edges_between([n.vid for n in nodes], limit=5000)

    bundle = SearchResultBundle(
        nodes=nodes[: app_config.settings.search_topk],
        edges=edges,
        total_candidates=len(vids_scores),
        reason="es_ok",
    )
    return bundle, es_ms, fetch_ms, "es_ok"


def _serialize_search_payload(
    bundle: SearchResultBundle,
    req: SearchRequest,
    diagnostics: SearchDiagnostics,
) -> Dict[str, Any]:
    nodes_payload = [n.to_node_payload() for n in bundle.nodes]
    edges_payload = bundle.edges if req.include_edges else []
    return {
        "nodes": nodes_payload,
        "edges": edges_payload,
        "total_candidates": max(int(bundle.total_candidates or 0), len(nodes_payload)),
        "truncated": bool(bundle.truncated),
        "meta": {
            "request_id": diagnostics.request_id,
            "strategy": diagnostics.strategy,
            "reason": diagnostics.reason or bundle.reason,
            "timings_ms": {
                "es_ms": round(diagnostics.es_ms, 3),
                "candidate_ms": round(diagnostics.candidate_ms, 3),
                "fetch_ms": round(diagnostics.fetch_ms, 3),
                "serialize_ms": round(diagnostics.serialize_ms, 3),
                "total_ms": round(diagnostics.total_ms, 3),
            },
        },
    }


def _log_search(diagnostics: SearchDiagnostics, req: SearchRequest, returned_nodes: int) -> None:
    logger.warning(
        "search request_id=%s strategy=%s es_ms=%.2f candidate_ms=%.2f fetch_ms=%.2f serialize_ms=%.2f total_ms=%.2f returned_nodes=%d include_edges=%s reason=%s q_len=%d",
        diagnostics.request_id,
        diagnostics.strategy,
        diagnostics.es_ms,
        diagnostics.candidate_ms,
        diagnostics.fetch_ms,
        diagnostics.serialize_ms,
        diagnostics.total_ms,
        returned_nodes,
        req.include_edges,
        diagnostics.reason,
        len((req.q or "").strip()),
    )


def search(req: SearchRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    request_id = _request_id()
    diagnostics = SearchDiagnostics(strategy="FALLBACK", request_id=request_id)

    # Enforce default behavior even if clients omit include_edges.
    if req.include_edges is None:
        req.include_edges = app_config.settings.search_include_edges_default

    try:
        bundle = SearchResultBundle(reason="empty")

        if _should_use_es(req):
            healthy, health_ms, health_reason = _es_health()
            diagnostics.es_ms += health_ms
            if healthy:
                diagnostics.strategy = "ES"
                try:
                    bundle, es_ms, fetch_ms, reason = _es_search(req, request_id)
                    diagnostics.es_ms += es_ms
                    diagnostics.fetch_ms += fetch_ms
                    diagnostics.reason = reason
                except (NebulaTimeoutError, NebulaConnectionError, NebulaQueryError):
                    raise
                except Exception as exc:
                    diagnostics.strategy = "FALLBACK"
                    diagnostics.reason = f"es_unavailable:{exc}"
                    logger.warning(
                        "search degrade request_id=%s strategy=FALLBACK reason=es_query_failed error=%s",
                        request_id,
                        exc,
                    )
            else:
                diagnostics.strategy = "FALLBACK"
                diagnostics.reason = f"es_unavailable:{health_reason}"
                logger.warning(
                    "search degrade request_id=%s strategy=FALLBACK reason=es_health_failed detail=%s",
                    request_id,
                    health_reason,
                )

        if diagnostics.strategy == "FALLBACK":
            bundle, candidate_ms, reason = fallback_engine.search(req)
            diagnostics.candidate_ms += candidate_ms
            if not diagnostics.reason:
                diagnostics.reason = reason

            # fallback mode can still return edges only if explicitly requested
            if req.include_edges and bundle.nodes:
                edges, fetch_edges_ms = nebula_client.fetch_edges_between([n.vid for n in bundle.nodes], limit=3000)
                diagnostics.fetch_ms += fetch_edges_ms
                bundle.edges = edges

        serialize_started = time.perf_counter()
        diagnostics.total_ms = (time.perf_counter() - started) * 1000.0
        payload = _serialize_search_payload(bundle, req, diagnostics)
        diagnostics.serialize_ms = (time.perf_counter() - serialize_started) * 1000.0
        diagnostics.total_ms = (time.perf_counter() - started) * 1000.0
        payload = _serialize_search_payload(bundle, req, diagnostics)
        _log_search(diagnostics, req, len(payload.get("nodes") or []))
        return payload

    except NebulaTimeoutError as exc:
        diagnostics.total_ms = (time.perf_counter() - started) * 1000.0
        logger.warning(
            "search timeout request_id=%s strategy=%s reason=%s",
            request_id,
            diagnostics.strategy,
            str(exc),
        )
        raise _http_error(504, request_id, f"nebula timeout: {exc}")
    except NebulaConnectionError as exc:
        diagnostics.total_ms = (time.perf_counter() - started) * 1000.0
        logger.warning(
            "search unavailable request_id=%s strategy=%s reason=%s",
            request_id,
            diagnostics.strategy,
            str(exc),
        )
        raise _http_error(503, request_id, f"nebula connection error: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        diagnostics.total_ms = (time.perf_counter() - started) * 1000.0
        logger.exception(
            "search internal error request_id=%s strategy=%s",
            request_id,
            diagnostics.strategy,
        )
        raise _http_error(500, request_id, f"internal error: {exc}")


def entity_types() -> List[Dict[str, Any]]:
    return entity_catalog_service.list_entity_types(
        list_entity_types_fn=metadata_service.list_entity_types,
        fallback_items=FALLBACK_ENTITY_TYPES,
        logger_instance=logger,
    )


def suggest(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    q_clean = (q or "").strip()
    if len(q_clean) < 2:
        return {"q": q_clean, "items": [], "truncated": False}

    safe_limit = max(1, min(int(limit), 20))
    fetch_limit = safe_limit + 1
    where_parts = [f'v.`Entity`.`entity_name` STARTS WITH "{esc(q_clean)}"']
    if entity_type and entity_type.strip():
        where_parts.append(f'v.`Entity`.`entity_type` == "{esc(entity_type.strip())}"')
    if source and source.strip():
        where_parts.append(f'v.`Entity`.`source` == "{esc(source.strip())}"')

    ngql = f"""
MATCH (v:`Entity`)
WHERE {' AND '.join(where_parts)}
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS name,
       v.`Entity`.`entity_type` AS type,
       v.`Entity`.`source` AS source,
       length(v.`Entity`.`entity_name`) AS name_len
ORDER BY name_len ASC, vid ASC
LIMIT {fetch_limit};
"""

    try:
        res, _ = nebula_client.execute(ngql)
    except NebulaTimeoutError as exc:
        logger.warning("suggest degraded on timeout: q=%r reason=%s", q_clean, exc)
        return {"q": q_clean, "items": [], "truncated": False}

    vids = res.column_values("vid")
    names = res.column_values("name")
    types = res.column_values("type")
    sources = res.column_values("source")

    items: List[Dict[str, Any]] = []
    for i in range(len(vids)):
        items.append(
            {
                "vid": int(vw(vids[i])),
                "label": str(vw(names[i]) or ""),
                "entity_type": str(vw(types[i]) or ""),
                "source": str(vw(sources[i]) or ""),
                "score": 1.0,
            }
        )

    truncated = len(items) > safe_limit
    return {"q": q_clean, "items": items[:safe_limit], "truncated": truncated}


def suggest_raw_id(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    q_clean = (q or "").strip()
    if len(q_clean) < 2:
        return {"q": q_clean, "items": [], "truncated": False}

    safe_limit = max(1, min(int(limit), 50))
    fetch_limit = safe_limit + 1
    q_norm = normalize_raw_id_for_suggest_prefix(q_clean)

    where_parts = [f'lower(coalesce(v.`Entity`.`entity_raw_id`, "")) STARTS WITH "{esc(q_norm)}"']
    if entity_type and entity_type.strip():
        where_parts.append(f'lower(coalesce(v.`Entity`.`entity_type`, "")) == "{esc(entity_type.strip().lower())}"')
    if source and source.strip():
        where_parts.append(f'lower(coalesce(v.`Entity`.`source`, "")) == "{esc(source.strip().lower())}"')

    ngql = f"""
MATCH (v:`Entity`)
WHERE {' AND '.join(where_parts)}
RETURN id(v) AS vid,
       coalesce(v.`Entity`.`entity_raw_id`, "") AS raw_id,
       coalesce(v.`Entity`.`entity_name`, "") AS name,
       coalesce(v.`Entity`.`entity_type`, "") AS type,
       coalesce(v.`Entity`.`source`, "") AS source
ORDER BY raw_id ASC, vid ASC
LIMIT {fetch_limit};
"""

    res, _ = nebula_client.execute(ngql)
    vids = res.column_values("vid")
    raw_ids = res.column_values("raw_id")
    names = res.column_values("name")
    types = res.column_values("type")
    sources = res.column_values("source")

    items: List[Dict[str, Any]] = []
    for i in range(len(vids)):
        rid = str(vw(raw_ids[i]) or "")
        if not rid:
            continue
        items.append(
            {
                "vid": int(vw(vids[i])),
                "entity_raw_id": rid,
                "label": str(vw(names[i]) or ""),
                "entity_type": str(vw(types[i]) or ""),
                "source": str(vw(sources[i]) or ""),
            }
        )

    truncated = len(items) > safe_limit
    return {"q": q_clean, "items": items[:safe_limit], "truncated": truncated}
