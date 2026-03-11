import time
from typing import Dict, List, Tuple

from app.config import settings
from app.db.nebula_client import execute_ngql_safe
from app.services import metadata_service
from app.services.common import esc, vw
from app.services.metadata_ids import metadata_stat_vid


ENTITY_STAT_TAG = "EntityTypeStat"
RELATION_STAT_TAG = "RelationTypeStat"


def _query_entity_type_counts_db() -> List[Tuple[str, int]]:
    res = execute_ngql_safe(
        """
        MATCH (v:`Entity`)
        RETURN lower(coalesce(v.`Entity`.`entity_type`, "")) AS entity_type, count(*) AS cnt;
        """
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


def _query_relation_type_counts_db() -> List[Tuple[str, int]]:
    res = execute_ngql_safe(
        f"""
        MATCH ()-[e:`{settings.edge_type}`]-()
        RETURN lower(coalesce(properties(e).relation, "")) AS relation_type, count(*) AS cnt;
        """
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


def _ensure_metadata_schema() -> None:
    execute_ngql_safe(
        """
        CREATE TAG IF NOT EXISTS `EntityTypeStat`(
          `entity_type` string,
          `entity_type_norm` string,
          `count` int64,
          `updated_at` int64,
          `updated_by` string
        );
        """
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
        """
    )


def _clear_tag(tag: str) -> None:
    res = execute_ngql_safe(f"MATCH (m:`{tag}`) RETURN id(m) AS vid;")
    vids = [int(vw(item)) for item in res.column_values("vid")]
    if vids:
        execute_ngql_safe("DELETE VERTEX " + ",".join(str(vid) for vid in vids) + ";")


def _insert_stats(*, tag: str, kind: str, label_field: str, norm_field: str, rows: List[Tuple[str, int]], actor: str) -> None:
    if not rows:
        return
    now_sec = int(time.time())
    values = []
    for key, count in rows:
        vid = metadata_stat_vid(kind, key)
        values.append(
            f'{vid}:("{esc(key)}", "{esc(key)}", {int(count)}, {now_sec}, "{esc(actor)}")'
        )
    execute_ngql_safe(
        f"INSERT VERTEX `{tag}`(`{label_field}`, `{norm_field}`, `count`, `updated_at`, `updated_by`) VALUES "
        + ",".join(values)
        + ";"
    )


def refresh_from_db(actor: str = "import_job") -> dict:
    _ensure_metadata_schema()
    entity_counts = _query_entity_type_counts_db()
    relation_counts = _query_relation_type_counts_db()
    _clear_tag(ENTITY_STAT_TAG)
    _clear_tag(RELATION_STAT_TAG)
    _insert_stats(
        tag=ENTITY_STAT_TAG,
        kind="entity_type",
        label_field="entity_type",
        norm_field="entity_type_norm",
        rows=entity_counts,
        actor=actor,
    )
    _insert_stats(
        tag=RELATION_STAT_TAG,
        kind="relation_type",
        label_field="relation_type",
        norm_field="relation_type_norm",
        rows=relation_counts,
        actor=actor,
    )
    metadata_service.invalidate_metadata_cache()
    return {
        "source": "db",
        "entity_type_count": len(entity_counts),
        "relation_type_count": len(relation_counts),
    }
