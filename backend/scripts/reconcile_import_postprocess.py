#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.imports import postprocess_reconcile_service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconcile import postprocess for a space or failed job")
    parser.add_argument("--space", type=str, default="", help="target space_name; defaults to job space or current space")
    parser.add_argument("--job-id", type=str, default="", help="optional failed import job id to reconcile in place")
    parser.add_argument("--actor", type=str, default="postprocess_reconcile", help="actor recorded in metadata refresh")
    parser.add_argument(
        "--sync-scope",
        type=str,
        default="auto",
        choices=["auto", "none", "job", "space"],
        help="auto = use job affected vids when reconcile is job-scoped; space = full-space ES sync",
    )
    parser.add_argument("--refresh-metadata", action="store_true", help="force metadata refresh")
    parser.add_argument("--skip-metadata", action="store_true", help="force skip metadata refresh")
    parser.add_argument("--summary-json", type=str, default="", help="optional output path for reconcile summary")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    refresh_metadata = None
    if args.refresh_metadata:
        refresh_metadata = True
    if args.skip_metadata:
        refresh_metadata = False

    result = postprocess_reconcile_service.reconcile_postprocess(
        space_name=args.space or None,
        job_id=args.job_id or None,
        actor=args.actor,
        refresh_metadata=refresh_metadata,
        sync_scope=args.sync_scope,
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.summary_json:
        Path(args.summary_json).write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
