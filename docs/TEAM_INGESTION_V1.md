# Team Ingestion V1

`/api/v1/team-ingestion` is a machine-facing CSV submission gateway layered on top of the existing formal imports pipeline. It does not replace the imports engine; it reuses the current draft, validate, job creation, executor, postprocess, and searchable closure logic.

## Current Contract

- V1 only executes in `demo_kg`.
- V1 rejects any external `X-KG-Space` header.
- V1 requires Bearer token auth.
- V1 accepts exactly one standard CSV file per submission.
- V1 preflight is intentionally strict: only UTF-8 / UTF-8-SIG, current Entity shard header, or current REL2 shard header.
- Retry semantics are idempotent: callers must reuse the same `idempotency_key` for the same submission request.

## Completion Standard

Submission success does not mean only “job created”.

The current business-complete standard remains:

- internal `job_status == succeeded`
- `searchable == true`

## Failures Endpoint

- `/submissions/{submission_id}/failures` returns row-level `raw_error` and related raw fields when the underlying `failed_rows.csv` artifact still exists.
- V1 does not promise a stable structured `error_code` for row failures because the current imports kernel only emits raw error text at that layer.

## Runtime Limitation

The current imports executor is a single-process in-memory worker queue. V1 therefore only has single-instance deployment semantics today. Multi-process or multi-replica deployment will require a future job claim/lease mechanism.
