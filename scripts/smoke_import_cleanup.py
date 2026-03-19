#!/usr/bin/env python3

# COMPAT(2026-03): keep the legacy top-level verify entrypoint while teammates
# switch to `scripts/verify/smoke_import_cleanup.py`, remove after docs and
# habit paths no longer reference the top-level wrapper.

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "verify" / "smoke_import_cleanup.py"),
        run_name="__main__",
    )
