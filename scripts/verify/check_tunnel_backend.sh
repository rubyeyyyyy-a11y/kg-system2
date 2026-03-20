#!/usr/bin/env bash
set -euo pipefail

TUNNEL_BASE_URL="${TUNNEL_BASE_URL:-}"
SPACE_NAME="${SPACE_NAME:-}"
SEARCH_PAYLOAD='{"q":"ca","search_in_name":true,"search_in_description":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}'

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

[ -n "$TUNNEL_BASE_URL" ] || fail "set TUNNEL_BASE_URL, for example https://example.trycloudflare.com"
BASE_URL="$(normalize_base_url "$TUNNEL_BASE_URL")"

printf '[info] tunnel=%s\n' "$BASE_URL"

printf '\n[STEP] tunnel /api/health\n'
health_json="$(curl -fsS --max-time 20 "${request_headers[@]}" "$BASE_URL/api/health")" || fail "tunnel /api/health failed"
printf '%s' "$health_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("ok") is True; print(f"ok={data['\''ok'\'']} hosts_rows={data['\''hosts_rows'\'']}")'
ok "tunnel /api/health"

printf '\n[STEP] tunnel /api/import/schema\n'
schema_json="$(curl -fsS --max-time 20 "${request_headers[@]}" "$BASE_URL/api/import/schema")" || fail "tunnel /api/import/schema failed"
printf '%s' "$schema_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("tags"), list); assert isinstance(data.get("edge_types"), list); print(f"tags={len(data['\''tags'\''])} edge_types={len(data['\''edge_types'\''])}")'
ok "tunnel /api/import/schema"

printf '\n[STEP] tunnel /api/search\n'
search_json="$(curl -fsS --max-time 30 "${request_headers[@]}" -H 'Content-Type: application/json' --data-raw "$SEARCH_PAYLOAD" "$BASE_URL/api/search")" || fail "tunnel /api/search failed"
printf '%s' "$search_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("nodes"), list); assert isinstance(data.get("edges"), list); assert isinstance(data.get("total_candidates"), int); print(f"nodes={len(data['\''nodes'\''])} edges={len(data['\''edges'\''])} total_candidates={data['\''total_candidates'\'']}")'
ok "tunnel /api/search"

printf '\n[RESULT] tunnel backend verification completed successfully\n'
