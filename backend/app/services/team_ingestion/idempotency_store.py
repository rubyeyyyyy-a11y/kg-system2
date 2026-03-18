from __future__ import annotations

import hashlib
import json
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, TypeVar

import fcntl
from fastapi import HTTPException

from app.schemas.team_ingestion import (
    TeamIngestionIdempotencyRecord,
    TeamIngestionSubmissionRecord,
)
from app.services.imports import file_store

T = TypeVar("T")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def team_ingestion_root() -> Path:
    return file_store.RUN_ROOT / "team-ingestion"


def submissions_dir() -> Path:
    return team_ingestion_root() / "submissions"


def idempotency_dir() -> Path:
    return team_ingestion_root() / "idempotency"


def lock_path() -> Path:
    return team_ingestion_root() / "store.lock"


def ensure_store_dirs() -> None:
    submissions_dir().mkdir(parents=True, exist_ok=True)
    idempotency_dir().mkdir(parents=True, exist_ok=True)


def new_submission_id() -> str:
    return f"submission_{uuid.uuid4().hex[:12]}"


def submission_path(submission_id: str) -> Path:
    return submissions_dir() / f"{submission_id}.json"


def _idempotency_file_name(idempotency_key: str) -> str:
    digest = hashlib.sha256(str(idempotency_key or "").encode("utf-8")).hexdigest()
    return f"{digest}.json"


def idempotency_path(idempotency_key: str) -> Path:
    return idempotency_dir() / _idempotency_file_name(idempotency_key)


@contextmanager
def _store_lock():
    ensure_store_dirs()
    with lock_path().open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        tmp_path = Path(handle.name)
        handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
        handle.flush()
    tmp_path.replace(path)


def load_submission(submission_id: str) -> TeamIngestionSubmissionRecord:
    path = submission_path(submission_id)
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "TEAM_INGESTION_SUBMISSION_NOT_FOUND",
                "message": f"submission `{submission_id}` not found",
                "field": "submission_id",
            },
        )
    return TeamIngestionSubmissionRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def save_submission(record: TeamIngestionSubmissionRecord) -> TeamIngestionSubmissionRecord:
    with _store_lock():
        _write_json_atomic(submission_path(record.submission_id), record.model_dump())
    return record


def _load_idempotency_record_unlocked(idempotency_key: str) -> TeamIngestionIdempotencyRecord | None:
    path = idempotency_path(idempotency_key)
    if not path.exists():
        return None
    return TeamIngestionIdempotencyRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _save_idempotency_record_unlocked(record: TeamIngestionIdempotencyRecord) -> None:
    _write_json_atomic(idempotency_path(record.idempotency_key), record.model_dump())


def mutate_submission(submission_id: str, mutator: Callable[[TeamIngestionSubmissionRecord], T]) -> T:
    with _store_lock():
        record = load_submission(submission_id)
        result = mutator(record)
        _write_json_atomic(submission_path(record.submission_id), record.model_dump())
        return result


def reserve_submission(
    *,
    source_system: str,
    batch_id: str,
    idempotency_key: str,
    file_sha256: str,
    request_fingerprint: str,
    created_by: str,
    principal: str,
    space_name: str,
    template_version: str | None,
    contract_kind: str,
) -> tuple[TeamIngestionSubmissionRecord, bool]:
    now = _now_iso()
    with _store_lock():
        existing = _load_idempotency_record_unlocked(idempotency_key)
        if existing is not None:
            if (
                existing.source_system == source_system
                and existing.batch_id == batch_id
                and existing.file_sha256 == file_sha256
                and existing.request_fingerprint == request_fingerprint
            ):
                record = load_submission(existing.submission_id)
                return record, True
            raise HTTPException(
                status_code=409,
                detail={
                    "error_code": "TEAM_INGESTION_IDEMPOTENCY_CONFLICT",
                    "message": "idempotency_key was already used for a different file or request fingerprint",
                    "field": "idempotency_key",
                },
            )

        record = TeamIngestionSubmissionRecord(
            submission_id=new_submission_id(),
            source_system=source_system,
            batch_id=batch_id,
            idempotency_key=idempotency_key,
            file_sha256=file_sha256,
            request_fingerprint=request_fingerprint,
            created_by=created_by,
            principal=principal,
            space_name=space_name,
            submitted_at=now,
            updated_at=now,
            template_version=template_version,
            contract_kind=contract_kind,
            status="accepted",
            job_status_snapshot=None,
            searchable_snapshot=False,
        )
        _write_json_atomic(submission_path(record.submission_id), record.model_dump())
        _save_idempotency_record_unlocked(
            TeamIngestionIdempotencyRecord(
                idempotency_key=idempotency_key,
                submission_id=record.submission_id,
                source_system=source_system,
                batch_id=batch_id,
                file_sha256=file_sha256,
                request_fingerprint=request_fingerprint,
                created_at=now,
                updated_at=now,
            )
        )
        return record, False
