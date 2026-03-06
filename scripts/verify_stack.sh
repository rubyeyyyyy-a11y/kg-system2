#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cleanup_stale_pid_file "$BACKEND_PID_FILE"
cleanup_stale_pid_file "$FRONTEND_PID_FILE"

backend_pid="$(read_pid_file "$BACKEND_PID_FILE" || true)"
frontend_pid="$(read_pid_file "$FRONTEND_PID_FILE" || true)"

[ -n "$backend_pid" ] && is_pid_running "$backend_pid" || fail "backend is not running; start with bash scripts/start_stack.sh"
[ -n "$frontend_pid" ] && is_pid_running "$frontend_pid" || fail "frontend is not running; start with bash scripts/start_stack.sh"

backend_health="$(curl -fsS --max-time 5 "$(backend_url)/api/health")" || fail "backend health check failed: $(backend_url)/api/health"
frontend_headers="$(curl -fsSI --max-time 5 "$(frontend_url)")" || fail "frontend entry check failed: $(frontend_url)"

echo "backend: pid=$backend_pid url=$(backend_url) health=$backend_health"
printf 'frontend: pid=%s url=%s\n' "$frontend_pid" "$(frontend_url)"
if ! printf '%s\n' "$frontend_headers" | grep -iE '^(HTTP/|content-type:)' ; then
  echo "frontend: headers unavailable"
fi
