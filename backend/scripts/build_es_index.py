#!/usr/bin/env python3
import argparse
import csv
import glob
import json
import sys
import time
from pathlib import Path
from typing import Dict, Iterator, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings
from app.clients.es_client import ElasticsearchClient
from app.services.search_v2 import indexing_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build/refresh ES index from Nebula Entity nodes")
    parser.add_argument("--space", type=str, default=settings.nebula_space)
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--max", type=int, default=0, help="0 means no limit")
    parser.add_argument("--since", type=int, default=None, help="start from vid > since")
    parser.add_argument(
        "--seed-vids",
        type=str,
        default="",
        help="comma-separated vids; when set, skip full scan and index only these vids",
    )
    parser.add_argument("--es-index", type=str, default=None)
    parser.add_argument("--state-file", type=str, default=str(ROOT / "state" / "es_indexer.state"))
    parser.add_argument(
        "--vertices-glob",
        type=str,
        default="",
        help="optional CSV glob for full vertex shards; when set, build from CSV instead of Nebula",
    )
    return parser.parse_args()


def read_state(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text())
        return int(data.get("cursor") or data.get("last_vid") or 0)
    except Exception:
        return 0


def write_state(path: Path, cursor: int, indexed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "cursor": int(cursor),
        "indexed_total": int(indexed),
        "updated_at": int(time.time()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def iter_csv_batches(vertices_glob: str, since: int, batch_size: int, *, space_name: str) -> Iterator[List[Dict[str, object]]]:
    pattern = str(vertices_glob or "").strip()
    if not pattern:
        return

    matches = [Path(p) for p in sorted(glob.glob(pattern))]
    if not matches:
        raise RuntimeError(f"no vertex shard files matched: {pattern}")

    batch: List[Dict[str, object]] = []
    skipped = 0
    for path in matches:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_vid = row.get("ID") or row.get("vid") or row.get("Vid") or ""
                if not raw_vid:
                    continue
                if skipped < since:
                    skipped += 1
                    continue
                vid = int(raw_vid)
                batch.append(
                    indexing_service.build_entity_doc(
                        {
                            "vid": vid,
                            "label": row.get("entity_name"),
                            "description": row.get("description"),
                            "raw_id": row.get("entity_raw_id"),
                            "entity_type": row.get("entity_type"),
                            "source": row.get("source"),
                        },
                        space_name=space_name,
                    )
                )
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
    if batch:
        yield batch


def _bulk_upsert(es: ElasticsearchClient, *, space_name: str, docs: List[Dict[str, object]], index_name: str | None) -> tuple[int, int, float]:
    result = indexing_service.bulk_upsert(
        space_name,
        docs,
        es_client=es,
        index_name=index_name,
        ensure_index=False,
    )
    return int(result["ok_count"]), int(result["fail_count"]), float(result["bulk_ms"])


def main() -> int:
    args = parse_args()
    space_name = str(args.space or "").strip() or settings.nebula_space
    batch_size = max(10, int(args.batch_size))
    max_docs = max(0, int(args.max))

    state_path = Path(args.state_file)
    resume_vid = read_state(state_path)
    cursor = int(args.since) if args.since is not None else resume_vid
    seed_vids = [int(x.strip()) for x in str(args.seed_vids or "").split(",") if x.strip()]
    vertices_glob = str(args.vertices_glob or "").strip()

    if seed_vids and vertices_glob:
        print("[indexer] error: --seed-vids cannot be combined with --vertices-glob")
        return 2

    es = ElasticsearchClient(index=args.es_index)

    ok, reason = es.ensure_index(index_name=args.es_index)
    if not ok:
        print(f"[indexer] failed to ensure ES index: {reason}")
        return 2

    print(
        f"[indexer] start space={space_name} batch_size={batch_size} max={max_docs} cursor={cursor} index={es.index} seed_count={len(seed_vids)} vertices_glob={vertices_glob or '-'}"
    )
    total = 0
    loop = 0
    started = time.perf_counter()

    if seed_vids:
        rows = indexing_service.fetch_entity_rows(space_name, vids=seed_vids)
        docs = [indexing_service.build_entity_doc(row, space_name=space_name) for row in rows]
        if max_docs > 0:
            docs = docs[:max_docs]
        ok_count, fail_count, bulk_ms = _bulk_upsert(es, space_name=space_name, docs=docs, index_name=args.es_index)
        total += ok_count
        if docs:
            cursor += len(docs)
            write_state(state_path, cursor=cursor, indexed=total)
        elapsed = time.perf_counter() - started
        rate = (total / elapsed) if elapsed > 0 else 0.0
        print(
            f"[indexer] seed-mode batch={len(docs)} ok={ok_count} fail={fail_count} total={total} bulk_ms={bulk_ms:.1f} rate={rate:.1f}/s"
        )
        print(f"[indexer] done total={total} cursor={cursor} elapsed_s={elapsed:.2f}")
        return 0

    if vertices_glob:
        for docs in iter_csv_batches(vertices_glob, since=cursor, batch_size=batch_size, space_name=space_name):
            loop += 1

            if max_docs > 0 and total + len(docs) > max_docs:
                docs = docs[: max_docs - total]

            ok_count, fail_count, bulk_ms = _bulk_upsert(es, space_name=space_name, docs=docs, index_name=args.es_index)
            total += ok_count

            if docs:
                cursor += len(docs)
                write_state(state_path, cursor=cursor, indexed=total)

            if total % 1000 == 0 or loop == 1 or fail_count > 0:
                elapsed = time.perf_counter() - started
                rate = (total / elapsed) if elapsed > 0 else 0.0
                print(
                    f"[indexer] loop={loop} cursor={cursor} batch={len(docs)} ok={ok_count} fail={fail_count} total={total} bulk_ms={bulk_ms:.1f} rate={rate:.1f}/s"
                )

            if fail_count > 0:
                print("[indexer] warning: bulk has failed documents, please inspect ES logs")
                return 3

            if max_docs > 0 and total >= max_docs:
                break

        elapsed = time.perf_counter() - started
        print(f"[indexer] done total={total} cursor={cursor} elapsed_s={elapsed:.2f}")
        return 0

    while True:
        loop += 1
        rows = indexing_service.fetch_entity_rows(space_name, cursor=cursor, batch_size=batch_size)
        docs = [indexing_service.build_entity_doc(row, space_name=space_name) for row in rows]
        if not docs:
            break

        if max_docs > 0 and total + len(docs) > max_docs:
            docs = docs[: max_docs - total]

        ok_count, fail_count, bulk_ms = _bulk_upsert(es, space_name=space_name, docs=docs, index_name=args.es_index)
        total += ok_count

        if docs:
            cursor += len(docs)
            write_state(state_path, cursor=cursor, indexed=total)

        if total % 1000 == 0 or loop == 1 or fail_count > 0:
            elapsed = time.perf_counter() - started
            rate = (total / elapsed) if elapsed > 0 else 0.0
            print(
                f"[indexer] loop={loop} cursor={cursor} batch={len(docs)} ok={ok_count} fail={fail_count} total={total} bulk_ms={bulk_ms:.1f} rate={rate:.1f}/s"
            )

        if fail_count > 0:
            print("[indexer] warning: bulk has failed documents, please inspect ES logs")

        if max_docs > 0 and total >= max_docs:
            break

    elapsed = time.perf_counter() - started
    print(f"[indexer] done total={total} cursor={cursor} elapsed_s={elapsed:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
