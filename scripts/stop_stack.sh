#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cleanup_stale_pid_file "$BACKEND_PID_FILE"
cleanup_stale_pid_file "$FRONTEND_PID_FILE"

stopped_any=0

stop_named_processes() {
  local pid_file="$1"
  local name="$2"
  shift 2
  local pids=()
  local pid

  pid="$(read_pid_file "$pid_file" || true)"
  if [ -n "$pid" ]; then
    pids+=("$pid")
  fi

  while IFS= read -r pid; do
    [ -n "$pid" ] || continue
    pids+=("$pid")
  done < <("$@")

  if [ "${#pids[@]}" -eq 0 ]; then
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

  rm -f "$pid_file"
  echo "$name: stopped"
}

stop_named_processes "$FRONTEND_PID_FILE" "frontend" find_frontend_pids
stop_named_processes "$BACKEND_PID_FILE" "backend" find_backend_pids

if [ "$stopped_any" -eq 0 ]; then
  exit 0
fi
