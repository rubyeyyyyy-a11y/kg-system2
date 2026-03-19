# Multi-Space ES Alignment

## Problem Definition

This is not a generic "search bug".

The missing capability is historical Elasticsearch index alignment after the system moved to the multi-space contract:

- request-level current space from `X-KG-Space`
- ES query must filter by `space_name=<current_space>`
- ES document `_id = {space_name}:{vid}`
- ES document `_source.space_name = <space_name>`

New managed spaces already follow this contract because imports incremental ES sync writes the new shape.
Historical spaces can still contain legacy single-space ES documents:

- missing `_source.space_name`
- `_id` is only `{vid}`

Once search/suggest/entity-candidates became strictly space-aware, those legacy documents stopped matching for historical spaces.

## Why Query Fallback Is Not Allowed

We do not:

- remove the `space_name` filter
- add legacy fallback in search path
- special-case `demo_kg`

Those changes would split the contract and keep migration debt permanently in the online query path.

## Canonical ES Contract

The system now has one canonical ES document contract:

- `_id = {space_name}:{vid}`
- `_source.space_name = <space_name>`

All write paths must converge on the same entity indexing service:

- imports incremental sync
- historical backfill
- ad-hoc rebuild tools

## Canonical Indexing Service

Canonical service:

- `backend/app/services/search_v2/indexing_service.py`

Responsibilities:

- `build_entity_doc(...)`
- `fetch_entity_rows(space_name, vids|cursor|range)`
- `iter_entity_doc_batches(...)`
- `bulk_upsert(space_name, docs)`
- `sync_entities(...)`
- `verify_space(space_name)`

This keeps imports incremental sync and historical backfill on the same document builder and ES write path.

## Backfill Runner

Thin orchestration script:

- `backend/scripts/backfill_es_spaces.py`

Supported flags:

- `--space <name>` can be repeated
- `--all-ready-spaces`
- `--dry-run`
- `--verify`
- `--resume`

Notes:

- backfill must pass `space_name` explicitly
- it must not depend on request context
- resume state is bucketed by `space_name`
- the script does not add a third document builder

## Space Source Strategy

Primary source:

- `.run/space-registry/spaces.json`
- only `status=ready` spaces are included for managed-space backfill

Additional source:

- default project space from `NEBULA_SPACE`
- in the current environment this is `demo_kg`
- even if it is not yet written into the registry, the default project space is still an explicit backfill target

Excluded:

- `provisioning`
- `failed`

Why only `ready`:

- backfill is a platform governance action for spaces that are currently usable
- `provisioning` and `failed` do not represent stable, queryable targets

Why new managed spaces do not need historical migration:

- their imports incremental sync already writes `space_name`
- their ES `_id` already uses `{space_name}:{vid}`

## Repair Scope

Direct ES-repair objects:

- `/api/search`
- `/api/suggest`
- `/api/suggest_raw_id`
- `/api/discovery/entity_candidates`

Product-layer validation objects:

- `/api/graph/discovery`
- `/api/node/*`
- `/api/edge_detail`
- `/api/subgraph`
- `/api/expand`
- `/api/relation_types`

The second group is not repaired by ES backfill directly, but it must be validated to prove multi-space discovery still works end-to-end after candidate search is restored.

## Verification Layers

Index layer:

- sample documents use `_id = {space_name}:{vid}`
- sample documents carry `_source.space_name = <space_name>`
- same `vid` can coexist across spaces
- `space_name`-filtered ES queries hit the correct documents

Product layer:

- switch current space
- search/suggest/suggest_raw_id return current-space-only candidates
- discovery entity candidates return current-space-only candidates
- graph discovery can continue from those candidates
- current-space switch coordinator must finish reset + readiness/index refresh before new candidate requests resume

## Legacy Document Handling

Legacy ES documents may still exist after backfill.

That is acceptable for now because:

- current queries always filter by `space_name`
- legacy documents without `space_name` do not match the new query contract

Deletion is a later action, not part of this phase.

Before deletion, all of the following must be true:

- new-format documents are fully backfilled for target spaces
- index-layer verification passes
- product-layer verification passes
- no current-space query depends on legacy documents

## Current Limits

- discovery remains phase-1 best-effort at product level
- historical full-space backfill can still be operationally heavy on large Nebula spaces and should be run as a controlled governance task, not inside imports jobs
- for the current environment, `demo_kg` full canonical rebuild is still in progress and remains part of feature-completeness work for historical search recovery

## Verification Status Classes

Backfill / verify output should use these meanings:

- `verified_nonempty`
  - verification passed
  - `doc_count > 0`
- `verified_empty`
  - space is ready
  - `doc_count = 0`
  - this is an empty usable space, not a backfill failure
- `verified_partial`
  - space is usable
  - canonical ES coverage is only partially aligned to Nebula
  - search/suggest/entity-candidates can work only over the canonical subset already rebuilt
- `failed`
  - ES write failed, or a non-empty space failed verification

Current delivery-state snapshot and operations handover:

- [docs/archive/MULTI_SPACE_DELIVERY_20260312.md](/home/ray/kg-system/docs/archive/MULTI_SPACE_DELIVERY_20260312.md)
- [docs/archive/DEMO_KG_FULL_BACKFILL_RUNBOOK.md](/home/ray/kg-system/docs/archive/DEMO_KG_FULL_BACKFILL_RUNBOOK.md)
