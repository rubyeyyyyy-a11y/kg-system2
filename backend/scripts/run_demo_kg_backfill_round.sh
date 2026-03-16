#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${BACKEND_ROOT}/.." && pwd)"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="${DEMO_KG_BACKFILL_LOG_DIR:-${BACKEND_ROOT}/logs/demo_kg_backfill}"
STATE_FILE="${DEMO_KG_BACKFILL_STATE_FILE:-${BACKEND_ROOT}/state/es_backfill_spaces.state.json}"
SUMMARY_DIR="${DEMO_KG_BACKFILL_SUMMARY_DIR:-${BACKEND_ROOT}/state/demo_kg_backfill_runs}"
LATEST_SUMMARY="${DEMO_KG_BACKFILL_LATEST_SUMMARY:-${BACKEND_ROOT}/state/demo_kg_backfill_summary_latest.json}"
BATCH_SIZE="${DEMO_KG_BACKFILL_BATCH_SIZE:-500}"
MAX_DOCS="${DEMO_KG_BACKFILL_MAX_DOCS:-5000}"
LOG_FILE="${LOG_DIR}/demo_kg_backfill_${TIMESTAMP}.log"
SUMMARY_FILE="${SUMMARY_DIR}/demo_kg_backfill_${TIMESTAMP}.json"

mkdir -p "${LOG_DIR}" "${SUMMARY_DIR}"

cd "${REPO_ROOT}"

echo "[demo_kg_backfill] repo_root=${REPO_ROOT}"
echo "[demo_kg_backfill] log_file=${LOG_FILE}"
echo "[demo_kg_backfill] state_file=${STATE_FILE}"
echo "[demo_kg_backfill] summary_file=${SUMMARY_FILE}"
echo "[demo_kg_backfill] latest_summary=${LATEST_SUMMARY}"
echo "[demo_kg_backfill] batch_size=${BATCH_SIZE}"
echo "[demo_kg_backfill] max_docs=${MAX_DOCS}"

set +e
PYTHONPATH=backend backend/.venv/bin/python backend/scripts/backfill_es_spaces.py \
  --space demo_kg \
  --resume \
  --verify \
  --batch-size "${BATCH_SIZE}" \
  --max "${MAX_DOCS}" \
  --state-file "${STATE_FILE}" \
  --summary-json "${SUMMARY_FILE}" \
  "$@" 2>&1 | tee "${LOG_FILE}"
cmd_status=${PIPESTATUS[0]}
set -e

if [[ -f "${SUMMARY_FILE}" ]]; then
  cp "${SUMMARY_FILE}" "${LATEST_SUMMARY}"
fi

echo "[demo_kg_backfill] exit_code=${cmd_status}"
echo "[demo_kg_backfill] log_file=${LOG_FILE}"
echo "[demo_kg_backfill] summary_file=${SUMMARY_FILE}"
echo "[demo_kg_backfill] latest_summary=${LATEST_SUMMARY}"
echo "[demo_kg_backfill] inspect=PYTHONPATH=backend backend/.venv/bin/python backend/scripts/check_demo_kg_backfill.py"

exit "${cmd_status}"
