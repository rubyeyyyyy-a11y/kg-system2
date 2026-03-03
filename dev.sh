#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"

# ---------- backend ----------
echo "[backend] starting..."
cd "$ROOT/backend"

# activate venv
if [ ! -d ".venv" ]; then
  echo "[backend] .venv not found, creating..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# optional deps install if requirements exists
if [ -f "requirements.txt" ]; then
  pip install -r requirements.txt
fi

# ensure venv python is active and sane
if ! which python | grep -q "/.venv/bin/python"; then
  echo "[backend] ERROR: venv not active or broken."
  exit 1
fi

# try uvicorn entrypoints
BACK_LOG="$ROOT/backend/server.dev.log"
rm -f "$BACK_LOG"

start_backend () {
  local target="$1"
  echo "[backend] python -m uvicorn $target --port 8000"
  (python -m uvicorn "$target" --host 0.0.0.0 --port 8000 --reload 2>&1 | tee -a "$BACK_LOG") &
  echo $!
}

BACK_PID="$(start_backend app:app)"
sleep 1
if ! curl -sSf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
  echo "[backend] app:app healthcheck failed, retry with main:app"
  kill "$BACK_PID" >/dev/null 2>&1 || true
  sleep 1
  BACK_PID="$(start_backend main:app)"
  sleep 1
  curl -sSf "http://127.0.0.1:8000/api/health" >/dev/null
fi

echo "[backend] ok (PID=$BACK_PID). log=$BACK_LOG"

# ---------- frontend ----------
echo "[frontend] starting..."
cd "$ROOT/frontend"

# install once if needed
if [ ! -d "node_modules" ]; then
  npm install
fi

FRONT_LOG="$ROOT/frontend/vite.dev.log"
rm -f "$FRONT_LOG"
(npm run dev -- --host 0.0.0.0 --port 5173 2>&1 | tee -a "$FRONT_LOG") &
FRONT_PID=$!

echo "[frontend] ok (PID=$FRONT_PID). log=$FRONT_LOG"
echo "Open: http://localhost:5173"

# keep in foreground
wait
