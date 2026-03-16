from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException, Request

from app.config import settings

SPACE_HEADER = "X-KG-Space"
_current_space: ContextVar[Optional[str]] = ContextVar("current_space", default=None)


@dataclass(frozen=True)
class ResolvedSpace:
    space_name: str
    source: str
    header_present: bool
    header_value: Optional[str]
    registry_status: Optional[str]


def _space_error(status_code: int, error_code: str, message: str, field: str = "X-KG-Space") -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error_code": error_code, "message": message, "field": field})


def get_current_space() -> str:
    return str(_current_space.get() or settings.nebula_space)


def set_current_space(space_name: str) -> Token:
    return _current_space.set(str(space_name or "").strip() or settings.nebula_space)


def reset_current_space(token: Token) -> None:
    _current_space.reset(token)


@contextmanager
def use_space(space_name: str):
    token = set_current_space(space_name)
    try:
        yield
    finally:
        reset_current_space(token)


def resolve_request_space(request: Request) -> ResolvedSpace:
    # Phase-1 keeps request-level space resolution intentionally narrow:
    # only the X-KG-Space header can override the default space. APIs must not
    # reintroduce scattered body-level target_space fields as competing inputs.
    from app.services.spaces import registry_service, validation_service

    header_value = request.headers.get(SPACE_HEADER)
    if header_value is None or not str(header_value).strip():
        registry_service.register_default_space()
        return ResolvedSpace(
            space_name=settings.nebula_space,
            source="default",
            header_present=False,
            header_value=header_value,
            registry_status=(registry_service.get_space(settings.nebula_space).status if registry_service.get_space(settings.nebula_space) else None),
        )

    try:
        space_name = validation_service.validate_space_name(header_value)
    except HTTPException as exc:
        raise _space_error(400, "SPACE_HEADER_INVALID", exc.detail["message"]) from exc

    registry_entry = registry_service.get_space(space_name)
    if registry_entry is None:
        raise _space_error(404, "SPACE_NOT_REGISTERED", f"space `{space_name}` is not registered")
    return ResolvedSpace(
        space_name=space_name,
        source="header",
        header_present=True,
        header_value=header_value,
        registry_status=registry_entry.status,
    )


def bind_request_space(request: Request) -> Token:
    # Bind the resolved request space once at the HTTP entrypoint so downstream
    # services read a single request-scoped truth from request.state/ContextVar.
    resolved = resolve_request_space(request)
    request.state.space_name = resolved.space_name
    request.state.space_resolution = resolved
    return set_current_space(resolved.space_name)
