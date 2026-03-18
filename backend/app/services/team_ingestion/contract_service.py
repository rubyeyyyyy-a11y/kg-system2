from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.services.imports import file_store


TEAM_STANDARD_CSV_TEMPLATE_VERSION = "team_standard_csv.v1"
TEAM_INGESTION_MAX_UPLOAD_BYTES = int(
    os.getenv("TEAM_INGESTION_MAX_UPLOAD_BYTES", str(file_store.MAX_UPLOAD_BYTES))
)
TEAM_INGESTION_ALLOWED_MIME_TYPES = set(file_store.ALLOWED_UPLOAD_MIME_TYPES)
TEAM_INGESTION_ALLOWED_ENCODINGS = {"utf-8", "utf-8-sig"}

ENTITY_CSV_REQUIRED_HEADER = [
    "ID",
    "entity_type",
    "entity_name",
    "entity_raw_id",
    "description",
    "source",
]
ENTITY_CSV_OPTIONAL_HEADER = [
    "synonyms",
    "version",
    "updated_at",
    "updated_by",
]
REL2_CSV_REQUIRED_HEADER = [
    "srcVID",
    "dstVID",
    "rank",
    "relation",
    "source",
]
REL2_CSV_OPTIONAL_HEADER = [
    "evidence",
    "edge_kind",
    "version",
    "updated_at",
    "updated_by",
]
STANDARD_CSV_CONTRACTS: dict[str, list[str]] = {
    "entity_csv": ENTITY_CSV_REQUIRED_HEADER,
    "rel2_csv": REL2_CSV_REQUIRED_HEADER,
}


@dataclass(frozen=True)
class PreflightResult:
    contract_kind: str
    detected_encoding: str
    headers: list[str]
    template_version: str


def _contract_error(status_code: int, error_code: str, message: str, field: str = "file") -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
            "field": field,
        },
    )


def reject_blank_text(value: str, *, field: str) -> str:
    text = str(value or "").strip()
    if text:
        return text
    raise _contract_error(422, "TEAM_INGESTION_FIELD_REQUIRED", f"{field} is required", field=field)


def validate_upload_metadata(upload: UploadFile) -> None:
    filename = str(upload.filename or "").strip()
    content_type = str(upload.content_type or "").strip().lower()
    if not filename.lower().endswith(".csv"):
        raise _contract_error(415, "TEAM_INGESTION_UNSUPPORTED_FILE_TYPE", "only .csv files are supported")
    if content_type and content_type not in TEAM_INGESTION_ALLOWED_MIME_TYPES:
        raise _contract_error(
            415,
            "TEAM_INGESTION_UNSUPPORTED_CONTENT_TYPE",
            f"unsupported upload content_type `{content_type}`",
        )


def detect_stream_encoding(prefix: bytes) -> str:
    return "utf-8-sig" if prefix.startswith(b"\xef\xbb\xbf") else "utf-8"


def validate_template_version(template_version: str | None) -> str | None:
    if template_version is None or not str(template_version).strip():
        return None
    resolved = str(template_version).strip()
    if resolved != TEAM_STANDARD_CSV_TEMPLATE_VERSION:
        raise _contract_error(
            422,
            "TEAM_INGESTION_TEMPLATE_VERSION_UNSUPPORTED",
            f"template_version `{resolved}` is not supported",
            field="template_version",
        )
    return resolved


def preflight_saved_csv(
    path: Path,
    *,
    upload: UploadFile,
    size_bytes: int,
    detected_encoding: str,
    template_version: str | None,
) -> PreflightResult:
    validate_upload_metadata(upload)
    validate_template_version(template_version)
    if size_bytes <= 0:
        raise _contract_error(422, "TEAM_INGESTION_EMPTY_FILE", "uploaded CSV must not be empty")
    if size_bytes > TEAM_INGESTION_MAX_UPLOAD_BYTES:
        raise _contract_error(
            413,
            "TEAM_INGESTION_UPLOAD_TOO_LARGE",
            f"upload exceeds max size {TEAM_INGESTION_MAX_UPLOAD_BYTES} bytes",
        )
    if detected_encoding not in TEAM_INGESTION_ALLOWED_ENCODINGS:
        raise _contract_error(
            415,
            "TEAM_INGESTION_ENCODING_UNSUPPORTED",
            "only utf-8 and utf-8-sig encoded CSV files are supported",
        )

    with path.open("r", encoding=detected_encoding, newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader, None)
    normalized_headers = [str(item or "").strip() for item in list(headers or [])]
    if not normalized_headers:
        raise _contract_error(422, "TEAM_INGESTION_EMPTY_FILE", "uploaded CSV must include a header row")

    for contract_kind, expected_headers in STANDARD_CSV_CONTRACTS.items():
        if normalized_headers[: len(expected_headers)] == expected_headers:
            return PreflightResult(
                contract_kind=contract_kind,
                detected_encoding=detected_encoding,
                headers=normalized_headers,
                template_version=template_version or TEAM_STANDARD_CSV_TEMPLATE_VERSION,
            )

    raise _contract_error(
        422,
        "TEAM_INGESTION_CSV_CONTRACT_INVALID",
        "CSV header does not match the current Entity or REL2 standard import contract",
    )


def build_request_fingerprint(
    *,
    source_system: str,
    batch_id: str,
    created_by: str,
    template_version: str | None,
    contract_kind: str,
) -> str:
    payload = {
        "source_system": str(source_system or "").strip(),
        "batch_id": str(batch_id or "").strip(),
        "created_by": str(created_by or "").strip(),
        "template_version": str(template_version or "").strip(),
        "contract_kind": str(contract_kind or "").strip(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
