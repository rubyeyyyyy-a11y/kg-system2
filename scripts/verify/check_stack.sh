#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../dev/common.sh"

status=0

print_service_state() {
  local name="$1"
  local log_file="$2"
  local -n state_ref="$3"

  local pid_display="${state_ref[pid]:-missing}"
  local matched_display="${state_ref[matched_pids]:-none}"
  local pidfile_display="missing"
  local port_display="closed"
  local http_display="fail"

  if [ "${state_ref[pid_file_present]}" -eq 1 ]; then
    pidfile_display="present"
  fi
  if [ "${state_ref[port_listening]}" -eq 1 ]; then
    port_display="listening"
  fi
  if [ "${state_ref[http_reachable]}" -eq 1 ]; then
    http_display="ok"
  fi

  printf '%s: status=%s pidfile=%s pid=%s pid_running=%s matched_pids=%s port=%s:%s http=%s url=%s log=%s' \
    "$name" \
    "${state_ref[status]}" \
    "$pidfile_display" \
    "$pid_display" \
    "${state_ref[pid_running]}" \
    "$matched_display" \
    "${state_ref[port]}" \
    "$port_display" \
    "$http_display" \
    "${state_ref[url]}" \
    "$log_file"

  if [ -n "${state_ref[detail]}" ]; then
    printf ' detail=%s' "${state_ref[detail]}"
  fi
  printf '\n'

  if [ "${state_ref[status]}" != "running" ]; then
    status=1
  fi
}

declare -A backend_state=()
declare -A frontend_state=()

collect_service_state "$BACKEND_PID_FILE" "$BACKEND_PORT" "$(backend_url)/api/health" find_backend_pids backend_state
collect_service_state "$FRONTEND_PID_FILE" "$FRONTEND_PORT" "$(frontend_url)" find_frontend_pids frontend_state

print_service_state "backend" "$BACKEND_LOG_FILE" backend_state
print_service_state "frontend" "$FRONTEND_LOG_FILE" frontend_state

exit "$status"
