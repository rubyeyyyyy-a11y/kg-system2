import logging
import time
from typing import Any, Dict, List, Optional

from app.core.space_context import get_current_space
from app.db.nebula_client import NebulaExecutionError, execute_ngql_safe
from app.services.common import esc, vw
from app.services.metadata_ids import metadata_stat_vid

logger = logging.getLogger(__name__)

ENTITY_STAT_TAG = "EntityTypeStat"
RELATION_STAT_TAG = "RelationTypeStat"
_CACHE_TTL_SEC = 300.0
_ENTITY_CACHE_BY_SPACE: Dict[str, Dict[str, Any]] = {}
_RELATION_CACHE_BY_SPACE: Dict[str, Dict[str, Any]] = {}


def _normalize_key(raw: Optional[str]) -> str:
    return str(raw or "").strip().lower()


def _bucket(cache: Dict[str, Dict[str, Any]], space_name: str) -> Dict[str, Any]:
    # Metadata caches are partitioned by space_name so refresh/reads do not
    # leak entity or relation type stats across managed spaces.
    return cache.setdefault(space_name, {"ts": 0.0, "data": []})


def invalidate_metadata_cache(space_name: Optional[str] = None) -> None:
    if space_name is None:
        _ENTITY_CACHE_BY_SPACE.clear()
        _RELATION_CACHE_BY_SPACE.clear()
        return
    _bucket(_ENTITY_CACHE_BY_SPACE, space_name).update({"ts": 0.0, "data": []})
    _bucket(_RELATION_CACHE_BY_SPACE, space_name).update({"ts": 0.0, "data": []})


def _actor_text(actor: Optional[str]) -> str:
    text = str(actor or "").strip()
    if not text:
        return "metadata_sync"
    return text[:64]


def list_entity_types(limit: int = 200, *, space_name: Optional[str] = None) -> List[Dict[str, Any]]:
    resolved_space = str(space_name or get_current_space())
    entity_cache = _bucket(_ENTITY_CACHE_BY_SPACE, resolved_space)
    now = time.time()
    if entity_cache["data"] and (now - float(entity_cache["ts"])) < _CACHE_TTL_SEC:
        return [dict(x) for x in entity_cache["data"]]

    ngql = f"""
    MATCH (m:`{ENTITY_STAT_TAG}`)
    WHERE coalesce(m.`{ENTITY_STAT_TAG}`.`count`, 0) > 0
    RETURN coalesce(m.`{ENTITY_STAT_TAG}`.`entity_type_norm`, "") AS entity_type,
           coalesce(m.`{ENTITY_STAT_TAG}`.`count`, 0) AS cnt
    ORDER BY cnt DESC, entity_type ASC
    LIMIT {max(1, int(limit))};
    """
    res = execute_ngql_safe(ngql, space_name=resolved_space)

    types = res.column_values("entity_type")
    counts = res.column_values("cnt")
    items: List[Dict[str, Any]] = []
    for i in range(len(types)):
        key = _normalize_key(vw(types[i]))
        if not key:
            continue
        cnt = int(vw(counts[i]) or 0)
        if cnt <= 0:
            continue
        items.append({"entity_type": key, "count": cnt})

    entity_cache["ts"] = now
    entity_cache["data"] = [dict(x) for x in items]
    return items


def list_relation_type_stats(*, space_name: Optional[str] = None) -> List[Dict[str, int | str]]:
    resolved_space = str(space_name or get_current_space())
    relation_cache = _bucket(_RELATION_CACHE_BY_SPACE, resolved_space)
    now = time.time()
    if relation_cache["data"] and (now - float(relation_cache["ts"])) < _CACHE_TTL_SEC:
        return [dict(x) for x in relation_cache["data"]]

    ngql = f"""
    MATCH (m:`{RELATION_STAT_TAG}`)
    WHERE coalesce(m.`{RELATION_STAT_TAG}`.`count`, 0) > 0
    RETURN coalesce(m.`{RELATION_STAT_TAG}`.`relation_type_norm`, "") AS relation_type,
           coalesce(m.`{RELATION_STAT_TAG}`.`count`, 0) AS cnt
    ORDER BY cnt DESC, relation_type ASC;
    """
    res = execute_ngql_safe(ngql, space_name=resolved_space)
    rels: List[Dict[str, int | str]] = []
    rel_values = res.column_values("relation_type")
    count_values = res.column_values("cnt")
    for i in range(len(rel_values)):
        rel = _normalize_key(vw(rel_values[i]))
        if rel:
            rels.append({"relation_type": rel, "count": int(vw(count_values[i]) or 0)})

    relation_cache["ts"] = now
    relation_cache["data"] = [dict(x) for x in rels]
    return [dict(x) for x in rels]


def list_relation_types(limit: int = 5000, *, space_name: Optional[str] = None) -> List[str]:
    items = list_relation_type_stats(space_name=space_name)
    safe_limit = max(1, int(limit))
    return [str(x["relation_type"]) for x in items[:safe_limit]]


def query_relation_types(
    *,
    q: str = "",
    limit: int = 100,
    offset: int = 0,
    space_name: Optional[str] = None,
) -> Dict[str, Any]:
    safe_limit = max(1, min(int(limit or 100), 200))
    safe_offset = max(0, int(offset or 0))
    needle = _normalize_key(q)

    items = list_relation_type_stats(space_name=space_name)
    if needle:
        filtered = [dict(x) for x in items if needle in str(x.get("relation_type") or "")]
    else:
        filtered = [dict(x) for x in items]

    matched_total = len(filtered)
    page = filtered[safe_offset : safe_offset + safe_limit + 1]
    has_more = len(page) > safe_limit
    visible_items = page[:safe_limit]
    next_offset = safe_offset + len(visible_items) if has_more else None
    return {
        "items": visible_items,
        "q": needle,
        "limit": safe_limit,
        "offset": safe_offset,
        "next_offset": next_offset,
        "has_more": has_more,
        "matched_total": matched_total,
    }


def _find_stat_vertex(
    *,
    tag: str,
    norm_field: str,
    key_norm: str,
    space_name: Optional[str] = None,
) -> Optional[Dict[str, int]]:
    ngql = f"""
    MATCH (m:`{tag}`)
    WHERE coalesce(m.`{tag}`.`{norm_field}`, "") == "{esc(key_norm)}"
    RETURN id(m) AS vid, coalesce(m.`{tag}`.`count`, 0) AS cnt
    LIMIT 1;
    """
    res = execute_ngql_safe(ngql, space_name=space_name)
    if len(res.rows()) == 0:
        return None
    return {
        "vid": int(vw(res.column_values("vid")[0])),
        "count": int(vw(res.column_values("cnt")[0]) or 0),
    }


def _update_stat_vertex(
    *,
    tag: str,
    vid: int,
    label_field: str,
    norm_field: str,
    label: str,
    key_norm: str,
    count: int,
    actor: str,
    space_name: Optional[str] = None,
) -> None:
    now_sec = int(time.time())
    ngql = f"""
    UPDATE VERTEX ON `{tag}` {int(vid)}
    SET `{tag}`.`{label_field}` = "{esc(label)}",
        `{tag}`.`{norm_field}` = "{esc(key_norm)}",
        `{tag}`.`count` = {max(0, int(count))},
        `{tag}`.`updated_at` = {now_sec},
        `{tag}`.`updated_by` = "{esc(actor)}"
    ;
    """
    execute_ngql_safe(ngql, space_name=space_name)


def _insert_stat_vertex(
    *,
    tag: str,
    kind: str,
    label_field: str,
    norm_field: str,
    label: str,
    key_norm: str,
    count: int,
    actor: str,
    space_name: Optional[str] = None,
) -> None:
    now_sec = int(time.time())
    for salt in range(0, 8):
        vid = metadata_stat_vid(kind, key_norm, salt=salt)
        ngql = f"""
        INSERT VERTEX {tag}({label_field}, {norm_field}, count, updated_at, updated_by)
        VALUES {int(vid)}:("{esc(label)}", "{esc(key_norm)}", {max(0, int(count))}, {now_sec}, "{esc(actor)}");
        """
        try:
            execute_ngql_safe(ngql, space_name=space_name)
            return
        except NebulaExecutionError:
            existing = _find_stat_vertex(tag=tag, norm_field=norm_field, key_norm=key_norm, space_name=space_name)
            if existing is not None:
                _update_stat_vertex(
                    tag=tag,
                    vid=int(existing["vid"]),
                    label_field=label_field,
                    norm_field=norm_field,
                    label=label,
                    key_norm=key_norm,
                    count=int(existing["count"]) + max(0, int(count)),
                    actor=actor,
                    space_name=space_name,
                )
                return
            if salt >= 7:
                raise


def _apply_delta(
    *,
    kind: str,
    tag: str,
    label_field: str,
    norm_field: str,
    raw_label: str,
    delta: int,
    actor: str,
    space_name: Optional[str] = None,
) -> None:
    key_norm = _normalize_key(raw_label)
    if not key_norm:
        return

    found = _find_stat_vertex(tag=tag, norm_field=norm_field, key_norm=key_norm, space_name=space_name)
    if found is None:
        if int(delta) <= 0:
            return
        _insert_stat_vertex(
            tag=tag,
            kind=kind,
            label_field=label_field,
            norm_field=norm_field,
            label=key_norm,
            key_norm=key_norm,
            count=int(delta),
            actor=actor,
            space_name=space_name,
        )
        return

    new_count = max(0, int(found["count"]) + int(delta))
    _update_stat_vertex(
        tag=tag,
        vid=int(found["vid"]),
        label_field=label_field,
        norm_field=norm_field,
        label=key_norm,
        key_norm=key_norm,
        count=new_count,
        actor=actor,
        space_name=space_name,
    )


def sync_entity_type_change(before_type: str, after_type: str, actor: Optional[str] = None) -> None:
    before_norm = _normalize_key(before_type)
    after_norm = _normalize_key(after_type)
    if before_norm == after_norm:
        return

    actor_text = _actor_text(actor)
    space_name = get_current_space()
    try:
        _apply_delta(
            kind="entity_type",
            tag=ENTITY_STAT_TAG,
            label_field="entity_type",
            norm_field="entity_type_norm",
            raw_label=before_norm,
            delta=-1,
            actor=actor_text,
            space_name=space_name,
        )
        _apply_delta(
            kind="entity_type",
            tag=ENTITY_STAT_TAG,
            label_field="entity_type",
            norm_field="entity_type_norm",
            raw_label=after_norm,
            delta=1,
            actor=actor_text,
            space_name=space_name,
        )
        invalidate_metadata_cache(space_name)
    except Exception as exc:
        logger.warning(
            "sync_entity_type_change failed before=%r after=%r actor=%r reason=%s",
            before_type,
            after_type,
            actor_text,
            exc,
        )


def sync_relation_type_change(before_relation: str, after_relation: str, actor: Optional[str] = None) -> None:
    before_norm = _normalize_key(before_relation)
    after_norm = _normalize_key(after_relation)
    if before_norm == after_norm:
        return

    actor_text = _actor_text(actor)
    space_name = get_current_space()
    try:
        _apply_delta(
            kind="relation_type",
            tag=RELATION_STAT_TAG,
            label_field="relation_type",
            norm_field="relation_type_norm",
            raw_label=before_norm,
            delta=-1,
            actor=actor_text,
            space_name=space_name,
        )
        _apply_delta(
            kind="relation_type",
            tag=RELATION_STAT_TAG,
            label_field="relation_type",
            norm_field="relation_type_norm",
            raw_label=after_norm,
            delta=1,
            actor=actor_text,
            space_name=space_name,
        )
        invalidate_metadata_cache(space_name)
    except Exception as exc:
        logger.warning(
            "sync_relation_type_change failed before=%r after=%r actor=%r reason=%s",
            before_relation,
            after_relation,
            actor_text,
            exc,
        )
