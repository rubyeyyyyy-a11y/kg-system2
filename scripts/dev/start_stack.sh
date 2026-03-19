#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cleanup_stale_pid_file "$BACKEND_PID_FILE"
cleanup_stale_pid_file "$FRONTEND_PID_FILE"
ensure_backend_ready
ensure_frontend_ready

BACKEND_STARTING_PID_FILE="$RUN_DIR/backend.pid.starting"
FRONTEND_STARTING_PID_FILE="$RUN_DIR/frontend.pid.starting"

cleanup_starting_pid_files() {
  rm -f "$BACKEND_STARTING_PID_FILE" "$FRONTEND_STARTING_PID_FILE"
}

trap cleanup_starting_pid_files EXIT

start_detached() {
  local pid_file="$1"
  local log_file="$2"
  local workdir="$3"
  shift 3

  if command -v setsid >/dev/null 2>&1; then
    setsid bash -lc '
      pid_file="$1"
      workdir="$2"
      shift 2
      cd "$workdir"
      echo $$ > "$pid_file"
      exec "$@"
    ' bash "$pid_file" "$workdir" "$@" >>"$log_file" 2>&1 < /dev/null &
  else
    nohup bash -lc '
      pid_file="$1"
      workdir="$2"
      shift 2
      cd "$workdir"
      echo $$ > "$pid_file"
      exec "$@"
    ' bash "$pid_file" "$workdir" "$@" >>"$log_file" 2>&1 < /dev/null &
  fi
}

wait_for_pid_file() {
  local pid_file="$1"
  local attempts="${2:-20}"
  local i
  for ((i = 1; i <= attempts; i += 1)); do
    if read_pid_file "$pid_file" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

existing_backend_pids="$(find_backend_pids | tr '\n' ' ' | xargs -r echo || true)"
existing_frontend_pids="$(find_frontend_pids | tr '\n' ' ' | xargs -r echo || true)"

if [ -n "$existing_backend_pids" ] || [ -n "$existing_frontend_pids" ] || [ -f "$BACKEND_PID_FILE" ] || [ -f "$FRONTEND_PID_FILE" ]; then
  bash "$ROOT/scripts/dev/stop_stack.sh" >/dev/null 2>&1 || true
fi

cleanup_starting_pid_files
: > "$BACKEND_LOG_FILE"
: > "$FRONTEND_LOG_FILE"

start_detached "$BACKEND_STARTING_PID_FILE" "$BACKEND_LOG_FILE" "$ROOT/backend" \
  .venv/bin/python3 -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT" --log-level info

wait_for_pid_file "$BACKEND_STARTING_PID_FILE" || fail "backend pid file was not created: $BACKEND_STARTING_PID_FILE"
backend_pid="$(read_pid_file "$BACKEND_STARTING_PID_FILE" || true)"
if [ -z "$backend_pid" ] || ! is_pid_running "$backend_pid"; then
  rm -f "$BACKEND_STARTING_PID_FILE" "$BACKEND_PID_FILE"
  fail "backend failed to start; see $BACKEND_LOG_FILE"
fi

if ! wait_for_pid_service_ready "$backend_pid" "$BACKEND_PORT" "$(backend_url)/api/health" 30 1; then
  tail -n 40 "$BACKEND_LOG_FILE" || true
  rm -f "$BACKEND_STARTING_PID_FILE" "$BACKEND_PID_FILE"
  bash "$ROOT/scripts/dev/stop_stack.sh" >/dev/null 2>&1 || true
  fail "backend health check failed: $(backend_url)/api/health"
fi
mv "$BACKEND_STARTING_PID_FILE" "$BACKEND_PID_FILE"

start_detached "$FRONTEND_STARTING_PID_FILE" "$FRONTEND_LOG_FILE" "$ROOT/frontend" \
  node "$FRONTEND_VITE_ENTRY" --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort

wait_for_pid_file "$FRONTEND_STARTING_PID_FILE" || fail "frontend pid file was not created: $FRONTEND_STARTING_PID_FILE"
frontend_pid="$(read_pid_file "$FRONTEND_STARTING_PID_FILE" || true)"
if [ -z "$frontend_pid" ] || ! is_pid_running "$frontend_pid"; then
  tail -n 40 "$FRONTEND_LOG_FILE" || true
  rm -f "$FRONTEND_STARTING_PID_FILE" "$FRONTEND_PID_FILE"
  bash "$ROOT/scripts/dev/stop_stack.sh" >/dev/null 2>&1 || true
  fail "frontend failed to start; see $FRONTEND_LOG_FILE"
fi

if ! wait_for_pid_service_ready "$frontend_pid" "$FRONTEND_PORT" "$(frontend_url)" 30 1; then
  tail -n 40 "$FRONTEND_LOG_FILE" || true
  rm -f "$FRONTEND_STARTING_PID_FILE" "$FRONTEND_PID_FILE"
  bash "$ROOT/scripts/dev/stop_stack.sh" >/dev/null 2>&1 || true
  fail "frontend health check failed: $(frontend_url)"
fi
mv "$FRONTEND_STARTING_PID_FILE" "$FRONTEND_PID_FILE"

echo "backend: pid=$backend_pid url=$(backend_url) log=$BACKEND_LOG_FILE"
echo "frontend: pid=$frontend_pid url=$(frontend_url) log=$FRONTEND_LOG_FILE"
