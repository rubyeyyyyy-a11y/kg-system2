#!/usr/bin/env python3
import argparse
import csv
import re
import unicodedata
from pathlib import Path


def normalize_raw_id(value: str) -> str:
    v = unicodedata.normalize("NFKC", value or "")
    v = v.replace("：", ":")
    v = v.replace(":", "")
    v = re.sub(r"\s+", "", v)
    return v.casefold()


def resolve_raw_id_column(fieldnames: list[str], explicit: str | None) -> str:
    if explicit:
        if explicit not in fieldnames:
            raise ValueError(f"raw id column '{explicit}' not found in CSV headers")
        return explicit

    candidates = ["entity_raw_id", "raw_id", "Entity.entity_raw_id"]
    for c in candidates:
        if c in fieldnames:
            return c
    raise ValueError(
        "cannot infer raw id column, please set --raw-id-column (tried: entity_raw_id/raw_id/Entity.entity_raw_id)"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate/overwrite raw_id_norm column in vertices CSV for NebulaGraph import."
    )
    parser.add_argument("--input", required=True, help="input vertices csv path")
    parser.add_argument("--output", required=True, help="output csv path")
    parser.add_argument("--raw-id-column", default=None, help="raw id column name, e.g. entity_raw_id")
    parser.add_argument("--norm-column", default="raw_id_norm", help="normalized column name")
    parser.add_argument("--encoding", default="utf-8-sig", help="csv encoding, default utf-8-sig")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    rows = 0
    with input_path.open("r", encoding=args.encoding, newline="") as fin:
        reader = csv.DictReader(fin)
        if not reader.fieldnames:
            raise ValueError("empty CSV header")
        raw_id_col = resolve_raw_id_column(reader.fieldnames, args.raw_id_column)

        out_fields = list(reader.fieldnames)
        if args.norm_column not in out_fields:
            out_fields.append(args.norm_column)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding=args.encoding, newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=out_fields)
            writer.writeheader()
            for row in reader:
                row[args.norm_column] = normalize_raw_id(str(row.get(raw_id_col, "") or ""))
                writer.writerow(row)
                rows += 1

    print(f"done: rows={rows}, raw_id_column={raw_id_col}, norm_column={args.norm_column}")
    print(f"input={input_path}")
    print(f"output={output_path}")


if __name__ == "__main__":
    main()
