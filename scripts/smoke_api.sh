#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

SMOKE_SEARCH_Q="${SMOKE_SEARCH_Q:-ca}"
SMOKE_RAW_ID_Q="${SMOKE_RAW_ID_Q:-MONDO:0000771}"
SMOKE_ROOT_VID="${SMOKE_ROOT_VID:-1}"

declare -A backend_state=()

collect_service_state "$BACKEND_PID_FILE" "$BACKEND_PORT" "$(backend_url)/api/health" find_backend_pids backend_state
require_service_http "backend" backend_state

backend_base="$(backend_url)"

printf '[smoke] backend state: %s\n' "$(service_state_summary backend_state)"

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

echo "[smoke] GET /api/suggest"
suggest_json="$(curl -fsS --max-time 20 --get --data-urlencode "q=$SMOKE_SEARCH_Q" --data "limit=5" "$backend_base/api/suggest")"
printf '%s' "$suggest_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("items"), list); print(f"ok q={data.get('\''q'\'', '')!r} items={len(data['\''items'\''])} truncated={bool(data.get('\''truncated'\''))}")'

echo "[smoke] GET /api/suggest_raw_id"
raw_id_json="$(curl -fsS --max-time 20 --get --data-urlencode "q=$SMOKE_RAW_ID_Q" --data "limit=5" "$backend_base/api/suggest_raw_id")"
printf '%s' "$raw_id_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); assert isinstance(data.get("items"), list); print(f"ok q={data.get('\''q'\'', '')!r} items={len(data['\''items'\''])} truncated={bool(data.get('\''truncated'\''))}")'

echo "[smoke] POST /api/subgraph"
subgraph_payload="$(SMOKE_ROOT_VID="$SMOKE_ROOT_VID" python3 -c 'import json,os; print(json.dumps({"root_vid": int(os.environ["SMOKE_ROOT_VID"]), "hop": 1, "max_nodes": 120, "max_edges": 4000, "relations": []}))' )"
subgraph_json="$(curl -fsS --max-time 30 -H 'Content-Type: application/json' -d "$subgraph_payload" "$backend_base/api/subgraph")"
printf '%s' "$subgraph_json" | SMOKE_ROOT_VID="$SMOKE_ROOT_VID" python3 -c 'import json,os,sys; data=json.load(sys.stdin); root_vid=int(os.environ["SMOKE_ROOT_VID"]); assert int(data.get("root_vid"))==root_vid; assert isinstance(data.get("nodes"), list); assert isinstance(data.get("edges"), list); stats=data.get("stats") or {}; assert isinstance(stats.get("node_count"), int); assert isinstance(stats.get("edge_count"), int); assert "truncated" in stats; print(f"ok root_vid={root_vid} nodes={len(data['\''nodes'\''])} edges={len(data['\''edges'\''])} truncated={stats.get('\''truncated'\'')}")'

echo "[smoke] POST /api/graph/discovery"
discovery_payload="$(SMOKE_ROOT_VID="$SMOKE_ROOT_VID" python3 -c 'import json,os; print(json.dumps({"seed_vids": [int(os.environ["SMOKE_ROOT_VID"])], "allowed_entity_types": [], "allowed_relation_types": [], "max_nodes": 80, "max_edges": 200, "top_k_per_type": 10, "include_candidate_candidate_edges": True, "include_seed_seed_edges": False, "hop": 1}))' )"
discovery_json="$(curl -fsS --max-time 30 -H 'Content-Type: application/json' -d "$discovery_payload" "$backend_base/api/graph/discovery")"
printf '%s' "$discovery_json" | SMOKE_ROOT_VID="$SMOKE_ROOT_VID" python3 -c 'import json,os,sys; data=json.load(sys.stdin); root_vid=int(os.environ["SMOKE_ROOT_VID"]); nodes=data.get("nodes") or []; edges=data.get("edges") or []; stats=data.get("stats") or {}; facets=data.get("facets") or {}; assert any(int(n.get("id"))==root_vid for n in nodes); assert isinstance(edges, list); assert isinstance(stats.get("seed_count"), int); assert stats.get("seed_count", 0) >= 1; assert isinstance(stats.get("candidate_count"), int); assert isinstance(facets.get("entity_types"), list); assert isinstance(facets.get("relation_types"), list); print(f"ok seed_vid={root_vid} nodes={len(nodes)} edges={len(edges)} candidates={stats.get('\''candidate_count'\'')} truncated={stats.get('\''truncated'\'')}")'

echo "[smoke] POST /api/graph/discovery layered_multiseed"
discovery_layered_payload="$(python3 -c 'import json; print(json.dumps({"seed_vids": [1, 2, 3], "allowed_entity_types": [], "allowed_relation_types": [], "max_nodes": 90, "max_edges": 140, "top_k_per_type": 10, "include_candidate_candidate_edges": True, "include_seed_seed_edges": True, "hop": 3, "ranking_mode": "layered_multiseed"}))' )"
discovery_layered_json="$(curl -fsS --max-time 45 -H 'Content-Type: application/json' -d "$discovery_layered_payload" "$backend_base/api/graph/discovery")"
printf '%s' "$discovery_layered_json" | python3 -c 'import json,sys; data=json.load(sys.stdin); stats=data.get("stats") or {}; facets=data.get("facets") or {}; query_summary=facets.get("query_summary") or {}; layers=facets.get("layers") or []; seeds=facets.get("seeds") or []; assert stats.get("ranking_mode")=="layered_multiseed"; assert int(stats.get("seed_count") or 0)==3; assert isinstance(layers, list) and len(layers) >= 1; assert isinstance(seeds, list) and len(seeds) == 3; assert int(query_summary.get("selected_seed_count") or 0)==3; print(f"ok ranking_mode={stats.get('\''ranking_mode'\'')} nodes={stats.get('\''node_count'\'')} edges={stats.get('\''edge_count'\'')} layers={len(layers)}")'

echo "[smoke] completed"
