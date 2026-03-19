from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import HTTPException

from app.schemas.team_ingestion import TeamIngestionFailureItem, TeamIngestionFailuresResp
from app.schemas.team_ingestion import TeamIngestionSubmissionRecord
from app.services.imports import file_store, job_service


TEAM_INGESTION_MAX_FAILURE_PAYLOAD_BYTES = int(
    os.getenv("TEAM_INGESTION_MAX_FAILURE_PAYLOAD_BYTES", str(8 * 1024))
)
FAILED_ROW_INTERNAL_COLUMNS = {
    "__source_id",
    "__file_id",
    "__row_number",
    "__error",
    "__target_id",
    "__target_object",
    "__target_type",
}


def _truncate_row_payload(payload: dict[str, str]) -> tuple[dict[str, str], bool]:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= TEAM_INGESTION_MAX_FAILURE_PAYLOAD_BYTES:
        return payload, False

    remaining = TEAM_INGESTION_MAX_FAILURE_PAYLOAD_BYTES
    trimmed: dict[str, str] = {}
    for key, value in payload.items():
        key_bytes = len(str(key).encode("utf-8"))
        if remaining <= key_bytes + 8:
            break
        budget = max(0, remaining - key_bytes - 8)
        value_bytes = str(value).encode("utf-8")
        if len(value_bytes) > budget:
            trimmed[key] = value_bytes[:budget].decode("utf-8", errors="ignore")
            return trimmed, True
        trimmed[key] = str(value)
        remaining -= key_bytes + len(value_bytes) + 8
    return trimmed, True


def build_failures_response(submission: TeamIngestionSubmissionRecord) -> TeamIngestionFailuresResp:
    if not submission.job_id:
        return TeamIngestionFailuresResp(submission_id=submission.submission_id, total_failed_rows=0, items=[])

    state = job_service.get_job(submission.job_id)
    path = Path(state.failed_rows_path or "")
    if not path.exists():
        if int(state.failed_rows or 0) <= 0:
            return TeamIngestionFailuresResp(
                submission_id=submission.submission_id,
                job_id=submission.job_id,
                total_failed_rows=0,
                items=[],
            )
        # failed_rows.csv and per-target artifacts are subject to the existing
        # import artifact retention window. Once cleanup removes them, this
        # endpoint can no longer materialize row-level failure details.
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "TEAM_INGESTION_FAILURES_NOT_AVAILABLE",
                "message": "failed_rows artifact is no longer available for this submission",
                "field": "submission_id",
            },
        )

    items: list[TeamIngestionFailureItem] = []
    for row in file_store.read_csv_rows_from_path(path, encoding="utf-8", delimiter=","):
        payload = {
            str(key): str(value or "")
            for key, value in row.items()
            if str(key or "") not in FAILED_ROW_INTERNAL_COLUMNS and str(value or "") != ""
        }
        row_payload, payload_truncated = _truncate_row_payload(payload)
        raw_error = str(row.get("__error") or "")
        marker_truncated = "failed_rows truncated after" in raw_error
        row_number = str(row.get("__row_number") or "").strip()
        items.append(
            TeamIngestionFailureItem(
                row_number=int(row_number) if row_number.lstrip("-").isdigit() else None,
                raw_error=raw_error,
                row_payload=row_payload,
                target_id=str(row.get("__target_id") or "").strip() or None,
                target_object=str(row.get("__target_object") or "").strip() or None,
                source_id=str(row.get("__source_id") or "").strip() or None,
                truncated=payload_truncated or marker_truncated,
            )
        )

    return TeamIngestionFailuresResp(
        submission_id=submission.submission_id,
        job_id=submission.job_id,
        total_failed_rows=int(state.failed_rows or 0),
        items=items,
    )
