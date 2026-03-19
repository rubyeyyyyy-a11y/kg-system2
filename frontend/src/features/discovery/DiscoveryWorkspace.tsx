// COMPAT(2026-03): preserve the historical feature entrypoint path while
// imports migrate to `features/discovery/container/DiscoveryWorkspace`,
// remove after all imports use the container path directly.
export * from "./container/DiscoveryWorkspace";
