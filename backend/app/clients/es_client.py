import json
import logging
import socket
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings
from app.core.space_context import get_current_space

logger = logging.getLogger(__name__)


class ElasticsearchClient:
    def __init__(
        self,
        base_url: str | None = None,
        index: str | None = None,
        timeout_ms: int | None = None,
        bulk_timeout_ms: int | None = None,
        bulk_max_actions: int | None = None,
        bulk_max_bytes: int | None = None,
    ) -> None:
        self.base_url = (base_url or settings.es_url).rstrip("/")
        self.index = index or settings.es_index
        self.timeout_s = max(0.1, float(timeout_ms or settings.es_timeout_ms) / 1000.0)
        self.bulk_timeout_s = max(self.timeout_s, float(bulk_timeout_ms or settings.es_bulk_timeout_ms) / 1000.0)
        self.bulk_max_actions = max(1, int(bulk_max_actions or settings.es_bulk_upsert_batch_size))
        self.bulk_max_bytes = max(16 * 1024, int(bulk_max_bytes or settings.es_bulk_upsert_max_bytes))

    @staticmethod
    def document_id(space_name: str, vid: int) -> str:
        # Shared-index phase-1 isolation relies on a composite _id so one space
        # cannot overwrite another space's document for the same Nebula VID.
        return f"{space_name}:{int(vid)}"

    @staticmethod
    def _resolved_space(space_name: Optional[str]) -> str:
        return str(space_name or get_current_space())

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        content_type: str = "application/json",
        timeout_s: float | None = None,
    ) -> Tuple[Dict[str, Any], float]:
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"

        data = raw_body
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif raw_body is not None:
            headers["Content-Type"] = content_type

        req = Request(url=url, data=data, headers=headers, method=method)
        start = time.perf_counter()
        try:
            with urlopen(req, timeout=timeout_s or self.timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"ES HTTP {exc.code}: {detail}") from exc
        except (TimeoutError, socket.timeout) as exc:
            resolved_timeout_s = timeout_s or self.timeout_s
            raise RuntimeError(f"ES request timed out after {resolved_timeout_s:.3f}s") from exc
        except URLError as exc:
            raise RuntimeError(f"ES URL error: {exc}") from exc

        took_ms = (time.perf_counter() - start) * 1000.0
        if not body:
            return {}, took_ms
        try:
            return json.loads(body), took_ms
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"ES invalid JSON response: {body[:200]}") from exc

    def healthcheck(self) -> Tuple[bool, float, str]:
        try:
            data, took_ms = self._request_json(
                "GET",
                "/_cluster/health",
                query={"timeout": "1s", "filter_path": "status,timed_out"},
            )
            status = str(data.get("status") or "")
            timed_out = bool(data.get("timed_out"))
            if timed_out:
                return False, took_ms, "cluster health timed out"
            if status in {"green", "yellow"}:
                return True, took_ms, status
            return False, took_ms, f"status={status or 'unknown'}"
        except Exception as exc:
            return False, 0.0, str(exc)

    def search_entity_vids(
        self,
        q: str,
        *,
        limit: int,
        offset: int = 0,
        space_name: Optional[str] = None,
        search_in_name: bool,
        search_in_description: bool,
        search_in_type: bool,
        search_in_raw_id: bool,
        entity_type: Optional[str],
        source: Optional[str],
    ) -> Tuple[List[Tuple[int, float]], float]:
        should: List[Dict[str, Any]] = []
        if search_in_name:
            should.append({"match": {"entity_name": {"query": q}}})
        if search_in_description:
            should.append({"match": {"description": {"query": q}}})
        if search_in_type:
            should.append({"match": {"entity_type_text": {"query": q}}})
        if search_in_raw_id:
            should.append({"match": {"entity_raw_id_text": {"query": q}}})
        if not should:
            should.append({"match": {"entity_name": {"query": q}}})

        filters: List[Dict[str, Any]] = []
        filters.append({"term": {"space_name": self._resolved_space(space_name)}})
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})
        resolved_space = self._resolved_space(space_name)
        logger.warning(
            "es_search_entities index=%s space=%s limit=%d offset=%d entity_type=%s source=%s",
            self.index,
            resolved_space,
            max(1, min(int(limit), 500)),
            max(0, int(offset)),
            str(entity_type or "").strip() or "-",
            str(source or "").strip() or "-",
        )

        body: Dict[str, Any] = {
            "size": max(1, min(int(limit), 500)),
            "from": max(0, int(offset)),
            "query": {
                "bool": {
                    "should": should,
                    "minimum_should_match": 1,
                    "filter": filters,
                }
            },
            "_source": ["vid"],
        }

        data, took_ms = self._request_json("POST", f"/{self.index}/_search", payload=body)
        hits = (data.get("hits") or {}).get("hits") or []
        out: List[Tuple[int, float]] = []
        for h in hits:
            src = h.get("_source") or {}
            try:
                vid = int(src.get("vid"))
            except Exception:
                continue
            score = float(h.get("_score") or 0.0)
            out.append((vid, score))
        return out, took_ms

    def search_entity_vids_by_raw_id_norm(
        self,
        raw_id_norm: str,
        *,
        raw_id_original: str,
        mode: str,
        limit: int,
        offset: int = 0,
        space_name: Optional[str] = None,
        entity_type: Optional[str],
        source: Optional[str],
    ) -> Tuple[List[Tuple[int, float]], float]:
        mode_norm = str(mode or "contains").strip().lower()
        if mode_norm not in {"contains", "prefix", "exact"}:
            mode_norm = "contains"

        filters: List[Dict[str, Any]] = []
        filters.append({"term": {"space_name": self._resolved_space(space_name)}})
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})
        resolved_space = self._resolved_space(space_name)
        logger.warning(
            "es_search_raw_id index=%s space=%s mode=%s limit=%d offset=%d entity_type=%s source=%s",
            self.index,
            resolved_space,
            mode_norm,
            max(1, min(int(limit), 500)),
            max(0, int(offset)),
            str(entity_type or "").strip() or "-",
            str(source or "").strip() or "-",
        )

        if mode_norm == "exact":
            should: List[Dict[str, Any]] = [
                {"term": {"raw_id_norm": raw_id_norm}},
                {"term": {"entity_raw_id": raw_id_original}},
            ]
        elif mode_norm == "prefix":
            should = [
                {"prefix": {"raw_id_norm": raw_id_norm}},
                {"prefix": {"entity_raw_id": raw_id_original}},
            ]
        else:
            # contains query in ES (still avoids Nebula full-scan fallback)
            should = [
                {"wildcard": {"raw_id_norm": {"value": f"*{raw_id_norm}*"}}},
                {"wildcard": {"entity_raw_id": {"value": f"*{raw_id_original}*"}}},
            ]

        body: Dict[str, Any] = {
            "size": max(1, min(int(limit), 500)),
            "from": max(0, int(offset)),
            "query": {
                "bool": {
                    "should": should,
                    "minimum_should_match": 1,
                    "filter": filters,
                }
            },
            "_source": ["vid"],
        }

        data, took_ms = self._request_json("POST", f"/{self.index}/_search", payload=body)
        hits = (data.get("hits") or {}).get("hits") or []
        out: List[Tuple[int, float]] = []
        for h in hits:
            src = h.get("_source") or {}
            try:
                vid = int(src.get("vid"))
            except Exception:
                continue
            score = float(h.get("_score") or 0.0)
            out.append((vid, score))
        return out, took_ms

    def suggest_entities_by_name_prefix(
        self,
        q: str,
        *,
        limit: int,
        space_name: Optional[str] = None,
        entity_type: Optional[str],
        source: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], float]:
        filters: List[Dict[str, Any]] = []
        filters.append({"term": {"space_name": self._resolved_space(space_name)}})
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})
        logger.warning(
            "es_suggest_name index=%s space=%s limit=%d entity_type=%s source=%s",
            self.index,
            self._resolved_space(space_name),
            max(1, min(int(limit), 100)),
            str(entity_type or "").strip() or "-",
            str(source or "").strip() or "-",
        )

        body: Dict[str, Any] = {
            "size": max(1, min(int(limit), 100)),
            "query": {
                "bool": {
                    "must": [{"match_phrase_prefix": {"entity_name": {"query": q}}}],
                    "filter": filters,
                }
            },
            "_source": ["vid", "entity_name", "entity_type", "source"],
        }

        data, took_ms = self._request_json("POST", f"/{self.index}/_search", payload=body)
        hits = (data.get("hits") or {}).get("hits") or []
        out: List[Dict[str, Any]] = []
        for h in hits:
            src = h.get("_source") or {}
            try:
                vid = int(src.get("vid"))
            except Exception:
                continue
            out.append(
                {
                    "vid": vid,
                    "label": str(src.get("entity_name") or ""),
                    "entity_type": str(src.get("entity_type") or ""),
                    "source": str(src.get("source") or ""),
                    "score": float(h.get("_score") or 0.0),
                }
            )
        return out, took_ms

    def suggest_entities_by_raw_id_prefix(
        self,
        raw_id_norm_prefix: str,
        *,
        raw_id_original_prefix: str,
        limit: int,
        space_name: Optional[str] = None,
        entity_type: Optional[str],
        source: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], float]:
        filters: List[Dict[str, Any]] = []
        filters.append({"term": {"space_name": self._resolved_space(space_name)}})
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})
        logger.warning(
            "es_suggest_raw_id index=%s space=%s limit=%d entity_type=%s source=%s",
            self.index,
            self._resolved_space(space_name),
            max(1, min(int(limit), 100)),
            str(entity_type or "").strip() or "-",
            str(source or "").strip() or "-",
        )

        body: Dict[str, Any] = {
            "size": max(1, min(int(limit), 100)),
            "query": {
                "bool": {
                    "should": [
                        {"prefix": {"raw_id_norm": raw_id_norm_prefix}},
                        {"prefix": {"entity_raw_id": raw_id_original_prefix}},
                    ],
                    "minimum_should_match": 1,
                    "filter": filters,
                }
            },
            "_source": ["vid", "entity_raw_id", "entity_name", "entity_type", "source"],
        }

        data, took_ms = self._request_json("POST", f"/{self.index}/_search", payload=body)
        hits = (data.get("hits") or {}).get("hits") or []
        out: List[Dict[str, Any]] = []
        for h in hits:
            src = h.get("_source") or {}
            try:
                vid = int(src.get("vid"))
            except Exception:
                continue
            rid = str(src.get("entity_raw_id") or "")
            if not rid:
                continue
            out.append(
                {
                    "vid": vid,
                    "entity_raw_id": rid,
                    "label": str(src.get("entity_name") or ""),
                    "entity_type": str(src.get("entity_type") or ""),
                    "source": str(src.get("source") or ""),
                    "score": float(h.get("_score") or 0.0),
                }
            )
        return out, took_ms

    def count_documents_for_space(
        self,
        space_name: str,
        *,
        index_name: Optional[str] = None,
    ) -> Tuple[int, float]:
        resolved_space = self._resolved_space(space_name)
        body: Dict[str, Any] = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"space_name": resolved_space}},
                    ]
                }
            }
        }
        data, took_ms = self._request_json("POST", f"/{index_name or self.index}/_count", payload=body)
        return int(data.get("count") or 0), took_ms

    def count_documents_missing_space(
        self,
        *,
        index_name: Optional[str] = None,
    ) -> Tuple[int, float]:
        body: Dict[str, Any] = {
            "query": {
                "bool": {
                    "must_not": [
                        {"exists": {"field": "space_name"}},
                    ]
                }
            }
        }
        data, took_ms = self._request_json("POST", f"/{index_name or self.index}/_count", payload=body)
        return int(data.get("count") or 0), took_ms

    def fetch_documents_for_space(
        self,
        space_name: str,
        *,
        limit: int = 10,
        index_name: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        resolved_space = self._resolved_space(space_name)
        body: Dict[str, Any] = {
            "size": max(1, min(int(limit), 100)),
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"space_name": resolved_space}},
                    ]
                }
            },
            "sort": [{"vid": {"order": "asc"}}],
            "_source": [
                "vid",
                "space_name",
                "entity_name",
                "entity_raw_id",
                "raw_id_norm",
                "entity_type",
                "source",
            ],
        }
        data, took_ms = self._request_json("POST", f"/{index_name or self.index}/_search", payload=body)
        hits = (data.get("hits") or {}).get("hits") or []
        out: List[Dict[str, Any]] = []
        for hit in hits:
            out.append(
                {
                    "_id": str(hit.get("_id") or ""),
                    "_source": dict(hit.get("_source") or {}),
                }
            )
        return out, took_ms

    def fetch_documents_by_ids(
        self,
        space_name: str,
        vids: List[int],
        *,
        index_name: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        resolved_space = self._resolved_space(space_name)
        unique_vids = sorted({int(vid) for vid in vids if int(vid) > 0})
        if not unique_vids:
            return [], 0.0
        body = {"ids": [self.document_id(resolved_space, vid) for vid in unique_vids]}
        data, took_ms = self._request_json("POST", f"/{index_name or self.index}/_mget", payload=body)
        docs = data.get("docs") or []
        out: List[Dict[str, Any]] = []
        for doc in docs:
            out.append(
                {
                    "_id": str(doc.get("_id") or ""),
                    "found": bool(doc.get("found")),
                    "_source": dict(doc.get("_source") or {}),
                }
            )
        return out, took_ms

    def fetch_documents_missing_space(
        self,
        *,
        limit: int = 500,
        after_vid: int | None = None,
        index_name: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], float]:
        body: Dict[str, Any] = {
            "size": max(1, min(int(limit), 5000)),
            "query": {
                "bool": {
                    "must_not": [
                        {"exists": {"field": "space_name"}},
                    ]
                }
            },
            "sort": [{"vid": {"order": "asc"}}],
            "_source": [
                "vid",
                "entity_name",
                "description",
                "entity_raw_id",
                "raw_id_norm",
                "entity_type",
                "source",
            ],
        }
        if after_vid is not None and int(after_vid) > 0:
            body["search_after"] = [int(after_vid)]
        data, took_ms = self._request_json("POST", f"/{index_name or self.index}/_search", payload=body)
        hits = (data.get("hits") or {}).get("hits") or []
        out: List[Dict[str, Any]] = []
        for hit in hits:
            out.append(
                {
                    "_id": str(hit.get("_id") or ""),
                    "_source": dict(hit.get("_source") or {}),
                }
            )
        return out, took_ms

    def delete_documents_missing_space(
        self,
        *,
        index_name: Optional[str] = None,
        refresh: str = "true",
        wait_for_completion: bool = True,
        conflicts: str = "proceed",
        slices: str = "auto",
    ) -> Tuple[Dict[str, Any], float]:
        body: Dict[str, Any] = {
            "query": {
                "bool": {
                    "must_not": [
                        {"exists": {"field": "space_name"}},
                    ]
                }
            }
        }
        return self._request_json(
            "POST",
            f"/{index_name or self.index}/_delete_by_query",
            payload=body,
            query={
                "refresh": refresh,
                "wait_for_completion": str(bool(wait_for_completion)).lower(),
                "conflicts": conflicts,
                "slices": slices,
            },
        )

    def delete_documents_by_ids(
        self,
        space_name: str,
        vids: List[int],
        *,
        index_name: Optional[str] = None,
        refresh: str = "wait_for",
    ) -> Dict[str, Any]:
        resolved_space = self._resolved_space(space_name)
        unique_vids = sorted({int(vid) for vid in vids if int(vid) > 0})
        if not unique_vids:
            return {
                "space_name": resolved_space,
                "docs": 0,
                "ok_count": 0,
                "fail_count": 0,
                "bulk_ms": 0.0,
                "skipped": True,
                "reason": "no_entity_vids",
            }
        idx = index_name or self.index
        ok = 0
        fail = 0
        took_ms = 0.0
        payloads: List[bytes] = []
        current_parts: List[bytes] = []
        current_bytes = 0
        current_actions = 0
        for vid in unique_vids:
            action_line = json.dumps(
                {"delete": {"_index": idx, "_id": self.document_id(resolved_space, vid)}},
                ensure_ascii=False,
            ).encode("utf-8") + b"\n"
            action_bytes = len(action_line)
            if action_bytes > self.bulk_max_bytes:
                raise RuntimeError(
                    f"ES bulk delete action exceeds configured request budget: vid={vid} bytes={action_bytes} max={self.bulk_max_bytes}"
                )
            if current_parts and (
                current_actions >= self.bulk_max_actions or current_bytes + action_bytes > self.bulk_max_bytes
            ):
                payloads.append(b"".join(current_parts))
                current_parts = []
                current_bytes = 0
                current_actions = 0
            current_parts.append(action_line)
            current_bytes += action_bytes
            current_actions += 1
        if current_parts:
            payloads.append(b"".join(current_parts))
        for batch_index, payload in enumerate(payloads):
            batch_refresh = str(refresh or "wait_for") if batch_index == len(payloads) - 1 else "false"
            data, batch_took_ms = self._request_json(
                "POST",
                "/_bulk",
                raw_body=payload,
                query={"refresh": batch_refresh},
                content_type="application/x-ndjson",
                timeout_s=self.bulk_timeout_s,
            )
            items = data.get("items") or []
            for item in items:
                op = item.get("delete") or {}
                status = int(op.get("status") or 0)
                if status in {200, 404}:
                    ok += 1
                else:
                    fail += 1
            took_ms += float(batch_took_ms)
        return {
            "space_name": resolved_space,
            "docs": len(unique_vids),
            "ok_count": ok,
            "fail_count": fail,
            "bulk_ms": round(took_ms, 3),
            "skipped": False,
        }

    def ensure_index(self, index_name: Optional[str] = None) -> Tuple[bool, str]:
        idx = index_name or self.index
        try:
            self._request_json("GET", f"/{idx}")
            # Keep mapping additive to avoid stale indexes missing new fields.
            try:
                self._request_json("PUT", f"/{idx}/_mapping", payload={"properties": self._mapping_properties()})
                return True, "exists"
            except Exception as exc:
                return False, f"mapping_update_failed: {exc}"
        except Exception:
            pass

        mapping = {"mappings": {"properties": self._mapping_properties()}}
        try:
            self._request_json("PUT", f"/{idx}", payload=mapping)
            return True, "created"
        except Exception as exc:
            return False, str(exc)

    def bulk_upsert(
        self,
        docs: List[Dict[str, Any]],
        index_name: Optional[str] = None,
        *,
        refresh: str = "false",
    ) -> Tuple[int, int, float]:
        if not docs:
            return 0, 0, 0.0
        idx = index_name or self.index
        spaces = sorted({self._resolved_space(str(doc.get("space_name") or "")) for doc in docs})
        logger.warning("es_bulk_upsert index=%s spaces=%s docs=%d", idx, ",".join(spaces), len(docs))
        ok = 0
        fail = 0
        took_ms = 0.0
        payloads = self._build_bulk_payloads(docs, index_name=idx)
        for batch_index, payload in enumerate(payloads):
            batch_refresh = str(refresh or "false") if batch_index == len(payloads) - 1 else "false"
            data, batch_took_ms = self._request_json(
                "POST",
                "/_bulk",
                raw_body=payload,
                query={"refresh": batch_refresh},
                content_type="application/x-ndjson",
                timeout_s=self.bulk_timeout_s,
            )
            items = data.get("items") or []
            for item in items:
                op = item.get("index") or {}
                if 200 <= int(op.get("status") or 0) < 300:
                    ok += 1
                else:
                    fail += 1
            took_ms += float(batch_took_ms)
        return ok, fail, took_ms

    def _build_bulk_payloads(self, docs: List[Dict[str, Any]], *, index_name: str) -> List[bytes]:
        payloads: List[bytes] = []
        current_parts: List[bytes] = []
        current_bytes = 0
        current_actions = 0

        for doc in docs:
            vid = int(doc["vid"])
            space_name = self._resolved_space(str(doc.get("space_name") or ""))
            action_line = json.dumps(
                {"index": {"_index": index_name, "_id": self.document_id(space_name, vid)}},
                ensure_ascii=False,
            ).encode("utf-8") + b"\n"
            doc_line = json.dumps(doc, ensure_ascii=False).encode("utf-8") + b"\n"
            entry_parts = [action_line, doc_line]
            entry_bytes = len(action_line) + len(doc_line)

            if entry_bytes > self.bulk_max_bytes:
                raise RuntimeError(
                    f"ES bulk document exceeds configured request budget: vid={vid} bytes={entry_bytes} max={self.bulk_max_bytes}"
                )

            if current_parts and (
                current_actions >= self.bulk_max_actions or current_bytes + entry_bytes > self.bulk_max_bytes
            ):
                payloads.append(b"".join(current_parts))
                current_parts = []
                current_bytes = 0
                current_actions = 0

            current_parts.extend(entry_parts)
            current_bytes += entry_bytes
            current_actions += 1

        if current_parts:
            payloads.append(b"".join(current_parts))
        return payloads

    @staticmethod
    def _mapping_properties() -> Dict[str, Any]:
        return {
            "vid": {"type": "long"},
            "space_name": {"type": "keyword"},
            "entity_name": {"type": "text"},
            "description": {"type": "text"},
            "entity_raw_id": {"type": "keyword"},
            "entity_raw_id_text": {"type": "text"},
            "raw_id_norm": {"type": "keyword"},
            "raw_id_norm_text": {"type": "text"},
            "entity_type": {"type": "keyword"},
            "entity_type_text": {"type": "text"},
            "source": {"type": "keyword"},
        }
