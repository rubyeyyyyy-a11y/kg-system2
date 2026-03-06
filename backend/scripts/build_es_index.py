#!/usr/bin/env python3
import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

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
        vid = int(vw(vids[i]))
        raw_id = str(vw(raw_ids[i]) or "")
        raw_id_norm = normalize_raw_id(raw_id)
        entity_type = str(vw(types[i]) or "")
        out.append(
            {
                "vid": vid,
                "entity_name": str(vw(names[i]) or ""),
                "description": str(vw(descriptions[i]) or ""),
                "entity_raw_id": raw_id,
                "entity_raw_id_text": raw_id,
                "raw_id_norm": raw_id_norm,
                "raw_id_norm_text": raw_id_norm,
                "entity_type": entity_type,
                "entity_type_text": entity_type,
                "source": str(vw(sources[i]) or ""),
            }
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
        vid = int(vw(vids_col[i]))
        raw_id = str(vw(raw_ids[i]) or "")
        raw_id_norm = normalize_raw_id(raw_id)
        entity_type = str(vw(types[i]) or "")
        out.append(
            {
                "vid": vid,
                "entity_name": str(vw(names[i]) or ""),
                "description": str(vw(descriptions[i]) or ""),
                "entity_raw_id": raw_id,
                "entity_raw_id_text": raw_id,
                "raw_id_norm": raw_id_norm,
                "raw_id_norm_text": raw_id_norm,
                "entity_type": entity_type,
                "entity_type_text": entity_type,
                "source": str(vw(sources[i]) or ""),
            }
        )
    return out


def main() -> int:
    args = parse_args()
    batch_size = max(10, int(args.batch_size))
    max_docs = max(0, int(args.max))

    state_path = Path(args.state_file)
    resume_vid = read_state(state_path)
    last_vid = int(args.since) if args.since is not None else resume_vid
    seed_vids = [int(x.strip()) for x in str(args.seed_vids or "").split(",") if x.strip()]

    nebula = NebulaClient()
    es = ElasticsearchClient(index=args.es_index)

    ok, reason = es.ensure_index(index_name=args.es_index)
    if not ok:
        print(f"[indexer] failed to ensure ES index: {reason}")
        return 2

    print(
        f"[indexer] start batch_size={batch_size} max={max_docs} since={last_vid} index={es.index} seed_count={len(seed_vids)}"
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
