import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import settings

logger = logging.getLogger(__name__)


class ElasticsearchClient:
    def __init__(self, base_url: str | None = None, index: str | None = None, timeout_ms: int | None = None) -> None:
        self.base_url = (base_url or settings.es_url).rstrip("/")
        self.index = index or settings.es_index
        self.timeout_s = max(0.1, float(timeout_ms or settings.es_timeout_ms) / 1000.0)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        raw_body: Optional[bytes] = None,
        content_type: str = "application/json",
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
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"ES HTTP {exc.code}: {detail}") from exc
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
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})

        body: Dict[str, Any] = {
            "size": max(1, min(int(limit), 500)),
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
        entity_type: Optional[str],
        source: Optional[str],
    ) -> Tuple[List[Tuple[int, float]], float]:
        mode_norm = str(mode or "contains").strip().lower()
        if mode_norm not in {"contains", "prefix", "exact"}:
            mode_norm = "contains"

        filters: List[Dict[str, Any]] = []
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})

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
        entity_type: Optional[str],
        source: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], float]:
        filters: List[Dict[str, Any]] = []
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})

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
        entity_type: Optional[str],
        source: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], float]:
        filters: List[Dict[str, Any]] = []
        if entity_type and entity_type.strip():
            filters.append({"term": {"entity_type": entity_type.strip()}})
        if source and source.strip():
            filters.append({"term": {"source": source.strip()}})

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

    def bulk_upsert(self, docs: List[Dict[str, Any]], index_name: Optional[str] = None) -> Tuple[int, int, float]:
        if not docs:
            return 0, 0, 0.0
        idx = index_name or self.index
        lines: List[str] = []
        for doc in docs:
            vid = int(doc["vid"])
            lines.append(json.dumps({"index": {"_index": idx, "_id": str(vid)}}, ensure_ascii=False))
            lines.append(json.dumps(doc, ensure_ascii=False))
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        data, took_ms = self._request_json(
            "POST",
            "/_bulk",
            raw_body=payload,
            query={"refresh": "false"},
            content_type="application/x-ndjson",
        )

        items = data.get("items") or []
        ok = 0
        fail = 0
        for item in items:
            op = item.get("index") or {}
            if 200 <= int(op.get("status") or 0) < 300:
                ok += 1
            else:
                fail += 1
        return ok, fail, took_ms

    @staticmethod
    def _mapping_properties() -> Dict[str, Any]:
        return {
            "vid": {"type": "long"},
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
