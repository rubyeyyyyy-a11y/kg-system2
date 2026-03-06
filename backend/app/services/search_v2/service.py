import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException

from app import config as app_config
from app.clients import ElasticsearchClient
from app.clients.nebula_client import NebulaClient, NebulaConnectionError, NebulaQueryError, NebulaTimeoutError
from app.models.search_models import CandidateNode
from app.schemas.search import SearchRequest
from app.services.common import normalize_raw_id
from app.services.search_v2.budget import search_budget
from app.services.search_v2.errors import SearchErrorCode, SearchServiceError, mk_search_error, to_http_exception

logger = logging.getLogger(__name__)

nebula_client = NebulaClient()
es_client = ElasticsearchClient(timeout_ms=search_budget.es_timeout_ms)

_ES_HEALTH_CACHE: Dict[str, Any] = {"ok": False, "reason": "cold", "at": 0.0, "ms": 0.0}


def _request_id() -> str:
    return uuid.uuid4().hex[:12]


def _is_timeout_text(text: str) -> bool:
    msg = str(text or "").lower()
    return "timeout" in msg or "timed out" in msg


def _raise_es_error(exc: Exception) -> None:
    msg = str(exc or "")
    if _is_timeout_text(msg):
        raise mk_search_error(
            code=SearchErrorCode.ES_TIMEOUT,
            message="elasticsearch timeout",
            status_code=504,
            reason=msg,
            upstream="elasticsearch",
        )
    raise mk_search_error(
        code=SearchErrorCode.ES_UNAVAILABLE,
        message="elasticsearch unavailable",
        status_code=503,
        reason=msg,
        upstream="elasticsearch",
    )


def _healthcheck_es() -> Tuple[bool, float, str]:
    now = time.time()
    ttl = float(search_budget.es_health_ttl_sec)
    if ttl > 0 and (now - float(_ES_HEALTH_CACHE.get("at") or 0.0) < ttl):
        return bool(_ES_HEALTH_CACHE.get("ok")), float(_ES_HEALTH_CACHE.get("ms") or 0.0), str(
            _ES_HEALTH_CACHE.get("reason") or ""
        )

    ok, took_ms, reason = es_client.healthcheck()
    _ES_HEALTH_CACHE.update({"ok": ok, "reason": reason, "at": now, "ms": took_ms})
    return ok, took_ms, reason


def _ensure_es_available() -> float:
    if not app_config.settings.es_enabled:
        raise mk_search_error(
            code=SearchErrorCode.ES_UNAVAILABLE,
            message="elasticsearch is disabled by configuration",
            status_code=503,
            reason="es_enabled=false",
            upstream="elasticsearch",
        )

    ok, took_ms, reason = _healthcheck_es()
    if ok:
        return took_ms
    if _is_timeout_text(reason):
        raise mk_search_error(
            code=SearchErrorCode.ES_TIMEOUT,
            message="elasticsearch health check timeout",
            status_code=504,
            reason=reason,
            upstream="elasticsearch",
        )
    raise mk_search_error(
        code=SearchErrorCode.ES_UNAVAILABLE,
        message="elasticsearch health check failed",
        status_code=503,
        reason=reason,
        upstream="elasticsearch",
    )


def _fetch_nodes(vids_scores: List[Tuple[int, float]]) -> Tuple[List[CandidateNode], float]:
    vids = [vid for vid, _ in vids_scores]
    if not vids:
        return [], 0.0

    try:
        rows, fetch_ms = nebula_client.fetch_entity_props(vids)
    except NebulaTimeoutError as exc:
        raise mk_search_error(
            code=SearchErrorCode.NEBULA_FETCH_TIMEOUT,
            message="nebula fetch timeout",
            status_code=504,
            reason=str(exc),
            upstream="nebula",
        )
    except (NebulaConnectionError, NebulaQueryError) as exc:
        raise mk_search_error(
            code=SearchErrorCode.NEBULA_FETCH_UNAVAILABLE,
            message="nebula fetch failed",
            status_code=503,
            reason=str(exc),
            upstream="nebula",
        )

    row_map = {int(row["vid"]): row for row in rows}
    out: List[CandidateNode] = []
    for vid, score in vids_scores:
        row = row_map.get(int(vid))
        if row is None:
            continue
        out.append(
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
    return out, fetch_ms


def _fetch_edges_limited(nodes: List[CandidateNode]) -> Tuple[List[Dict[str, Any]], float]:
    if not nodes:
        return [], 0.0
    cap_nodes = nodes[: search_budget.include_edges_node_cap]
    vids = [n.vid for n in cap_nodes]

    try:
        edges, took_ms = nebula_client.fetch_edges_between(vids, limit=search_budget.include_edges_edge_limit)
        return edges, took_ms
    except NebulaTimeoutError as exc:
        raise mk_search_error(
            code=SearchErrorCode.NEBULA_FETCH_TIMEOUT,
            message="nebula edge fetch timeout",
            status_code=504,
            reason=str(exc),
            upstream="nebula",
        )
    except (NebulaConnectionError, NebulaQueryError) as exc:
        raise mk_search_error(
            code=SearchErrorCode.NEBULA_FETCH_UNAVAILABLE,
            message="nebula edge fetch failed",
            status_code=503,
            reason=str(exc),
            upstream="nebula",
        )


def _search_candidates(req: SearchRequest) -> Tuple[List[Tuple[int, float]], float, str]:
    raw_id_query = (req.entity_raw_id or "").strip()
    if raw_id_query:
        raw_norm = normalize_raw_id(raw_id_query)
        if not raw_norm:
            return [], 0.0, "raw_id_empty_after_normalize"
        try:
            result, took_ms = es_client.search_entity_vids_by_raw_id_norm(
                raw_norm,
                raw_id_original=raw_id_query,
                mode=req.entity_raw_id_mode,
                limit=search_budget.es_topk,
                entity_type=req.entity_type,
                source=req.source,
            )
        except Exception as exc:
            _raise_es_error(exc)
        return result, took_ms, "raw_id_es"

    q = (req.q or "").strip()
    if len(q) < search_budget.min_query_len:
        return [], 0.0, "q_too_short"
    try:
        result, took_ms = es_client.search_entity_vids(
            q,
            limit=search_budget.es_topk,
            search_in_name=req.search_in_name,
            search_in_description=req.search_in_description,
            search_in_type=req.search_in_type,
            search_in_raw_id=req.search_in_raw_id,
            entity_type=req.entity_type,
            source=req.source,
        )
    except Exception as exc:
        _raise_es_error(exc)
    return result, took_ms, "text_es"


def _search_payload(
    *,
    request_id: str,
    reason: str,
    nodes: List[CandidateNode],
    edges: List[Dict[str, Any]],
    total_candidates: int,
    es_ms: float,
    fetch_ms: float,
    total_ms: float,
    include_edges_requested: bool,
    include_edges_applied: bool,
) -> Dict[str, Any]:
    return {
        "nodes": [n.to_node_payload() for n in nodes],
        "edges": edges if include_edges_applied else [],
        "total_candidates": int(max(total_candidates, len(nodes))),
        "truncated": False,
        "meta": {
            "request_id": request_id,
            "strategy": "ES_V2",
            "reason": reason,
            "timings_ms": {
                "es_ms": round(es_ms, 3),
                "fetch_ms": round(fetch_ms, 3),
                "total_ms": round(total_ms, 3),
            },
            "include_edges_applied": bool(include_edges_applied),
            "include_edges_requested": bool(include_edges_requested),
            "include_edges_legacy_note": (
                "include_edges is legacy; recommended flow is nodes-first then graph expand APIs"
                if include_edges_requested
                else ""
            ),
            "edge_fetch_budget": {
                "node_cap": int(search_budget.include_edges_node_cap),
                "edge_limit": int(search_budget.include_edges_edge_limit),
            },
        },
    }


def search(req: SearchRequest) -> Dict[str, Any]:
    started = time.perf_counter()
    request_id = _request_id()
    es_ms = 0.0
    fetch_ms = 0.0

    include_edges_requested = bool(req.include_edges)
    include_edges_applied = bool(include_edges_requested and search_budget.include_edges_allow)

    q = (req.q or "").strip()
    raw_id_q = (req.entity_raw_id or "").strip()
    if not q and not raw_id_q:
        err = mk_search_error(
            code=SearchErrorCode.VALIDATION_ERROR,
            message="either q or entity_raw_id must be provided",
            status_code=400,
            reason="empty_query",
        )
        raise to_http_exception(err, request_id)
    if not raw_id_q and len(q) < search_budget.min_query_len:
        total_ms = (time.perf_counter() - started) * 1000.0
        return _search_payload(
            request_id=request_id,
            reason="q_too_short",
            nodes=[],
            edges=[],
            total_candidates=0,
            es_ms=0.0,
            fetch_ms=0.0,
            total_ms=total_ms,
            include_edges_requested=False,
            include_edges_applied=False,
        )

    try:
        es_ms += _ensure_es_available()

        vids_scores, query_ms, query_reason = _search_candidates(req)
        es_ms += query_ms
        if not vids_scores:
            total_ms = (time.perf_counter() - started) * 1000.0
            return _search_payload(
                request_id=request_id,
                reason=query_reason if query_reason != "text_es" else "es_no_hits",
                nodes=[],
                edges=[],
                total_candidates=0,
                es_ms=es_ms,
                fetch_ms=0.0,
                total_ms=total_ms,
                include_edges_requested=include_edges_requested,
                include_edges_applied=False,
            )

        nodes, node_fetch_ms = _fetch_nodes(vids_scores)
        fetch_ms += node_fetch_ms
        nodes = nodes[: search_budget.search_topk]
        edges: List[Dict[str, Any]] = []
        if include_edges_applied and nodes:
            edges, edge_fetch_ms = _fetch_edges_limited(nodes)
            fetch_ms += edge_fetch_ms

        total_ms = (time.perf_counter() - started) * 1000.0
        reason = "es_ok" if query_reason == "text_es" else query_reason
        return _search_payload(
            request_id=request_id,
            reason=reason,
            nodes=nodes,
            edges=edges,
            total_candidates=len(vids_scores),
            es_ms=es_ms,
            fetch_ms=fetch_ms,
            total_ms=total_ms,
            include_edges_requested=include_edges_requested,
            include_edges_applied=include_edges_applied,
        )
    except SearchServiceError as err:
        logger.warning("search_v2 error request_id=%s code=%s reason=%s", request_id, err.code.value, err.reason)
        raise to_http_exception(err, request_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("search_v2 unexpected error request_id=%s", request_id)
        err = mk_search_error(
            code=SearchErrorCode.INTERNAL_ERROR,
            message="search internal error",
            status_code=500,
            reason=str(exc),
        )
        raise to_http_exception(err, request_id)


def suggest(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    request_id = _request_id()
    q_clean = (q or "").strip()
    if len(q_clean) < search_budget.suggest_min_query_len:
        return {"q": q_clean, "items": [], "truncated": False}

    safe_limit = max(1, min(int(limit), search_budget.suggest_limit_max))
    try:
        _ensure_es_available()
        items, _ = es_client.suggest_entities_by_name_prefix(
            q_clean,
            limit=safe_limit + 1,
            entity_type=entity_type,
            source=source,
        )
        truncated = len(items) > safe_limit
        return {"q": q_clean, "items": items[:safe_limit], "truncated": truncated}
    except SearchServiceError as err:
        logger.warning("suggest_v2 error request_id=%s code=%s reason=%s", request_id, err.code.value, err.reason)
        raise to_http_exception(err, request_id)
    except Exception as exc:
        try:
            _raise_es_error(exc)
        except SearchServiceError as err:
            logger.warning("suggest_v2 error request_id=%s code=%s reason=%s", request_id, err.code.value, err.reason)
            raise to_http_exception(err, request_id)
        raise


def suggest_raw_id(
    q: str,
    limit: int = 12,
    entity_type: Optional[str] = None,
    source: Optional[str] = None,
) -> Dict[str, Any]:
    request_id = _request_id()
    q_clean = (q or "").strip()
    if len(q_clean) < search_budget.suggest_min_query_len:
        return {"q": q_clean, "items": [], "truncated": False}

    q_norm = normalize_raw_id(q_clean)
    if not q_norm:
        return {"q": q_clean, "items": [], "truncated": False}

    safe_limit = max(1, min(int(limit), search_budget.suggest_raw_id_limit_max))
    try:
        _ensure_es_available()
        items, _ = es_client.suggest_entities_by_raw_id_prefix(
            q_norm,
            raw_id_original_prefix=q_clean,
            limit=safe_limit + 1,
            entity_type=entity_type,
            source=source,
        )
        truncated = len(items) > safe_limit
        return {"q": q_clean, "items": items[:safe_limit], "truncated": truncated}
    except SearchServiceError as err:
        logger.warning(
            "suggest_raw_id_v2 error request_id=%s code=%s reason=%s", request_id, err.code.value, err.reason
        )
        raise to_http_exception(err, request_id)
    except Exception as exc:
        try:
            _raise_es_error(exc)
        except SearchServiceError as err:
            logger.warning(
                "suggest_raw_id_v2 error request_id=%s code=%s reason=%s", request_id, err.code.value, err.reason
            )
            raise to_http_exception(err, request_id)
        raise
