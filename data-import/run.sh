#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$ROOT_DIR/scripts"
CONFIGS_DIR="$ROOT_DIR/configs"
SCHEMA_FILE="$ROOT_DIR/schema/00_schema.ngql"
STATE_DIR="$ROOT_DIR/state"
LOG_DIR="$ROOT_DIR/logs"
OUT_DIR="$ROOT_DIR/out"

mkdir -p "$STATE_DIR" "$LOG_DIR" "$OUT_DIR" "$OUT_DIR/vertices_shards" "$OUT_DIR/edges_shards" "$OUT_DIR/tmp"

GRAPH_HOST="${GRAPH_HOST:-127.0.0.1}"
GRAPH_PORT="${GRAPH_PORT:-9669}"
GRAPH_USER="${GRAPH_USER:-root}"
GRAPH_PASSWORD="${GRAPH_PASSWORD:-nebula}"
SPACE="${SPACE:-demo_kg}"
IMPORT_CONCURRENCY="${IMPORT_CONCURRENCY:-8}"
SHARD_SIZE="${SHARD_SIZE:-2000000}"
VERTICES_INPUT="${VERTICES_INPUT:-/home/ray/data/kg_demo/unified_entities_with_synonyms.csv}"
EDGES_ROOT="${EDGES_ROOT:-/home/ray/data/kg_demo/edges}"

log() {
  printf '[run] %s\n' "$*"
}

fail() {
  printf '[run][ERROR] %s\n' "$*" >&2
  exit 1
}

step_done() {
  [ -f "$STATE_DIR/$1.ok" ]
}

mark_done() {
  : > "$STATE_DIR/$1.ok"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "command not found: $1"
}

detect_importer_bin() {
  if [ -n "${IMPORTER_BIN:-}" ] && [ -x "${IMPORTER_BIN}" ]; then
    return 0
  fi
  if command -v nebula-importer >/dev/null 2>&1; then
    IMPORTER_BIN="$(command -v nebula-importer)"
    return 0
  fi
  if [ -x "/home/ray/nebula-importer/bin/nebula-importer" ]; then
    IMPORTER_BIN="/home/ray/nebula-importer/bin/nebula-importer"
    return 0
  fi
  if [ -x "/home/ray/nebula-importer/nebula-importer" ]; then
    IMPORTER_BIN="/home/ray/nebula-importer/nebula-importer"
    return 0
  fi
  fail "nebula-importer not found (set IMPORTER_BIN or install nebula-importer)"
}

detect_console_cmd() {
  if [ -n "${NEBULA_CONSOLE_CMD:-}" ]; then
    return 0
  fi
  if command -v nebula-console >/dev/null 2>&1; then
    NEBULA_CONSOLE_CMD="nebula-console"
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^nebula-docker-compose-console-1$'; then
      NEBULA_CONSOLE_CMD="docker exec -i nebula-docker-compose-console-1 nebula-console"
      if [ "${GRAPH_HOST}" = "127.0.0.1" ]; then
        GRAPH_HOST="graphd"
      fi
      return 0
    fi
  fi
  fail "nebula-console not found. Install nebula-console or run with docker console container available."
}

detect_nebula_python() {
  if [ -n "${NEBULA_PYTHON:-}" ] && [ -x "${NEBULA_PYTHON}" ]; then
    return 0
  fi
  if command -v python3 >/dev/null 2>&1; then
    if python3 - <<'PY' >/dev/null 2>&1
import nebula3
print("ok")
PY
    then
      NEBULA_PYTHON="$(command -v python3)"
      return 0
    fi
  fi
  if [ -x "$ROOT_DIR/../backend/.venv/bin/python" ]; then
    if "$ROOT_DIR/../backend/.venv/bin/python" - <<'PY' >/dev/null 2>&1
import nebula3
print("ok")
PY
    then
      NEBULA_PYTHON="$ROOT_DIR/../backend/.venv/bin/python"
      return 0
    fi
  fi
  fail "python with nebula3 not found (set NEBULA_PYTHON)"
}

run_ngql() {
  local query="$1"
  detect_console_cmd
  # shellcheck disable=SC2086
  $NEBULA_CONSOLE_CMD -addr "$GRAPH_HOST" -port "$GRAPH_PORT" -u "$GRAPH_USER" -p "$GRAPH_PASSWORD" -e "$query" < /dev/null
}

run_ngql_checked() {
  local query="$1"
  local output
  output="$(run_ngql "$query" 2>&1)" || {
    printf '%s\n' "$output" >&2
    return 1
  }
  printf '%s\n' "$output"
  if printf '%s\n' "$output" | grep -q "\\[ERROR"; then
    return 1
  fi
}

apply_schema_file() {
  local line stmt exec_stmt
  stmt=""
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%--*}"
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    stmt="${stmt} ${line}"
    if [[ "$line" == *";" ]]; then
      exec_stmt="$stmt"
      if ! echo "$stmt" | grep -Eq '^[[:space:]]*USE[[:space:]]+'; then
        exec_stmt="USE ${SPACE}; ${stmt}"
      fi
      run_ngql_checked "$exec_stmt" >> "$LOG_DIR/step2_schema_apply.log" 2>&1 || return 1
      stmt=""
    fi
  done < "$SCHEMA_FILE"
  if [ -n "$stmt" ]; then
    exec_stmt="$stmt"
    if ! echo "$stmt" | grep -Eq '^[[:space:]]*USE[[:space:]]+'; then
      exec_stmt="USE ${SPACE}; ${stmt}"
    fi
    run_ngql_checked "$exec_stmt" >> "$LOG_DIR/step2_schema_apply.log" 2>&1
  fi
}

render_config() {
  local template="$1"
  local output="$2"
  local data_glob="$3"
  local fail_path="$4"
  local log_path="$5"

  sed \
    -e "s|__CONCURRENCY__|${IMPORT_CONCURRENCY}|g" \
    -e "s|__LOG_PATH__|${log_path}|g" \
    -e "s|__FAIL_PATH__|${fail_path}|g" \
    -e "s|__VERTICES_GLOB__|${data_glob}|g" \
    -e "s|__EDGES_GLOB__|${data_glob}|g" \
    "$template" > "$output"
}

if ! step_done env_checked; then
  log "Step 1/8 env_check"
  "$SCRIPTS_DIR/00_env_check.sh" | tee "$LOG_DIR/step1_env_check.log"
  mark_done env_checked
else
  log "Step 1/8 env_check skipped (state/env_checked.ok exists)"
fi

if ! step_done space_reset; then
  log "Step 2/8 reset space + schema"
  echo "WARNING: This will clear all Entity/REL2 data in space '${SPACE}'."
  echo "If you proceed, existing imported data in ${SPACE} will be removed."
  read -r -p "Type YES to continue: " confirm_yes
  [ "$confirm_yes" = "YES" ] || fail "aborted by user (expected YES)"

  read -r -p "Type DROP to allow DROP SPACE ${SPACE}: " confirm_drop
  [ "$confirm_drop" = "DROP" ] || fail "aborted by user (DROP SPACE not authorized)"

  run_ngql_checked "DROP SPACE IF EXISTS ${SPACE};" | tee "$LOG_DIR/step2_drop_space.log"
  run_ngql_checked "CREATE SPACE IF NOT EXISTS ${SPACE}(partition_num=10, replica_factor=1, vid_type=INT64);" | tee "$LOG_DIR/step2_create_space.log"
  log "Waiting for meta propagation..."
  sleep 8

  : > "$LOG_DIR/step2_schema_apply.log"
  if ! apply_schema_file; then
    cat "$LOG_DIR/step2_schema_apply.log" >&2
    fail "schema apply failed"
  fi

  run_ngql_checked "USE ${SPACE}; SHOW TAGS; SHOW EDGES; DESCRIBE TAG Entity; DESCRIBE EDGE REL2; DESCRIBE TAG EntityTypeStat; DESCRIBE TAG RelationTypeStat;" \
    | tee "$LOG_DIR/step2_schema_verify.log"

  mark_done space_reset
else
  log "Step 2/8 reset space skipped (state/space_reset.ok exists)"
fi

if ! step_done vertices_prepared; then
  log "Step 3/8 prepare_vertices"
  rm -f "$OUT_DIR/vertices_shards"/Entity_*.csv
  python3 "$SCRIPTS_DIR/01_prepare_vertices.py" \
    --input "$VERTICES_INPUT" \
    --output-dir "$OUT_DIR/vertices_shards" \
    --shard-size "$SHARD_SIZE" \
    | tee "$LOG_DIR/step3_prepare_vertices.log"
  mark_done vertices_prepared
else
  log "Step 3/8 prepare_vertices skipped (state/vertices_prepared.ok exists)"
fi

if ! step_done vertices_imported; then
  detect_importer_bin
  log "Step 4/8 import_vertices"

  RENDERED="$LOG_DIR/import_vertices.rendered.yaml"
  mkdir -p "$LOG_DIR/failed_vertices"
  render_config "$CONFIGS_DIR/import_vertices.yaml" "$RENDERED" "$OUT_DIR/vertices_shards/Entity_*.csv" "$LOG_DIR/failed_vertices" "$LOG_DIR/nebula-importer-vertices.log"

  "$IMPORTER_BIN" --config "$RENDERED" | tee "$LOG_DIR/step4_import_vertices.log"
  mark_done vertices_imported
else
  log "Step 4/8 import_vertices skipped (state/vertices_imported.ok exists)"
fi

if ! step_done edges_prepared; then
  log "Step 5/8 prepare_edges"
  rm -f "$OUT_DIR/edges_shards"/REL2_*.csv
  rm -f "$OUT_DIR/tmp"/edges_part_*.tsv "$OUT_DIR/tmp"/edges_part_*.sorted.tsv
  python3 "$SCRIPTS_DIR/02_prepare_edges.py" \
    --edges-root "$EDGES_ROOT" \
    --tmp-dir "$OUT_DIR/tmp" \
    --output-dir "$OUT_DIR/edges_shards" \
    --shard-size "$SHARD_SIZE" \
    | tee "$LOG_DIR/step5_prepare_edges.log"
  mark_done edges_prepared
else
  log "Step 5/8 prepare_edges skipped (state/edges_prepared.ok exists)"
fi

if ! step_done edges_imported; then
  detect_importer_bin
  log "Step 6/8 import_edges"

  RENDERED="$LOG_DIR/import_edges.rendered.yaml"
  mkdir -p "$LOG_DIR/failed_edges"
  render_config "$CONFIGS_DIR/import_edges.yaml" "$RENDERED" "$OUT_DIR/edges_shards/REL2_*.csv" "$LOG_DIR/failed_edges" "$LOG_DIR/nebula-importer-edges.log"

  "$IMPORTER_BIN" --config "$RENDERED" | tee "$LOG_DIR/step6_import_edges.log"
  mark_done edges_imported
else
  log "Step 6/8 import_edges skipped (state/edges_imported.ok exists)"
fi

if ! step_done metadata_refreshed; then
  log "Step 7/8 refresh_metadata"
  detect_nebula_python
  NEBULA_HOST="$GRAPH_HOST" \
  NEBULA_PORT="$GRAPH_PORT" \
  NEBULA_USER="$GRAPH_USER" \
  NEBULA_PASSWORD="$GRAPH_PASSWORD" \
  NEBULA_SPACE="$SPACE" \
  NEBULA_TIMEOUT_MS="${NEBULA_TIMEOUT_MS:-120000}" \
  EDGE_TYPE="${EDGE_TYPE:-REL2}" \
  "$NEBULA_PYTHON" "$SCRIPTS_DIR/04_refresh_metadata.py" --mode rebuild --source "${METADATA_SOURCE_MODE:-auto}" \
    | tee "$LOG_DIR/step7_refresh_metadata.log"
  mark_done metadata_refreshed
else
  log "Step 7/8 refresh_metadata skipped (state/metadata_refreshed.ok exists)"
fi

if ! step_done verified; then
  log "Step 8/8 verify"
  "$SCRIPTS_DIR/03_verify_after_import.sh" | tee "$LOG_DIR/step8_verify.log"
  "$SCRIPTS_DIR/05_verify_metadata.sh" | tee -a "$LOG_DIR/step8_verify.log"
  mark_done verified
else
  log "Step 8/8 verify skipped (state/verified.ok exists)"
fi

log "All steps completed."
log "To rerun from scratch: rm -f $STATE_DIR/*.ok"
