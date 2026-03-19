#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cleanup_stale_pid_file "$BACKEND_PID_FILE"
cleanup_stale_pid_file "$FRONTEND_PID_FILE"

stopped_any=0
stop_status=0

print_stop_residual() {
  local name="$1"
  local -n state_ref="$2"

  local matched_display="${state_ref[matched_pids]:-none}"
  local pid_display="${state_ref[pid]:-missing}"

  printf '%s: stop_incomplete status=%s pid=%s pid_running=%s matched_pids=%s port=%s:%s http=%s url=%s' \
    "$name" \
    "${state_ref[status]}" \
    "$pid_display" \
    "${state_ref[pid_running]}" \
    "$matched_display" \
    "${state_ref[port]}" \
    "$([ "${state_ref[port_listening]}" -eq 1 ] && printf 'listening' || printf 'closed')" \
    "$([ "${state_ref[http_reachable]}" -eq 1 ] && printf 'ok' || printf 'fail')" \
    "${state_ref[url]}"

  if [ -n "${state_ref[detail]}" ]; then
    printf ' detail=%s' "${state_ref[detail]}"
  fi
  printf '\n'
}

stop_named_processes() {
  local pid_file="$1"
  local name="$2"
  local port="$3"
  local url="$4"
  local pid_finder="$5"
  shift 5
  local pids=()
  local pid

  pid="$(read_pid_file "$pid_file" || true)"
  if [ -n "$pid" ]; then
    pids+=("$pid")
  fi

  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    pids+=("$pid")
  done < <("$pid_finder")

  local -A initial_state=()
  collect_service_state "$pid_file" "$port" "$url" "$pid_finder" initial_state

  if [ "${#pids[@]}" -eq 0 ]; then
    if service_has_runtime_activity initial_state; then
      if wait_for_service_shutdown "$pid_file" "$port" "$url" "$pid_finder" 20 0.5; then
        rm -f "$pid_file"
        echo "$name: stopped"
      else
        local -A residual_state=()
        collect_service_state "$pid_file" "$port" "$url" "$pid_finder" residual_state
        print_stop_residual "$name" residual_state
        stop_status=1
      fi
      return
    fi
    echo "$name: not running"
    rm -f "$pid_file"
    return
  fi

  local unique_pids
  unique_pids="$(printf '%s\n' "${pids[@]}" | awk '!seen[$0]++')"
  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    stop_pid_gracefully "$pid" "$name"
    stopped_any=1
  done <<< "$unique_pids"

  if ! wait_for_service_shutdown "$pid_file" "$port" "$url" "$pid_finder" 20 0.5; then
    local -A residual_state=()
    collect_service_state "$pid_file" "$port" "$url" "$pid_finder" residual_state
    print_stop_residual "$name" residual_state
    stop_status=1
    return
  fi

  rm -f "$pid_file"
  echo "$name: stopped"
}

stop_named_processes "$FRONTEND_PID_FILE" "frontend" "$FRONTEND_PORT" "$(frontend_url)" find_frontend_pids
stop_named_processes "$BACKEND_PID_FILE" "backend" "$BACKEND_PORT" "$(backend_url)/api/health" find_backend_pids

if [ "$stopped_any" -eq 0 ]; then
  exit "$stop_status"
fi

exit "$stop_status"
