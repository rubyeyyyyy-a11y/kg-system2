#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

VERTICES_INPUT="${VERTICES_INPUT:-/home/ray/data/kg_demo/unified_entities_with_synonyms.csv}"
EDGES_ROOT="${EDGES_ROOT:-/home/ray/data/kg_demo/edges}"
IMPORTER_VERSION="4.1.0"
IMPORTER_DEB="nebula-importer_${IMPORTER_VERSION}_amd64.deb"
IMPORTER_URL="https://github.com/vesoft-inc/nebula-importer/releases/download/v${IMPORTER_VERSION}/${IMPORTER_DEB}"

log() {
  printf '[env_check] %s\n' "$*"
}

fail() {
  printf '[env_check][ERROR] %s\n' "$*" >&2
  exit 1
}

log "ROOT_DIR=$ROOT_DIR"
log "VERTICES_INPUT=$VERTICES_INPUT"
log "EDGES_ROOT=$EDGES_ROOT"

[ -f "$VERTICES_INPUT" ] || fail "vertices file not found: $VERTICES_INPUT"
[ -d "$EDGES_ROOT" ] || fail "edges root not found: $EDGES_ROOT"

EDGE_COUNT=$(find "$EDGES_ROOT" -type f -name '*_edges.csv' | wc -l | tr -d ' ')
[ "${EDGE_COUNT:-0}" -gt 0 ] || fail "no *_edges.csv found under: $EDGES_ROOT"
log "detected edge csv files: $EDGE_COUNT"

if command -v nebula-importer >/dev/null 2>&1; then
  log "nebula-importer already installed: $(command -v nebula-importer)"
elif [ -x "/home/ray/nebula-importer/bin/nebula-importer" ]; then
  log "using local nebula-importer binary: /home/ray/nebula-importer/bin/nebula-importer"
elif [ -x "/home/ray/nebula-importer/nebula-importer" ]; then
  log "using local nebula-importer binary: /home/ray/nebula-importer/nebula-importer"
else
  log "nebula-importer not found, installing v${IMPORTER_VERSION}"
  TMP_DEB="/tmp/${IMPORTER_DEB}"
  rm -f "$TMP_DEB"

  if ! env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u all_proxy \
      curl -fL "$IMPORTER_URL" -o "$TMP_DEB"; then
    fail "failed to download $IMPORTER_URL (check network access)"
  fi

  if ! sudo dpkg -i "$TMP_DEB"; then
    log "dpkg reported dependency issues, running apt-get -f install"
    sudo apt-get -f install -y
    sudo dpkg -i "$TMP_DEB"
  fi
fi

IMPORTER_BIN="${IMPORTER_BIN:-}"
if [ -z "$IMPORTER_BIN" ]; then
  if command -v nebula-importer >/dev/null 2>&1; then
    IMPORTER_BIN="$(command -v nebula-importer)"
  elif [ -x "/home/ray/nebula-importer/bin/nebula-importer" ]; then
    IMPORTER_BIN="/home/ray/nebula-importer/bin/nebula-importer"
  elif [ -x "/home/ray/nebula-importer/nebula-importer" ]; then
    IMPORTER_BIN="/home/ray/nebula-importer/nebula-importer"
  fi
fi

if [ -z "$IMPORTER_BIN" ]; then
  fail "nebula-importer binary still not found after install attempt"
fi

if ! "$IMPORTER_BIN" --version; then
  fail "nebula-importer install/check failed"
fi

if command -v nebula-console >/dev/null 2>&1; then
  log "nebula-console found"
else
  log "nebula-console not found in PATH. run.sh will stop before schema/import and print install hint"
fi

if command -v python3 >/dev/null 2>&1; then
  python3 --version
else
  fail "python3 not found"
fi

log "environment check passed"
