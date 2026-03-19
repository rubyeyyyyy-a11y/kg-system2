#!/usr/bin/env bash
set -euo pipefail

# COMPAT(2026-03): keep the legacy top-level smoke entrypoint while teammates
# switch to `scripts/verify/smoke_api.sh`, remove after docs and habit paths no
# longer reference the top-level wrapper.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/verify/smoke_api.sh" "$@"
