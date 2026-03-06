#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

cleanup_stale_pid_file "$BACKEND_PID_FILE"
cleanup_stale_pid_file "$FRONTEND_PID_FILE"

status=0

backend_pid="$(read_pid_file "$BACKEND_PID_FILE" || true)"
frontend_pid="$(read_pid_file "$FRONTEND_PID_FILE" || true)"

if [ -n "$backend_pid" ] && is_pid_running "$backend_pid"; then
  if curl -fsS "$(backend_url)/api/health" >/dev/null 2>&1; then
    echo "backend: running pid=$backend_pid url=$(backend_url) health=ok log=$BACKEND_LOG_FILE"
  else
    echo "backend: running pid=$backend_pid url=$(backend_url) health=fail log=$BACKEND_LOG_FILE"
    status=1
  fi
else
  fallback_backend="$(find_backend_pids | tr '\n' ' ' | xargs -r echo || true)"
  if [ -n "$fallback_backend" ]; then
    echo "backend: running_without_pidfile pids=$fallback_backend url=$(backend_url) log=$BACKEND_LOG_FILE"
    status=1
  else
    echo "backend: stopped"
    status=1
  fi
fi

if [ -n "$frontend_pid" ] && is_pid_running "$frontend_pid"; then
  if curl -fsS "$(frontend_url)" >/dev/null 2>&1; then
    echo "frontend: running pid=$frontend_pid url=$(frontend_url) health=ok log=$FRONTEND_LOG_FILE"
  else
    echo "frontend: running pid=$frontend_pid url=$(frontend_url) health=fail log=$FRONTEND_LOG_FILE"
    status=1
  fi
else
  fallback_frontend="$(find_frontend_pids | tr '\n' ' ' | xargs -r echo || true)"
  if [ -n "$fallback_frontend" ]; then
    echo "frontend: running_without_pidfile pids=$fallback_frontend url=$(frontend_url) log=$FRONTEND_LOG_FILE"
    status=1
  else
    echo "frontend: stopped"
    status=1
  fi
fi

exit "$status"
