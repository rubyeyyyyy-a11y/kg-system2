from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException


TEMPLATE_TYPE = "entity_rel2_default"
TEMPLATE_VERSION = "entity_rel2_default.v1"
INTEGRATION_SCOPE = "entity_rel2_core"
SCHEMA_FILE = Path(__file__).resolve().parents[4] / "data-import" / "schema" / "00_schema.ngql"
DISCOVERY_WARNING = "discovery is best-effort in phase 1 and is not a fully supported multi-space contract"


def template_summary(template_type: str) -> dict[str, str]:
    if template_type != TEMPLATE_TYPE:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "SPACE_TEMPLATE_UNSUPPORTED",
                "message": f"template_type `{template_type}` is not supported",
                "field": "template_type",
            },
        )
    return {
        "template_type": TEMPLATE_TYPE,
        "template_version": TEMPLATE_VERSION,
        "integration_scope": INTEGRATION_SCOPE,
    }


def schema_statements(template_type: str) -> list[str]:
    template_summary(template_type)
    raw = SCHEMA_FILE.read_text(encoding="utf-8")
    chunks: list[str] = []
    current: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped.upper().startswith("USE "):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip()
            if statement:
                chunks.append(statement)
            current = []
    if current:
        statement = "\n".join(current).strip()
        if statement:
            chunks.append(statement if statement.endswith(";") else f"{statement};")
    return chunks


def readiness_statements(template_type: str) -> list[str]:
    template_summary(template_type)
    return [
        "MATCH (v:`Entity`) RETURN count(v) AS cnt;",
        "MATCH ()-[e:`REL2`]-() RETURN count(e) AS cnt;",
        "MATCH (m:`EntityTypeStat`) RETURN count(m) AS cnt;",
        "MATCH (m:`RelationTypeStat`) RETURN count(m) AS cnt;",
    ]
