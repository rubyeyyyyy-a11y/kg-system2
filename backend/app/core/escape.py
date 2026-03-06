import re

from fastapi import HTTPException

from app.core import config

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def raise_validation_error(message: str, field: str | None = None) -> None:
    detail = {"error_code": "VALIDATION_ERROR", "message": message}
    if field:
        detail["field"] = field
    raise HTTPException(status_code=422, detail=detail)


def sanitize_text(value: str) -> str:
    if not isinstance(value, str):
        raise_validation_error("string field type required")
    # Keep newline(\n), carriage return(\r), tab(\t); strip other controls.
    return _CONTROL_CHARS_RE.sub("", value)


def validate_text(
    field_name: str,
    value: str,
    max_len: int,
    multiline: bool,
) -> str:
    cleaned = sanitize_text(value)
    if not multiline and ("\n" in cleaned or "\r" in cleaned):
        raise_validation_error(f"field '{field_name}' does not allow newline", field=field_name)
    if len(cleaned) > int(max_len):
        raise_validation_error(f"field '{field_name}' exceeds maxLen={max_len}", field=field_name)
    return cleaned


def validate_updated_by(value: str) -> str:
    cleaned = sanitize_text(value or "").strip()
    if not cleaned:
        raise_validation_error("'updated_by' is required", field="updated_by")
    if len(cleaned) > config.SYSTEM_FIELD_MAX_LEN["updated_by"]:
        raise_validation_error(
            f"'updated_by' exceeds maxLen={config.SYSTEM_FIELD_MAX_LEN['updated_by']}",
            field="updated_by",
        )
    return cleaned


def escape_ngql_string(value: str, field_name: str, max_len: int, multiline: bool) -> str:
    cleaned = validate_text(field_name=field_name, value=value, max_len=max_len, multiline=multiline)
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return escaped
