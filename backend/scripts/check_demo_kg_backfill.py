#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.spaces import index_status_service
from app.clients.es_client import ElasticsearchClient

DEFAULT_STATE_FILE = ROOT / "state" / "es_backfill_spaces.state.json"
DEFAULT_LATEST_SUMMARY = ROOT / "state" / "demo_kg_backfill_summary_latest.json"
DEFAULT_REGISTRY = REPO_ROOT / ".run" / "space-registry" / "spaces.json"
DEFAULT_LOG_DIR = ROOT / "logs" / "demo_kg_backfill"
DEFAULT_STATE_DIR = ROOT / "state"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the latest demo_kg backfill state and summary")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--summary-file", type=Path, default=DEFAULT_LATEST_SUMMARY)
    parser.add_argument("--registry-file", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--tail", type=int, default=20, help="how many lines to print from the latest log; 0 disables")
    parser.add_argument("--require-full", action="store_true", help="return non-zero unless demo_kg reached full completion")
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_error": str(exc), "_path": str(path)}
    return payload if isinstance(payload, dict) else {"_error": "json_root_not_object", "_path": str(path)}


def latest_log_file(log_dir: Path) -> Path | None:
    if not log_dir.exists():
        return None
    items = sorted(log_dir.glob("demo_kg_backfill_*.log"))
    return items[-1] if items else None


def resolve_summary_file(summary_file: Path) -> Path:
    if summary_file.exists():
        return summary_file

    preferred = DEFAULT_STATE_DIR / "demo_kg_backfill_full.json"
    if preferred.exists():
        return preferred

    latest_alias = DEFAULT_STATE_DIR / "demo_kg_backfill_summary_latest.json"
    if latest_alias.exists():
        return latest_alias

    candidates = sorted(DEFAULT_STATE_DIR.glob("demo_kg_backfill_summary_*.json"))
    if candidates:
        return candidates[-1]

    run_dir = DEFAULT_STATE_DIR / "demo_kg_backfill_runs"
    run_candidates = sorted(run_dir.glob("demo_kg_backfill_*.json")) if run_dir.exists() else []
    if run_candidates:
        return run_candidates[-1]

    return summary_file


def tail_lines(path: Path, limit: int) -> list[str]:
    if limit <= 0 or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-limit:]


def main() -> int:
    args = parse_args()
    resolved_summary_file = resolve_summary_file(args.summary_file)

    state_payload = read_json(args.state_file) or {}
    summary_payload = read_json(resolved_summary_file) or {}
    registry_payload = read_json(args.registry_file) or {}
    latest_log = latest_log_file(args.log_dir)

    state_bucket = ((state_payload.get("spaces") or {}) if isinstance(state_payload, dict) else {}).get("demo_kg")
    summaries = summary_payload.get("summaries") if isinstance(summary_payload, dict) else None
    latest_summary = summaries[0] if isinstance(summaries, list) and summaries else None
    registry_demo = (((registry_payload.get("spaces") or {}) if isinstance(registry_payload, dict) else {}).get("demo_kg") or {})
    es_client = ElasticsearchClient(index="kg_entity")

    print("== demo_kg backfill inspection ==")
    print(f"state_file: {args.state_file}")
    print(f"summary_file: {resolved_summary_file}")
    print(f"registry_file: {args.registry_file}")
    print(f"log_dir: {args.log_dir}")
    print()

    print("state_bucket:")
    print(json.dumps(state_bucket or {}, ensure_ascii=False, indent=2))
    print()

    print("latest_summary:")
    print(json.dumps(latest_summary or {}, ensure_ascii=False, indent=2))
    print()

    print("registry_index_status:")
    print(json.dumps((registry_demo or {}).get("index_status") or {}, ensure_ascii=False, indent=2))
    print()

    try:
        legacy_missing_space_doc_count, legacy_count_ms = es_client.count_documents_missing_space()
    except Exception as exc:
        legacy_missing_space_doc_count, legacy_count_ms = None, str(exc)
    print("legacy_missing_space_doc_count:")
    print(json.dumps({"count": legacy_missing_space_doc_count, "took_ms": legacy_count_ms}, ensure_ascii=False, indent=2))
    print()

    latest_completion = {}
    if state_bucket:
        latest_completion = index_status_service.build_completion_snapshot(
            status=str((state_bucket or {}).get("status") or ""),
            nebula_entity_count=(state_bucket or {}).get("nebula_entity_count"),
            es_doc_count=(state_bucket or {}).get("es_doc_count"),
            coverage_pct=(state_bucket or {}).get("coverage_pct"),
        )
    elif registry_demo:
        index_status = (registry_demo or {}).get("index_status") or {}
        latest_completion = index_status_service.build_completion_snapshot(
            status=str(index_status.get("status") or ""),
            nebula_entity_count=index_status.get("nebula_entity_count"),
            es_doc_count=index_status.get("doc_count"),
            coverage_pct=index_status.get("coverage_pct"),
        )
    elif latest_summary:
        latest_completion = index_status_service.build_completion_snapshot(
            status=str(latest_summary.get("status") or ""),
            nebula_entity_count=latest_summary.get("nebula_entity_count"),
            es_doc_count=latest_summary.get("es_doc_count"),
            coverage_pct=latest_summary.get("coverage_pct"),
        )

    print("full_completion:")
    print(json.dumps(latest_completion or {}, ensure_ascii=False, indent=2))
    print()

    if latest_log is None:
        print("latest_log: <missing>")
        return 0

    print(f"latest_log: {latest_log}")
    if args.tail > 0:
        print("-- latest_log_tail --")
        for line in tail_lines(latest_log, args.tail):
            print(line)
    if args.require_full and not bool(latest_completion.get("full_completion")):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
