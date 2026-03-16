from __future__ import annotations

import re

from fastapi import HTTPException

from app.services.spaces import registry_service


SPACE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def validate_space_name(space_name: str) -> str:
    value = str(space_name or "").strip()
    if not value:
        raise HTTPException(
            status_code=422,
            detail={"error_code": "SPACE_NAME_REQUIRED", "message": "space_name is required", "field": "space_name"},
        )
    if not SPACE_NAME_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "SPACE_NAME_INVALID",
                "message": "space_name must match ^[A-Za-z_][A-Za-z0-9_]{0,63}$",
                "field": "space_name",
            },
        )
    return value


def ensure_space_not_exists(space_name: str) -> None:
    if registry_service.get_space(space_name) is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "SPACE_ALREADY_EXISTS",
                "message": f"space `{space_name}` already exists",
                "field": "space_name",
            },
        )


def ensure_space_ready(space_name: str) -> None:
    summary = registry_service.get_space(space_name)
    if summary is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "SPACE_NOT_REGISTERED",
                "message": f"space `{space_name}` is not registered",
                "field": "X-KG-Space",
            },
        )
    if summary.status == "ready":
        return
    reason = "provisioning" if summary.status == "provisioning" else "failed"
    suffix = f": {summary.last_error}" if summary.status == "failed" and summary.last_error else ""
    raise HTTPException(
        status_code=409,
        detail={
            "error_code": "SPACE_NOT_READY",
            "message": f"space `{space_name}` is {summary.status}{suffix}",
            "field": "X-KG-Space",
            "reason": reason,
            "status": summary.status,
            "internal_status": summary.internal_status,
        },
    )
