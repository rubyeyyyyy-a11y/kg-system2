#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clients.es_client import ElasticsearchClient
from app.config import settings
from app.services.spaces import index_status_service

DEFAULT_REGISTRY = REPO_ROOT / "runtime" / ".run" / "space-registry" / "spaces.json"
DEFAULT_STATE_DIR = ROOT / "state"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Globally purge legacy ES documents that do not have space_name.")
    parser.add_argument("--execute", action="store_true", help="perform delete_by_query; default is dry-run only")
    parser.add_argument("--registry-file", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--es-index", default=settings.es_index)
    parser.add_argument("--es-timeout-ms", type=int, default=max(int(settings.es_timeout_ms), 600_000))
    parser.add_argument("--summary-json", type=Path, default=None)
    return parser.parse_args()


def resolve_summary_path(explicit: Path | None, *, execute: bool) -> Path:
    if explicit is not None:
        return explicit
    stem = "legacy_es_purge_execute" if execute else "legacy_es_purge_dry_run"
    return DEFAULT_STATE_DIR / f"{stem}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"


def collect_ready_space_counts(client: ElasticsearchClient, registry_payload: dict[str, Any], *, index_name: str) -> dict[str, dict[str, Any]]:
    spaces = (registry_payload.get("spaces") or {}) if isinstance(registry_payload, dict) else {}
    out: dict[str, dict[str, Any]] = {}
    for space_name, item in sorted(spaces.items()):
        summary = item or {}
        if str(summary.get("status") or "") != "ready":
            continue
        if str(summary.get("internal_status") or "") != "ready":
            continue
        if not summary.get("index_status"):
            continue
        doc_count, took_ms = client.count_documents_for_space(space_name, index_name=index_name)
        out[str(space_name)] = {
            "doc_count": doc_count,
            "took_ms": round(float(took_ms), 3),
            "expected_doc_count": int(((summary.get("index_status") or {}).get("doc_count") or 0)),
        }
    return out


def build_preconditions(registry_payload: dict[str, Any], client: ElasticsearchClient, *, index_name: str) -> dict[str, Any]:
    demo = (((registry_payload.get("spaces") or {}) if isinstance(registry_payload, dict) else {}).get("demo_kg") or {})
    demo_index_status = dict(demo.get("index_status") or {})
    completion = index_status_service.build_completion_snapshot(
        status=str(demo_index_status.get("status") or ""),
        nebula_entity_count=demo_index_status.get("nebula_entity_count"),
        es_doc_count=demo_index_status.get("doc_count"),
        coverage_pct=demo_index_status.get("coverage_pct"),
    )
    legacy_missing_space_count, legacy_missing_space_took_ms = client.count_documents_missing_space(index_name=index_name)
    ready_space_counts = collect_ready_space_counts(client, registry_payload, index_name=index_name)
    doc_counts_match = int(demo_index_status.get("doc_count") or 0) == int(demo_index_status.get("nebula_entity_count") or 0)
    return {
        "demo_kg": {
            "index_status": demo_index_status,
            "full_completion": bool(completion.get("full_completion")),
            "remaining_docs": completion.get("remaining_docs"),
            "doc_counts_match": doc_counts_match,
        },
        "legacy_missing_space": {
            "count": legacy_missing_space_count,
            "took_ms": round(float(legacy_missing_space_took_ms), 3),
        },
        "canonical_counts_before": ready_space_counts,
        "ready_space_count": len(ready_space_counts),
        "gate_ok": bool(completion.get("full_completion")) and doc_counts_match and legacy_missing_space_count is not None,
    }


def run_demo_kg_full_check() -> dict[str, Any]:
    cmd = [sys.executable, str(ROOT / "scripts" / "check_demo_kg_backfill.py"), "--require-full", "--tail", "0"]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": proc.stdout.splitlines()[-20:],
        "stderr_tail": proc.stderr.splitlines()[-20:],
    }


def main() -> int:
    args = parse_args()
    summary_path = resolve_summary_path(args.summary_json, execute=args.execute)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    registry_payload = read_json(args.registry_file)
    client = ElasticsearchClient(index=args.es_index, timeout_ms=args.es_timeout_ms)
    preconditions = build_preconditions(registry_payload, client, index_name=args.es_index)

    summary: dict[str, Any] = {
        "started_at": _now_iso(),
        "mode": "execute" if args.execute else "dry-run",
        "es_index": args.es_index,
        "es_timeout_ms": args.es_timeout_ms,
        "registry_file": str(args.registry_file),
        "summary_json": str(summary_path),
        "preconditions": preconditions,
        "delete": None,
        "verification": None,
    }

    if not args.execute:
        summary["finished_at"] = _now_iso()
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if not bool(preconditions.get("gate_ok")):
        summary["finished_at"] = _now_iso()
        summary["error"] = "preconditions_not_met"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    try:
        delete_response, delete_took_ms = client.delete_documents_missing_space(index_name=args.es_index)
    except Exception as exc:
        summary["finished_at"] = _now_iso()
        summary["error"] = f"delete_failed: {exc}"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 4
    canonical_counts_after = collect_ready_space_counts(client, registry_payload, index_name=args.es_index)
    legacy_missing_space_after, legacy_missing_space_after_took_ms = client.count_documents_missing_space(index_name=args.es_index)
    counts_unchanged = {
        space_name: {
            "before": preconditions["canonical_counts_before"][space_name]["doc_count"],
            "after": canonical_counts_after.get(space_name, {}).get("doc_count"),
            "unchanged": preconditions["canonical_counts_before"][space_name]["doc_count"]
            == canonical_counts_after.get(space_name, {}).get("doc_count"),
        }
        for space_name in preconditions["canonical_counts_before"]
    }
    demo_full_check = run_demo_kg_full_check()

    summary["delete"] = {
        "took_ms": round(float(delete_took_ms), 3),
        "response": delete_response,
    }
    summary["verification"] = {
        "legacy_missing_space_after": {
            "count": legacy_missing_space_after,
            "took_ms": round(float(legacy_missing_space_after_took_ms), 3),
        },
        "canonical_counts_after": canonical_counts_after,
        "canonical_counts_unchanged": counts_unchanged,
        "all_canonical_counts_unchanged": all(bool(item["unchanged"]) for item in counts_unchanged.values()),
        "demo_kg_full_check": demo_full_check,
    }
    summary["finished_at"] = _now_iso()
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if legacy_missing_space_after == 0 and summary["verification"]["all_canonical_counts_unchanged"] and demo_full_check["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
