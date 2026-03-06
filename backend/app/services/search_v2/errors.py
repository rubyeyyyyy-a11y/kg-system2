from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from fastapi import HTTPException


class SearchErrorCode(str, Enum):
    ES_UNAVAILABLE = "es_unavailable"
    ES_TIMEOUT = "es_timeout"
    NEBULA_FETCH_TIMEOUT = "nebula_fetch_timeout"
    NEBULA_FETCH_UNAVAILABLE = "nebula_fetch_unavailable"
    VALIDATION_ERROR = "validation_error"
    INTERNAL_ERROR = "internal_error"


@dataclass
class SearchServiceError(Exception):
    code: SearchErrorCode
    message: str
    status_code: int
    reason: str = ""
    upstream: str = ""


def to_http_exception(err: SearchServiceError, request_id: str) -> HTTPException:
    detail: Dict[str, Any] = {
        "code": err.code.value,
        "message": err.message,
        "request_id": request_id,
    }
    if err.reason:
        detail["reason"] = err.reason
    if err.upstream:
        detail["upstream"] = err.upstream
    return HTTPException(status_code=int(err.status_code), detail=detail)


def mk_search_error(
    *,
    code: SearchErrorCode,
    message: str,
    status_code: int,
    reason: str = "",
    upstream: Optional[str] = None,
) -> SearchServiceError:
    return SearchServiceError(
        code=code,
        message=message,
        status_code=status_code,
        reason=reason,
        upstream=str(upstream or ""),
    )

