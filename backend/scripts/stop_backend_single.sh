#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8000}"
PIDS="$(
  ps -eo pid=,args= \
    | rg "python3? -m uvicorn app\\.main:app.*--port ${PORT}" -N \
    | awk '{print $1}' \
    | tr '\n' ' ' \
    || true
)"

if [ -z "$PIDS" ]; then
  echo "no uvicorn app.main:app process on port ${PORT}"
  exit 0
fi

kill $PIDS || true
echo "stopped pids: $PIDS"
