import os
import re
from typing import Optional

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

NEBULA_HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
NEBULA_PORT = int(os.getenv("NEBULA_PORT", "9669"))
NEBULA_USER = os.getenv("NEBULA_USER", "root")
NEBULA_PASSWORD = os.getenv("NEBULA_PASSWORD", "nebula")
NEBULA_SPACE = os.getenv("NEBULA_SPACE", "demo_kg")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(raw: str, fallback: str) -> str:
    value = (raw or "").strip()
    if value and _IDENTIFIER_RE.match(value):
        return value
    return fallback


EDGE_TYPE = _safe_identifier(os.getenv("EDGE_TYPE", "REL2"), "REL2")
EDGE_TAG = f"`{EDGE_TYPE}`"

_pool: Optional[ConnectionPool] = None


def get_session():
    """Get Nebula session; enforce USE space with error check."""
    global _pool

    if _pool is None:
        cfg = Config()
        cfg.max_connection_pool_size = 10
        _pool = ConnectionPool()
        ok = _pool.init([(NEBULA_HOST, NEBULA_PORT)], cfg)
        if not ok:
            raise RuntimeError(f"Failed to init pool to {NEBULA_HOST}:{NEBULA_PORT}")

    session = _pool.get_session(NEBULA_USER, NEBULA_PASSWORD)
    if not session:
        raise RuntimeError("Failed to get Nebula session (check user/password)")

    r = session.execute(f"USE {NEBULA_SPACE};")
    if not r.is_succeeded():
        raise RuntimeError(f"USE failed: {r.error_msg()}")

    return session


def execute_ngql(ngql: str):
    session = get_session()
    return session.execute(ngql)
