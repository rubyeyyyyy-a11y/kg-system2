#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/.env}"
BACKEND_DIR="$ROOT/backend"
VENV_PY="$BACKEND_DIR/.venv/bin/python"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
SMOKE_SEARCH_Q="${SMOKE_SEARCH_Q:-abc}"

ok() {
  printf '[OK] %s\n' "$*"
}

fail() {
  local category="$1"
  shift
  printf '[FAIL] %s | category=%s\n' "$*" "$category" >&2
  exit 1
}

step() {
  printf '\n[STEP] %s\n' "$*"
}

get_env() {
  local key="$1"
  awk -F= -v key="$key" '$1 == key { print substr($0, length(key) + 2); exit }' "$ENV_FILE"
}

detect_windows_host_ip() {
  local route_ip
  route_ip="$(ip route show default 2>/dev/null | awk '/default/ { print $3; exit }')"
  if [ -n "$route_ip" ]; then
    printf '%s\n' "$route_ip"
    return 0
  fi
  awk '/^nameserver / { print $2; exit }' /etc/resolv.conf
}

curl_json_check() {
  local method="$1"
  local url="$2"
  local body="${3:-}"
  local output
  if [ "$method" = "GET" ]; then
    output="$(curl -fsS --max-time 20 -H 'Connection: close' "$url")" || return 1
  else
    output="$(curl -fsS --max-time 20 -H 'Connection: close' -H 'Content-Type: application/json' -d "$body" "$url")" || return 1
  fi
  printf '%s' "$output"
}

[ -f "$ENV_FILE" ] || fail "backend config problem" "missing env file: $ENV_FILE"
[ -x "$VENV_PY" ] || fail "dependency install problem" "missing backend venv python: $VENV_PY"

step "load local configuration"
NEBULA_HOST="$(get_env NEBULA_HOST)"
NEBULA_PORT="$(get_env NEBULA_PORT)"
NEBULA_SPACE="$(get_env NEBULA_SPACE)"
ES_URL="$(get_env ES_URL)"
ES_ENABLED="$(get_env ES_ENABLED)"
WINDOWS_HOST_IP="$(detect_windows_host_ip)"
printf '[info] NEBULA_HOST=%s\n' "${NEBULA_HOST:-}"
printf '[info] NEBULA_PORT=%s\n' "${NEBULA_PORT:-}"
printf '[info] NEBULA_SPACE=%s\n' "${NEBULA_SPACE:-}"
printf '[info] ES_ENABLED=%s\n' "${ES_ENABLED:-}"
printf '[info] ES_URL=%s\n' "${ES_URL:-}"
printf '[info] WINDOWS_HOST_IP=%s\n' "${WINDOWS_HOST_IP:-unknown}"

step "verify backend import"
(
  cd "$BACKEND_DIR"
  "$VENV_PY" -c "import app.main; print('IMPORT_APP_MAIN_OK')"
) >/tmp/check_local_backend_import.out 2>&1 \
  && { cat /tmp/check_local_backend_import.out; ok "backend import app.main"; } \
  || { cat /tmp/check_local_backend_import.out >&2; fail "dependency install problem" "import app.main failed"; }

step "verify Nebula with repository module"
(
  cd "$BACKEND_DIR"
  "$VENV_PY" - <<'PY'
from app.db.nebula import NEBULA_HOST, NEBULA_PORT, NEBULA_SPACE, execute_ngql
print(f"config host={NEBULA_HOST} port={NEBULA_PORT} space={NEBULA_SPACE}")
result = execute_ngql("SHOW HOSTS;", use_space=False)
if not result.is_succeeded():
    raise SystemExit(f"SHOW HOSTS failed: {result.error_msg()}")
print(f"hosts_rows={len(result.rows())}")
PY
) >/tmp/check_local_backend_nebula.out 2>&1 \
  && { cat /tmp/check_local_backend_nebula.out; ok "Nebula reachable via backend module"; } \
  || {
    cat /tmp/check_local_backend_nebula.out >&2
    fail "WSL->Windows network problem" "Nebula check failed from WSL; inspect $NEBULA_HOST:$NEBULA_PORT and Docker Desktop port publishing"
  }

step "verify ES with curl"
[ -n "${ES_URL:-}" ] || fail "backend config problem" "ES_URL is empty"
curl -fsSI --max-time 10 "$ES_URL" >/tmp/check_local_backend_es.headers 2>/tmp/check_local_backend_es.err \
  && {
    python3 - <<'PY' /tmp/check_local_backend_es.headers
import sys

headers = {}
for line in open(sys.argv[1], "r", encoding="utf-8"):
    line = line.strip()
    if not line or ":" not in line:
        continue
    key, value = line.split(":", 1)
    headers[key.strip().lower()] = value.strip()

print(
    "status=200"
    f" content_length={headers.get('content-length', 'unknown')}"
    f" content_type={headers.get('content-type', 'unknown')}"
    f" x_elastic_product={headers.get('x-elastic-product', 'missing')}"
)
PY
    ok "ES reachable via curl"
  } || {
    cat /tmp/check_local_backend_es.err >&2 || true
    fail "WSL->Windows network problem" "ES check failed from WSL; inspect $ES_URL and Docker Desktop port publishing"
  }

step "smoke /api/health"
health_json="$(curl_json_check GET "$BASE_URL/api/health")" \
  || fail "backend config problem" "GET $BASE_URL/api/health failed"
printf '%s' "$health_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("ok") is True; assert isinstance(data.get("hosts_rows"), int); print(f"ok={data['\''ok'\'']} hosts_rows={data['\''hosts_rows'\'']}")' \
  && ok "/api/health"

step "smoke /api/spaces/current"
space_json="$(curl_json_check GET "$BASE_URL/api/spaces/current")" \
  || fail "backend config problem" "GET $BASE_URL/api/spaces/current failed"
printf '%s' "$space_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("space_name"); assert data.get("graph_status") in {"ready","unavailable"}; assert data.get("search_status") in {"full","partial","empty","failed","unavailable"}; print(f"space_name={data['\''space_name'\'']} graph_status={data['\''graph_status'\'']} search_status={data['\''search_status'\'']}")' \
  && ok "/api/spaces/current"

step "smoke /api/import/schema"
schema_json="$(curl_json_check GET "$BASE_URL/api/import/schema")" \
  || fail "backend config problem" "GET $BASE_URL/api/import/schema failed"
printf '%s' "$schema_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("tags"), list); assert isinstance(data.get("edge_types"), list); print(f"tags={len(data['\''tags'\''])} edge_types={len(data['\''edge_types'\''])}")' \
  && ok "/api/import/schema"

step "smoke /api/search"
search_payload="$(SMOKE_SEARCH_Q="$SMOKE_SEARCH_Q" python3 - <<'PY'
import json, os
print(json.dumps({
    "q": os.environ["SMOKE_SEARCH_Q"],
    "search_in_name": True,
    "search_in_description": False,
    "search_in_type": False,
    "search_in_raw_id": False,
    "include_edges": False
}))
PY
)"
search_json="$(curl_json_check POST "$BASE_URL/api/search" "$search_payload")" \
  || fail "backend config problem" "POST $BASE_URL/api/search failed"
printf '%s' "$search_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("nodes"), list); assert isinstance(data.get("edges"), list); assert isinstance(data.get("total_candidates"), int); meta=data.get("space_meta") or {}; print(f"nodes={len(data['\''nodes'\''])} edges={len(data['\''edges'\''])} total_candidates={data['\''total_candidates'\'']} space_name={meta.get('\''space_name'\'', '\'''\'' )}")' \
  && ok "/api/search"

printf '\n[RESULT] local backend verification completed successfully\n'
