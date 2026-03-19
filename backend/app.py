# COMPAT(2026-03): preserve the legacy `backend/app.py -> app` import surface
# for tooling that still targets `app:app`, remove after entrypoints fully
# standardize on `app.main:app`.
from app.main import app

__all__ = ["app"]
