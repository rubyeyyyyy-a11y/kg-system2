#!/usr/bin/env python3
import argparse
import csv
import glob
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_IMPORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend" / "app"))

from db import nebula as nebula_db
from db.nebula import EDGE_TAG, execute_ngql
from services.common import esc, vw
from services.metadata_ids import metadata_stat_vid

ENTITY_STAT_TAG = "EntityTypeStat"
RELATION_STAT_TAG = "RelationTypeStat"


def _run_ngql(ngql: str):
    res = execute_ngql(ngql)
    if not res.is_succeeded():
        raise RuntimeError(res.error_msg())
    return res


def _chunks(items: List[str], size: int) -> Iterable[List[str]]:
    step = max(1, int(size))
    for i in range(0, len(items), step):
        yield items[i : i + step]


def _sort_counts(items: Dict[str, int]) -> List[Tuple[str, int]]:
    out = [(k, int(v)) for k, v in items.items() if k and int(v) > 0]
    out.sort(key=lambda x: (-int(x[1]), x[0]))
    return out


def _count_from_csv(glob_pattern: str, field_name: str, label: str) -> Dict[str, int]:
    files = sorted(glob.glob(glob_pattern))
    if not files:
        return {}

    counter: Dict[str, int] = {}
    csv.field_size_limit(1024 * 1024 * 256)
    for idx, path in enumerate(files, start=1):
        with open(path, "r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames is None:
                continue
            field_map = {str(name or "").strip().lower(): str(name or "").strip() for name in reader.fieldnames}
            col = field_map.get(field_name.lower())
            if not col:
                continue
            for row in reader:
                key = str(row.get(col) or "").strip().lower()
                if not key:
                    continue
                counter[key] = int(counter.get(key) or 0) + 1
        if idx % 10 == 0:
            print(f"[metadata] csv_progress {label} files={idx}/{len(files)}")
    return counter


def _query_entity_type_counts_db() -> List[Tuple[str, int]]:
    ngql = """
    MATCH (v:`Entity`)
    RETURN lower(coalesce(v.`Entity`.`entity_type`, "")) AS entity_type, count(*) AS cnt;
    """
    res = _run_ngql(ngql)
    keys = res.column_values("entity_type")
    counts = res.column_values("cnt")
    items: Dict[str, int] = {}
    for i in range(len(keys)):
        key = str(vw(keys[i]) or "").strip().lower()
        cnt = int(vw(counts[i]) or 0)
        if key and cnt > 0:
            items[key] = cnt
    return _sort_counts(items)


def _query_relation_type_counts_db() -> List[Tuple[str, int]]:
    ngql = f"""
    MATCH ()-[e:{EDGE_TAG}]-()
    RETURN lower(coalesce(properties(e).relation, "")) AS relation_type, count(*) AS cnt;
    """
    res = _run_ngql(ngql)
    keys = res.column_values("relation_type")
    counts = res.column_values("cnt")
    items: Dict[str, int] = {}
    for i in range(len(keys)):
        key = str(vw(keys[i]) or "").strip().lower()
        cnt = int(vw(counts[i]) or 0)
        if key and cnt > 0:
            items[key] = cnt
    return _sort_counts(items)


def _resolve_source_counts(
    *,
    source: str,
    vertices_glob: str,
    edges_glob: str,
) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]], str]:
    mode = str(source or "auto").strip().lower()
    if mode not in {"auto", "csv", "db"}:
        raise RuntimeError(f"unsupported source mode: {source}")

    vertex_files = sorted(glob.glob(vertices_glob))
    edge_files = sorted(glob.glob(edges_glob))
    has_csv = len(vertex_files) > 0 and len(edge_files) > 0

    if mode == "csv" and not has_csv:
        raise RuntimeError(
            f"csv source requested but shard files missing: vertices={vertices_glob} edges={edges_glob}"
        )

    if mode == "csv" or (mode == "auto" and has_csv):
        entity_counts = _sort_counts(_count_from_csv(vertices_glob, "entity_type", "entity_type"))
        relation_counts = _sort_counts(_count_from_csv(edges_glob, "relation", "relation_type"))
        return entity_counts, relation_counts, "csv"

    return _query_entity_type_counts_db(), _query_relation_type_counts_db(), "db"


def _query_metadata_counts(tag: str, key_field: str) -> Dict[str, int]:
    ngql = f"""
    MATCH (m:`{tag}`)
    WHERE coalesce(m.`{tag}`.`count`, 0) > 0
    RETURN coalesce(m.`{tag}`.`{key_field}`, "") AS key, coalesce(m.`{tag}`.`count`, 0) AS cnt;
    """
    res = _run_ngql(ngql)
    out: Dict[str, int] = {}
    keys = res.column_values("key")
    counts = res.column_values("cnt")
    for i in range(len(keys)):
        key = str(vw(keys[i]) or "").strip().lower()
        cnt = int(vw(counts[i]) or 0)
        if key and cnt > 0:
            out[key] = cnt
    return out


def _ensure_metadata_schema() -> None:
    _run_ngql(
        """
        CREATE TAG IF NOT EXISTS EntityTypeStat(
          entity_type string,
          entity_type_norm string,
          count int64,
          updated_at int64,
          updated_by string
        );
        """
    )
    _run_ngql(
        """
        CREATE TAG IF NOT EXISTS RelationTypeStat(
          relation_type string,
          relation_type_norm string,
          count int64,
          updated_at int64,
          updated_by string
        );
        """
    )


def _clear_old_metadata() -> None:
    for tag in (ENTITY_STAT_TAG, RELATION_STAT_TAG):
        res = _run_ngql(f"MATCH (m:`{tag}`) RETURN id(m) AS vid;")
        vids = [int(vw(v)) for v in res.column_values("vid")]
        if not vids:
            continue
        for chunk in _chunks([str(v) for v in vids], 500):
            _run_ngql("DELETE VERTEX " + ",".join(chunk) + ";")


def _insert_stats(
    *,
    tag: str,
    kind: str,
    label_field: str,
    norm_field: str,
    rows: List[Tuple[str, int]],
    actor: str,
) -> None:
    if not rows:
        return

    now_sec = int(time.time())
    values: List[str] = []
    used_vids = set()
    for key, cnt in rows:
        salt = 0
        vid = metadata_stat_vid(kind, key, salt=salt)
        while vid in used_vids:
            salt += 1
            vid = metadata_stat_vid(kind, key, salt=salt)
        used_vids.add(vid)
        values.append(
            f'{int(vid)}:("{esc(key)}", "{esc(key)}", {int(cnt)}, {now_sec}, "{esc(actor)}")'
        )

    for chunk in _chunks(values, 200):
        ngql = (
            f"INSERT VERTEX {tag}({label_field}, {norm_field}, count, updated_at, updated_by) VALUES\n  "
            + ",\n  ".join(chunk)
            + ";"
        )
        _run_ngql(ngql)


def _summary_from_counts(data: Dict[str, int]) -> Tuple[int, int]:
    return len(data), int(sum(int(v) for v in data.values()))


def rebuild(args) -> None:
    _ensure_metadata_schema()
    entity_counts, relation_counts, source_used = _resolve_source_counts(
        source=args.source,
        vertices_glob=args.vertices_glob,
        edges_glob=args.edges_glob,
    )
    print(
        "[metadata] source "
        f"mode={args.source} resolved={source_used} "
        f"entity_types={len(entity_counts)} relation_types={len(relation_counts)}"
    )

    if not args.allow_empty:
        if len(entity_counts) == 0:
            raise RuntimeError("entity type aggregation returned empty result")
        if len(relation_counts) == 0:
            raise RuntimeError("relation type aggregation returned empty result")

    _clear_old_metadata()
    _insert_stats(
        tag=ENTITY_STAT_TAG,
        kind="entity_type",
        label_field="entity_type",
        norm_field="entity_type_norm",
        rows=entity_counts,
        actor=args.actor,
    )
    _insert_stats(
        tag=RELATION_STAT_TAG,
        kind="relation_type",
        label_field="relation_type",
        norm_field="relation_type_norm",
        rows=relation_counts,
        actor=args.actor,
    )

    verify(args, from_rebuild=True)


def verify(args, from_rebuild: bool = False) -> None:
    entity_meta = _query_metadata_counts(ENTITY_STAT_TAG, "entity_type_norm")
    relation_meta = _query_metadata_counts(RELATION_STAT_TAG, "relation_type_norm")

    entity_rows, entity_total = _summary_from_counts(entity_meta)
    relation_rows, relation_total = _summary_from_counts(relation_meta)
    print(
        "[metadata] existing_stats "
        f"entity_types={entity_rows} entity_total={entity_total} "
        f"relation_types={relation_rows} relation_total={relation_total}"
    )

    if not args.allow_empty:
        if entity_rows <= 0:
            raise RuntimeError("EntityTypeStat is empty")
        if relation_rows <= 0:
            raise RuntimeError("RelationTypeStat is empty")

    if args.compare:
        entity_base, relation_base, source_used = _resolve_source_counts(
            source=args.source,
            vertices_glob=args.vertices_glob,
            edges_glob=args.edges_glob,
        )
        entity_expected = dict(entity_base)
        relation_expected = dict(relation_base)
        if entity_expected != entity_meta:
            raise RuntimeError("EntityTypeStat mismatch against baseline source")
        if relation_expected != relation_meta:
            raise RuntimeError("RelationTypeStat mismatch against baseline source")
        print(f"[metadata] compare=ok source={source_used}")
    elif from_rebuild:
        print("[metadata] compare=skipped")


def parse_args():
    parser = argparse.ArgumentParser(description="Rebuild/verify metadata stats in NebulaGraph")
    parser.add_argument("--mode", choices=["rebuild", "verify"], default="rebuild")
    parser.add_argument("--actor", default="metadata_rebuild")
    parser.add_argument("--source", choices=["auto", "csv", "db"], default="auto")
    parser.add_argument(
        "--vertices-glob",
        default=str(DATA_IMPORT_ROOT / "out" / "vertices_shards" / "Entity_*.csv"),
    )
    parser.add_argument(
        "--edges-glob",
        default=str(DATA_IMPORT_ROOT / "out" / "edges_shards" / "REL2_*.csv"),
    )
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--allow-empty", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(
        "[metadata] start "
        f"mode={args.mode} source={args.source} edge_tag={EDGE_TAG} "
        f"nebula={nebula_db.NEBULA_HOST}:{nebula_db.NEBULA_PORT} space={nebula_db.NEBULA_SPACE}"
    )
    if args.mode == "rebuild":
        rebuild(args)
    else:
        verify(args)
    print("[metadata] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
