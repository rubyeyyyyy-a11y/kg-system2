from __future__ import annotations

import codecs
import hashlib
import shutil
import time
from dataclasses import dataclass

from fastapi import HTTPException, UploadFile

from app.schemas.team_ingestion import (
    TeamIngestionFailureSummary,
    TeamIngestionSubmissionRecord,
    TeamIngestionSubmissionResp,
)
from app.services.imports import draft_service, executor_service, file_store, job_service
from app.services.imports.models import ImportFileRecord, ImportJobState
from app.services.spaces import validation_service
from app.services.team_ingestion import contract_service, idempotency_store
from app.services.team_ingestion.adapters.standard_csv_to_draft import build_system_managed_draft_payload


TEAM_INGESTION_SPACE_NAME = "demo_kg"
_UTF8_BOM = b"\xef\xbb\xbf"


@dataclass(frozen=True)
class StreamedUpload:
    file_id: str
    size_bytes: int
    file_sha256: str
    detected_encoding: str


def _submission_error(status_code: int, error_code: str, message: str, field: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "message": message,
            "field": field,
        },
    )


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _aggregate_submission_status(job_status: str | None, searchable: bool) -> str:
    if not job_status:
        return "accepted"
    if job_status == "queued":
        return "accepted"
    if job_status in {"running", "post_metadata_refresh", "post_es_sync", "post_verify_index"}:
        return "running"
    if job_status == "succeeded":
        return "succeeded" if searchable else "failed"
    return "failed"


def _searchable_from_job(job: ImportJobState | None) -> bool:
    if job is None or job.completion_summary is None:
        return False
    return bool(job.completion_summary.searchable)


async def _stream_upload_to_import_staging(upload: UploadFile) -> StreamedUpload:
    contract_service.validate_upload_metadata(upload)
    file_store.ensure_import_dirs()
    file_id = file_store.new_id("file")
    file_dir = file_store._file_dir(file_id)
    file_dir.mkdir(parents=True, exist_ok=True)
    staged = file_store.staged_file_path(file_id)
    staging_tmp = staged.with_suffix(".part")

    size_bytes = 0
    file_sha256 = hashlib.sha256()
    decoder = codecs.getincrementaldecoder("utf-8")()
    bom_probe = bytearray()
    bom_decided = False
    detected_encoding = "utf-8"

    try:
        with staging_tmp.open("wb") as handle:
            while True:
                chunk = await upload.read(file_store.UPLOAD_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > contract_service.TEAM_INGESTION_MAX_UPLOAD_BYTES:
                    raise _submission_error(
                        413,
                        "TEAM_INGESTION_UPLOAD_TOO_LARGE",
                        f"upload exceeds max size {contract_service.TEAM_INGESTION_MAX_UPLOAD_BYTES} bytes",
                        "file",
                    )
                file_sha256.update(chunk)
                handle.write(chunk)

                if not bom_decided:
                    bom_probe.extend(chunk)
                    if len(bom_probe) < len(_UTF8_BOM):
                        continue
                    if bom_probe.startswith(_UTF8_BOM):
                        detected_encoding = "utf-8-sig"
                        decode_bytes = bytes(bom_probe[len(_UTF8_BOM) :])
                    else:
                        detected_encoding = "utf-8"
                        decode_bytes = bytes(bom_probe)
                    bom_decided = True
                    bom_probe.clear()
                else:
                    decode_bytes = chunk

                try:
                    decoder.decode(decode_bytes, final=False)
                except UnicodeDecodeError as exc:
                    raise _submission_error(
                        415,
                        "TEAM_INGESTION_ENCODING_UNSUPPORTED",
                        "only utf-8 and utf-8-sig encoded CSV files are supported",
                        "file",
                    ) from exc

            if not bom_decided:
                raw = bytes(bom_probe)
                if raw.startswith(_UTF8_BOM):
                    detected_encoding = "utf-8-sig"
                    raw = raw[len(_UTF8_BOM) :]
                try:
                    decoder.decode(raw, final=True)
                except UnicodeDecodeError as exc:
                    raise _submission_error(
                        415,
                        "TEAM_INGESTION_ENCODING_UNSUPPORTED",
                        "only utf-8 and utf-8-sig encoded CSV files are supported",
                        "file",
                    ) from exc
            else:
                try:
                    decoder.decode(b"", final=True)
                except UnicodeDecodeError as exc:
                    raise _submission_error(
                        415,
                        "TEAM_INGESTION_ENCODING_UNSUPPORTED",
                        "only utf-8 and utf-8-sig encoded CSV files are supported",
                        "file",
                    ) from exc

        staging_tmp.replace(staged)
        file_store.save_file_record(
            ImportFileRecord(
                file_id=file_id,
                original_name=upload.filename or "upload.csv",
                size_bytes=size_bytes,
                detected_delimiter=",",
                detected_encoding=detected_encoding,
                row_count=0,
                row_count_pending=True,
            )
        )
        return StreamedUpload(
            file_id=file_id,
            size_bytes=size_bytes,
            file_sha256=file_sha256.hexdigest(),
            detected_encoding=detected_encoding,
        )
    except Exception:
        shutil.rmtree(file_dir, ignore_errors=True)
        raise
    finally:
        await upload.close()


def _refresh_submission_record(record: TeamIngestionSubmissionRecord) -> TeamIngestionSubmissionRecord:
    if not record.job_id:
        return record

    state = job_service.get_job(record.job_id)
    searchable = _searchable_from_job(state)
    next_record = record.model_copy(
        update={
            "status": _aggregate_submission_status(state.status, searchable),
            "job_status_snapshot": state.status,
            "searchable_snapshot": searchable,
            "updated_at": _now_iso(),
            "failure_summary": TeamIngestionFailureSummary(
                failed_rows=int(state.failed_rows or 0),
                failure_stage=state.failure_stage,
                error_message=state.error_message,
            ),
        }
    )
    return next_record


def _submission_response(
    record: TeamIngestionSubmissionRecord,
    *,
    reused_existing_submission: bool,
    state: ImportJobState | None = None,
) -> TeamIngestionSubmissionResp:
    resolved_state = state
    if resolved_state is None and record.job_id:
        resolved_state = job_service.get_job(record.job_id)
    searchable = _searchable_from_job(resolved_state)
    job_status = resolved_state.status if resolved_state is not None else record.job_status_snapshot
    status = _aggregate_submission_status(job_status, searchable)
    return TeamIngestionSubmissionResp(
        submission_id=record.submission_id,
        status=status,
        searchable=searchable,
        reused_existing_submission=reused_existing_submission,
        source_system=record.source_system,
        batch_id=record.batch_id,
        idempotency_key=record.idempotency_key,
        created_by=record.created_by,
        submitted_at=record.submitted_at,
        updated_at=record.updated_at,
        job_id=record.job_id,
        draft_id=record.draft_id,
        import_batch_id=record.import_batch_id,
        job_status=job_status,
        failure_stage=resolved_state.failure_stage if resolved_state is not None else record.failure_summary.failure_stage if record.failure_summary else None,
        completion_summary=None if resolved_state is None or resolved_state.completion_summary is None else resolved_state.completion_summary.model_dump(),
        index_status_snapshot=(
            None
            if resolved_state is None or resolved_state.index_status_snapshot is None
            else resolved_state.index_status_snapshot.model_dump()
        ),
    )


def get_submission(submission_id: str) -> TeamIngestionSubmissionResp:
    validation_service.ensure_space_ready(TEAM_INGESTION_SPACE_NAME)
    record = idempotency_store.load_submission(submission_id)
    refreshed = _refresh_submission_record(record)
    if refreshed != record:
        idempotency_store.save_submission(refreshed)
    return _submission_response(refreshed, reused_existing_submission=False)


async def create_submission(
    *,
    upload: UploadFile,
    source_system: str,
    batch_id: str,
    idempotency_key: str,
    created_by: str,
    principal: str,
    template_version: str | None,
) -> TeamIngestionSubmissionResp:
    validation_service.ensure_space_ready(TEAM_INGESTION_SPACE_NAME)
    streamed = await _stream_upload_to_import_staging(upload)
    preflight = contract_service.preflight_saved_csv(
        file_store.staged_file_path(streamed.file_id),
        upload=upload,
        size_bytes=streamed.size_bytes,
        detected_encoding=streamed.detected_encoding,
        template_version=template_version,
    )
    request_fingerprint = contract_service.build_request_fingerprint(
        source_system=source_system,
        batch_id=batch_id,
        created_by=created_by,
        template_version=preflight.template_version,
        contract_kind=preflight.contract_kind,
    )
    record, reused = idempotency_store.reserve_submission(
        source_system=source_system,
        batch_id=batch_id,
        idempotency_key=idempotency_key,
        file_sha256=streamed.file_sha256,
        request_fingerprint=request_fingerprint,
        created_by=created_by,
        principal=principal,
        space_name=TEAM_INGESTION_SPACE_NAME,
        template_version=preflight.template_version,
        contract_kind=preflight.contract_kind,
    )
    if reused:
        refreshed = _refresh_submission_record(record)
        if refreshed != record:
            idempotency_store.save_submission(refreshed)
        return _submission_response(refreshed, reused_existing_submission=True)

    draft = None
    try:
        draft_payload = build_system_managed_draft_payload(
            file_id=streamed.file_id,
            contract_kind=preflight.contract_kind,
            space_name=TEAM_INGESTION_SPACE_NAME,
        )
        draft = draft_service.upsert_draft(draft_payload)
        job_state = job_service.create_job(
            draft_id=draft.draft_id,
            created_by=created_by,
            source_type="team_ingestion",
            is_test_data=False,
            submission_id=record.submission_id,
        )
        executor_service.ensure_worker_running()
        try:
            job_state = job_service.get_job(job_state.job_id)
        except Exception:
            pass
        updated = record.model_copy(
            update={
                "draft_id": draft.draft_id,
                "job_id": job_state.job_id,
                "import_batch_id": job_state.batch_id,
                "status": _aggregate_submission_status(job_state.status, _searchable_from_job(job_state)),
                "job_status_snapshot": job_state.status,
                "searchable_snapshot": _searchable_from_job(job_state),
                "updated_at": _now_iso(),
                "failure_summary": TeamIngestionFailureSummary(
                    failed_rows=int(job_state.failed_rows or 0),
                    failure_stage=job_state.failure_stage,
                    error_message=job_state.error_message,
                ),
            }
        )
        idempotency_store.save_submission(updated)
        return _submission_response(updated, reused_existing_submission=False, state=job_state)
    except HTTPException as exc:
        failed_record = record.model_copy(
            update={
                "draft_id": draft.draft_id if draft is not None else record.draft_id,
                "status": "failed",
                "updated_at": _now_iso(),
                "failure_summary": TeamIngestionFailureSummary(error_message=str(exc.detail)),
            }
        )
        idempotency_store.save_submission(failed_record)
        raise
    except Exception as exc:
        failed_record = record.model_copy(
            update={
                "draft_id": draft.draft_id if draft is not None else record.draft_id,
                "status": "failed",
                "updated_at": _now_iso(),
                "failure_summary": TeamIngestionFailureSummary(error_message=str(exc)),
            }
        )
        idempotency_store.save_submission(failed_record)
        raise
