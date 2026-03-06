#!/usr/bin/env python3
import argparse
import csv
import glob
import hashlib
import os
import re
import time

MAX_LEN = {
    "relation": 256,
    "source": 256,
    "evidence": 4096,
    "updated_by": 64,
}

OUTPUT_HEADER = [
    "srcVID",
    "dstVID",
    "rank",
    "relation",
    "source",
    "evidence",
    "version",
    "updated_at",
    "updated_by",
]


def normalize_col(name: str) -> str:
    return (name or "").replace("\ufeff", "").strip().lower()


def clean_text(value: str) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "")
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit]


def q(path: str) -> str:
    return "'" + path.replace("'", "'\"'\"'") + "'"


class PartitionWriter:
    def __init__(self, tmp_dir: str, partitions: int):
        self.tmp_dir = tmp_dir
        self.partitions = partitions
        self.handles = {}

    def _path(self, idx: int) -> str:
        return os.path.join(self.tmp_dir, f"edges_part_{idx:03d}.tsv")

    def write(self, idx: int, line: str):
        fp = self.handles.get(idx)
        if fp is None:
            fp = open(self._path(idx), "a", encoding="utf-8", newline="")
            self.handles[idx] = fp
        fp.write(line)

    def close(self):
        for fp in self.handles.values():
            fp.close()
        self.handles = {}


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
    parser = argparse.ArgumentParser(description="Prepare REL2 edge shards with rank")
    parser.add_argument(
        "--edges-root",
        default="/home/ray/data/kg_demo/edges",
        help="root directory to recursively match **/*_edges.csv",
    )
    parser.add_argument(
        "--tmp-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "out", "tmp"),
        help="temp directory for partition files",
    )
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "out", "edges_shards"),
        help="output shard directory",
    )
    parser.add_argument("--shard-size", type=int, default=2000000)
    parser.add_argument("--partitions", type=int, default=256)
    return parser.parse_args()


def partition_of(src: str, dst: str, mod: int) -> int:
    key = f"{src}|{dst}".encode("utf-8")
    digest = hashlib.sha1(key).hexdigest()
    return int(digest[:8], 16) % mod


def row_get(row: dict, key: str) -> str:
    return row.get(key, "")


def normalize_vid(value: str) -> str:
    text = clean_text(value)
    if re.fullmatch(r"-?\d+", text):
        return str(int(text))
    m = re.fullmatch(r"(-?\d+)\.0+", text)
    if m:
        return str(int(m.group(1)))
    return ""


def build_evidence(row: dict) -> str:
    parts = []
    pmid = clean_text(row_get(row, "pmid"))
    detail = clean_text(row_get(row, "relation_detail"))
    direction = clean_text(row_get(row, "direction"))
    score = clean_text(row_get(row, "score"))

    if pmid:
        parts.append(f"pmid={pmid}")
    if detail:
        parts.append(f"detail={detail}")
    if direction:
        parts.append(f"dir={direction}")
    if score:
        parts.append(f"score={score}")

    return clip("; ".join(parts), MAX_LEN["evidence"])


def preprocess_to_partitions(args):
    pattern = os.path.join(args.edges_root, "**", "*_edges.csv")
    files = sorted(glob.glob(pattern, recursive=True))
    if not files:
        raise RuntimeError(f"no edge csv matched: {pattern}")

    os.makedirs(args.tmp_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    for old in glob.glob(os.path.join(args.tmp_dir, "edges_part_*.tsv")):
        os.remove(old)
    for old in glob.glob(os.path.join(args.tmp_dir, "edges_part_*.sorted.tsv")):
        os.remove(old)

    writer = PartitionWriter(args.tmp_dir, args.partitions)

    files_seen = 0
    input_rows = 0
    invalid_rows = 0

    for path in files:
        files_seen += 1
        with open(path, "r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames is None:
                continue
            reader.fieldnames = [normalize_col(x) for x in reader.fieldnames]

            for raw in reader:
                input_rows += 1
                row = {normalize_col(k): v for k, v in raw.items()}

                src = normalize_vid(row_get(row, "subject_our_defined_id"))
                dst = normalize_vid(row_get(row, "object_our_defined_id"))
                if not src or not dst:
                    invalid_rows += 1
                    continue

                relation = clip(clean_text(row_get(row, "relation")), MAX_LEN["relation"])
                source = clip(clean_text(row_get(row, "source")) or "KG", MAX_LEN["source"])
                evidence = build_evidence(row)

                pid = partition_of(src, dst, args.partitions)
                writer.write(pid, f"{src}\t{dst}\t{relation}\t{source}\t{evidence}\n")

        if files_seen % 10 == 0:
            print(f"[prepare_edges] scanned_files={files_seen} input_rows={input_rows}")

    writer.close()
    return files_seen, input_rows, invalid_rows


def partition_paths(tmp_dir: str):
    return sorted(glob.glob(os.path.join(tmp_dir, "edges_part_*.tsv")))


def sort_and_rank(args, shard_writer: CsvShardWriter):
    total_unique = 0
    rank_nonzero = 0

    for part in partition_paths(args.tmp_dir):
        sorted_part = part.replace(".tsv", ".sorted.tsv")
        tab = "\t"
        cmd = (
            f"LC_ALL=C sort -t '{tab}' -k1,1n -k2,2n -k3,3 -k4,4 -k5,5 "
            f"{q(part)} | uniq > {q(sorted_part)}"
        )
        rc = os.system(cmd)
        if rc != 0:
            raise RuntimeError(f"sort failed (rc={rc}) for partition file: {part}")

        prev_src = None
        prev_dst = None
        rank = -1

        with open(sorted_part, "r", encoding="utf-8", newline="") as fp:
            for line in fp:
                line = line.rstrip("\n")
                if not line:
                    continue
                cols = line.split("\t")
                if len(cols) < 5:
                    continue

                src, dst, relation, source, evidence = cols[0], cols[1], cols[2], cols[3], cols[4]
                if src != prev_src or dst != prev_dst:
                    rank = 0
                    prev_src, prev_dst = src, dst
                else:
                    rank += 1

                if rank > 0:
                    rank_nonzero += 1

                out_row = {
                    "srcVID": src,
                    "dstVID": dst,
                    "rank": str(rank),
                    "relation": relation,
                    "source": source,
                    "evidence": evidence,
                    "version": "0",
                    "updated_at": "0",
                    "updated_by": "importer",
                }
                shard_writer.write(out_row)
                total_unique += 1

        os.remove(sorted_part)

    return total_unique, rank_nonzero


def main():
    args = parse_args()
    started = time.time()
    csv.field_size_limit(1024 * 1024 * 256)

    files_seen, input_rows, invalid_rows = preprocess_to_partitions(args)

    edge_writer = CsvShardWriter(args.output_dir, "REL2", args.shard_size, OUTPUT_HEADER)
    total_unique, rank_nonzero = sort_and_rank(args, edge_writer)
    edge_writer.close()

    for part in partition_paths(args.tmp_dir):
        os.remove(part)

    elapsed = int(time.time() - started)
    print(
        "[prepare_edges] done "
        f"files={files_seen} input_rows={input_rows} invalid_rows={invalid_rows} "
        f"unique_rows={total_unique} rank_gt0={rank_nonzero} "
        f"shards={edge_writer.file_index} elapsed={elapsed}s"
    )


if __name__ == "__main__":
    main()
