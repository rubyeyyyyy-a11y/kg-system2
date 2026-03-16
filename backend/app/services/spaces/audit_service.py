from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


AUDIT_PATH = Path(__file__).resolve().parents[4] / ".run" / "space-registry" / "audit.jsonl"


def write_audit(event_type: str, payload: dict[str, Any]) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event_type": event_type,
        **payload,
    }
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

