import os
from typing import Optional

from nebula3.Config import Config
from nebula3.gclient.net import ConnectionPool

NEBULA_HOST = os.getenv("NEBULA_HOST", "127.0.0.1")
NEBULA_PORT = int(os.getenv("NEBULA_PORT", "9669"))
NEBULA_USER = os.getenv("NEBULA_USER", "root")
NEBULA_PASSWORD = os.getenv("NEBULA_PASSWORD", "nebula")
NEBULA_SPACE = os.getenv("NEBULA_SPACE", "demo_kg")

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
