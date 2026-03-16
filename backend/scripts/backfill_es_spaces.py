#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.clients.es_client import ElasticsearchClient
from app.services.search_v2 import indexing_service
from app.services.spaces import registry_service, validation_service
from app.services.spaces import index_status_service

DEFAULT_STATE_FILE = ROOT / "state" / "es_backfill_spaces.state.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill multi-space ES documents for ready spaces")
    parser.add_argument("--space", action="append", default=[], help="explicit space_name; can be repeated")
    parser.add_argument("--all-ready-spaces", action="store_true", help="backfill all registry spaces with status=ready plus default space")
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max", type=int, default=0, help="0 means no limit")
    parser.add_argument("--dry-run", action="store_true", help="scan Nebula rows and report counts without writing ES")
    parser.add_argument("--verify", action="store_true", help="verify each space after backfill")
    parser.add_argument("--resume", action="store_true", help="resume from per-space state buckets")
    parser.add_argument(
        "--reset-space-state",
        action="append",
        default=[],
        help="drop saved resume state for the given space_name before running; can be repeated",
    )
    parser.add_argument("--state-file", type=str, default=str(DEFAULT_STATE_FILE))
    parser.add_argument("--es-index", type=str, default=None)
    parser.add_argument("--summary-json", type=str, default="", help="optional path to write the run summary as json")
    return parser.parse_args()


def read_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"format_version": "es-backfill-v2", "spaces": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"format_version": "es-backfill-v2", "spaces": {}}
    if not isinstance(payload, dict):
        return {"format_version": "es-backfill-v2", "spaces": {}}
    payload.setdefault("format_version", "es-backfill-v2")
    payload.setdefault("spaces", {})
    return payload


def write_state(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def update_space_state(
    payload: Dict[str, Any],
    *,
    space_name: str,
    cursor: int,
    indexed_total: int,
    last_vid: int | None = None,
    phase: str | None = None,
    status: str | None = None,
    note: str | None = None,
    es_doc_count: int | None = None,
    nebula_entity_count: int | None = None,
    coverage_pct: float | None = None,
    full_completion: bool | None = None,
    remaining_docs: int | None = None,
    verify_result: Dict[str, Any] | None = None,
) -> None:
    spaces = payload.setdefault("spaces", {})
    bucket = dict(spaces.get(str(space_name)) or {})
    bucket.update(
        {
        "cursor": int(cursor),
        "indexed_total": int(indexed_total),
        "last_vid": int(last_vid or 0),
        "updated_at": int(time.time()),
        }
    )
    if phase is not None:
        bucket["phase"] = str(phase)
    if status is not None:
        bucket["status"] = str(status)
    if note is not None:
        bucket["note"] = str(note)
    if es_doc_count is not None:
        bucket["es_doc_count"] = int(es_doc_count)
    if nebula_entity_count is not None:
        bucket["nebula_entity_count"] = int(nebula_entity_count)
    if coverage_pct is not None:
        bucket["coverage_pct"] = round(float(coverage_pct), 2)
    if full_completion is not None:
        bucket["full_completion"] = bool(full_completion)
    if remaining_docs is not None:
        bucket["remaining_docs"] = int(remaining_docs)
    if verify_result is not None:
        bucket["verify"] = verify_result
    spaces[str(space_name)] = bucket


def classify_space_status(
    *,
    dry_run: bool,
    fail_count: int,
    verify_result: Dict[str, Any] | None,
    nebula_count: int | None = None,
    es_doc_count: int | None = None,
) -> tuple[str, str]:
    return index_status_service.classify_index_status(
        dry_run=dry_run,
        fail_count=fail_count,
        verify_result=verify_result,
        nebula_count=nebula_count,
        es_doc_count=es_doc_count,
    )


def reset_space_state(payload: Dict[str, Any], *, space_name: str) -> bool:
    spaces = payload.setdefault("spaces", {})
    if str(space_name) not in spaces:
        return False
    del spaces[str(space_name)]
    return True


def _default_space_name() -> str:
    return str(settings.nebula_space or "").strip() or "demo_kg"


def ready_managed_spaces() -> List[str]:
    names = [space.space_name for space in registry_service.list_spaces() if space.status == "ready"]
    default_space = _default_space_name()
    if default_space not in names:
        names.insert(0, default_space)
    return list(dict.fromkeys(names))


def validate_target_space(space_name: str) -> str:
    resolved = validation_service.validate_space_name(space_name)
    default_space = _default_space_name()
    if resolved == default_space:
        return resolved

    summary = registry_service.get_space(resolved)
    if summary is None:
        raise RuntimeError(
            f"space `{resolved}` is not registered; only default `{default_space}` may be backfilled outside registry"
        )
    if summary.status != "ready":
        raise RuntimeError(f"space `{resolved}` is {summary.status}; only status=ready spaces are eligible for backfill")
    return resolved


def resolve_target_spaces(explicit_spaces: List[str], *, include_all_ready: bool) -> List[str]:
    targets: List[str] = []
    if include_all_ready:
        targets.extend(ready_managed_spaces())
    for raw_space in explicit_spaces or []:
        targets.append(validate_target_space(raw_space))
    deduped = list(dict.fromkeys(targets))
    if not deduped:
        raise RuntimeError("no target spaces resolved; use --space and/or --all-ready-spaces")
    return deduped


def _should_use_legacy_es_rewrite(space_name: str, *, es_client: ElasticsearchClient) -> tuple[bool, int]:
    default_space = _default_space_name()
    if str(space_name) != default_space:
        return False, 0
    legacy_count, _took_ms = es_client.count_documents_missing_space()
    return legacy_count > 0, legacy_count


def _run_legacy_es_rewrite_for_space(
    space_name: str,
    *,
    batch_size: int,
    max_docs: int,
    verify: bool,
    resume: bool,
    state_path: Path,
    state_payload: Dict[str, Any],
    es_client: ElasticsearchClient,
    index_name: str | None,
    legacy_doc_count: int,
) -> Dict[str, Any]:
    resumed_state = dict((state_payload.get("spaces") or {}).get(space_name) or {})
    start_last_vid = int(resumed_state.get("last_vid") or 0) if resume else 0
    state_indexed_total = int(resumed_state.get("indexed_total") or 0) if resume else 0
    total_docs = 0
    total_ok = 0
    total_fail = 0
    batch_count = 0
    next_after_vid = start_last_vid
    started = time.perf_counter()
    nebula_count_result = index_status_service.resolve_entity_count(space_name)
    nebula_count = nebula_count_result["count"]
    nebula_count_error = nebula_count_result["error"]

    print(
        f"[backfill] space={space_name} strategy=legacy_es_rewrite start_last_vid={start_last_vid} batch_size={batch_size} max={max_docs} legacy_missing_space_docs={legacy_doc_count} nebula_entity_count={nebula_count if nebula_count is not None else 'unknown'}"
    )
    if nebula_count_error:
        print(f"[backfill] space={space_name} nebula_count_unavailable reason={nebula_count_error}")
    if resume:
        update_space_state(
            state_payload,
            space_name=space_name,
            cursor=state_indexed_total,
            indexed_total=state_indexed_total,
            last_vid=start_last_vid,
            phase="legacy_rewrite_running",
            nebula_entity_count=nebula_count if nebula_count is not None else None,
            note="rewriting legacy no-space ES documents into canonical docs",
        )
        write_state(state_path, state_payload)

    while True:
        docs_page, fetch_ms = es_client.fetch_documents_missing_space(
            limit=batch_size,
            after_vid=next_after_vid if next_after_vid > 0 else None,
            index_name=index_name,
        )
        if not docs_page:
            break

        docs = [
            indexing_service.build_entity_doc(item.get("_source") or {}, space_name=space_name)
            for item in docs_page
            if item.get("_source")
        ]
        if max_docs > 0 and total_docs + len(docs) > int(max_docs):
            docs = docs[: max(0, int(max_docs) - total_docs)]
        if not docs:
            break

        batch_count += 1
        result = indexing_service.bulk_upsert(
            space_name,
            docs,
            es_client=es_client,
            index_name=index_name,
            ensure_index=False,
            refresh="wait_for",
        )
        ok_count = int(result["ok_count"])
        fail_count = int(result["fail_count"])
        total_docs += len(docs)
        total_ok += ok_count
        total_fail += fail_count
        state_indexed_total += ok_count
        next_after_vid = max(int(doc["vid"]) for doc in docs)

        if resume:
            update_space_state(
                state_payload,
                space_name=space_name,
                cursor=state_indexed_total,
                indexed_total=state_indexed_total,
                last_vid=next_after_vid,
                phase="legacy_rewrite_running",
                nebula_entity_count=nebula_count if nebula_count is not None else None,
                note="rewriting legacy no-space ES documents into canonical docs",
            )
            write_state(state_path, state_payload)

        if batch_count == 1 or total_docs % 10000 == 0 or total_fail > 0:
            elapsed = time.perf_counter() - started
            rate = (total_docs / elapsed) if elapsed > 0 else 0.0
            print(
                f"[backfill] space={space_name} strategy=legacy_es_rewrite batch={batch_count} last_vid={next_after_vid} docs={len(docs)} total_docs={total_docs} ok={total_ok} fail={total_fail} fetch_ms={fetch_ms:.1f} bulk_ms={float(result['bulk_ms']):.1f} rate={rate:.1f}/s"
            )

        if total_fail > 0:
            break
        if max_docs > 0 and total_docs >= int(max_docs):
            break

    es_doc_count, es_count_ms = es_client.count_documents_for_space(space_name, index_name=index_name)
    verify_result = None
    if verify:
        verify_result = indexing_service.verify_space(space_name, es_client=es_client, index_name=index_name)
        verified_status, verified_note = classify_space_status(
            dry_run=False,
            fail_count=total_fail,
            verify_result=verify_result,
            nebula_count=nebula_count,
            es_doc_count=es_doc_count,
        )
        print(
            f"[backfill] verify space={space_name} strategy=legacy_es_rewrite status={verified_status} doc_count={verify_result['doc_count']} sample_query_ok={verify_result['sample_query_ok']} es_doc_count={es_doc_count} nebula_entity_count={nebula_count if nebula_count is not None else 'unknown'} note={verified_note}"
        )

    elapsed = time.perf_counter() - started
    status, note = classify_space_status(
        dry_run=False,
        fail_count=total_fail,
        verify_result=verify_result,
        nebula_count=nebula_count,
        es_doc_count=es_doc_count,
    )
    coverage_pct = None
    if nebula_count is not None:
        coverage_pct = 100.0 if nebula_count <= 0 else round((float(es_doc_count) / float(nebula_count)) * 100.0, 2)
    completion_snapshot = index_status_service.build_completion_snapshot(
        status=status,
        nebula_entity_count=nebula_count,
        es_doc_count=es_doc_count,
        coverage_pct=coverage_pct,
    )
    summary = {
        "space_name": space_name,
        "strategy": "legacy_es_rewrite",
        "status": status,
        "note": note,
        "start_cursor": state_indexed_total if resume else 0,
        "start_last_vid": start_last_vid,
        "cursor": state_indexed_total,
        "last_vid": next_after_vid,
        "batch_count": batch_count,
        "docs": total_docs,
        "ok_count": total_ok,
        "fail_count": total_fail,
        "legacy_missing_space_doc_count": legacy_doc_count,
        "nebula_entity_count": nebula_count,
        "nebula_count_ms": nebula_count_result["took_ms"],
        "nebula_count_source": nebula_count_result["source"],
        "nebula_count_error": nebula_count_error,
        "es_doc_count": es_doc_count,
        "es_count_ms": round(es_count_ms, 3),
        "coverage_pct": coverage_pct,
        "verify": verify_result,
        "elapsed_s": round(elapsed, 3),
        **completion_snapshot,
    }
    print(
        f"[backfill] done space={space_name} strategy=legacy_es_rewrite status={status} full_completion={summary['full_completion']} remaining_docs={summary['remaining_docs']} docs={summary['docs']} ok={summary['ok_count']} fail={summary['fail_count']} last_vid={next_after_vid} es_doc_count={es_doc_count} nebula_entity_count={nebula_count if nebula_count is not None else 'unknown'} coverage_pct={coverage_pct if coverage_pct is not None else 'unknown'} elapsed_s={summary['elapsed_s']} note={note}"
    )
    index_status_service.update_index_status_from_summary(space_name, summary)
    update_space_state(
        state_payload,
        space_name=space_name,
        cursor=state_indexed_total,
        indexed_total=state_indexed_total,
        last_vid=next_after_vid,
        phase="full_complete" if summary["full_completion"] else ("failed" if status == "failed" else "verified_partial"),
        status=status,
        note=note,
        es_doc_count=es_doc_count,
        nebula_entity_count=nebula_count if nebula_count is not None else None,
        coverage_pct=coverage_pct,
        full_completion=summary["full_completion"],
        remaining_docs=summary["remaining_docs"] if summary["remaining_docs"] is not None else None,
        verify_result=verify_result,
    )
    write_state(state_path, state_payload)
    return summary


def run_backfill_for_space(
    space_name: str,
    *,
    batch_size: int,
    max_docs: int,
    dry_run: bool,
    verify: bool,
    resume: bool,
    state_path: Path,
    state_payload: Dict[str, Any],
    es_client: ElasticsearchClient,
    index_name: str | None,
) -> Dict[str, Any]:
    use_legacy_rewrite, legacy_doc_count = _should_use_legacy_es_rewrite(space_name, es_client=es_client)
    if use_legacy_rewrite:
        return _run_legacy_es_rewrite_for_space(
            space_name,
            batch_size=batch_size,
            max_docs=max_docs,
            verify=verify,
            resume=resume,
            state_path=state_path,
            state_payload=state_payload,
            es_client=es_client,
            index_name=index_name,
            legacy_doc_count=legacy_doc_count,
        )

    resumed_state = dict((state_payload.get("spaces") or {}).get(space_name) or {})
    start_cursor = int(resumed_state.get("cursor") or 0) if resume else 0
    start_last_vid = int(resumed_state.get("last_vid") or 0) if resume else 0
    resumed_indexed_total = int(resumed_state.get("indexed_total") or start_cursor or 0) if resume else 0
    use_offset_resume = bool(resume and start_last_vid <= 0 and start_cursor > 0)
    total_docs = 0
    total_ok = 0
    total_fail = 0
    state_indexed_total = resumed_indexed_total
    next_cursor = start_cursor
    next_after_vid = start_last_vid
    batch_count = 0
    started = time.perf_counter()
    nebula_count_error = None
    nebula_count_result = index_status_service.resolve_entity_count(space_name)
    nebula_count = nebula_count_result["count"]
    nebula_count_error = nebula_count_result["error"]

    print(
        f"[backfill] space={space_name} mode={'dry-run' if dry_run else 'write'} start_cursor={start_cursor} start_last_vid={start_last_vid} resume_mode={'offset_legacy' if use_offset_resume else 'vid'} batch_size={batch_size} max={max_docs} nebula_entity_count={nebula_count if nebula_count is not None else 'unknown'}"
    )
    if nebula_count_error:
        print(f"[backfill] space={space_name} nebula_count_unavailable reason={nebula_count_error}")
    if resume:
        update_space_state(
            state_payload,
            space_name=space_name,
            cursor=start_cursor,
            indexed_total=resumed_indexed_total,
            last_vid=start_last_vid,
            phase="running",
            nebula_entity_count=nebula_count if nebula_count is not None else None,
        )
        write_state(state_path, state_payload)

    for batch in indexing_service.iter_entity_doc_batches(
        space_name,
        cursor=start_cursor if use_offset_resume else 0,
        after_vid=None if use_offset_resume else start_last_vid,
        batch_size=batch_size,
        max_docs=max_docs,
    ):
        batch_count += 1
        docs = list(batch["docs"])
        total_docs += len(docs)
        next_cursor = int(batch["next_cursor"])
        next_after_vid = int(batch.get("next_after_vid") or batch.get("last_vid") or next_after_vid)

        if dry_run:
            ok_count = len(docs)
            fail_count = 0
            bulk_ms = 0.0
        else:
            result = indexing_service.bulk_upsert(
                space_name,
                docs,
                es_client=es_client,
                index_name=index_name,
                ensure_index=False,
                refresh="wait_for",
            )
            ok_count = int(result["ok_count"])
            fail_count = int(result["fail_count"])
            bulk_ms = float(result["bulk_ms"])
            total_ok += ok_count
            total_fail += fail_count
            state_indexed_total += ok_count
            if resume:
                update_space_state(
                    state_payload,
                    space_name=space_name,
                    cursor=next_cursor,
                    indexed_total=state_indexed_total,
                    last_vid=next_after_vid,
                    phase="running",
                    nebula_entity_count=nebula_count if nebula_count is not None else None,
                )
                write_state(state_path, state_payload)

        if batch_count == 1 or total_docs % 1000 == 0 or total_fail > 0:
            elapsed = time.perf_counter() - started
            rate = (total_docs / elapsed) if elapsed > 0 else 0.0
            print(
                f"[backfill] space={space_name} batch={batch_count} cursor={next_cursor} last_vid={next_after_vid} docs={len(docs)} total_docs={total_docs} ok={total_ok if not dry_run else total_docs} fail={total_fail} bulk_ms={bulk_ms:.1f} rate={rate:.1f}/s"
            )

        if total_fail > 0:
            break

    es_doc_count, es_count_ms = es_client.count_documents_for_space(space_name, index_name=index_name)
    verify_result = None
    if verify:
        verify_result = indexing_service.verify_space(space_name, es_client=es_client, index_name=index_name)
        verified_status, verified_note = classify_space_status(
            dry_run=dry_run,
            fail_count=total_fail,
            verify_result=verify_result,
            nebula_count=nebula_count,
            es_doc_count=es_doc_count,
        )
        print(
            f"[backfill] verify space={space_name} status={verified_status} doc_count={verify_result['doc_count']} sample_query_ok={verify_result['sample_query_ok']} es_doc_count={es_doc_count} nebula_entity_count={nebula_count if nebula_count is not None else 'unknown'} note={verified_note}"
        )

    elapsed = time.perf_counter() - started
    status, note = classify_space_status(
        dry_run=dry_run,
        fail_count=total_fail,
        verify_result=verify_result,
        nebula_count=nebula_count,
        es_doc_count=es_doc_count,
    )
    coverage_pct = None
    if nebula_count is not None:
        coverage_pct = 100.0 if nebula_count <= 0 else round((float(es_doc_count) / float(nebula_count)) * 100.0, 2)
    completion_snapshot = index_status_service.build_completion_snapshot(
        status=status,
        nebula_entity_count=nebula_count,
        es_doc_count=es_doc_count,
        coverage_pct=coverage_pct,
    )
    summary = {
        "space_name": space_name,
        "status": status,
        "note": note,
        "start_cursor": start_cursor,
        "start_last_vid": start_last_vid,
        "cursor": next_cursor,
        "last_vid": next_after_vid,
        "batch_count": batch_count,
        "docs": total_docs,
        "ok_count": total_docs if dry_run else total_ok,
        "fail_count": total_fail,
        "nebula_entity_count": nebula_count,
        "nebula_count_ms": nebula_count_result["took_ms"],
        "nebula_count_source": nebula_count_result["source"],
        "nebula_count_error": nebula_count_error,
        "es_doc_count": es_doc_count,
        "es_count_ms": round(es_count_ms, 3),
        "coverage_pct": coverage_pct,
        "verify": verify_result,
        "elapsed_s": round(elapsed, 3),
        **completion_snapshot,
    }
    print(
        f"[backfill] done space={space_name} status={status} full_completion={summary['full_completion']} remaining_docs={summary['remaining_docs']} docs={summary['docs']} ok={summary['ok_count']} fail={summary['fail_count']} cursor={next_cursor} last_vid={next_after_vid} es_doc_count={es_doc_count} nebula_entity_count={nebula_count if nebula_count is not None else 'unknown'} coverage_pct={coverage_pct if coverage_pct is not None else 'unknown'} elapsed_s={summary['elapsed_s']} note={note}"
    )
    index_status_service.update_index_status_from_summary(space_name, summary)
    update_space_state(
        state_payload,
        space_name=space_name,
        cursor=next_cursor,
        indexed_total=state_indexed_total if resume else (total_docs if dry_run else total_ok),
        last_vid=next_after_vid,
        phase="full_complete" if summary["full_completion"] else ("failed" if status == "failed" else "verified_partial"),
        status=status,
        note=note,
        es_doc_count=es_doc_count,
        nebula_entity_count=nebula_count if nebula_count is not None else None,
        coverage_pct=coverage_pct,
        full_completion=summary["full_completion"],
        remaining_docs=summary["remaining_docs"] if summary["remaining_docs"] is not None else None,
        verify_result=verify_result,
    )
    write_state(state_path, state_payload)
    return summary


def main() -> int:
    args = parse_args()
    try:
        spaces = resolve_target_spaces(args.space, include_all_ready=bool(args.all_ready_spaces))
    except Exception as exc:
        print(f"[backfill] error: {exc}")
        return 2

    state_path = Path(args.state_file)
    state_payload = read_state(state_path)
    for raw_space in args.reset_space_state or []:
        space_name = validate_target_space(raw_space)
        if reset_space_state(state_payload, space_name=space_name):
            print(f"[backfill] reset_state space={space_name}")
    if args.reset_space_state:
        write_state(state_path, state_payload)
    # Backfill and verify operate on large batches and must not inherit the
    # low-latency online search timeout budget.
    admin_timeout_ms = max(int(settings.es_timeout_ms), 30000)
    es_client = ElasticsearchClient(index=args.es_index, timeout_ms=admin_timeout_ms)

    if not args.dry_run:
        ok, reason = es_client.ensure_index(index_name=args.es_index)
        if not ok:
            print(f"[backfill] failed to ensure ES index: {reason}")
            return 2

    print(f"[backfill] target_spaces={','.join(spaces)}")
    summaries: List[Dict[str, Any]] = []
    for space_name in spaces:
        summary = run_backfill_for_space(
            space_name,
            batch_size=max(1, int(args.batch_size)),
            max_docs=max(0, int(args.max)),
            dry_run=bool(args.dry_run),
            verify=bool(args.verify),
            resume=bool(args.resume),
            state_path=state_path,
            state_payload=state_payload,
            es_client=es_client,
            index_name=args.es_index,
        )
        summaries.append(summary)

    failed = [item for item in summaries if item["status"] == "failed"]
    print("[backfill] summary")
    for item in summaries:
        print(
            f"[backfill] space={item['space_name']} status={item['status']} full_completion={item['full_completion']} remaining_docs={item['remaining_docs']} docs={item['docs']} ok={item['ok_count']} fail={item['fail_count']} es_doc_count={item['es_doc_count']} nebula_entity_count={item['nebula_entity_count'] if item['nebula_entity_count'] is not None else 'unknown'} coverage_pct={item['coverage_pct'] if item['coverage_pct'] is not None else 'unknown'} elapsed_s={item['elapsed_s']}"
        )
    if args.summary_json:
        summary_path = Path(args.summary_json)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(
                {
                    "generated_at": int(time.time()),
                    "target_spaces": spaces,
                    "state_file": str(state_path),
                    "index_name": args.es_index or settings.es_index,
                    "summaries": summaries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"[backfill] wrote_summary_json path={summary_path}")
    return 3 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
