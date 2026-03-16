from __future__ import annotations

import logging

from fastapi import HTTPException

from app.services.imports import metadata_postprocess_service
from app.services.spaces.index_status_service import mark_space_empty_ready
from app.services.spaces import admin_executor, audit_service, registry_service, template_service, validation_service
from app.services.spaces.models import SpaceSummary

logger = logging.getLogger(__name__)


def create_space(
    *,
    space_name: str,
    display_name: str,
    description: str,
    template_type: str,
    created_by: str,
) -> tuple[SpaceSummary, list[str]]:
    validated_name = validation_service.validate_space_name(space_name)
    validation_service.ensure_space_not_exists(validated_name)
    template_meta = template_service.template_summary(template_type)
    provisioning = SpaceSummary(
        space_name=validated_name,
        display_name=str(display_name or validated_name).strip() or validated_name,
        description=str(description or "").strip(),
        template_type=template_meta["template_type"],
        template_version=template_meta["template_version"],
        integration_scope=template_meta["integration_scope"],
        status="provisioning",
        internal_status="creating_space",
        created_by=str(created_by or "").strip() or "internal_user",
        created_at=registry_service._now_iso(),
    )
    registry_service.write_space(provisioning)
    audit_service.write_audit("space_provision_start", {"space_name": validated_name, "created_by": provisioning.created_by})
    try:
        logger.warning("space_provision_step space=%s step=creating_space", validated_name)
        admin_executor.create_space(validated_name)
        registry_service.update_space(validated_name, internal_status="waiting_ready")
        logger.warning("space_provision_step space=%s step=waiting_ready", validated_name)
        admin_executor.wait_until_space_ready(validated_name)
        registry_service.update_space(validated_name, internal_status="applying_schema")
        logger.warning("space_provision_step space=%s step=applying_schema", validated_name)
        admin_executor.apply_statements(validated_name, template_service.schema_statements(template_type))
        logger.warning("space_provision_step space=%s step=waiting_schema_queryable", validated_name)
        admin_executor.wait_until_statements_succeed(validated_name, template_service.readiness_statements(template_type))
        registry_service.update_space(validated_name, internal_status="initializing_metadata")
        logger.warning("space_provision_step space=%s step=initializing_metadata", validated_name)
        metadata_postprocess_service.refresh_from_db(actor=provisioning.created_by, space_name=validated_name)
        ready = registry_service.update_space(
            validated_name,
            status="ready",
            internal_status="ready",
            ready_at=registry_service._now_iso(),
            last_error=None,
        )
        ready = registry_service.update_space(
            validated_name,
            index_status=mark_space_empty_ready(validated_name),
        )
        logger.warning("space_provision_step space=%s step=ready", validated_name)
        audit_service.write_audit("space_provision_ready", {"space_name": validated_name})
        return ready, [template_service.DISCOVERY_WARNING]
    except Exception as exc:
        registry_service.update_space(
            validated_name,
            status="failed",
            internal_status="failed",
            last_error=str(exc),
        )
        logger.exception("space_provision_step space=%s step=failed error=%s", validated_name, str(exc))
        audit_service.write_audit("space_provision_failed", {"space_name": validated_name, "last_error": str(exc)})
        raise HTTPException(
            status_code=500,
            detail={"error_code": "SPACE_PROVISION_FAILED", "message": str(exc), "field": "space_name"},
        ) from exc
