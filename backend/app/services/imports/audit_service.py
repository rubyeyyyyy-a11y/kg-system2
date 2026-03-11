from typing import Any

from app.core.audit_logger import write_audit_record


def write_import_audit(action: str, payload: dict[str, Any]) -> None:
    record = {"kind": "import", "action": action}
    record.update(payload)
    write_audit_record(record)
