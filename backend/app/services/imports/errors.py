from typing import Any, Optional

from fastapi import HTTPException


def import_http_error(
    *,
    status_code: int,
    error_code: str,
    message: str,
    field: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> HTTPException:
    detail: dict[str, Any] = {
        "error_code": error_code,
        "message": message,
    }
    if field:
        detail["field"] = field
    if extra:
        detail["extra"] = extra
    return HTTPException(status_code=status_code, detail=detail)


def raise_import_http_error(
    *,
    status_code: int,
    error_code: str,
    message: str,
    field: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    raise import_http_error(
        status_code=status_code,
        error_code=error_code,
        message=message,
        field=field,
        extra=extra,
    )
