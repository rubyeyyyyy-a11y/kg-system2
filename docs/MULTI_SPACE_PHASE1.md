# Managed Spaces Phase 1

## Why this phase starts with de-single-spacing

This phase is not a superficial `spaces` feature. The main work is removing the old single-space assumption so Nebula, Elasticsearch, metadata, imports, and graph/search APIs stop reading a fixed global `NEBULA_SPACE` at runtime.

The request header `X-KG-Space` is now the request-level truth source. Background imports workers do not read mutable global state; they execute inside the frozen `space_name` captured in the job snapshot.

## Why this is not a general graph platform

Phase 1 is an internal managed capability, not a generic schema-flexible graph platform.

- Only internal operators are expected to use it.
- Only one template is supported: `entity_rel2_default`.
- Only the current mainline chain is promised for that template:
  - `Entity`
  - `REL2`
  - `EntityTypeStat`
  - `RelationTypeStat`
- Discovery is best-effort only in phase 1.

## Current space resolution

`backend/app/core/space_context.py` is the only runtime space resolver.

- Header: `X-KG-Space: <space_name>`
- Header missing: fallback to configured default space
- Header present but invalid: explicit `400 SPACE_HEADER_INVALID`
- Header present but unregistered: explicit `404 SPACE_NOT_REGISTERED`
- Current space is never sourced from request body fields such as `target_space`
- Resolved space is written to:
  - `request.state.space_name`
  - `request.state.space_resolution`
  - a `ContextVar`

There is no global mutable current-space singleton.

## Space-aware data access

### Nebula

- Shared connection pool remains global.
- `USE <space>` now happens per session in `backend/app/db/nebula.py`.
- Callers can pass `space_name=...`, otherwise the current request/job context is used.
- Admin-only `CREATE SPACE` is isolated in `backend/app/services/spaces/admin_executor.py`.

### Elasticsearch

- Still uses one shared index in phase 1.
- Documents now include `space_name`.
- `_id` is now `{space_name}:{vid}` to avoid cross-space overwrite.
- All ES queries add a `space_name` filter.
- Imports entity sync writes `space_name` on every upsert.
- Edge-only imports still skip ES sync.
- Historical spaces may still require controlled ES backfill if their documents were created before the multi-space contract landed.
- Backfill/readiness rules are documented in `docs/MULTI_SPACE_ES_ALIGNMENT.md`.

### Metadata cache

- Metadata caches are now bucketed by `space_name`.
- Invalidation is space-scoped.
- Entity/relation type reads follow current request/job space.

## Managed spaces and registry

Runtime registry path:

`/.run/space-registry/spaces.json`

Registry is the platform truth source for UI and management state. Nebula graph spaces remain the data truth source.

Registry guarantees:

- top-level `format_version = spaces-v1`
- atomic write via temp file rename
- file lock around read-modify-write
- per-space status fields:
  - `status`
  - `internal_status`
  - `last_error`
  - lifecycle timestamps

Default legacy space is bootstrapped into the registry as a ready entry so old clients still work when they omit the header.

## Template initialization flow

Space creation uses a controlled synchronous flow:

1. validate space name
2. write registry provisioning record
3. `CREATE SPACE`
4. wait until `USE <space>` works
5. apply template schema
6. initialize metadata state
7. mark registry `ready`
8. on failure mark registry `failed` and persist `last_error`

Template schema is derived from `data-import/schema/00_schema.ngql`, but `USE demo_kg` is stripped and admin provisioning injects the target space context.

## Imports, search, graph binding

Imports v1 stayed additive:

- Draft adds `space_name`
- Compiled plan adds `space_name`, `template_type`, `integration_scope`
- Job state adds `space_name`, `template_type`

Effects:

- job snapshots freeze `space_name`
- executor writes only to that space
- metadata refresh targets only that space
- ES sync targets only that space
- draft/job listing is current-space scoped

Search, suggest, node detail, edge detail, subgraph, expand, and imports all resolve space from request-level context. They no longer decide behavior from a fixed global space constant.

## Truth sources summary

- Draft truth source:
  `.run/import-drafts/<draft_id>.json`
- Compiled plan truth source for execution:
  `.run/import-jobs/<job_id>/compiled_plan.json`
- Job truth source:
  `.run/import-jobs/<job_id>/state.json`
- Space registry truth source:
  `.run/space-registry/spaces.json`
- UI is presentation only and must not become a competing truth source.

## Frontend information architecture in this phase

- Create/switch space remains a `spaces` subdomain capability in backend and frontend data hooks.
- The primary UI entry is now collected into Import Workspace instead of a separate top-level space workflow.
- Main user path:
  1. choose or create current space
  2. upload CSV and complete imports v1 flow
  3. view graph/search/discovery against that same current space
- Discovery on non-default spaces is still best-effort and must be labeled as such in the UI.

## Discovery in phase 1

Discovery is not treated as fully supported multi-space output yet. APIs now return an explicit warning so the frontend can surface that it is best-effort.

## Known limitations

- no space delete
- no advanced Nebula create parameters in frontend
- no auth/permission model
- no multi-worker concurrency contract
- no resume-from-checkpoint imports
- registry is runtime-local JSON, not a distributed control plane

## Phase 2 direction

- stronger discovery guarantees per template
- richer template/version migration story
- background provisioning execution and progress polling
- explicit operational tooling for registry repair and reconciliation
- safer cross-instance coordination if multi-worker operation is introduced
