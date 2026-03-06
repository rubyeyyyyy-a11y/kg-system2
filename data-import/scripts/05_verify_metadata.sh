#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
SCRIPT_PATH="$ROOT_DIR/scripts/04_refresh_metadata.py"

GRAPH_HOST="${GRAPH_HOST:-127.0.0.1}"
GRAPH_PORT="${GRAPH_PORT:-9669}"
GRAPH_USER="${GRAPH_USER:-root}"
GRAPH_PASSWORD="${GRAPH_PASSWORD:-nebula}"
SPACE="${SPACE:-demo_kg}"
EDGE_TYPE="${EDGE_TYPE:-REL2}"
SOURCE_MODE="${SOURCE_MODE:-auto}"

log() {
  printf '[verify-metadata] %s\n' "$*"
}

fail() {
  printf '[verify-metadata][ERROR] %s\n' "$*" >&2
  exit 1
}

detect_nebula_python() {
  if [ -n "${NEBULA_PYTHON:-}" ] && [ -x "${NEBULA_PYTHON}" ]; then
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    if python3 - <<'PY' >/dev/null 2>&1
import nebula3
print("ok")
PY
    then
      NEBULA_PYTHON="$(command -v python3)"
      return 0
    fi
  fi

  if [ -x "$REPO_ROOT/backend/.venv/bin/python" ]; then
    if "$REPO_ROOT/backend/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import nebula3
print("ok")
PY
    then
      NEBULA_PYTHON="$REPO_ROOT/backend/.venv/bin/python"
      return 0
    fi
  fi

  fail "python with nebula3 not found (set NEBULA_PYTHON)"
}

detect_nebula_python
log "using python: $NEBULA_PYTHON"

NEBULA_HOST="$GRAPH_HOST" \
NEBULA_PORT="$GRAPH_PORT" \
NEBULA_USER="$GRAPH_USER" \
NEBULA_PASSWORD="$GRAPH_PASSWORD" \
NEBULA_SPACE="$SPACE" \
NEBULA_TIMEOUT_MS="${NEBULA_TIMEOUT_MS:-120000}" \
EDGE_TYPE="$EDGE_TYPE" \
"$NEBULA_PYTHON" "$SCRIPT_PATH" --mode verify --compare --source "$SOURCE_MODE"

log "metadata verification passed"
