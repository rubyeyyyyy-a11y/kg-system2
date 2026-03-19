#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_DIR="${RUN_DIR:-$ROOT/runtime/.run}"
LOG_DIR="${LOG_DIR:-$ROOT/runtime/logs}"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
FRONTEND_PID_FILE="$RUN_DIR/frontend.pid"
BACKEND_LOG_FILE="$LOG_DIR/backend.log"
FRONTEND_LOG_FILE="$LOG_DIR/frontend.log"
FRONTEND_VITE_ENTRY="$ROOT/frontend/node_modules/vite/bin/vite.js"
FRONTEND_VITE_SHIM="$ROOT/frontend/node_modules/.bin/vite"

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
  ps -eo pid=,comm=,args= | awk -v vite_entry="$FRONTEND_VITE_ENTRY" -v vite_shim="$FRONTEND_VITE_SHIM" -v host="$FRONTEND_HOST" -v port="$FRONTEND_PORT" '
    ($2 == "node" || $2 == "nodejs") &&
    (index($0, vite_entry) || index($0, vite_shim)) &&
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

is_port_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -lHtn "( sport = :$port )" 2>/dev/null | awk 'NF { found=1; exit } END { exit found ? 0 : 1 }'
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi
  return 1
}

list_listening_pids() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp "( sport = :$port )" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | awk '!seen[$0]++'
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk '!seen[$0]++'
    return
  fi
}

is_pid_listening_on_port() {
  local pid="$1"
  local port="$2"
  [ -n "$pid" ] || return 1
  list_listening_pids "$port" | grep -Fxq "$pid"
}

http_ok() {
  local url="$1"
  local max_time="${2:-3}"
  curl -fsS --max-time "$max_time" "$url" >/dev/null 2>&1
}

join_by() {
  local delimiter="$1"
  shift
  local result=""
  local item
  for item in "$@"; do
    [ -n "$item" ] || continue
    if [ -n "$result" ]; then
      result+="$delimiter"
    fi
    result+="$item"
  done
  printf '%s\n' "$result"
}

pid_list_contains() {
  local pid_list="$1"
  local pid="$2"
  [ -n "$pid" ] || return 1
  printf '%s\n' "$pid_list" | tr ' ' '\n' | awk 'NF' | grep -Fxq "$pid"
}

normalize_pid_list() {
  awk 'NF && !seen[$0]++'
}

collect_service_state() {
  local pid_file="$1"
  local port="$2"
  local url="$3"
  local pid_finder="$4"
  local -n out="$5"

  local pid_file_present=0
  local pid=""
  local pid_running=0
  local matched_pids=""
  local process_detected=0
  local port_listening=0
  local http_reachable=0
  local status=""
  local detail=""
  local details=()

  [ -f "$pid_file" ] && pid_file_present=1
  pid="$(read_pid_file "$pid_file" || true)"
  if [ -n "$pid" ] && is_pid_running "$pid"; then
    pid_running=1
  fi

  matched_pids="$($pid_finder | normalize_pid_list | tr '\n' ' ' | xargs -r echo || true)"
  if [ "$pid_running" -eq 1 ] && ! pid_list_contains "$matched_pids" "$pid"; then
    matched_pids="$(printf '%s\n%s\n' "$pid" "$matched_pids" | normalize_pid_list | tr '\n' ' ' | xargs -r echo || true)"
  fi
  [ -n "$matched_pids" ] && process_detected=1

  if is_port_listening "$port"; then
    port_listening=1
  fi

  if http_ok "$url"; then
    http_reachable=1
  fi

  if [ "$pid_file_present" -eq 1 ] && [ -z "$pid" ]; then
    details+=("invalid_pidfile")
  fi
  if [ "$pid_file_present" -eq 1 ] && [ -n "$pid" ] && [ "$pid_running" -eq 0 ]; then
    details+=("stale_pidfile")
  fi
  if [ "$pid_file_present" -eq 0 ] && { [ "$process_detected" -eq 1 ] || [ "$port_listening" -eq 1 ] || [ "$http_reachable" -eq 1 ]; }; then
    details+=("pidfile_missing")
  fi
  if [ "$pid_running" -eq 0 ] && [ -n "$pid" ] && [ "$process_detected" -eq 1 ]; then
    details+=("pidfile_pid_not_owner")
  fi
  if [ "$process_detected" -eq 0 ] && [ "$port_listening" -eq 1 ]; then
    details+=("port_alive_pid_missing")
  fi
  if [ "$process_detected" -eq 0 ] && [ "$http_reachable" -eq 1 ]; then
    details+=("http_alive_pid_missing")
  fi
  if [ "$process_detected" -eq 1 ] && [ "$port_listening" -eq 0 ]; then
    details+=("pid_alive_port_closed")
  fi
  if [ "$port_listening" -eq 1 ] && [ "$http_reachable" -eq 0 ]; then
    details+=("port_alive_http_failed")
  fi

  if [ "$pid_file_present" -eq 1 ] && [ "$pid_running" -eq 0 ] && [ "$process_detected" -eq 0 ] && [ "$port_listening" -eq 0 ] && [ "$http_reachable" -eq 0 ]; then
    status="stale_pidfile"
  elif [ "$process_detected" -eq 0 ] && [ "$port_listening" -eq 0 ] && [ "$http_reachable" -eq 0 ]; then
    status="stopped"
  elif [ "$pid_file_present" -eq 1 ] && [ "$pid_running" -eq 1 ] && [ "$port_listening" -eq 1 ] && [ "$http_reachable" -eq 1 ]; then
    status="running"
  else
    status="degraded"
  fi

  detail="$(join_by "," "${details[@]}")"

  out=(
    [pid_file]="$pid_file"
    [pid_file_present]="$pid_file_present"
    [pid]="$pid"
    [pid_running]="$pid_running"
    [matched_pids]="$matched_pids"
    [process_detected]="$process_detected"
    [port]="$port"
    [port_listening]="$port_listening"
    [url]="$url"
    [http_reachable]="$http_reachable"
    [status]="$status"
    [detail]="$detail"
  )
}

wait_for_pid_service_ready() {
  local pid="$1"
  local port="$2"
  local url="$3"
  local attempts="${4:-30}"
  local sleep_sec="${5:-1}"
  local i

  for ((i = 1; i <= attempts; i += 1)); do
    if ! is_pid_running "$pid"; then
      return 1
    fi
    if is_pid_listening_on_port "$pid" "$port" && http_ok "$url"; then
      return 0
    fi
    sleep "$sleep_sec"
  done
  return 1
}

service_has_runtime_activity() {
  local -n state_ref="$1"
  [ "${state_ref[process_detected]}" -eq 1 ] || [ "${state_ref[port_listening]}" -eq 1 ] || [ "${state_ref[http_reachable]}" -eq 1 ]
}

wait_for_service_shutdown() {
  local pid_file="$1"
  local port="$2"
  local url="$3"
  local pid_finder="$4"
  local attempts="${5:-20}"
  local sleep_sec="${6:-0.5}"
  local i
  local -A state=()

  for ((i = 1; i <= attempts; i += 1)); do
    collect_service_state "$pid_file" "$port" "$url" "$pid_finder" state
    if ! service_has_runtime_activity state; then
      return 0
    fi
    sleep "$sleep_sec"
  done

  return 1
}

service_state_summary() {
  local -n state_ref="$1"
  local pidfile_display="missing"
  local pid_display="${state_ref[pid]:-missing}"
  local matched_display="${state_ref[matched_pids]:-none}"
  local port_display="closed"
  local http_display="fail"
  local summary=""

  if [ "${state_ref[pid_file_present]}" -eq 1 ]; then
    pidfile_display="present"
  fi
  if [ "${state_ref[port_listening]}" -eq 1 ]; then
    port_display="listening"
  fi
  if [ "${state_ref[http_reachable]}" -eq 1 ]; then
    http_display="ok"
  fi

  summary="$(printf 'status=%s pidfile=%s pid=%s pid_running=%s matched_pids=%s port=%s:%s http=%s url=%s' \
    "${state_ref[status]}" \
    "$pidfile_display" \
    "$pid_display" \
    "${state_ref[pid_running]}" \
    "$matched_display" \
    "${state_ref[port]}" \
    "$port_display" \
    "$http_display" \
    "${state_ref[url]}")"

  if [ -n "${state_ref[detail]}" ]; then
    summary="$summary detail=${state_ref[detail]}"
  fi

  printf '%s\n' "$summary"
}

require_service_http() {
  local name="$1"
  local state_var_name="$2"
  local -n service_state_ref="$2"
  local hint="${3:-start with bash scripts/start_stack.sh}"

  if [ "${service_state_ref[http_reachable]}" -eq 1 ]; then
    return 0
  fi

  fail "$name is not reachable; $(service_state_summary "$state_var_name"); $hint"
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
