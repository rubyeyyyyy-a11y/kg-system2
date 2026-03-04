import logging
import time
from typing import Any

from app.db.nebula import execute_ngql

logger = logging.getLogger(__name__)


class NebulaExecutionError(RuntimeError):
    def __init__(self, message: str, *, ngql: str, code: str = "NEBULA_EXEC_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.ngql = ngql
        self.code = code


def execute_ngql_safe(ngql: str, retries: int = 1, sleep_sec: float = 0.05) -> Any:
    last_error: NebulaExecutionError | None = None
    attempts = max(1, retries + 1)
    for attempt in range(1, attempts + 1):
        try:
            res = execute_ngql(ngql)
        except Exception as exc:
            last_error = NebulaExecutionError(str(exc), ngql=ngql, code="NEBULA_SESSION_ERROR")
            if attempt < attempts:
                time.sleep(sleep_sec)
                continue
            raise last_error

        if not res.is_succeeded():
            last_error = NebulaExecutionError(str(res.error_msg()), ngql=ngql, code="NEBULA_QUERY_FAILED")
            if attempt < attempts:
                time.sleep(sleep_sec)
                continue
            raise last_error
        return res

    if last_error is None:
        last_error = NebulaExecutionError("unknown nebula error", ngql=ngql)
    logger.error("nebula execute failed: %s", last_error.message)
    raise last_error
