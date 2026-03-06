#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

declare -A backend_state=()
declare -A frontend_state=()

collect_service_state "$BACKEND_PID_FILE" "$BACKEND_PORT" "$(backend_url)/api/health" find_backend_pids backend_state
collect_service_state "$FRONTEND_PID_FILE" "$FRONTEND_PORT" "$(frontend_url)" find_frontend_pids frontend_state

require_service_http "backend" backend_state
require_service_http "frontend" frontend_state

backend_health="$(curl -fsS --max-time 5 "$(backend_url)/api/health")" || fail "backend health check failed: $(backend_url)/api/health"
frontend_headers="$(curl -fsSI --max-time 5 "$(frontend_url)")" || fail "frontend entry check failed: $(frontend_url)"

printf 'backend: %s health=%s\n' "$(service_state_summary backend_state)" "$backend_health"
printf 'frontend: %s\n' "$(service_state_summary frontend_state)"
if ! printf '%s\n' "$frontend_headers" | grep -iE '^(HTTP/|content-type:)' ; then
  echo "frontend: headers unavailable"
fi
