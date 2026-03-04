#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate REL2 importer CSV with rank=0..n-1 per (src,dst). "
            "Rows are sorted by relation/source/evidence to ensure stable reproducibility."
        )
    )
    parser.add_argument("--input", required=True, help="input edges CSV path")
    parser.add_argument("--output", required=True, help="output edges CSV path with rank column")
    parser.add_argument("--src-col", default="src")
    parser.add_argument("--dst-col", default="dst")
    parser.add_argument("--relation-col", default="relation")
    parser.add_argument("--source-col", default="source_db")
    parser.add_argument("--evidence-col", default="evidence")
    parser.add_argument("--rank-col", default="rank")
    parser.add_argument("--encoding", default="utf-8-sig")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    grouped: Dict[tuple[str, str], List[dict[str, str]]] = defaultdict(list)

    with in_path.open("r", encoding=args.encoding, newline="") as fin:
        reader = csv.DictReader(fin)
        if not reader.fieldnames:
            raise ValueError("empty csv header")
        for row in reader:
            src = str(row.get(args.src_col, "") or "").strip()
            dst = str(row.get(args.dst_col, "") or "").strip()
            if not src or not dst:
                continue
            grouped[(src, dst)].append(row)

        fields = list(reader.fieldnames)
        if args.rank_col not in fields:
            fields.append(args.rank_col)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with out_path.open("w", encoding=args.encoding, newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=fields)
        writer.writeheader()
        for key in sorted(grouped.keys(), key=lambda x: (int(x[0]), int(x[1]))):
            rows = grouped[key]
            rows.sort(
                key=lambda r: (
                    str(r.get(args.relation_col, "") or ""),
                    str(r.get(args.source_col, "") or ""),
                    str(r.get(args.evidence_col, "") or ""),
                )
            )
            for idx, row in enumerate(rows):
                row[args.rank_col] = str(idx)
                writer.writerow(row)
                rows_written += 1

    print(f"done: wrote {rows_written} rows")
    print(f"output={out_path}")


if __name__ == "__main__":
    main()
