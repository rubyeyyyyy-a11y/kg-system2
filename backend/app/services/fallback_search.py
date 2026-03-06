import re
import os
import time
from typing import List, Tuple

from app import config as app_config
from app.clients.nebula_client import NebulaClient
from app.models.search_models import CandidateNode, SearchResultBundle
from app.schemas.search import SearchRequest
from app.services.common import esc, normalize_raw_id, text_score, vw


class FallbackSearchEngine:
    def __init__(self, nebula_client: NebulaClient) -> None:
        self.nebula_client = nebula_client

    def _build_filter_parts(self, req: SearchRequest) -> List[str]:
        parts: List[str] = []
        if req.entity_type and req.entity_type.strip():
            parts.append(f'v.`Entity`.`entity_type` == "{esc(req.entity_type.strip())}"')
        if req.source and req.source.strip():
            parts.append(f'v.`Entity`.`source` == "{esc(req.source.strip())}"')
        return parts

    def _fetch_candidates(self, where_clause: str, limit: int) -> Tuple[List[CandidateNode], float]:
        ngql = f"""
MATCH (v:`Entity`)
WHERE {where_clause}
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS name,
       v.`Entity`.`entity_type` AS entity_type,
       v.`Entity`.`entity_raw_id` AS raw_id,
       v.`Entity`.`source` AS source,
       v.`Entity`.`description` AS description
LIMIT {int(limit)};
"""
        res, took_ms = self.nebula_client.execute(ngql)

        vids = res.column_values("vid")
        names = res.column_values("name")
        types = res.column_values("entity_type")
        raw_ids = res.column_values("raw_id")
        sources = res.column_values("source")
        descriptions = res.column_values("description")

        rows: List[CandidateNode] = []
        for i in range(len(vids)):
            rows.append(
                CandidateNode(
                    vid=int(vw(vids[i])),
                    label=str(vw(names[i]) or ""),
                    entity_type=str(vw(types[i]) or ""),
                    raw_id=str(vw(raw_ids[i]) or ""),
                    source=str(vw(sources[i]) or ""),
                    description=str(vw(descriptions[i]) or ""),
                )
            )
        return rows, took_ms

    def _search_raw_id(self, req: SearchRequest) -> Tuple[SearchResultBundle, float, str]:
        query = (req.entity_raw_id or "").strip()
        if not query:
            return SearchResultBundle(reason="raw_id_empty"), 0.0, "raw_id_empty"

        mode = (req.entity_raw_id_mode or "contains").strip().lower()
        if mode not in {"contains", "prefix", "exact"}:
            mode = "contains"

        filters = self._build_filter_parts(req)
        query_esc = esc(query)
        if mode == "exact":
            raw_expr = f'v.`Entity`.`entity_raw_id` == "{query_esc}"'
        elif mode == "prefix":
            raw_expr = f'v.`Entity`.`entity_raw_id` STARTS WITH "{query_esc}"'
        else:
            raw_expr = f'v.`Entity`.`entity_raw_id` CONTAINS "{query_esc}"'

        where_parts = [f"({raw_expr})", *[f"({p})" for p in filters]]
        where_clause = " AND ".join(where_parts)

        limit = min(app_config.settings.search_candidate_limit, 120)
        rows, candidate_ms = self._fetch_candidates(where_clause, limit)

        query_norm = normalize_raw_id(query)
        for row in rows:
            rid_norm = normalize_raw_id(row.raw_id)
            if rid_norm == query_norm:
                row.score = 1.0
            elif rid_norm.startswith(query_norm):
                row.score = 0.9
            elif query_norm and query_norm in rid_norm:
                row.score = 0.7
            else:
                row.score = 0.4

        rows.sort(key=lambda x: float(x.score or 0.0), reverse=True)
        top = rows[: app_config.settings.search_topk]
        return (
            SearchResultBundle(nodes=top, total_candidates=len(rows), reason="fallback_raw_id"),
            candidate_ms,
            "fallback_raw_id",
        )

    def search(self, req: SearchRequest) -> Tuple[SearchResultBundle, float, str]:
        started = time.perf_counter()
        if (req.entity_raw_id or "").strip():
            return self._search_raw_id(req)

        q = (req.q or "").strip()
        if len(q) < app_config.settings.search_min_query_len:
            return SearchResultBundle(reason="q_too_short"), 0.0, "q_too_short"

        # Strict guardrail for million-scale graph without fulltext index:
        # by default block text scan fallback and only allow exact-id style lookups.
        # Set FALLBACK_ENABLE_SCAN=1 to re-enable nGQL text scan in emergency.
        fallback_scan_enabled = str(os.getenv("FALLBACK_ENABLE_SCAN", "0")).strip() in {
            "1",
            "true",
            "yes",
            "on",
        }
        if not fallback_scan_enabled:
            if q.isdigit():
                ngql = f"""
MATCH (v:`Entity`)
WHERE id(v) == {int(q)}
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS name,
       v.`Entity`.`entity_type` AS entity_type,
       v.`Entity`.`entity_raw_id` AS raw_id,
       v.`Entity`.`source` AS source,
       v.`Entity`.`description` AS description
LIMIT 1;
"""
                res, candidate_ms = self.nebula_client.execute(ngql)
                vids = res.column_values("vid")
                names = res.column_values("name")
                types = res.column_values("entity_type")
                raw_ids = res.column_values("raw_id")
                sources = res.column_values("source")
                descriptions = res.column_values("description")
                nodes: List[CandidateNode] = []
                for i in range(len(vids)):
                    nodes.append(
                        CandidateNode(
                            vid=int(vw(vids[i])),
                            label=str(vw(names[i]) or ""),
                            entity_type=str(vw(types[i]) or ""),
                            raw_id=str(vw(raw_ids[i]) or ""),
                            source=str(vw(sources[i]) or ""),
                            description=str(vw(descriptions[i]) or ""),
                            score=1.0,
                        )
                    )
                return SearchResultBundle(nodes=nodes, total_candidates=len(nodes), reason="fallback_vid_exact"), candidate_ms, "fallback_vid_exact"

            if re.match(r"^[A-Za-z][A-Za-z0-9_]+:[A-Za-z0-9_\\-]+$", q):
                cloned = req.model_copy(update={"entity_raw_id": q, "entity_raw_id_mode": "prefix"})
                return self._search_raw_id(cloned)

            return SearchResultBundle(reason="fallback_scan_blocked"), 0.0, "fallback_scan_blocked"

        filters = self._build_filter_parts(req)
        q_esc = esc(q)

        allow_desc = bool(req.search_in_description and len(q) >= app_config.settings.search_min_query_len)
        if allow_desc:
            limit = min(app_config.settings.search_desc_candidate_limit, 50)
        else:
            limit = app_config.settings.search_candidate_limit

        conditions: List[str] = []
        if req.search_in_name:
            conditions.append(f'v.`Entity`.`entity_name` CONTAINS "{q_esc}"')
        if allow_desc:
            conditions.append(f'v.`Entity`.`description` CONTAINS "{q_esc}"')
        if req.search_in_type:
            conditions.append(f'v.`Entity`.`entity_type` CONTAINS "{q_esc}"')
        if req.search_in_raw_id:
            conditions.append(f'v.`Entity`.`entity_raw_id` CONTAINS "{q_esc}"')
        if not conditions:
            conditions.append(f'v.`Entity`.`entity_name` CONTAINS "{q_esc}"')

        # Guardrail: never force name AND description scan together.
        text_clause = " OR ".join([f"({expr})" for expr in conditions])
        where_parts = [f"({text_clause})", *[f"({f})" for f in filters]]
        where_clause = " AND ".join(where_parts)

        rows, candidate_ms = self._fetch_candidates(where_clause, limit)
        for row in rows:
            row.score = text_score(q, row.label, row.description)
        rows.sort(key=lambda x: float(x.score or 0.0), reverse=True)
        top = rows[: app_config.settings.search_topk]

        reason = "fallback_contains"
        if not allow_desc and req.search_in_description:
            reason = "fallback_description_disabled"
        _ = started
        return SearchResultBundle(nodes=top, total_candidates=len(rows), reason=reason), candidate_ms, reason
