import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from app.core.config import AUDIT_LOG_PATH, ensure_audit_log_dir

logger = logging.getLogger(__name__)


def write_audit_record(record: Dict[str, Any]) -> None:
    ensure_audit_log_dir()
    payload = dict(record)
    payload.setdefault("ts", int(time.time()))
    path = Path(AUDIT_LOG_PATH)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover - non-blocking by design
        logger.exception("failed to write audit log: %s", exc)
