import os
from pathlib import Path

from app.config import settings

SPACE = settings.nebula_space
EDGE_TYPE = os.getenv("EDGE_TYPE", "REL2").strip() or "REL2"
UPDATED_AT_UNIT = "seconds"

# Relative to backend/ working directory.
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "logs/edit_audit.jsonl")

ENTITY_FIELD_MAX_LEN = {
    "entity_name": 256,
    "entity_type": 128,
    "source": 256,
    "description": 4096,
}
EDGE_FIELD_MAX_LEN = {
    "relation": 256,
    "source": 256,
    "evidence": 4096,
}
SYSTEM_FIELD_MAX_LEN = {
    "updated_by": 64,
}

ENTITY_EDITABLE_FIELDS = {"entity_name", "entity_type", "source", "description"}
ENTITY_FORBIDDEN_FIELDS = {"entity_raw_id"}
EDGE_EDITABLE_FIELDS = {"relation", "source", "evidence"}
ALLOW_MULTILINE_FIELDS = {"description", "evidence"}


def ensure_audit_log_dir() -> None:
    path = Path(AUDIT_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
