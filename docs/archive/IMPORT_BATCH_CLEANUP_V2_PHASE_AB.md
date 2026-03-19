# Import Batch Governance V2 (Phase A + B)

## Scope

V2 Phase A/B keeps the V1.5 main loop available:

`import -> batch registry -> item ledger -> cleanup job -> search/suggest cleanup -> audit retention`

No runtime/storage migration is introduced in this round. The system remains file-based, single-worker, and non-transactional.

## Phase A: Explicit Cleanup Planning

Cleanup execution is now split into:

- `planning`
- `deleting_relations`
- `deleting_entities`
- `deleting_es_docs`
- `refreshing_metadata`
- `reconciling`
- `verifying`
- `completed` / `failed`

Planning is now an explicit internal stage that produces structured outputs used by execute/verify.

New cleanup job planning fields:

- `plan_summary`
- `has_plan_artifacts`

`plan_summary` includes:

- `requested_entity_count`
- `requested_relation_count`
- `ledger_blocked_entity_count`
- `live_graph_blocked_entity_count`
- `blocked_entity_count`
- `deletable_entity_count`
- `deletable_relation_count`
- `conflict_count`
- `warnings`
- `verification_scope_note`
- `generated_at`

Planning artifacts are persisted under:

- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/plan_summary.json`
- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/blocked_entities.json`
- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/deletable_entities.json`
- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/deletable_relations.json`

## Phase B: Ledger + Live Graph Conflict Detection

Entity deletion blockers now combine:

- ledger blockers (`source=ledger`)
- live graph blockers (`source=live_graph`)

Live graph scan is integrated at planning time, not scattered in delete executor paths.

Implementation notes:

- Cleanup adds a dedicated live scan service: `cleanup_graph_scan_service.py`
- Nebula read layer adds incident-edge helper in `clients/nebula_client.py`
- Planner excludes relation keys scheduled for deletion from live blocker results

## Boundaries and Limits (Current Version)

- External cleanup entry remains `POST /api/import/batches/cleanup` (single-step API remains).
- No standalone plan preview API is added in this phase.
- Runtime abstraction / sqlite repository migration is not included.
- Worker model remains single-process file-state.
- Cleanup remains non-transactional.
- Historical imports without ledger still cannot be fully recovered by cleanup.
- Live graph scan currently targets configured `EDGE_TYPE` incident edges and may be affected by scan-size limits (`IMPORT_CLEANUP_LIVE_SCAN_MAX_EDGES`).
- `relations_only` still skips entity deletion and entity-level live scan verification.

