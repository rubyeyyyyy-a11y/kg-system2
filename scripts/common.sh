#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${RUN_DIR:-$ROOT/.run}"
LOG_DIR="$RUN_DIR/logs"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"
FRONTEND_VITE_ENTRY="$ROOT/frontend/node_modules/vite/bin/vite.js"

mkdir -p "$RUN_DIR" "$LOG_DIR"

backend_url() {
  printf 'http://%s:%s' "$BACKEND_HOST" "$BACKEND_PORT"
}

frontend_url() {
  printf 'http://%s:%s' "$FRONTEND_HOST" "$FRONTEND_PORT"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

is_pid_running() {
  local pid="${1:-}"
  [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1
}

read_pid_file() {
  local path="$1"
  if [ ! -f "$path" ]; then
    return 1
  fi
  local pid
  pid="$(tr -d '[:space:]' < "$path")"
  if [ -z "$pid" ]; then
    return 1
  fi
  printf '%s\n' "$pid"
}

cleanup_stale_pid_file() {
  local path="$1"
  local pid
  pid="$(read_pid_file "$path" || true)"
  if [ -n "$pid" ] && ! is_pid_running "$pid"; then
    rm -f "$path"
  fi
}

find_backend_pids() {
  ps -eo pid=,args= | awk -v host="$BACKEND_HOST" -v port="$BACKEND_PORT" '
    index($0, "uvicorn app.main:app") && index($0, "--host " host) && index($0, "--port " port) { print $1 }
  '
}

find_frontend_pids() {
  ps -eo pid=,comm=,args= | awk -v vite_entry="$FRONTEND_VITE_ENTRY" -v host="$FRONTEND_HOST" -v port="$FRONTEND_PORT" '
    ($2 == "node" || $2 == "nodejs") &&
    index($0, vite_entry) &&
    index($0, "--host " host) &&
    index($0, "--port " port) {
      print $1
    }
  ' | awk '!seen[$0]++'
}

ensure_backend_ready() {
  [ -x "$ROOT/backend/.venv/bin/python3" ] || fail "backend venv python not found: $ROOT/backend/.venv/bin/python3"
}

ensure_frontend_ready() {
  [ -x "$FRONTEND_VITE_ENTRY" ] || fail "frontend vite entry not found: run npm install in $ROOT/frontend"
  command -v node >/dev/null 2>&1 || fail "node command not found in PATH"
}

wait_for_http() {
  local url="$1"
  local attempts="${2:-30}"
  local sleep_sec="${3:-1}"
  local i
  for ((i = 1; i <= attempts; i += 1)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$sleep_sec"
  done
  return 1
}

stop_pid_gracefully() {
  local pid="$1"
  local name="$2"
  if ! is_pid_running "$pid"; then
    return 0
  fi
  kill "$pid" >/dev/null 2>&1 || true
  local i
  for ((i = 1; i <= 20; i += 1)); do
    if ! is_pid_running "$pid"; then
      return 0
    fi
    sleep 0.5
  done
  echo "force killing $name pid=$pid"
  kill -9 "$pid" >/dev/null 2>&1 || true
}
