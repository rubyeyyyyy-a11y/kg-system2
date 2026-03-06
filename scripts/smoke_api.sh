#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

SMOKE_SEARCH_Q="${SMOKE_SEARCH_Q:-ca}"
SMOKE_ROOT_VID="${SMOKE_ROOT_VID:-1}"

cleanup_stale_pid_file "$BACKEND_PID_FILE"
cleanup_stale_pid_file "$FRONTEND_PID_FILE"

backend_pid="$(read_pid_file "$BACKEND_PID_FILE" || true)"
frontend_pid="$(read_pid_file "$FRONTEND_PID_FILE" || true)"

[ -n "$backend_pid" ] && is_pid_running "$backend_pid" || fail "backend is not running; start with bash scripts/start_stack.sh"
[ -n "$frontend_pid" ] && is_pid_running "$frontend_pid" || fail "frontend is not running; start with bash scripts/start_stack.sh"

backend_base="$(backend_url)"
frontend_base="$(frontend_url)"

echo "[smoke] frontend entry: $frontend_base"
curl -fsSI --max-time 5 "$frontend_base" >/dev/null

echo "[smoke] GET /api/health"
health_json="$(curl -fsS --max-time 10 "$backend_base/api/health")"
printf '%s' "$health_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert data.get("ok") is True; assert isinstance(data.get("hosts_rows"), int); print(f"ok hosts_rows={data['\''hosts_rows'\'']}")'

echo "[smoke] GET /api/entity_types"
entity_types_json="$(curl -fsS --max-time 15 "$backend_base/api/entity_types")"
printf '%s' "$entity_types_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data, list); print(f"ok items={len(data)}")'

echo "[smoke] GET /api/relation_types?limit=20&offset=0"
relation_types_json="$(curl -fsS --max-time 15 "$backend_base/api/relation_types?limit=20&offset=0")"
printf '%s' "$relation_types_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("items"), list); assert data.get("limit")==20; assert data.get("offset")==0; print(f"ok items={len(data['\''items'\''])} matched_total={data.get('\''matched_total'\'', 0)} has_more={bool(data.get('\''has_more'\''))}")'

echo "[smoke] POST /api/search"
search_payload="$(SMOKE_SEARCH_Q="$SMOKE_SEARCH_Q" python3 -c 'import json,os; print(json.dumps({"q": os.environ["SMOKE_SEARCH_Q"], "search_in_name": True, "search_in_description": False, "include_edges": False}))' )"
search_json="$(curl -fsS --max-time 20 -H 'Content-Type: application/json' -d "$search_payload" "$backend_base/api/search")"
printf '%s' "$search_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("nodes"), list); assert isinstance(data.get("edges"), list); assert isinstance(data.get("total_candidates"), int); print(f"ok nodes={len(data['\''nodes'\''])} edges={len(data['\''edges'\''])} total_candidates={data['\''total_candidates'\'']}")'

echo "[smoke] POST /api/subgraph"
subgraph_payload="$(SMOKE_ROOT_VID="$SMOKE_ROOT_VID" python3 -c 'import json,os; print(json.dumps({"root_vid": int(os.environ["SMOKE_ROOT_VID"]), "hop": 1, "max_nodes": 120, "max_edges": 4000, "relations": []}))' )"
subgraph_json="$(curl -fsS --max-time 30 -H 'Content-Type: application/json' -d "$subgraph_payload" "$backend_base/api/subgraph")"
printf '%s' "$subgraph_json" | SMOKE_ROOT_VID="$SMOKE_ROOT_VID" python3 -c 'import json,os,sys; data=json.load(sys.stdin); root_vid=int(os.environ["SMOKE_ROOT_VID"]); assert int(data.get("root_vid"))==root_vid; assert isinstance(data.get("nodes"), list); assert isinstance(data.get("edges"), list); stats=data.get("stats") or {}; assert isinstance(stats.get("node_count"), int); assert isinstance(stats.get("edge_count"), int); assert "truncated" in stats; print(f"ok root_vid={root_vid} nodes={len(data['\''nodes'\''])} edges={len(data['\''edges'\''])} truncated={stats.get('\''truncated'\'')}")'

echo "[smoke] completed"
