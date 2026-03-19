# COMPAT(2026-03): preserve `from app import app` for legacy entrypoints,
# remove after imports are normalized to `app.main:app`.
from .main import app

__all__ = ["app"]
