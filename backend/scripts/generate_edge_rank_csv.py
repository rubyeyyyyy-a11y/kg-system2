#!/usr/bin/env python3
import argparse
import csv
import hashlib
from pathlib import Path


def stable_hash64(text: str) -> int:
    digest = hashlib.sha1(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def resolve_column(fieldnames: list[str], explicit: str | None, candidates: list[str], column_role: str) -> str:
    if explicit:
        if explicit not in fieldnames:
            raise ValueError(f"{column_role} column '{explicit}' not found in CSV headers")
        return explicit
    for c in candidates:
        if c in fieldnames:
            return c
    raise ValueError(f"cannot infer {column_role} column, please pass explicit argument; tried: {candidates}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate edges_with_rank.csv from edges_clean.csv. "
            "rank = stable_hash64(f'{relation}|{source_db}') using SHA1 first 8 bytes -> int64."
        )
    )
    parser.add_argument("--input", required=True, help="input edges csv path, e.g. edges_clean.csv")
    parser.add_argument("--output", required=True, help="output csv path, e.g. edges_with_rank.csv")
    parser.add_argument("--relation-column", default=None, help="relation column name (default auto infer)")
    parser.add_argument(
        "--source-db-column",
        default=None,
        help="source db column name (default auto infer: source_db/source)",
    )
    parser.add_argument("--rank-column", default="rank", help="rank output column name (default: rank)")
    parser.add_argument("--encoding", default="utf-8-sig", help="csv encoding (default: utf-8-sig)")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    rows = 0
    unique_ranks = set()
    with input_path.open("r", encoding=args.encoding, newline="") as fin:
        reader = csv.DictReader(fin)
        if not reader.fieldnames:
            raise ValueError("empty CSV header")

        relation_col = resolve_column(
            reader.fieldnames,
            explicit=args.relation_column,
            candidates=["relation", "edge_relation", "REL.relation"],
            column_role="relation",
        )
        source_db_col = resolve_column(
            reader.fieldnames,
            explicit=args.source_db_column,
            candidates=["source_db", "source", "REL.source"],
            column_role="source_db",
        )

        out_fields = list(reader.fieldnames)
        if args.rank_column not in out_fields:
            out_fields.append(args.rank_column)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding=args.encoding, newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=out_fields)
            writer.writeheader()
            for row in reader:
                relation = str(row.get(relation_col, "") or "")
                source_db = str(row.get(source_db_col, "") or "")
                rank = stable_hash64(f"{relation}|{source_db}")
                row[args.rank_column] = str(rank)
                writer.writerow(row)
                rows += 1
                unique_ranks.add(rank)

    print(f"done: rows={rows}, unique_ranks={len(unique_ranks)}")
    print(f"relation_column={relation_col}, source_db_column={source_db_col}, rank_column={args.rank_column}")
    print(f"input={input_path}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
