#!/usr/bin/env bash
set -euo pipefail

VERCEL_BASE_URL="${VERCEL_BASE_URL:-}"
SPACE_NAME="${SPACE_NAME:-}"
SEARCH_PAYLOAD='{"q":"ca","search_in_name":true,"search_in_description":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}'
DISCOVERY_PAYLOAD='{"seed_vids":[1],"allowed_entity_types":[],"allowed_relation_types":[],"max_nodes":80,"max_edges":200,"top_k_per_type":10,"include_candidate_candidate_edges":true,"include_seed_seed_edges":false,"hop":1}'

ok() {
  printf '[OK] %s\n' "$*"
}

fail() {
  printf '[FAIL] %s\n' "$*" >&2
  exit 1
}

normalize_base_url() {
  printf '%s' "${1%/}"
}

request_headers=()
if [ -n "$SPACE_NAME" ]; then
  request_headers+=(-H "X-KG-Space: $SPACE_NAME")
fi

[ -n "$VERCEL_BASE_URL" ] || fail "set VERCEL_BASE_URL, for example https://your-project.vercel.app"
BASE_URL="$(normalize_base_url "$VERCEL_BASE_URL")"

printf '[info] vercel=%s\n' "$BASE_URL"

printf '\n[STEP] vercel /api/health\n'
health_json="$(curl -fsS --max-time 30 "${request_headers[@]}" "$BASE_URL/api/health")" || fail "vercel /api/health failed"
printf '%s' "$health_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("ok") is True; print(f"ok={data['\''ok'\'']} hosts_rows={data['\''hosts_rows'\'']}")'
ok "vercel /api/health"

printf '\n[STEP] vercel /api/import/schema\n'
schema_json="$(curl -fsS --max-time 30 "${request_headers[@]}" "$BASE_URL/api/import/schema")" || fail "vercel /api/import/schema failed"
printf '%s' "$schema_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("tags"), list); assert isinstance(data.get("edge_types"), list); print(f"tags={len(data['\''tags'\''])} edge_types={len(data['\''edge_types'\''])}")'
ok "vercel /api/import/schema"

printf '\n[STEP] vercel /api/search\n'
search_json="$(curl -fsS --max-time 45 "${request_headers[@]}" -H 'Content-Type: application/json' --data-raw "$SEARCH_PAYLOAD" "$BASE_URL/api/search")" || fail "vercel /api/search failed"
printf '%s' "$search_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("nodes"), list); assert isinstance(data.get("edges"), list); assert isinstance(data.get("total_candidates"), int); print(f"nodes={len(data['\''nodes'\''])} edges={len(data['\''edges'\''])} total_candidates={data['\''total_candidates'\'']}")'
ok "vercel /api/search"

printf '\n[STEP] vercel /api/graph/discovery\n'
discovery_json="$(curl -fsS --max-time 60 "${request_headers[@]}" -H 'Content-Type: application/json' --data-raw "$DISCOVERY_PAYLOAD" "$BASE_URL/api/graph/discovery")" || fail "vercel /api/graph/discovery failed"
printf '%s' "$discovery_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("nodes"), list); assert isinstance(data.get("edges"), list); stats=data.get("stats") or {}; assert isinstance(stats.get("seed_count"), int); print(f"nodes={len(data['\''nodes'\''])} edges={len(data['\''edges'\''])} seed_count={stats['\''seed_count'\'']}")'
ok "vercel /api/graph/discovery"

printf '\n[RESULT] vercel rewrite verification completed successfully\n'
