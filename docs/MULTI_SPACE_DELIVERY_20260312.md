# Multi-Space Delivery 2026-03-12

## 1. Scope

This delivery does not replace the current multi-space skeleton.

It closes the remaining gaps on top of the existing contract:

- current space stays request-scoped and comes only from `X-KG-Space`
- imports v1 keeps frozen `space_name` semantics in draft / compiled plan / job
- Elasticsearch stays space-aware with `_id = {space_name}:{vid}` and `_source.space_name = <space_name>`
- search and discovery do not add legacy query fallback

## 2. Current-Space Switch Coordinator

Frontend current-space switching is now treated as an explicit coordination action instead of ad-hoc state mutation.

Primary files:

- `frontend/src/features/space/store.ts`
- `frontend/src/features/space/hooks/useSpaceSwitchCoordinator.ts`
- `frontend/src/App.tsx`

Switch sequence:

1. persist the selected `currentSpace` into the shared store and local storage
2. mark the switch as in-progress with a `switchNonce`
3. reset space-scoped UI state
4. refresh readiness + `index_status` from `/api/spaces` and `/api/spaces/current`
5. only after refresh completes, unblock new search / discovery requests

Reset scope currently includes:

- search keyword and search results
- suggest / raw-id suggest / edge suggest UI state
- discovery candidate query and candidate result list
- discovery seeds
- graph data and graph-source mode
- runtime filters and expand filters
- selected detail state
- relation-type catalog cache
- entity-type options cache by scope key reset

Import Workspace is now wired to the same parent space state instead of running an independent `useSpaces()` refresh loop. This keeps current-space switching under one coordinator path.

## 3. Search / Discovery Contract

There are two layers and they must stay separate.

### ES candidate layer

Responsible for candidate retrieval inside the selected current space:

- `/api/search`
- `/api/suggest`
- `/api/suggest_raw_id`
- `/api/discovery/entity_candidates`

This layer is where canonical ES alignment matters. If a historical space has not been backfilled into canonical ES documents yet, candidate coverage will be incomplete even if Nebula still contains the full graph.

### Nebula graph layer

Responsible for graph traversal and detail retrieval inside the selected current space:

- `/api/graph/discovery`
- `/api/node/*`
- `/api/edge_detail`
- `/api/subgraph`
- `/api/expand`
- `/api/relation_types`

Best-effort means:

- candidate search must still work in the selected space
- graph richness depends on graph size, density, and budget pruning
- sparse graph output for a small managed space is a data-shape fact, not a space-routing failure

## 4. Index Status Product Contract

Only these `index_status.status` values are valid:

- `verified_nonempty`
- `verified_empty`
- `verified_partial`
- `failed`

Semantics:

- `verified_nonempty`: canonical ES is verified and non-empty
- `verified_empty`: space is ready but currently empty; this is not a failure
- `verified_partial`: space is usable, but canonical ES coverage is still incomplete
- `failed`: ES write or verification failed

The registry and `/api/spaces/current` now surface `index_status` as product data, not just script output.

## 5. Historical vs Managed Spaces

Managed spaces:

- created through the controlled provisioning flow
- after import, entity ES sync already writes canonical documents
- therefore they are naturally aligned to the new search contract

Historical spaces:

- existed before the canonical multi-space ES contract
- require controlled canonical backfill to recover full candidate coverage

`demo_kg` is the historical default space in the current environment. Its full canonical rebuild is part of feature completeness for historical search recovery, not an optional ops footnote.

## 6. demo_kg Full Canonical Rebuild

Current recorded state comes from:

- `.run/space-registry/spaces.json`
- `backend/state/es_backfill_spaces.state.json`
- `backend/state/demo_kg_backfill_summary_20260312.json`

Snapshot on 2026-03-12:

- `space_name=demo_kg`
- `index_status=verified_partial`
- `canonical doc_count=10000`
- `nebula_entity_count=5059789`
- `coverage_pct=0.2`

Interpretation:

- canonical search coverage is recovering
- candidate search is using the canonical contract correctly
- full historical coverage is not restored yet

Formal runner:

```bash
bash backend/scripts/run_demo_kg_backfill_round.sh
```

Operational expectations:

- resumable via per-space state buckets in `backend/state/es_backfill_spaces.state.json`
- observable via per-run logs in `backend/logs/demo_kg_backfill/` and per-run summaries in `backend/state/demo_kg_backfill_runs/`
- latest summary is copied to `backend/state/demo_kg_backfill_summary_latest.json`
- verifiable via canonical sample checks plus registry `index_status`

This backfill must remain outside imports jobs.

Formal runbook:

- [docs/DEMO_KG_FULL_BACKFILL_RUNBOOK.md](/home/ray/kg-system/docs/DEMO_KG_FULL_BACKFILL_RUNBOOK.md)

## 7. Current Acceptance Snapshot

Functional status in the current repo state:

- create new managed space: available
- switch current space: available through the coordinator
- import into selected space: available
- validate and submit frozen import job: available
- discovery candidate search in selected space: available
- graph discovery / detail / render in selected space: available
- cross-space data mixing: prevented by request-scoped space resolution plus ES `space_name` filter

Recorded examples from the current registry:

- `demo_kg`: `verified_partial`
- `it_space_218024`: `verified_nonempty`
- `it_space_217946`: `verified_empty`
- failed example `test`: `status=failed`, `index_status=null`, excluded from ready-space backfill targets

## 8. Remaining Non-Blocking Limits

- `demo_kg` full backfill is not complete yet
- legacy ES documents are still present until later cleanup
- registry remains runtime-local JSON, not a distributed control plane
- Import Workspace and App are better aligned now, but `App.tsx` is still large and should continue to shed orchestration details in later passes
