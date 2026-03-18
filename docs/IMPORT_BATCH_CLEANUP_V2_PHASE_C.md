# Import Batch Governance V2 (Phase C)

## Scope

Phase C keeps the validated main loop stable:

`import -> batch registry -> item ledger -> cleanup planning -> cleanup execute -> verify -> audit/artifacts retention`

The deployment/runtime boundary is unchanged:

- file-based state
- single-process worker model
- non-transactional cleanup execution
- no sqlite/postgres/redis/celery migration in this phase

## New API: Cleanup Plan Preview

New endpoint:

- `POST /api/import/batches/cleanup-plan`

Request body follows cleanup request style:

- `batch_ids: string[]`
- `scope: full_batch | relations_only`
- `created_by: string` (optional, defaults to `import_workspace_cleanup`)

Behavior:

- preview only
- does not create cleanup job records
- does not start cleanup worker
- does not execute graph/doc deletion

Response includes:

- `plan_summary`
- `conflicts`
- `blocked_entities` summary + sample
- `deletable_entities` summary + sample
- `deletable_relations` summary + sample
- `warning_messages`
- `verification_scope_note`
- `has_plan_artifacts` (currently `false` for preview)

## Preview vs Execute Consistency Boundary

Both preview and execute use the same planning core (`cleanup_planning_service.plan_cleanup(...)`).

Engineering boundary:

- preview is point-in-time analysis against current ledger + graph state
- execute recalculates plan again before deletion
- preview and execute results may differ if concurrent graph/ledger state changes happen between calls

## Frontend Flow Upgrade

Batch UI now promotes:

1. select batch(es)
2. preview cleanup plan
3. review blocked/deletable/warnings/verification scope note
4. confirm cleanup execution

A clearly labeled quick path is kept for compatibility:

- `Quick Cleanup (No Preview)`

## Runtime Shell Abstraction (Step 1)

New runtime shell module:

- `backend/app/services/imports/job_runtime.py`

Current extraction scope:

- queued-record discovery shell
- drain-loop shell
- worker thread lifecycle shell
- startup recover-and-start shell

Not included in this phase:

- generic business `JobExecutor` base class
- unified import/cleanup state-machine enums
- fully unified side-effect abstraction

## Repository Boundary Prep (Step 1)

New thin repository adapters:

- `backend/app/services/imports/state_repository.py`

High-value state models with file-store-backed adapters:

- `ImportJobState`
- `ImportBatchRecord`
- `CleanupJobRecord`

This phase only introduces boundary seams and selective adoption in new planning/runtime paths; storage backend remains file-based.
