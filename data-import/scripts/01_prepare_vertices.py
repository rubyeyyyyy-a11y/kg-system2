#!/usr/bin/env python3
import argparse
import csv
import os
import re
import time

MAX_LEN = {
    "entity_name": 256,
    "entity_type": 128,
    "source": 256,
    "description": 4096,
    "updated_by": 64,
}

OUTPUT_HEADER = [
    "ID",
    "entity_type",
    "entity_name",
    "entity_raw_id",
    "description",
    "source",
    "version",
    "updated_at",
    "updated_by",
]


def normalize_col(name: str) -> str:
    return (name or "").replace("\ufeff", "").strip()


def clean_text(value: str) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "")
    return text.strip()


def clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit]


class CsvShardWriter:
    def __init__(self, out_dir: str, prefix: str, shard_size: int, header):
        self.out_dir = out_dir
        self.prefix = prefix
        self.shard_size = shard_size
        self.header = header
        self.file_index = 0
        self.current_rows = 0
        self.total_rows = 0
        self.fp = None
        self.writer = None

    def _open_next(self):
        if self.fp is not None:
            self.fp.close()
        self.file_index += 1
        path = os.path.join(self.out_dir, f"{self.prefix}_{self.file_index:06d}.csv")
        self.fp = open(path, "w", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.fp, fieldnames=self.header)
        self.writer.writeheader()
        self.current_rows = 0

    def write(self, row: dict):
        if self.fp is None or self.current_rows >= self.shard_size:
            self._open_next()
        self.writer.writerow(row)
        self.current_rows += 1
        self.total_rows += 1

    def close(self):
        if self.fp is not None:
            self.fp.close()
            self.fp = None


def parse_args():
    parser = argparse.ArgumentParser(description="Prepare Entity vertex shards for nebula-importer")
    parser.add_argument(
        "--input",
        default="/home/ray/data/kg_demo/unified_entities_with_synonyms.csv",
        help="input vertices CSV",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "out", "vertices_shards"),
        help="output shard directory",
    )
    parser.add_argument("--shard-size", type=int, default=2000000)
    return parser.parse_args()


def main():
    args = parse_args()
    started = time.time()
    csv.field_size_limit(1024 * 1024 * 256)

    os.makedirs(args.output_dir, exist_ok=True)

    writer = CsvShardWriter(args.output_dir, "Entity", args.shard_size, OUTPUT_HEADER)

    total_in = 0
    total_out = 0
    bad_rows = 0

    with open(args.input, "r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames is None:
            raise RuntimeError("input CSV has no header")

        fields = [normalize_col(x) for x in reader.fieldnames]
        reader.fieldnames = fields

        required = {"ID", "entity_type", "entity_name", "entity_raw_id", "description", "source"}
        missing = [x for x in sorted(required) if x not in set(fields)]
        if missing:
            raise RuntimeError(f"missing required columns: {missing}")

        for raw in reader:
            total_in += 1
            row = {normalize_col(k): v for k, v in raw.items()}

            vid = clean_text(row.get("ID", ""))
            if not re.fullmatch(r"-?\d+", vid):
                bad_rows += 1
                continue

            entity_type = clip(clean_text(row.get("entity_type", "")), MAX_LEN["entity_type"])
            entity_name = clip(clean_text(row.get("entity_name", "")), MAX_LEN["entity_name"])
            entity_raw_id = clean_text(row.get("entity_raw_id", ""))
            source = clip(clean_text(row.get("source", "")), MAX_LEN["source"])

            description = clean_text(row.get("description", ""))
            if description.lower() == "nan":
                description = ""
            description = clip(description, MAX_LEN["description"])

            out_row = {
                "ID": vid,
                "entity_type": entity_type,
                "entity_name": entity_name,
                "entity_raw_id": entity_raw_id,
                "description": description,
                "source": source,
                "version": "0",
                "updated_at": "0",
                "updated_by": "importer",
            }

            writer.write(out_row)
            total_out += 1

            if total_out % 500000 == 0:
                print(f"[prepare_vertices] written={total_out} elapsed={int(time.time()-started)}s")

    writer.close()
    elapsed = int(time.time() - started)
    print(
        "[prepare_vertices] done "
        f"input={total_in} output={total_out} bad_rows={bad_rows} "
        f"shards={writer.file_index} elapsed={elapsed}s"
    )


if __name__ == "__main__":
    main()
