// COMPAT(2026-03): preserve the historical feature entrypoint path while
// imports migrate to `features/import/container/ImportWorkspace`, remove after
// all imports use the container path directly.
export * from "./container/ImportWorkspace";
