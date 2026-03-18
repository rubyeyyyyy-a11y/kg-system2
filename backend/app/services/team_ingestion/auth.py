from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


TEAM_INGESTION_BEARER_TOKEN_ENV = "TEAM_INGESTION_BEARER_TOKEN"
TEAM_INGESTION_BEARER_TOKENS_ENV = "TEAM_INGESTION_BEARER_TOKENS"
TEAM_INGESTION_DEFAULT_PRINCIPAL_ENV = "TEAM_INGESTION_DEFAULT_PRINCIPAL"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class TeamIngestionPrincipal:
    principal: str
    scheme: str = "bearer"


def _auth_error(status_code: int, error_code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
            "field": "Authorization",
        },
    )


def _default_principal() -> str:
    return str(os.getenv(TEAM_INGESTION_DEFAULT_PRINCIPAL_ENV, "team-ingestion")).strip() or "team-ingestion"


def _configured_tokens() -> dict[str, str]:
    configured: dict[str, str] = {}
    raw_mapping = str(os.getenv(TEAM_INGESTION_BEARER_TOKENS_ENV, "") or "").strip()
    if raw_mapping:
        for item in raw_mapping.split(","):
            token_spec = str(item or "").strip()
            if not token_spec:
                continue
            if ":" in token_spec:
                principal, token = token_spec.split(":", 1)
            elif "=" in token_spec:
                principal, token = token_spec.split("=", 1)
            else:
                principal, token = _default_principal(), token_spec
            resolved_principal = str(principal or "").strip() or _default_principal()
            resolved_token = str(token or "").strip()
            if resolved_token:
                configured[resolved_principal] = resolved_token
    single_token = str(os.getenv(TEAM_INGESTION_BEARER_TOKEN_ENV, "") or "").strip()
    if single_token:
        configured.setdefault(_default_principal(), single_token)
    return configured


def require_team_ingestion_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> TeamIngestionPrincipal:
    tokens = _configured_tokens()
    if not tokens:
        raise _auth_error(
            503,
            "TEAM_INGESTION_AUTH_NOT_CONFIGURED",
            "team-ingestion auth is not configured",
        )
    if credentials is None or str(credentials.scheme or "").lower() != "bearer":
        raise _auth_error(401, "TEAM_INGESTION_AUTH_REQUIRED", "bearer token is required")
    token = str(credentials.credentials or "").strip()
    if not token:
        raise _auth_error(401, "TEAM_INGESTION_AUTH_REQUIRED", "bearer token is required")
    for principal, configured_token in tokens.items():
        if token == configured_token:
            return TeamIngestionPrincipal(principal=principal)
    raise _auth_error(401, "TEAM_INGESTION_AUTH_INVALID", "invalid bearer token")
