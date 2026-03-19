# COMPAT(2026-03): keep the legacy `backend.main:app` import surface for
# external runners and local habits, remove after all entrypoints standardize on
# `app.main:app`.
from app.main import app

__all__ = ["app"]
