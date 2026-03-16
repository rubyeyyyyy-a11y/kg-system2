from __future__ import annotations

import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, TypeVar

import fcntl

from app.config import settings
from app.services.spaces.models import SpaceRegistry, SpaceSummary
from app.services.spaces.template_service import INTEGRATION_SCOPE, TEMPLATE_TYPE, TEMPLATE_VERSION

T = TypeVar("T")

REGISTRY_ROOT = Path(__file__).resolve().parents[4] / ".run" / "space-registry"
REGISTRY_PATH = REGISTRY_ROOT / "spaces.json"
LOCK_PATH = REGISTRY_ROOT / "spaces.lock"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@contextmanager
def _registry_lock():
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_registry_unlocked(registry: SpaceRegistry) -> None:
    registry.updated_at = _now_iso()
    REGISTRY_ROOT.mkdir(parents=True, exist_ok=True)
    # spaces.json is the registry truth source. Write to a temp file and then
    # atomically replace the target so readers never observe a partial payload.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=REGISTRY_ROOT, delete=False) as handle:
        tmp_path = Path(handle.name)
        handle.write(json.dumps(registry.model_dump(), ensure_ascii=False, indent=2))
        handle.flush()
    tmp_path.replace(REGISTRY_PATH)


def _default_space_summary() -> SpaceSummary:
    now = _now_iso()
    return SpaceSummary(
        space_name=settings.nebula_space,
        display_name=settings.nebula_space,
        description="Legacy default single-space bootstrap entry",
        template_type=TEMPLATE_TYPE,
        template_version=TEMPLATE_VERSION,
        integration_scope=INTEGRATION_SCOPE,
        status="ready",
        internal_status="ready",
        created_by="system",
        created_at=now,
        ready_at=now,
    )


def _normalize_registry(payload: dict | None) -> SpaceRegistry:
    if not payload:
        return SpaceRegistry(spaces={settings.nebula_space: _default_space_summary()})
    registry = SpaceRegistry.model_validate(payload)
    if settings.nebula_space not in registry.spaces:
        registry.spaces[settings.nebula_space] = _default_space_summary()
    return registry


def read_registry() -> SpaceRegistry:
    with _registry_lock():
        if not REGISTRY_PATH.exists():
            registry = SpaceRegistry(spaces={settings.nebula_space: _default_space_summary()})
            _write_registry_unlocked(registry)
            return registry
        registry = _normalize_registry(json.loads(REGISTRY_PATH.read_text(encoding="utf-8")))
        if settings.nebula_space not in json.loads(REGISTRY_PATH.read_text(encoding="utf-8")).get("spaces", {}):
            _write_registry_unlocked(registry)
        return registry


def _mutate(mutator: Callable[[SpaceRegistry], T]) -> T:
    # All registry read-modify-write flows funnel through the same file lock so
    # provisioning status transitions stay serialized in this runtime-local v1.
    with _registry_lock():
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8")) if REGISTRY_PATH.exists() else None
        registry = _normalize_registry(payload)
        result = mutator(registry)
        _write_registry_unlocked(registry)
        return result


def register_default_space() -> SpaceSummary:
    def _ensure(registry: SpaceRegistry) -> SpaceSummary:
        existing = registry.spaces.get(settings.nebula_space)
        if existing is not None:
            return existing
        registry.spaces[settings.nebula_space] = _default_space_summary()
        return registry.spaces[settings.nebula_space]

    return _mutate(_ensure)


def list_spaces() -> list[SpaceSummary]:
    registry = read_registry()
    return sorted(registry.spaces.values(), key=lambda item: (item.created_at, item.space_name))


def get_space(space_name: str) -> SpaceSummary | None:
    registry = read_registry()
    return registry.spaces.get(str(space_name or "").strip())


def is_registered_space(space_name: str) -> bool:
    return get_space(space_name) is not None


def write_space(summary: SpaceSummary) -> SpaceSummary:
    def _write(registry: SpaceRegistry) -> SpaceSummary:
        registry.spaces[summary.space_name] = summary
        return summary

    return _mutate(_write)


def update_space(space_name: str, **changes) -> SpaceSummary:
    def _update(registry: SpaceRegistry) -> SpaceSummary:
        existing = registry.spaces[space_name]
        updated = existing.model_copy(update=changes)
        registry.spaces[space_name] = updated
        return updated

    return _mutate(_update)
