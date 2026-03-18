# Property System Delivery 1 Implementation

## Why `object_meta`

Delivery 1 introduces a shared property-governance kernel so detail and edit no longer depend on scattered hard-coded field lists.

- Backend validation and editable-field compatibility now resolve through `backend/app/object_meta/`
- Frontend detail and edit both resolve field labels, groups, long-text behavior, and read-only behavior from `frontend/src/features/objectMeta/`

This keeps Delivery 1 inside the existing API surface while moving rule ownership out of legacy component constants.

## Why Keep Single `Entity` / Single `REL2`

This delivery only upgrades field governance. It does not change the physical storage model.

- Nodes still live on single tag `Entity`
- Edges still live on single edge type `REL2`
- `edge_type` keeps its storage/API identity meaning
- Semantic edge classification is reserved under `edge_kind`

That keeps search, patch routes, and graph traversal behavior stable while detail/edit become metadata-driven.

## How Detail And Edit Share Rules

- Backend `object_meta.validation_service` now owns editable/read-only judgment for patch validation
- Backend snapshots in `edit_service.py` now read full current properties instead of fixed subsets
- Frontend detail normalizes top-level fields and `props` into a single canonical field map
- Frontend edit builds forms from base rules + current object properties + compatible metadata fields

Result: detail and edit now reason about the same field names, aliases, and read-only constraints.

## Panel Default Consolidation

Default collapse state now lives in:

- `frontend/src/features/objectMeta/config/panelDefaults.ts`

Current consumers:

- `frontend/src/hooks/useGraphData.ts`
- `frontend/src/features/discovery/hooks/useDiscoverySessionController.ts`
