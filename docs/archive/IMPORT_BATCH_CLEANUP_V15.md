# Import Batch Management + Cleanup Job V1.5

> V2 Phase A/B incremental governance updates are documented in `docs/archive/IMPORT_BATCH_CLEANUP_V2_PHASE_AB.md`.

## Summary

V1.5 keeps the existing V1 main loop intact:

`import -> batch registry -> item ledger -> cleanup job -> search/suggest cleanup -> audit retention`

This iteration adds stronger ledger idempotency, phased cleanup execution state, structured cleanup artifacts, and richer Batch UI detail without introducing new infrastructure.

## What Changed

- Item ledger writes are now persistently idempotent per `batch_id + item_key`.
- Each batch keeps a lightweight item-key index under `.run/import-batches/<batch_id>/item_keys.json`.
- Import executor writes ledger entries through an idempotent file-store API and records:
  - `requested_count`
  - `appended_count`
  - `skipped_existing_count`
- Batch records now carry structured `ledger_summary` plus ledger consistency warnings.
- Cleanup jobs now expose:
  - `phase`
  - `final_phase`
  - `phase_history`
  - `failure_phase`
  - `failure_kind`
  - `failure_detail`
  - `duration_ms`
  - structured counts and warnings
- Cleanup jobs emit JSON artifacts under `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/`.
- Batch UI now resolves the cleanup result relevant to the selected batch or selected batch set instead of always showing `cleanupJobs[0]`.

## Ledger Rules

Stable item keys:

- Entity: `entity:{vid}`
- Relation: `relation:{edge_type}:{src_vid}:{dst_vid}:{relation}:{rank}`

Notes:

- `edge_type` is included when available and defaults to `REL2`.
- The uniqueness boundary is the batch, not global graph state.
- Ledger append still happens only after Nebula write success.

## Cleanup Phases

Cleanup jobs move through these phases:

- `planning`
- `deleting_relations`
- `deleting_entities`
- `deleting_es_docs`
- `refreshing_metadata`
- `reconciling`
- `verifying`
- `completed`
- `failed`

Phase transitions are persisted to the cleanup job record and surfaced to the frontend.

## Cleanup Artifacts

Artifacts are written to:

- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/summary.json`
- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/conflicts.json`
- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/skipped_entities.json`
- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/skipped_relations.json`
- `.run/import-cleanup-jobs/<cleanup_job_id>/artifacts/verify_summary.json`

They are exposed by the imports API through cleanup job detail metadata and cleanup artifact download endpoints.

## Boundaries

- Only test batches support cleanup.
- Historical imports without ledger data are read-only from cleanup’s perspective.
- Cleanup is not transactional. A failed job may have already deleted some relations or entities before the failure point.
- V1.5 does not do graph live reference scan.
- V1.5 does not migrate cleanup state to sqlite/postgres.
- Team ingestion cleanup remains gated by current batch/test-data policy and is not newly opened here.

## Runtime Limits

- Worker mode remains single-process, file-based, and conservative.
- No Redis/Celery/Postgres dependency is introduced.
- Request dedupe is file-state based and scoped to active queued/running cleanup jobs.
- Startup recovery marks interrupted cleanup jobs as failed with structured interruption metadata.

## Recommended Test Flow

1. Submit a small test-data import batch with entity and relation rows.
2. Verify the batch record contains ledger items plus `ledger_summary`.
3. Re-run the same import/fallback scenario and confirm duplicate ledger rows are not appended.
4. Trigger cleanup from the Batch UI.
5. Inspect:
   - cleanup phase progression
   - counts
   - conflicts
   - verify summary
   - downloadable artifacts
6. Confirm search/suggest no longer returns deleted test entities when entity cleanup actually ran.

## Troubleshooting

If ledger counts look wrong:

- Inspect batch ledger summary in the batch record.
- Inspect `.run/import-batches/<batch_id>/items.jsonl`.
- Inspect `.run/import-batches/<batch_id>/item_keys.json`.
- Look for `batch_ledger_consistency_warning` in import job events/logs.

If cleanup fails:

- Check `failure_phase`, `failure_kind`, and `failure_detail`.
- Download `summary.json` and `verify_summary.json`.
- Review `conflicts.json` for blocked entity deletions.
- Remember that `relations_only` cleanup intentionally does not claim entity-level or relation-level full verification.

If cleanup looks duplicated:

- Compare `request_key`, `batch_ids`, `scope`, and current cleanup job status.
- Exact duplicate active requests are reused rather than creating another queued job.
