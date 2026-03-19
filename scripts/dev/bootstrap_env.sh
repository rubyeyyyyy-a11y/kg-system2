#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

echo "[env] root=$ROOT"

command -v python3 >/dev/null 2>&1 || {
  echo "[env] python3 not found" >&2
  exit 1
}
command -v node >/dev/null 2>&1 || {
  echo "[env] node not found" >&2
  exit 1
}
command -v npm >/dev/null 2>&1 || {
  echo "[env] npm not found" >&2
  exit 1
}

cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
  echo "[env] creating backend/.venv"
  python3 -m venv .venv
fi
echo "[env] installing backend dependencies"
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

cd "$ROOT/frontend"
if [ -f "package-lock.json" ]; then
  echo "[env] installing frontend dependencies with npm ci"
  npm ci
else
  echo "[env] installing frontend dependencies with npm install"
  npm install
fi

echo "[env] done"
echo "[env] backend python: $ROOT/backend/.venv/bin/python"
echo "[env] frontend node_modules: $ROOT/frontend/node_modules"
