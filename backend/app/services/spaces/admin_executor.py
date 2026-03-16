from __future__ import annotations

import logging
import os
import time

from app.config import settings
from app.db.nebula_client import execute_ngql_safe


ADMIN_WAIT_TIMEOUT_SEC = max(1.0, float(os.getenv("SPACE_CREATE_WAIT_TIMEOUT_SEC", "15")))
ADMIN_WAIT_POLL_SEC = max(0.1, float(os.getenv("SPACE_CREATE_WAIT_POLL_SEC", "0.5")))
logger = logging.getLogger(__name__)


def _admin_auth() -> tuple[str, str]:
    return settings.nebula_admin_user, settings.nebula_admin_password


def create_space(space_name: str) -> None:
    user, password = _admin_auth()
    execute_ngql_safe(
        f"CREATE SPACE IF NOT EXISTS `{space_name}`(partition_num=10, replica_factor=1, vid_type=INT64);",
        user=user,
        password=password,
        use_space=False,
    )


def can_use_space(space_name: str) -> bool:
    user, password = _admin_auth()
    try:
        execute_ngql_safe("SHOW TAGS;", space_name=space_name, user=user, password=password)
        return True
    except Exception:
        return False


def wait_until_space_ready(space_name: str, timeout_sec: float = ADMIN_WAIT_TIMEOUT_SEC) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if can_use_space(space_name):
            return
        time.sleep(ADMIN_WAIT_POLL_SEC)
    raise RuntimeError(f"space `{space_name}` is not ready before timeout")


def apply_statements(space_name: str, statements: list[str]) -> None:
    user, password = _admin_auth()
    for statement in statements:
        execute_ngql_safe(statement, space_name=space_name, user=user, password=password)


def wait_until_statements_succeed(
    space_name: str,
    statements: list[str],
    *,
    timeout_sec: float = ADMIN_WAIT_TIMEOUT_SEC,
) -> None:
    user, password = _admin_auth()
    deadline = time.time() + timeout_sec
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            for statement in statements:
                execute_ngql_safe(statement, space_name=space_name, user=user, password=password)
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "space_readiness_retry space=%s timeout_sec=%.1f reason=%s",
                space_name,
                timeout_sec,
                str(exc),
            )
            time.sleep(ADMIN_WAIT_POLL_SEC)
    raise RuntimeError(
        f"space `{space_name}` schema is not queryable before timeout: {last_error or 'unknown readiness error'}"
    )
