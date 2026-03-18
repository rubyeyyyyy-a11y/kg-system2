import logging
import time
from typing import Any, Dict, List, Sequence

from app.config import settings
from nebula3.Exception import IOErrorException, NotValidConnectionException

from app.core.space_context import get_current_space
from app.db.nebula import EDGE_TAG, execute_ngql
from app.services.common import vw

logger = logging.getLogger(__name__)


class NebulaQueryError(RuntimeError):
    pass


class NebulaTimeoutError(NebulaQueryError):
    pass


class NebulaConnectionError(NebulaQueryError):
    pass


def _is_timeout_text(text: str) -> bool:
    msg = str(text or "").lower()
    return "timeout" in msg or "timed out" in msg


def _is_connection_text(text: str) -> bool:
    msg = str(text or "").lower()
    return (
        "notvalidconnection" in msg
        or "not valid connection" in msg
        or "services status exception" in msg
        or "status: bad" in msg
        or "tsocket read 0 bytes" in msg
    )


class NebulaClient:
    def __init__(self, space_name: str | None = None) -> None:
        self.space_name = space_name

    def _resolved_space(self, space_name: str | None = None) -> str:
        return str(space_name or self.space_name or get_current_space())

    def execute(self, ngql: str, *, space_name: str | None = None):
        start = time.perf_counter()
        try:
            res = execute_ngql(ngql, space_name=self._resolved_space(space_name))
        except (IOErrorException, TimeoutError) as exc:
            msg = str(exc)
            if _is_timeout_text(msg):
                raise NebulaTimeoutError(msg) from exc
            raise NebulaConnectionError(msg) from exc
        except NotValidConnectionException as exc:
            raise NebulaConnectionError(str(exc)) from exc
        except Exception as exc:
            msg = str(exc)
            if _is_timeout_text(msg):
                raise NebulaTimeoutError(msg) from exc
            if _is_connection_text(msg):
                raise NebulaConnectionError(msg) from exc
            raise NebulaQueryError(msg) from exc

        took_ms = (time.perf_counter() - start) * 1000.0
        if not res.is_succeeded():
            msg = str(res.error_msg() or "")
            if _is_timeout_text(msg):
                raise NebulaTimeoutError(msg)
            if _is_connection_text(msg):
                raise NebulaConnectionError(msg)
            raise NebulaQueryError(msg)

        return res, took_ms

    def fetch_entity_props(self, vids: Sequence[int], *, space_name: str | None = None) -> tuple[List[Dict[str, Any]], float]:
        ids = sorted({int(v) for v in vids})
        if not ids:
            return [], 0.0

        vid_list = ",".join(str(v) for v in ids)
        ngql = f"""
MATCH (v:`Entity`)
WHERE id(v) IN [{vid_list}]
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS name,
       v.`Entity`.`entity_type` AS type,
       v.`Entity`.`entity_raw_id` AS raw_id,
       v.`Entity`.`source` AS source,
       v.`Entity`.`description` AS description;
"""
        res, took_ms = self.execute(ngql, space_name=space_name)
        vids_col = res.column_values("vid")
        names = res.column_values("name")
        types = res.column_values("type")
        raw_ids = res.column_values("raw_id")
        sources = res.column_values("source")
        descriptions = res.column_values("description")

        rows: List[Dict[str, Any]] = []
        for i in range(len(vids_col)):
            rows.append(
                {
                    "vid": int(vw(vids_col[i])),
                    "label": str(vw(names[i]) or ""),
                    "entity_type": str(vw(types[i]) or ""),
                    "raw_id": str(vw(raw_ids[i]) or ""),
                    "source": str(vw(sources[i]) or ""),
                    "description": str(vw(descriptions[i]) or ""),
                }
            )
        return rows, took_ms

    def fetch_edges_between(
        self,
        vids: Sequence[int],
        limit: int = 5000,
        *,
        space_name: str | None = None,
    ) -> tuple[List[Dict[str, Any]], float]:
        ids = sorted({int(v) for v in vids})
        if not ids:
            return [], 0.0
        id_list = ",".join(str(v) for v in ids)
        ngql = f"""
GO FROM {id_list} OVER {EDGE_TAG} BIDIRECT
YIELD src(edge) AS src, dst(edge) AS dst,
      rank(edge) AS rank,
      properties(edge).relation AS relation,
      properties(edge).source AS source_db
| LIMIT {int(limit)};
"""
        res, took_ms = self.execute(ngql, space_name=space_name)
        srcs = res.column_values("src")
        dsts = res.column_values("dst")
        ranks = res.column_values("rank")
        relations = res.column_values("relation")
        sources = res.column_values("source_db")

        allowed = set(ids)
        edges: List[Dict[str, Any]] = []
        for i in range(len(srcs)):
            src = int(vw(srcs[i]))
            dst = int(vw(dsts[i]))
            if src not in allowed or dst not in allowed:
                continue
            edges.append(
                {
                    "source": src,
                    "target": dst,
                    "rank": str(int(vw(ranks[i]) or 0)),
                    "edge_type": settings.edge_type,
                    "relation": str(vw(relations[i]) or ""),
                    "source_db": str(vw(sources[i]) or ""),
                }
            )
        return edges, took_ms

    def fetch_incident_edges(
        self,
        vid: int,
        *,
        edge_type: str | None = None,
        limit: int | None = None,
        space_name: str | None = None,
    ) -> tuple[List[Dict[str, Any]], float]:
        normalized_vid = int(vid)
        if normalized_vid <= 0:
            return [], 0.0
        edge_name = str(edge_type or settings.edge_type or "").strip()
        edge_tag = f"`{edge_name.replace('`', '')}`" if edge_name else EDGE_TAG
        ngql = (
            f"GO FROM {normalized_vid} OVER {edge_tag} BIDIRECT\n"
            "YIELD src(edge) AS src_vid,\n"
            "      dst(edge) AS dst_vid,\n"
            "      rank(edge) AS rank,\n"
            "      properties(edge).relation AS relation"
        )
        if limit is not None and int(limit) > 0:
            ngql += f"\n| LIMIT {int(limit)}"
        ngql += ";"
        res, took_ms = self.execute(ngql, space_name=space_name)
        srcs = res.column_values("src_vid")
        dsts = res.column_values("dst_vid")
        ranks = res.column_values("rank")
        relations = res.column_values("relation")
        edges: List[Dict[str, Any]] = []
        for i in range(len(srcs)):
            edges.append(
                {
                    "edge_type": edge_name or settings.edge_type,
                    "src_vid": int(vw(srcs[i]) or 0),
                    "dst_vid": int(vw(dsts[i]) or 0),
                    "rank": int(vw(ranks[i]) or 0),
                    "relation": str(vw(relations[i]) or ""),
                }
            )
        return edges, took_ms
