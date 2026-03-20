#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="$ROOT/backend"
VENV_PY="$BACKEND_DIR/.venv/bin/python"
RUN_DIR="$ROOT/runtime/.run"
LOG_DIR="$ROOT/runtime/logs"
PID_FILE="$RUN_DIR/backend.wsl.pid"
LOG_FILE="$LOG_DIR/backend.wsl.log"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
LOG_LEVEL="${LOG_LEVEL:-info}"
MODE="${1:-foreground}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

fail() {
  printf '[FAIL] %s\n' "$*" >&2
  exit 1
}

info() {
  printf '[run] %s\n' "$*"
}

backend_cmd=(
  "$VENV_PY" -m uvicorn app.main:app
  --host "$BACKEND_HOST"
  --port "$BACKEND_PORT"
  --log-level "$LOG_LEVEL"
)

if [ ! -x "$VENV_PY" ]; then
  fail "missing backend venv python: $VENV_PY"
fi

case "$MODE" in
  foreground)
    info "starting backend in foreground"
    info "cwd=$BACKEND_DIR"
    info "listen=http://$BACKEND_HOST:$BACKEND_PORT"
    info "command: cd $BACKEND_DIR && ${backend_cmd[*]}"
    cd "$BACKEND_DIR"
    exec "${backend_cmd[@]}"
    ;;
  background)
    if [ -f "$PID_FILE" ]; then
      old_pid="$(tr -d '[:space:]' < "$PID_FILE" || true)"
      if [ -n "${old_pid:-}" ] && kill -0 "$old_pid" >/dev/null 2>&1; then
        fail "backend already running with pid=$old_pid (pid file: $PID_FILE)"
      fi
      rm -f "$PID_FILE"
    fi

    info "starting backend in background"
    info "cwd=$BACKEND_DIR"
    info "listen=http://$BACKEND_HOST:$BACKEND_PORT"
    info "log=$LOG_FILE"
    (
      cd "$BACKEND_DIR"
      setsid "${backend_cmd[@]}" </dev/null >"$LOG_FILE" 2>&1 &
      echo $! >"$PID_FILE"
    )
    new_pid="$(tr -d '[:space:]' < "$PID_FILE")"
    sleep 1
    if ! kill -0 "$new_pid" >/dev/null 2>&1; then
      tail -n 80 "$LOG_FILE" >&2 || true
      fail "background backend exited immediately; inspect $LOG_FILE"
    fi
    info "pid=$new_pid"
    info "tail logs: tail -f $LOG_FILE"
    ;;
  *)
    cat <<'EOF'
Usage:
  bash scripts/dev/run_backend_wsl.sh foreground
  bash scripts/dev/run_backend_wsl.sh background

Env:
  BACKEND_HOST=127.0.0.1
  BACKEND_PORT=8000
  LOG_LEVEL=info

Fallback when Windows cannot reach WSL localhost:
  BACKEND_HOST=0.0.0.0 bash scripts/dev/run_backend_wsl.sh foreground
EOF
    exit 1
    ;;
esac
