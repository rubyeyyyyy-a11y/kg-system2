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

from app.clients.es_client import ElasticsearchClient
from app.clients.nebula_client import NebulaClient
from app.services.common import normalize_raw_id, vw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build/refresh ES index from Nebula Entity nodes")
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
        return int(data.get("last_vid") or 0)
    except Exception:
        return 0


def write_state(path: Path, last_vid: int, indexed: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_vid": int(last_vid),
        "indexed_total": int(indexed),
        "updated_at": int(time.time()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def build_doc(
    *,
    vid: int,
    entity_name: object,
    description: object,
    entity_raw_id: object,
    entity_type: object,
    source: object,
) -> Dict[str, object]:
    raw_id = str(entity_raw_id or "")
    raw_id_norm = normalize_raw_id(raw_id)
    entity_type_str = str(entity_type or "")
    return {
        "vid": int(vid),
        "entity_name": str(entity_name or ""),
        "description": str(description or ""),
        "entity_raw_id": raw_id,
        "entity_raw_id_text": raw_id,
        "raw_id_norm": raw_id_norm,
        "raw_id_norm_text": raw_id_norm,
        "entity_type": entity_type_str,
        "entity_type_text": entity_type_str,
        "source": str(source or ""),
    }


def fetch_batch(nebula: NebulaClient, last_vid: int, batch_size: int) -> List[Dict[str, object]]:
    ngql = f"""
MATCH (v:`Entity`)
WHERE id(v) > {int(last_vid)}
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS entity_name,
       v.`Entity`.`description` AS description,
       v.`Entity`.`entity_raw_id` AS entity_raw_id,
       v.`Entity`.`entity_type` AS entity_type,
       v.`Entity`.`source` AS source
ORDER BY vid ASC
LIMIT {int(batch_size)};
"""
    res, _ = nebula.execute(ngql)

    vids = res.column_values("vid")
    names = res.column_values("entity_name")
    descriptions = res.column_values("description")
    raw_ids = res.column_values("entity_raw_id")
    types = res.column_values("entity_type")
    sources = res.column_values("source")

    out: List[Dict[str, object]] = []
    for i in range(len(vids)):
        out.append(
            build_doc(
                vid=int(vw(vids[i])),
                entity_name=vw(names[i]),
                description=vw(descriptions[i]),
                entity_raw_id=vw(raw_ids[i]),
                entity_type=vw(types[i]),
                source=vw(sources[i]),
            )
        )
    return out


def fetch_by_vids(nebula: NebulaClient, vids: List[int]) -> List[Dict[str, object]]:
    ids = sorted({int(v) for v in vids})
    if not ids:
        return []
    id_list = ",".join(str(v) for v in ids)
    ngql = f"""
MATCH (v:`Entity`)
WHERE id(v) IN [{id_list}]
RETURN id(v) AS vid,
       v.`Entity`.`entity_name` AS entity_name,
       v.`Entity`.`description` AS description,
       v.`Entity`.`entity_raw_id` AS entity_raw_id,
       v.`Entity`.`entity_type` AS entity_type,
       v.`Entity`.`source` AS source;
"""
    res, _ = nebula.execute(ngql)

    vids_col = res.column_values("vid")
    names = res.column_values("entity_name")
    descriptions = res.column_values("description")
    raw_ids = res.column_values("entity_raw_id")
    types = res.column_values("entity_type")
    sources = res.column_values("source")

    out: List[Dict[str, object]] = []
    for i in range(len(vids_col)):
        out.append(
            build_doc(
                vid=int(vw(vids_col[i])),
                entity_name=vw(names[i]),
                description=vw(descriptions[i]),
                entity_raw_id=vw(raw_ids[i]),
                entity_type=vw(types[i]),
                source=vw(sources[i]),
            )
        )
    return out


def iter_csv_batches(vertices_glob: str, since: int, batch_size: int) -> Iterator[List[Dict[str, object]]]:
    pattern = str(vertices_glob or "").strip()
    if not pattern:
        return

    matches = [Path(p) for p in sorted(glob.glob(pattern))]
    if not matches:
        raise RuntimeError(f"no vertex shard files matched: {pattern}")

    batch: List[Dict[str, object]] = []
    for path in matches:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw_vid = row.get("ID") or row.get("vid") or row.get("Vid") or ""
                if not raw_vid:
                    continue
                vid = int(raw_vid)
                if vid <= since:
                    continue
                batch.append(
                    build_doc(
                        vid=vid,
                        entity_name=row.get("entity_name"),
                        description=row.get("description"),
                        entity_raw_id=row.get("entity_raw_id"),
                        entity_type=row.get("entity_type"),
                        source=row.get("source"),
                    )
                )
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
    if batch:
        yield batch


def main() -> int:
    args = parse_args()
    batch_size = max(10, int(args.batch_size))
    max_docs = max(0, int(args.max))

    state_path = Path(args.state_file)
    resume_vid = read_state(state_path)
    last_vid = int(args.since) if args.since is not None else resume_vid
    seed_vids = [int(x.strip()) for x in str(args.seed_vids or "").split(",") if x.strip()]
    vertices_glob = str(args.vertices_glob or "").strip()

    if seed_vids and vertices_glob:
        print("[indexer] error: --seed-vids cannot be combined with --vertices-glob")
        return 2

    nebula = NebulaClient()
    es = ElasticsearchClient(index=args.es_index)

    ok, reason = es.ensure_index(index_name=args.es_index)
    if not ok:
        print(f"[indexer] failed to ensure ES index: {reason}")
        return 2

    print(
        f"[indexer] start batch_size={batch_size} max={max_docs} since={last_vid} index={es.index} seed_count={len(seed_vids)} vertices_glob={vertices_glob or '-'}"
    )
    total = 0
    loop = 0
    started = time.perf_counter()

    if seed_vids:
        docs = fetch_by_vids(nebula, seed_vids)
        if max_docs > 0:
            docs = docs[:max_docs]
        ok_count, fail_count, bulk_ms = es.bulk_upsert(docs, index_name=args.es_index)
        total += ok_count
        if docs:
            last_vid = max(int(doc["vid"]) for doc in docs)
            write_state(state_path, last_vid=last_vid, indexed=total)
        elapsed = time.perf_counter() - started
        rate = (total / elapsed) if elapsed > 0 else 0.0
        print(
            f"[indexer] seed-mode batch={len(docs)} ok={ok_count} fail={fail_count} total={total} bulk_ms={bulk_ms:.1f} rate={rate:.1f}/s"
        )
        print(f"[indexer] done total={total} last_vid={last_vid} elapsed_s={elapsed:.2f}")
        return 0

    if vertices_glob:
        for docs in iter_csv_batches(vertices_glob, since=last_vid, batch_size=batch_size):
            loop += 1

            if max_docs > 0 and total + len(docs) > max_docs:
                docs = docs[: max_docs - total]

            ok_count, fail_count, bulk_ms = es.bulk_upsert(docs, index_name=args.es_index)
            total += ok_count

            if docs:
                last_vid = int(docs[-1]["vid"])
                write_state(state_path, last_vid=last_vid, indexed=total)

            if total % 1000 == 0 or loop == 1 or fail_count > 0:
                elapsed = time.perf_counter() - started
                rate = (total / elapsed) if elapsed > 0 else 0.0
                print(
                    f"[indexer] loop={loop} last_vid={last_vid} batch={len(docs)} ok={ok_count} fail={fail_count} total={total} bulk_ms={bulk_ms:.1f} rate={rate:.1f}/s"
                )

            if fail_count > 0:
                print("[indexer] warning: bulk has failed documents, please inspect ES logs")
                return 3

            if max_docs > 0 and total >= max_docs:
                break

        elapsed = time.perf_counter() - started
        print(f"[indexer] done total={total} last_vid={last_vid} elapsed_s={elapsed:.2f}")
        return 0

    while True:
        loop += 1
        docs = fetch_batch(nebula, last_vid=last_vid, batch_size=batch_size)
        if not docs:
            break

        if max_docs > 0 and total + len(docs) > max_docs:
            docs = docs[: max_docs - total]

        ok_count, fail_count, bulk_ms = es.bulk_upsert(docs, index_name=args.es_index)
        total += ok_count

        if docs:
            last_vid = int(docs[-1]["vid"])
            write_state(state_path, last_vid=last_vid, indexed=total)

        if total % 1000 == 0 or loop == 1 or fail_count > 0:
            elapsed = time.perf_counter() - started
            rate = (total / elapsed) if elapsed > 0 else 0.0
            print(
                f"[indexer] loop={loop} last_vid={last_vid} batch={len(docs)} ok={ok_count} fail={fail_count} total={total} bulk_ms={bulk_ms:.1f} rate={rate:.1f}/s"
            )

        if fail_count > 0:
            print("[indexer] warning: bulk has failed documents, please inspect ES logs")

        if max_docs > 0 and total >= max_docs:
            break

    elapsed = time.perf_counter() - started
    print(f"[indexer] done total={total} last_vid={last_vid} elapsed_s={elapsed:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
