#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_FILE="${LOG_FILE:-$ROOT/server.dev.log}"
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"

cd "$ROOT"
source .venv/bin/activate

# Stop existing uvicorn bound to the same app/port to avoid split-brain.
PIDS="$(
  ps -eo pid=,args= \
    | rg "python3? -m uvicorn app\\.main:app.*--port ${PORT}" -N \
    | awk '{print $1}' \
    | tr '\n' ' ' \
    || true
)"
if [ -n "$PIDS" ]; then
  kill $PIDS || true
  sleep 1
fi

exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --log-level debug 2>&1 | tee -a "$LOG_FILE"
