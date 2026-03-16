import time
import os
from typing import Dict, List, Tuple

from app.config import settings
from app.db.nebula_client import execute_ngql_safe
from app.services import metadata_service
from app.services.common import esc, vw
from app.services.metadata_ids import metadata_stat_vid


ENTITY_STAT_TAG = "EntityTypeStat"
RELATION_STAT_TAG = "RelationTypeStat"
_STAT_INSERT_BATCH_SIZE = 200
_NEBULA_QUERY_LIMIT_BYTES = max(1024, int(os.getenv("NEBULA_MAX_QUERY_BYTES", str(4 * 1024 * 1024))))
_NEBULA_QUERY_BUDGET_BYTES = max(1024, min(_NEBULA_QUERY_LIMIT_BYTES - 64 * 1024, int(_NEBULA_QUERY_LIMIT_BYTES * 0.85)))


def _query_entity_type_counts_db(space_name: str | None = None) -> List[Tuple[str, int]]:
    res = execute_ngql_safe(
        """
        MATCH (v:`Entity`)
        RETURN lower(coalesce(v.`Entity`.`entity_type`, "")) AS entity_type, count(*) AS cnt;
        """,
        space_name=space_name,
    )
    keys = res.column_values("entity_type")
    counts = res.column_values("cnt")
    items: Dict[str, int] = {}
    for idx in range(len(keys)):
        key = str(vw(keys[idx]) or "").strip().lower()
        cnt = int(vw(counts[idx]) or 0)
        if key and cnt > 0:
            items[key] = cnt
    return sorted(items.items(), key=lambda item: (-item[1], item[0]))


def _query_relation_type_counts_db(space_name: str | None = None) -> List[Tuple[str, int]]:
    res = execute_ngql_safe(
        f"""
        MATCH ()-[e:`{settings.edge_type}`]->()
        RETURN lower(coalesce(properties(e).relation, "")) AS relation_type, count(*) AS cnt;
        """,
        space_name=space_name,
    )
    keys = res.column_values("relation_type")
    counts = res.column_values("cnt")
    items: Dict[str, int] = {}
    for idx in range(len(keys)):
        key = str(vw(keys[idx]) or "").strip().lower()
        cnt = int(vw(counts[idx]) or 0)
        if key and cnt > 0:
            items[key] = cnt
    return sorted(items.items(), key=lambda item: (-item[1], item[0]))


def _ensure_metadata_schema(space_name: str | None = None) -> None:
    execute_ngql_safe(
        """
        CREATE TAG IF NOT EXISTS `EntityTypeStat`(
          `entity_type` string,
          `entity_type_norm` string,
          `count` int64,
          `updated_at` int64,
          `updated_by` string
        );
        """,
        space_name=space_name,
    )
    execute_ngql_safe(
        """
        CREATE TAG IF NOT EXISTS `RelationTypeStat`(
          `relation_type` string,
          `relation_type_norm` string,
          `count` int64,
          `updated_at` int64,
          `updated_by` string
        );
        """,
        space_name=space_name,
    )


def _clear_tag(tag: str, *, space_name: str | None = None) -> None:
    res = execute_ngql_safe(f"MATCH (m:`{tag}`) RETURN id(m) AS vid;", space_name=space_name)
    vids = [int(vw(item)) for item in res.column_values("vid")]
    if not vids:
        return
    prefix = "DELETE VERTEX "
    for batch in _iter_ngql_batches(prefix=prefix, fragments=[str(vid) for vid in vids]):
        execute_ngql_safe(batch, space_name=space_name)


def _iter_ngql_batches(
    *,
    prefix: str,
    fragments: List[str],
    suffix: str = ";",
    max_fragments: int | None = None,
    max_query_bytes: int | None = None,
) -> List[str]:
    if not fragments:
        return []
    resolved_max_query_bytes = _NEBULA_QUERY_BUDGET_BYTES if max_query_bytes is None else max(1024, int(max_query_bytes))

    batches: List[str] = []
    current: List[str] = []
    prefix_bytes = len(prefix.encode("utf-8"))
    suffix_bytes = len(suffix.encode("utf-8"))
    current_bytes = prefix_bytes + suffix_bytes

    for fragment in fragments:
        fragment_bytes = len(fragment.encode("utf-8"))
        separator_bytes = 1 if current else 0
        next_bytes = current_bytes + separator_bytes + fragment_bytes
        if current and (
            next_bytes > resolved_max_query_bytes
            or (max_fragments is not None and len(current) >= max(1, int(max_fragments)))
        ):
            batches.append(prefix + ",".join(current) + suffix)
            current = []
            current_bytes = prefix_bytes + suffix_bytes
            separator_bytes = 0
            next_bytes = current_bytes + fragment_bytes
        if next_bytes > resolved_max_query_bytes:
            raise RuntimeError(
                f"metadata query fragment exceeds safe Nebula query budget: bytes={next_bytes} max={resolved_max_query_bytes}"
            )
        current.append(fragment)
        current_bytes = next_bytes

    if current:
        batches.append(prefix + ",".join(current) + suffix)
    return batches


def _insert_stats(
    *,
    tag: str,
    kind: str,
    label_field: str,
    norm_field: str,
    rows: List[Tuple[str, int]],
    actor: str,
    space_name: str | None = None,
) -> None:
    if not rows:
        return
    now_sec = int(time.time())
    for offset in range(0, len(rows), _STAT_INSERT_BATCH_SIZE):
        batch = rows[offset : offset + _STAT_INSERT_BATCH_SIZE]
        values: List[str] = []
        for key, count in batch:
            vid = metadata_stat_vid(kind, key)
            values.append(
                f'{vid}:("{esc(key)}", "{esc(key)}", {int(count)}, {now_sec}, "{esc(actor)}")'
            )
        prefix = f"INSERT VERTEX `{tag}`(`{label_field}`, `{norm_field}`, `count`, `updated_at`, `updated_by`) VALUES "
        for statement in _iter_ngql_batches(
            prefix=prefix,
            fragments=values,
            max_fragments=_STAT_INSERT_BATCH_SIZE,
        ):
            execute_ngql_safe(statement, space_name=space_name)


def refresh_from_db(actor: str = "import_job", space_name: str | None = None) -> dict:
    # Metadata refresh is space-aware end-to-end: rebuild stats inside the
    # target Nebula space, then invalidate only that space's cache bucket.
    _ensure_metadata_schema(space_name=space_name)
    entity_counts = _query_entity_type_counts_db(space_name=space_name)
    relation_counts = _query_relation_type_counts_db(space_name=space_name)
    _clear_tag(ENTITY_STAT_TAG, space_name=space_name)
    _clear_tag(RELATION_STAT_TAG, space_name=space_name)
    _insert_stats(
        tag=ENTITY_STAT_TAG,
        kind="entity_type",
        label_field="entity_type",
        norm_field="entity_type_norm",
        rows=entity_counts,
        actor=actor,
        space_name=space_name,
    )
    _insert_stats(
        tag=RELATION_STAT_TAG,
        kind="relation_type",
        label_field="relation_type",
        norm_field="relation_type_norm",
        rows=relation_counts,
        actor=actor,
        space_name=space_name,
    )
    metadata_service.invalidate_metadata_cache(space_name)
    return {
        "source": "db",
        "entity_type_count": len(entity_counts),
        "relation_type_count": len(relation_counts),
    }
