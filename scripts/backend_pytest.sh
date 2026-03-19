#!/usr/bin/env bash
set -euo pipefail

# COMPAT(2026-03): keep the legacy top-level test entrypoint while teammates
# switch to `scripts/test/backend_pytest.sh`, remove after docs and habit paths
# no longer reference the top-level wrapper.
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/test/backend_pytest.sh" "$@"
