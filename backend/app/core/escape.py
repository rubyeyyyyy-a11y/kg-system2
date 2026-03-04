import re

from fastapi import HTTPException

from app.core import config

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_text(value: str) -> str:
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="string field type required")
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
        raise HTTPException(status_code=422, detail=f"field '{field_name}' does not allow newline")
    if len(cleaned) > int(max_len):
        raise HTTPException(status_code=422, detail=f"field '{field_name}' exceeds maxLen={max_len}")
    return cleaned


def validate_updated_by(value: str) -> str:
    cleaned = sanitize_text(value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="'updated_by' is required")
    if len(cleaned) > config.SYSTEM_FIELD_MAX_LEN["updated_by"]:
        raise HTTPException(
            status_code=422,
            detail=f"'updated_by' exceeds maxLen={config.SYSTEM_FIELD_MAX_LEN['updated_by']}",
        )
    return cleaned


def escape_ngql_string(value: str, field_name: str, max_len: int, multiline: bool) -> str:
    cleaned = validate_text(field_name=field_name, value=value, max_len=max_len, multiline=multiline)
    escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return escaped
