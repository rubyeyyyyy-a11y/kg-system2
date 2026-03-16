from __future__ import annotations

from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from app.clients.es_client import ElasticsearchClient
from app.clients.nebula_client import NebulaClient
from app.config import settings
from app.services.common import normalize_raw_id, vw

DEFAULT_FETCH_BATCH_SIZE = 500
DEFAULT_BULK_UPSERT_BATCH_SIZE = settings.es_bulk_upsert_batch_size


def _require_space_name(space_name: str) -> str:
    resolved = str(space_name or "").strip()
    if not resolved:
        raise ValueError("space_name is required")
    return resolved


def build_entity_doc(row: Dict[str, Any], *, space_name: str) -> Dict[str, Any]:
    resolved_space = _require_space_name(space_name)
    raw_id = str(row.get("raw_id") or row.get("entity_raw_id") or "")
    raw_id_norm = normalize_raw_id(raw_id)
    entity_type = str(row.get("entity_type") or "")
    return {
        "vid": int(row["vid"]),
        "space_name": resolved_space,
        "entity_name": str(row.get("label") or row.get("entity_name") or ""),
        "description": str(row.get("description") or ""),
        "entity_raw_id": raw_id,
        "entity_raw_id_text": raw_id,
        "raw_id_norm": raw_id_norm,
        "raw_id_norm_text": raw_id_norm,
        "entity_type": entity_type,
        "entity_type_text": entity_type,
        "source": str(row.get("source") or ""),
    }


def _rows_from_query_result(result: Any) -> List[Dict[str, Any]]:
    vids = result.column_values("vid")
    names = result.column_values("entity_name")
    descriptions = result.column_values("description")
    raw_ids = result.column_values("entity_raw_id")
    entity_types = result.column_values("entity_type")
    sources = result.column_values("source")

    rows: List[Dict[str, Any]] = []
    for index in range(len(vids)):
        rows.append(
            {
                "vid": int(vw(vids[index])),
                "label": str(vw(names[index]) or ""),
                "description": str(vw(descriptions[index]) or ""),
                "raw_id": str(vw(raw_ids[index]) or ""),
                "entity_type": str(vw(entity_types[index]) or ""),
                "source": str(vw(sources[index]) or ""),
            }
        )
    return rows


def fetch_entity_rows(
    space_name: str,
    *,
    vids: Optional[Sequence[int]] = None,
    cursor: Optional[int] = None,
    after_vid: Optional[int] = None,
    batch_size: int = DEFAULT_FETCH_BATCH_SIZE,
    vid_range: Optional[Tuple[Optional[int], Optional[int]]] = None,
    nebula_client: Optional[NebulaClient] = None,
) -> List[Dict[str, Any]]:
    resolved_space = _require_space_name(space_name)
    client = nebula_client or NebulaClient(space_name=resolved_space)

    if vids is not None:
        unique_vids = sorted({int(vid) for vid in vids if int(vid) > 0})
        if not unique_vids:
            return []
        rows: List[Dict[str, Any]] = []
        for offset in range(0, len(unique_vids), max(1, int(batch_size))):
            batch_vids = unique_vids[offset : offset + max(1, int(batch_size))]
            batch_rows, _ = client.fetch_entity_props(batch_vids, space_name=resolved_space)
            rows.extend(batch_rows)
        return rows

    safe_batch_size = max(1, int(batch_size))
    effective_min_vid = None if vid_range is None or vid_range[0] is None else max(0, int(vid_range[0]))
    effective_max_vid = None if vid_range is None or vid_range[1] is None else max(0, int(vid_range[1]))

    if after_vid is not None:
        safe_after_vid = max(0, int(after_vid))
        if effective_min_vid is not None:
            safe_after_vid = max(safe_after_vid, effective_min_vid - 1)
        where_parts = [f"id(v) > {safe_after_vid}"]
        if effective_max_vid is not None:
            where_parts.append(f"id(v) <= {effective_max_vid}")
        where_clause = "WHERE " + " AND ".join(where_parts)
        ngql = f"""
MATCH (v:`Entity`)
{where_clause}
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS entity_name,
       v.`Entity`.`description` AS description,
       v.`Entity`.`entity_raw_id` AS entity_raw_id,
       v.`Entity`.`entity_type` AS entity_type,
       v.`Entity`.`source` AS source
ORDER BY vid ASC
LIMIT {safe_batch_size};
"""
    else:
        safe_cursor = max(0, int(cursor or 0))
        ngql = f"""
MATCH (v:`Entity`)
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS entity_name,
       v.`Entity`.`description` AS description,
       v.`Entity`.`entity_raw_id` AS entity_raw_id,
       v.`Entity`.`entity_type` AS entity_type,
       v.`Entity`.`source` AS source
ORDER BY vid ASC
SKIP {safe_cursor}
LIMIT {safe_batch_size};
"""
    result, _ = client.execute(ngql, space_name=resolved_space)
    rows = _rows_from_query_result(result)
    if vid_range is None:
        return rows

    min_vid, max_vid = vid_range
    filtered: List[Dict[str, Any]] = []
    for row in rows:
        vid = int(row["vid"])
        if min_vid is not None and vid < int(min_vid):
            continue
        if max_vid is not None and vid > int(max_vid):
            continue
        filtered.append(row)
    return filtered


def iter_entity_doc_batches(
    space_name: str,
    *,
    cursor: int = 0,
    after_vid: Optional[int] = None,
    batch_size: int = DEFAULT_FETCH_BATCH_SIZE,
    max_docs: int = 0,
    vid_range: Optional[Tuple[Optional[int], Optional[int]]] = None,
    nebula_client: Optional[NebulaClient] = None,
) -> Iterator[Dict[str, Any]]:
    resolved_space = _require_space_name(space_name)
    emitted = 0
    next_cursor = max(0, int(cursor))
    next_after_vid = max(0, int(after_vid or 0))
    use_after_vid = after_vid is not None

    while True:
        rows = fetch_entity_rows(
            resolved_space,
            cursor=next_cursor,
            after_vid=next_after_vid if use_after_vid else None,
            batch_size=batch_size,
            vid_range=vid_range,
            nebula_client=nebula_client,
        )
        if not rows:
            break

        docs = [build_entity_doc(row, space_name=resolved_space) for row in rows]
        if max_docs > 0 and emitted + len(docs) > int(max_docs):
            docs = docs[: max(0, int(max_docs) - emitted)]
            rows = rows[: len(docs)]
        if not docs:
            break

        cursor_start = next_cursor
        last_vid = max(int(row["vid"]) for row in rows)
        next_cursor = cursor_start + len(rows)
        next_after_vid = last_vid
        emitted += len(docs)
        yield {
            "space_name": resolved_space,
            "rows": rows,
            "docs": docs,
            "cursor": cursor_start,
            "next_cursor": next_cursor,
            "last_vid": last_vid,
            "next_after_vid": next_after_vid,
            "batch_size": len(docs),
            "emitted_total": emitted,
        }

        if max_docs > 0 and emitted >= int(max_docs):
            break


def count_entities(
    space_name: str,
    *,
    nebula_client: Optional[NebulaClient] = None,
    vid_range: Optional[Tuple[Optional[int], Optional[int]]] = None,
) -> Dict[str, Any]:
    resolved_space = _require_space_name(space_name)
    client = nebula_client or NebulaClient(space_name=resolved_space)

    if vid_range is None:
        ngql = """
MATCH (v:`Entity`)
RETURN count(v) AS total;
"""
    else:
        min_vid, max_vid = vid_range
        where_parts: List[str] = []
        if min_vid is not None:
            where_parts.append(f"id(v) >= {max(0, int(min_vid))}")
        if max_vid is not None:
            where_parts.append(f"id(v) <= {max(0, int(max_vid))}")
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        ngql = f"""
MATCH (v:`Entity`)
{where_clause}
RETURN count(v) AS total;
"""

    result, took_ms = client.execute(ngql, space_name=resolved_space)
    totals = result.column_values("total")
    total = int(vw(totals[0])) if totals else 0
    return {
        "space_name": resolved_space,
        "count": total,
        "took_ms": round(float(took_ms), 3),
    }


def bulk_upsert(
    space_name: str,
    docs: Sequence[Dict[str, Any]],
    *,
    es_client: Optional[ElasticsearchClient] = None,
    index_name: Optional[str] = None,
    ensure_index: bool = True,
    refresh: str = "false",
) -> Dict[str, Any]:
    resolved_space = _require_space_name(space_name)
    client = es_client or ElasticsearchClient(index=index_name)

    normalized_docs: List[Dict[str, Any]] = []
    for doc in docs:
        doc_space = str(doc.get("space_name") or resolved_space).strip() or resolved_space
        if doc_space != resolved_space:
            raise ValueError(f"document space_name mismatch: expected `{resolved_space}`, got `{doc_space}`")
        normalized_docs.append({**doc, "space_name": resolved_space})

    ensure_result = {"ok": True, "reason": "skipped"}
    if ensure_index:
        ok, reason = client.ensure_index(index_name=index_name)
        ensure_result = {"ok": bool(ok), "reason": str(reason)}
        if not ok:
            raise RuntimeError(f"failed to ensure ES index: {reason}")

    ok_count, fail_count, bulk_ms = client.bulk_upsert(normalized_docs, index_name=index_name, refresh=refresh)
    return {
        "space_name": resolved_space,
        "docs": len(normalized_docs),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "bulk_ms": bulk_ms,
        "ensure_index": ensure_result,
    }


def sync_entities(
    vids: Sequence[int],
    *,
    space_name: str,
    es_client: Optional[ElasticsearchClient] = None,
    nebula_client: Optional[NebulaClient] = None,
    index_name: Optional[str] = None,
    refresh: str = "false",
) -> Dict[str, Any]:
    resolved_space = _require_space_name(space_name)
    unique_vids = sorted({int(vid) for vid in vids if int(vid) > 0})
    if not unique_vids:
        return {"skipped": True, "reason": "no_entity_vids", "space_name": resolved_space}

    rows = fetch_entity_rows(resolved_space, vids=unique_vids, nebula_client=nebula_client)
    docs = [build_entity_doc(row, space_name=resolved_space) for row in rows]
    ok_count = 0
    fail_count = 0
    bulk_ms = 0.0
    for offset in range(0, len(docs), DEFAULT_BULK_UPSERT_BATCH_SIZE):
        batch_docs = docs[offset : offset + DEFAULT_BULK_UPSERT_BATCH_SIZE]
        batch_refresh = refresh if offset + DEFAULT_BULK_UPSERT_BATCH_SIZE >= len(docs) else "false"
        result = bulk_upsert(
            resolved_space,
            batch_docs,
            es_client=es_client,
            index_name=index_name,
            ensure_index=offset == 0,
            refresh=batch_refresh,
        )
        ok_count += int(result["ok_count"])
        fail_count += int(result["fail_count"])
        bulk_ms += float(result["bulk_ms"])
    return {
        "skipped": False,
        "space_name": resolved_space,
        "input_vids": len(unique_vids),
        "docs": len(docs),
        "ok_count": ok_count,
        "fail_count": fail_count,
        "bulk_ms": round(bulk_ms, 3),
    }


def verify_space(
    space_name: str,
    *,
    es_client: Optional[ElasticsearchClient] = None,
    sample_limit: int = 3,
    index_name: Optional[str] = None,
) -> Dict[str, Any]:
    resolved_space = _require_space_name(space_name)
    client = es_client or ElasticsearchClient(index=index_name)

    doc_count, count_ms = client.count_documents_for_space(resolved_space, index_name=index_name)
    samples, sample_ms = client.fetch_documents_for_space(
        resolved_space,
        limit=max(1, min(int(sample_limit), 10)),
        index_name=index_name,
    )
    sample_ids_ok = True
    sample_space_ok = True
    sample_query_ok = False
    matched_vids: List[int] = []
    query_mode = "none"
    query_ms = 0.0

    for sample in samples:
        source = sample.get("_source") or {}
        try:
            vid = int(source.get("vid"))
        except Exception:
            sample_ids_ok = False
            sample_space_ok = False
            continue
        if str(sample.get("_id") or "") != ElasticsearchClient.document_id(resolved_space, vid):
            sample_ids_ok = False
        if str(source.get("space_name") or "") != resolved_space:
            sample_space_ok = False

    if samples:
        sample_source = samples[0].get("_source") or {}
        raw_id = str(sample_source.get("entity_raw_id") or "")
        query_mode = "raw_id_exact" if raw_id else "entity_name"
        if raw_id:
            raw_norm = normalize_raw_id(raw_id)
            if raw_norm:
                hits, query_ms = client.search_entity_vids_by_raw_id_norm(
                    raw_norm,
                    raw_id_original=raw_id,
                    mode="exact",
                    limit=max(5, int(sample_limit)),
                    space_name=resolved_space,
                    entity_type=None,
                    source=None,
                )
                matched_vids = [int(vid) for vid, _score in hits]
                sample_query_ok = int(sample_source.get("vid") or 0) in matched_vids
        if not sample_query_ok:
            label = str(sample_source.get("entity_name") or "").strip()
            if label:
                hits, query_ms = client.search_entity_vids(
                    label,
                    limit=max(5, int(sample_limit)),
                    offset=0,
                    space_name=resolved_space,
                    search_in_name=True,
                    search_in_description=False,
                    search_in_type=False,
                    search_in_raw_id=False,
                    entity_type=None,
                    source=None,
                )
                matched_vids = [int(vid) for vid, _score in hits]
                sample_query_ok = int(sample_source.get("vid") or 0) in matched_vids
                query_mode = "entity_name"

    ok = doc_count > 0 and bool(samples) and sample_ids_ok and sample_space_ok and sample_query_ok
    return {
        "ok": ok,
        "space_name": resolved_space,
        "doc_count": doc_count,
        "sample_count": len(samples),
        "sample_ids_ok": sample_ids_ok,
        "sample_space_ok": sample_space_ok,
        "sample_query_ok": sample_query_ok,
        "query_mode": query_mode,
        "matched_vids": matched_vids,
        "timings_ms": {
            "count_ms": round(count_ms, 3),
            "sample_ms": round(sample_ms, 3),
            "query_ms": round(query_ms, 3),
        },
        "samples": samples,
    }
