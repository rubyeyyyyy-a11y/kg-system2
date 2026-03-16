import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from typing import Generator, Optional

from nebula3.Config import Config
from nebula3.Exception import IOErrorException, NotValidConnectionException
from nebula3.gclient.net import ConnectionPool

from app.config import settings
from app.core.space_context import get_current_space

NEBULA_HOST = settings.nebula_host
NEBULA_PORT = settings.nebula_port
NEBULA_USER = settings.nebula_user
NEBULA_PASSWORD = settings.nebula_password
NEBULA_SPACE = settings.nebula_space
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
logger = logging.getLogger(__name__)


def _safe_identifier(raw: str, fallback: str) -> str:
    value = (raw or "").strip()
    if value and _IDENTIFIER_RE.match(value):
        return value
    return fallback


def _require_identifier(raw: str, field_name: str) -> str:
    value = (raw or "").strip()
    if value and _IDENTIFIER_RE.match(value):
        return value
    raise RuntimeError(f"invalid {field_name}: {raw!r}")


EDGE_TYPE = _safe_identifier(os.getenv("EDGE_TYPE", "REL2"), "REL2")
EDGE_TAG = f"`{EDGE_TYPE}`"

_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()
_RETRYABLE_EXCEPTIONS = (IOErrorException, NotValidConnectionException)
_POOL_INIT_BACKOFF_SECONDS = (0.2, 0.4, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0)
_POOL_INIT_MAX_ATTEMPTS = 8
_EXECUTE_RETRY_MAX = 1


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid int env %s=%r, fallback=%d", name, raw, default)
        return default


def _request_id() -> str:
    return f"nb-{int(time.time() * 1000)}-{os.getpid()}"


def _ngql_summary(ngql: str, limit: int = 200) -> str:
    normalized = " ".join((ngql or "").split())
    return normalized[:limit]


def _apply_timeout(cfg: Config, timeout_ms: int) -> None:
    timeout_fields = ("timeout", "connection_timeout", "connection_timeout_ms")
    applied = False
    for field in timeout_fields:
        if hasattr(cfg, field):
            try:
                setattr(cfg, field, timeout_ms)
                applied = True
            except Exception:
                logger.warning("failed to set Config.%s=%d", field, timeout_ms)
    if not applied:
        try:
            cfg.timeout = timeout_ms
        except Exception:
            logger.warning("nebula Config timeout field not found; timeout_ms=%d not applied", timeout_ms)


def _is_pool_status_bad_error(exc: Exception) -> bool:
    msg = str(exc or "").lower()
    return ("services status exception" in msg) or ("status: bad" in msg)


def _close_pool_safely(pool: ConnectionPool, reason: str) -> None:
    try:
        pool.close()
    except Exception:
        logger.warning("failed to close pool (%s)", reason, exc_info=True)


def _init_pool() -> ConnectionPool:
    total_attempts = min(_POOL_INIT_MAX_ATTEMPTS, len(_POOL_INIT_BACKOFF_SECONDS))
    last_error: Exception | None = None

    for attempt in range(1, total_attempts + 1):
        cfg = Config()
        cfg.max_connection_pool_size = _env_int("NEBULA_POOL_SIZE", 10)
        _apply_timeout(cfg, _env_int("NEBULA_TIMEOUT_MS", 5000))

        pool = ConnectionPool()
        try:
            ok = pool.init([(NEBULA_HOST, NEBULA_PORT)], cfg)
            if ok:
                return pool
            last_error = RuntimeError(f"Failed to init pool to {NEBULA_HOST}:{NEBULA_PORT}")
        except RuntimeError as exc:
            last_error = exc
        except Exception as exc:
            last_error = exc

        is_bad_status = isinstance(last_error, RuntimeError) and _is_pool_status_bad_error(last_error)
        has_next = attempt < total_attempts

        if is_bad_status and has_next:
            wait_s = _POOL_INIT_BACKOFF_SECONDS[attempt - 1]
            logger.warning(
                "nebula pool init retry on BAD status: attempt=%d/%d host=%s:%s wait=%.1fs error=%s",
                attempt,
                total_attempts,
                NEBULA_HOST,
                NEBULA_PORT,
                wait_s,
                str(last_error),
            )
            _close_pool_safely(pool, "bad_status_retry")
            time.sleep(wait_s)
            continue

        if last_error is not None:
            _close_pool_safely(pool, "init_failed")
            logger.error(
                "nebula pool init failed: host=%s:%s retries=%d error=%s",
                NEBULA_HOST,
                NEBULA_PORT,
                attempt,
                str(last_error),
                exc_info=True,
            )
            raise RuntimeError(
                f"Failed to init pool to {NEBULA_HOST}:{NEBULA_PORT}; retries={attempt}; last_error={last_error}"
            ) from last_error

    raise RuntimeError(
        f"Failed to init pool to {NEBULA_HOST}:{NEBULA_PORT}; retries={total_attempts}; last_error=unknown"
    )


def _ensure_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool
    with _pool_lock:
        if _pool is None:
            _pool = _init_pool()
        return _pool


def _invalidate_pool() -> None:
    global _pool
    old_pool: Optional[ConnectionPool] = None
    with _pool_lock:
        old_pool = _pool
        _pool = None
    if old_pool is not None:
        try:
            old_pool.close()
        except Exception:
            logger.warning("failed to close old nebula pool", exc_info=True)


def get_session(*, user: str | None = None, password: str | None = None):
    pool = _ensure_pool()
    session = pool.get_session(user or NEBULA_USER, password or NEBULA_PASSWORD)
    if not session:
        raise RuntimeError(f"Failed to get Nebula session at {NEBULA_HOST}:{NEBULA_PORT} (check user/password)")
    return session


@contextmanager
def nebula_session(
    space_name: str | None = None,
    *,
    user: str | None = None,
    password: str | None = None,
    use_space: bool = True,
) -> Generator:
    session = None
    try:
        session = get_session(user=user, password=password)
        if use_space:
            resolved_space = (
                _require_identifier(space_name, "space_name") if space_name is not None else _require_identifier(get_current_space(), "space_name")
            )
            use_res = session.execute(f"USE `{resolved_space}`;")
            if not use_res.is_succeeded():
                raise RuntimeError(f"USE failed: {use_res.error_msg()}")
        yield session
    finally:
        if session is not None:
            try:
                session.release()
            except Exception:
                logger.warning("failed to release nebula session", exc_info=True)


def execute_ngql(
    ngql: str,
    space_name: str | None = None,
    *,
    user: str | None = None,
    password: str | None = None,
    use_space: bool = True,
):
    request_id = _request_id()
    summary = _ngql_summary(ngql)
    total_attempts = _EXECUTE_RETRY_MAX + 1
    for attempt in range(1, total_attempts + 1):
        try:
            with nebula_session(space_name=space_name, user=user, password=password, use_space=use_space) as session:
                return session.execute(ngql)
        except _RETRYABLE_EXCEPTIONS as exc:
            should_retry = attempt <= _EXECUTE_RETRY_MAX
            if should_retry:
                logger.warning(
                    "nebula retryable error: request_id=%s attempt=%d/%d type=%s host=%s:%s reason=%s ngql=%s",
                    request_id,
                    attempt,
                    total_attempts,
                    type(exc).__name__,
                    NEBULA_HOST,
                    NEBULA_PORT,
                    str(exc),
                    summary,
                )
                _invalidate_pool()
                continue
            logger.error(
                "nebula retry exhausted: request_id=%s attempt=%d/%d type=%s host=%s:%s reason=%s ngql=%s",
                request_id,
                attempt,
                total_attempts,
                type(exc).__name__,
                NEBULA_HOST,
                NEBULA_PORT,
                str(exc),
                summary,
                exc_info=True,
            )
            raise


def execute_ngql_retry(
    ngql: str,
    space_name: str | None = None,
    *,
    user: str | None = None,
    password: str | None = None,
    use_space: bool = True,
):
    return execute_ngql(ngql, space_name=space_name, user=user, password=password, use_space=use_space)
