#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
OUT_DIR="$ROOT_DIR/out"
VERT_DIR="$OUT_DIR/vertices_shards"
EDGE_DIR="$OUT_DIR/edges_shards"
mkdir -p "$LOG_DIR"

GRAPH_HOST="${GRAPH_HOST:-127.0.0.1}"
GRAPH_PORT="${GRAPH_PORT:-9669}"
GRAPH_USER="${GRAPH_USER:-root}"
GRAPH_PASSWORD="${GRAPH_PASSWORD:-nebula}"
SPACE="${SPACE:-demo_kg}"

log() {
  printf '[verify] %s\n' "$*"
}

fail() {
  printf '[verify][ERROR] %s\n' "$*" >&2
  exit 1
}

run_ngql() {
  local query="$1"
  # shellcheck disable=SC2086
  $NEBULA_CONSOLE_CMD -addr "$GRAPH_HOST" -port "$GRAPH_PORT" -u "$GRAPH_USER" -p "$GRAPH_PASSWORD" -e "$query" < /dev/null
}

if command -v nebula-console >/dev/null 2>&1; then
  NEBULA_CONSOLE_CMD="nebula-console"
elif command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^nebula-docker-compose-console-1$'; then
  NEBULA_CONSOLE_CMD="docker exec -i nebula-docker-compose-console-1 nebula-console"
  if [ "$GRAPH_HOST" = "127.0.0.1" ]; then
    GRAPH_HOST="graphd"
  fi
else
  fail "nebula-console not found (PATH/container)."
fi

ls "$VERT_DIR"/Entity_*.csv >/dev/null 2>&1 || fail "vertex shards not found under $VERT_DIR"
ls "$EDGE_DIR"/REL2_*.csv >/dev/null 2>&1 || fail "edge shards not found under $EDGE_DIR"

log "SHOW STATS"
run_ngql "USE ${SPACE}; SUBMIT JOB STATS;" >/dev/null 2>&1 || true
sleep 2
run_ngql "USE ${SPACE}; SHOW STATS;" | tee "$LOG_DIR/verify_show_stats.log"

VIDS_CSV="$(python3 - <<'PY' "$VERT_DIR"
import csv, glob, os, sys
vdir = sys.argv[1]
ids = []
for p in sorted(glob.glob(os.path.join(vdir, 'Entity_*.csv'))):
    with open(p, 'r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            vid = str(row.get('ID','')).strip()
            if vid:
                ids.append(vid)
            if len(ids) >= 5:
                break
    if len(ids) >= 5:
        break
print(','.join(ids))
PY
)"

[ -n "$VIDS_CSV" ] || fail "failed to sample Entity IDs"
log "FETCH PROP ON Entity for sampled vids: $VIDS_CSV"
run_ngql "USE ${SPACE}; FETCH PROP ON Entity ${VIDS_CSV} YIELD id(vertex) AS vid, properties(vertex).entity_name AS entity_name, properties(vertex).version AS version;" \
  | tee "$LOG_DIR/verify_vertices.log"

python3 - <<'PY' "$EDGE_DIR" > "$LOG_DIR/verify_edge_samples.txt"
import csv, glob, os, sys
edir = sys.argv[1]
out = []
for p in sorted(glob.glob(os.path.join(edir, 'REL2_*.csv'))):
    with open(p, 'r', encoding='utf-8', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            src = str(row.get('srcVID','')).strip()
            dst = str(row.get('dstVID','')).strip()
            rank = str(row.get('rank','')).strip()
            if src and dst and rank:
                out.append((src, dst, rank))
            if len(out) >= 5:
                break
    if len(out) >= 5:
        break
for src, dst, rank in out:
    print(f"{src},{dst},{rank}")
PY

[ -s "$LOG_DIR/verify_edge_samples.txt" ] || fail "failed to sample REL2 edges"

log "FETCH PROP ON REL2 for sampled src->dst@rank"
while IFS=, read -r src dst rank; do
  [ -n "$src" ] || continue
  run_ngql "USE ${SPACE}; FETCH PROP ON REL2 ${src}->${dst}@${rank} YIELD src(edge) AS src, dst(edge) AS dst, rank(edge) AS rank, properties(edge).relation AS relation, properties(edge).source AS source;" \
    | tee -a "$LOG_DIR/verify_edges.log"
done < "$LOG_DIR/verify_edge_samples.txt"

if awk -F, 'NR>1 && ($3+0)>0 {found=1; exit 0} END{exit(found?0:1)}' "$EDGE_DIR"/REL2_*.csv; then
  log "rank check passed: found rank > 0 in REL2 shards"
else
  fail "rank check failed: all sampled/prepared ranks are 0"
fi

log "verification completed"
