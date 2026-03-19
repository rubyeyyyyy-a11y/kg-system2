import csv
import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Optional

from fastapi import HTTPException
from fastapi import UploadFile

from app.config import settings
from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import (
    CleanupJobArtifactRecord,
    CleanupJobRecord,
    ImportBatchItemRecord,
    ImportBatchRecord,
    ImportDraft,
    ImportFileRecord,
    ImportJobState,
    JobEvent,
)

logger = logging.getLogger(__name__)
_BATCH_ITEM_LOCKS: dict[str, Lock] = {}

RUN_ROOT = Path(os.getenv("IMPORT_RUN_ROOT", str(settings.runtime_run_dir)))
STAGING_FILES_DIR = RUN_ROOT / "import-staging" / "files"
DRAFTS_DIR = RUN_ROOT / "import-drafts"
JOBS_DIR = RUN_ROOT / "import-jobs"
IMPORT_BATCHES_DIR = RUN_ROOT / "import-batches"
IMPORT_CLEANUP_JOBS_DIR = RUN_ROOT / "import-cleanup-jobs"
MAX_UPLOAD_BYTES = int(os.getenv("IMPORT_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
MAX_DRAFT_TOTAL_BYTES = int(os.getenv("IMPORT_MAX_DRAFT_TOTAL_BYTES", str(200 * 1024 * 1024)))
MAX_DRAFT_FILES = int(os.getenv("IMPORT_MAX_DRAFT_FILES", "5"))
MAX_JOB_ROWS = int(os.getenv("IMPORT_MAX_JOB_ROWS", "300000"))
MAX_SAMPLE_ROWS = int(os.getenv("IMPORT_MAX_SAMPLE_ROWS", "300"))
STAGING_RETENTION_SEC = int(os.getenv("IMPORT_STAGING_RETENTION_SEC", str(3 * 24 * 3600)))
JOB_ARTIFACT_RETENTION_SEC = int(os.getenv("IMPORT_JOB_ARTIFACT_RETENTION_SEC", str(7 * 24 * 3600)))
MAX_JOB_LOG_BYTES = int(os.getenv("IMPORT_MAX_JOB_LOG_BYTES", str(512 * 1024)))
MAX_JOB_EVENTS_BYTES = int(os.getenv("IMPORT_MAX_JOB_EVENTS_BYTES", str(512 * 1024)))
UPLOAD_STREAM_CHUNK_BYTES = int(os.getenv("IMPORT_UPLOAD_STREAM_CHUNK_BYTES", str(1024 * 1024)))
UPLOAD_DETECT_SAMPLE_BYTES = int(os.getenv("IMPORT_UPLOAD_DETECT_SAMPLE_BYTES", str(64 * 1024)))
ALLOWED_UPLOAD_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
    "application/octet-stream",
}


@dataclass
class BatchItemAppendResult:
    appended: bool
    item_key: str
    item_count: int
    entity_count: int
    relation_count: int
    items_jsonl_key_count: int


def ensure_import_dirs() -> None:
    STAGING_FILES_DIR.mkdir(parents=True, exist_ok=True)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    IMPORT_BATCHES_DIR.mkdir(parents=True, exist_ok=True)
    IMPORT_CLEANUP_JOBS_DIR.mkdir(parents=True, exist_ok=True)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _file_dir(file_id: str) -> Path:
    return STAGING_FILES_DIR / file_id


def file_meta_path(file_id: str) -> Path:
    return _file_dir(file_id) / "meta.json"


def staged_file_path(file_id: str) -> Path:
    return _file_dir(file_id) / "source.csv"


def draft_path(draft_id: str) -> Path:
    return DRAFTS_DIR / f"{draft_id}.json"


def job_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def job_state_path(job_id: str) -> Path:
    return job_dir(job_id) / "state.json"


def job_events_path(job_id: str) -> Path:
    return job_dir(job_id) / "events.jsonl"


def job_log_path(job_id: str) -> Path:
    return job_dir(job_id) / "job.log"


def job_failed_rows_path(job_id: str) -> Path:
    return job_dir(job_id) / "failed_rows.csv"


def job_normalized_rows_path(job_id: str) -> Path:
    return job_dir(job_id) / "normalized_rows.csv"


def job_target_failed_rows_path(job_id: str, target_id: str) -> Path:
    return job_artifacts_dir(job_id) / f"failed_rows.{target_id}.csv"


def job_target_normalized_rows_path(job_id: str, target_id: str) -> Path:
    return job_artifacts_dir(job_id) / f"normalized_rows.{target_id}.csv"


def job_target_summary_path(job_id: str, target_id: str) -> Path:
    return job_artifacts_dir(job_id) / f"summary.{target_id}.json"


def job_compiled_plan_path(job_id: str) -> Path:
    return job_dir(job_id) / "compiled_plan.json"


def job_input_dir(job_id: str) -> Path:
    return job_dir(job_id) / "input"


def job_artifacts_dir(job_id: str) -> Path:
    return job_dir(job_id) / "artifacts"


def batch_dir(batch_id: str) -> Path:
    return IMPORT_BATCHES_DIR / batch_id


def batch_state_path(batch_id: str) -> Path:
    return IMPORT_BATCHES_DIR / f"{batch_id}.json"


def batch_items_path(batch_id: str) -> Path:
    return batch_dir(batch_id) / "items.jsonl"


def batch_item_keys_path(batch_id: str) -> Path:
    return batch_dir(batch_id) / "item_keys.json"


def cleanup_job_path(cleanup_job_id: str) -> Path:
    return IMPORT_CLEANUP_JOBS_DIR / f"{cleanup_job_id}.json"


def cleanup_job_dir(cleanup_job_id: str) -> Path:
    return IMPORT_CLEANUP_JOBS_DIR / cleanup_job_id


def cleanup_job_artifacts_dir(cleanup_job_id: str) -> Path:
    return cleanup_job_dir(cleanup_job_id) / "artifacts"


def cleanup_job_artifact_path(cleanup_job_id: str, filename: str) -> Path:
    return cleanup_job_artifacts_dir(cleanup_job_id) / filename


def _detect_encoding(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin1"


def _detect_delimiter(sample_text: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",\t;|")
        return str(getattr(dialect, "delimiter", ",") or ",")
    except Exception:
        return ","


async def save_upload(upload: UploadFile) -> ImportFileRecord:
    ensure_import_dirs()
    _validate_upload_metadata(upload)
    file_id = new_id("file")
    file_dir = _file_dir(file_id)
    file_dir.mkdir(parents=True, exist_ok=True)
    staged = staged_file_path(file_id)
    staging_tmp = staged.with_suffix(".part")
    size_bytes = 0
    sample = bytearray()
    try:
        with staging_tmp.open("wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_STREAM_CHUNK_BYTES)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    raise_import_http_error(
                        status_code=413,
                        error_code="IMPORT_UPLOAD_TOO_LARGE",
                        message=f"upload exceeds max size {MAX_UPLOAD_BYTES} bytes",
                        field="file",
                        extra={"max_upload_bytes": MAX_UPLOAD_BYTES},
                    )
                if len(sample) < UPLOAD_DETECT_SAMPLE_BYTES:
                    remaining = UPLOAD_DETECT_SAMPLE_BYTES - len(sample)
                    sample.extend(chunk[:remaining])
                handle.write(chunk)
        encoding = _detect_encoding(bytes(sample))
        delimiter = _detect_delimiter(bytes(sample).decode(encoding, errors="replace")[:8192])
        staging_tmp.replace(staged)
        record = ImportFileRecord(
            file_id=file_id,
            original_name=upload.filename or "upload.csv",
            size_bytes=size_bytes,
            detected_delimiter=delimiter,
            detected_encoding=encoding,
            row_count=0,
            row_count_pending=True,
        )
        save_file_record(record)
        return record
    except HTTPException:
        shutil.rmtree(file_dir, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(file_dir, ignore_errors=True)
        raise
    finally:
        await upload.close()


def _validate_upload_metadata(upload: UploadFile) -> None:
    filename = str(upload.filename or "").strip()
    content_type = str(upload.content_type or "").strip().lower()
    if not filename.lower().endswith(".csv"):
        raise_import_http_error(
            status_code=415,
            error_code="IMPORT_UNSUPPORTED_FILE_TYPE",
            message="only .csv files are supported",
            field="file",
        )
    if content_type and content_type not in ALLOWED_UPLOAD_MIME_TYPES:
        raise_import_http_error(
            status_code=415,
            error_code="IMPORT_UNSUPPORTED_CONTENT_TYPE",
            message=f"unsupported upload content_type `{content_type}`",
            field="file",
            extra={"allowed_content_types": sorted(ALLOWED_UPLOAD_MIME_TYPES)},
        )


def load_file_record(file_id: str) -> ImportFileRecord:
    path = file_meta_path(file_id)
    if not path.exists():
        raise_import_http_error(
            status_code=404,
            error_code="IMPORT_FILE_NOT_FOUND",
            message=f"uploaded file `{file_id}` not found",
            field="file_id",
        )
    return ImportFileRecord.model_validate(read_json(path))


def save_file_record(record: ImportFileRecord) -> None:
    write_json(file_meta_path(record.file_id), record.model_dump())


def update_file_row_count(file_id: str, row_count: int) -> ImportFileRecord:
    record = load_file_record(file_id)
    record.row_count = max(0, int(row_count))
    record.row_count_pending = False
    save_file_record(record)
    return record


def iter_csv_rows(file_id: str) -> tuple[list[str], Iterable[dict[str, str]], ImportFileRecord]:
    record = load_file_record(file_id)
    path = staged_file_path(file_id)
    handle = path.open("r", encoding=record.detected_encoding, errors="replace", newline="")
    reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")

    def _generator() -> Iterable[dict[str, str]]:
        try:
            for row in reader:
                yield {str(k or ""): str(v or "") for k, v in row.items()}
        finally:
            handle.close()

    return list(reader.fieldnames or []), _generator(), record


def read_csv_columns(file_id: str) -> list[str]:
    record = load_file_record(file_id)
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        return list(reader.fieldnames or [])


def read_csv_sample(file_id: str, sample_rows: int) -> tuple[list[str], list[dict[str, str]], ImportFileRecord, bool]:
    record = load_file_record(file_id)
    out: list[dict[str, str]] = []
    limit = max(1, min(int(sample_rows), MAX_SAMPLE_ROWS))
    sample_truncated = False
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        columns = list(reader.fieldnames or [])
        for index, row in enumerate(reader, start=1):
            if index > limit:
                sample_truncated = True
                break
            out.append({str(k or ""): str(v or "") for k, v in row.items()})
    return columns, out, record, sample_truncated


def count_csv_rows(file_id: str) -> int:
    record = load_file_record(file_id)
    if not record.row_count_pending:
        return int(record.row_count)
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        count = sum(1 for _ in reader)
    return update_file_row_count(file_id, count).row_count


def read_csv_rows(file_id: str) -> tuple[list[str], list[dict[str, str]], ImportFileRecord]:
    record = load_file_record(file_id)
    rows: list[dict[str, str]] = []
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        columns = list(reader.fieldnames or [])
        for row in reader:
            rows.append({str(k or ""): str(v or "") for k, v in row.items()})
    return columns, rows, record


def read_csv_headers_from_path(path: Path, *, encoding: str, delimiter: str = ",") -> list[str]:
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return list(reader.fieldnames or [])


def read_csv_rows_from_path(path: Path, *, encoding: str, delimiter: str = ",") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        for row in reader:
            rows.append({str(key or ""): str(value or "") for key, value in row.items()})
    return rows


def sum_file_sizes(file_ids: list[str]) -> int:
    return sum(load_file_record(file_id).size_bytes for file_id in file_ids)


def _batch_item_lock(batch_id: str) -> Lock:
    lock = _BATCH_ITEM_LOCKS.get(batch_id)
    if lock is None:
        lock = Lock()
        _BATCH_ITEM_LOCKS[batch_id] = lock
    return lock


def _write_text_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)


def write_json(path: Path, payload: Any) -> None:
    _write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_draft(draft: ImportDraft) -> None:
    ensure_import_dirs()
    write_json(draft_path(draft.draft_id), draft.model_dump())


def load_draft(draft_id: str) -> ImportDraft:
    return ImportDraft.model_validate(read_json(draft_path(draft_id)))


def save_job_state(state: ImportJobState) -> None:
    write_json(job_state_path(state.job_id), state.model_dump())


def load_job_state(job_id: str) -> ImportJobState:
    return ImportJobState.model_validate(read_json(job_state_path(job_id)))


def save_batch_record(record: ImportBatchRecord) -> None:
    ensure_import_dirs()
    write_json(batch_state_path(record.batch_id), record.model_dump())


def load_batch_record(batch_id: str) -> ImportBatchRecord:
    return ImportBatchRecord.model_validate(read_json(batch_state_path(batch_id)))


def batch_items_exist(batch_id: str) -> bool:
    return batch_items_path(batch_id).exists()


def _batch_item_index_payload(items: list[ImportBatchItemRecord]) -> dict[str, Any]:
    keys = sorted({str(item.item_key or "") for item in items if str(item.item_key or "").strip()})
    return {
        "keys": keys,
        "entity_count": sum(1 for item in items if item.item_type == "entity"),
        "relation_count": sum(1 for item in items if item.item_type == "relation"),
        "updated_at": int(__import__("time").time()),
    }


def _read_batch_items_file(batch_id: str) -> list[ImportBatchItemRecord]:
    path = batch_items_path(batch_id)
    if not path.exists():
        return []
    items: list[ImportBatchItemRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        items.append(ImportBatchItemRecord.model_validate(json.loads(line)))
    return items


def load_batch_item_keys(batch_id: str, *, repair: bool = True) -> dict[str, Any]:
    items = _read_batch_items_file(batch_id)
    item_payload = _batch_item_index_payload(items)
    path = batch_item_keys_path(batch_id)
    if not path.exists():
        if repair:
            write_json(path, item_payload)
        return item_payload
    try:
        stored = dict(read_json(path) or {})
    except Exception:
        if repair:
            write_json(path, item_payload)
        return item_payload
    stored_keys = {str(item) for item in list(stored.get("keys") or []) if str(item).strip()}
    computed_keys = set(item_payload["keys"])
    merged = {
        "keys": sorted(stored_keys | computed_keys),
        "entity_count": max(int(stored.get("entity_count") or 0), int(item_payload["entity_count"] or 0)),
        "relation_count": max(int(stored.get("relation_count") or 0), int(item_payload["relation_count"] or 0)),
        "updated_at": int(__import__("time").time()),
    }
    if repair and (
        merged["keys"] != list(stored.get("keys") or [])
        or int(stored.get("entity_count") or 0) != merged["entity_count"]
        or int(stored.get("relation_count") or 0) != merged["relation_count"]
    ):
        write_json(path, merged)
    return merged


def get_batch_ledger_consistency(batch_id: str) -> dict[str, Any]:
    items = _read_batch_items_file(batch_id)
    keys_payload = load_batch_item_keys(batch_id, repair=False)
    items_jsonl_keys = [str(item.item_key or "") for item in items if str(item.item_key or "").strip()]
    unique_item_keys = sorted(set(items_jsonl_keys))
    index_keys = sorted({str(item) for item in list(keys_payload.get("keys") or []) if str(item).strip()})
    entity_count = sum(1 for item in items if item.item_type == "entity")
    relation_count = sum(1 for item in items if item.item_type == "relation")
    return {
        "ok": len(items_jsonl_keys) == len(index_keys) == len(unique_item_keys),
        "items_jsonl_count": len(items_jsonl_keys),
        "items_jsonl_unique_key_count": len(unique_item_keys),
        "item_key_count": len(index_keys),
        "entity_count": entity_count,
        "relation_count": relation_count,
        "warnings": [
            warning
            for warning in [
                None if len(items_jsonl_keys) == len(unique_item_keys) else "items.jsonl contains duplicate item keys",
                None if len(index_keys) == len(unique_item_keys) else "item key index count does not match items.jsonl unique keys",
            ]
            if warning
        ],
    }


def append_batch_item(record: ImportBatchItemRecord) -> None:
    ensure_import_dirs()
    path = batch_items_path(record.batch_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.model_dump(), ensure_ascii=False) + "\n")


def append_batch_item_if_absent(record: ImportBatchItemRecord) -> BatchItemAppendResult:
    ensure_import_dirs()
    normalized = ImportBatchItemRecord.model_validate(record.model_dump())
    with _batch_item_lock(normalized.batch_id):
        items = _read_batch_items_file(normalized.batch_id)
        keys_payload = load_batch_item_keys(normalized.batch_id, repair=False)
        existing_keys = {str(item.item_key or "") for item in items if str(item.item_key or "").strip()}
        existing_keys.update({str(item) for item in list(keys_payload.get("keys") or []) if str(item).strip()})
        if normalized.item_key in existing_keys:
            repaired_payload = _batch_item_index_payload(items)
            if sorted(existing_keys) != list(keys_payload.get("keys") or []):
                write_json(
                    batch_item_keys_path(normalized.batch_id),
                    {
                        "keys": sorted(existing_keys),
                        "entity_count": repaired_payload["entity_count"],
                        "relation_count": repaired_payload["relation_count"],
                        "updated_at": int(__import__("time").time()),
                    },
                )
            return BatchItemAppendResult(
                appended=False,
                item_key=str(normalized.item_key or ""),
                item_count=len(existing_keys),
                entity_count=repaired_payload["entity_count"],
                relation_count=repaired_payload["relation_count"],
                items_jsonl_key_count=len({str(item.item_key or "") for item in items if str(item.item_key or "").strip()}),
            )
        path = batch_items_path(normalized.batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized.model_dump(), ensure_ascii=False) + "\n")
        items.append(normalized)
        payload = _batch_item_index_payload(items)
        write_json(batch_item_keys_path(normalized.batch_id), payload)
        return BatchItemAppendResult(
            appended=True,
            item_key=str(normalized.item_key or ""),
            item_count=len(payload["keys"]),
            entity_count=int(payload["entity_count"] or 0),
            relation_count=int(payload["relation_count"] or 0),
            items_jsonl_key_count=len({str(item.item_key or "") for item in items if str(item.item_key or "").strip()}),
        )


def load_batch_items(batch_id: str) -> list[ImportBatchItemRecord]:
    return _read_batch_items_file(batch_id)


def list_batch_ids() -> list[str]:
    ensure_import_dirs()
    return sorted([path.stem for path in IMPORT_BATCHES_DIR.glob("*.json") if path.is_file()])


def list_batch_records() -> list[ImportBatchRecord]:
    records: list[ImportBatchRecord] = []
    for batch_id in list_batch_ids():
        try:
            records.append(load_batch_record(batch_id))
        except Exception:
            continue
    records.sort(key=lambda item: (item.created_at, item.batch_id), reverse=True)
    return records


def update_batch_record(batch_id: str, **changes) -> ImportBatchRecord:
    record = load_batch_record(batch_id)
    for key, value in changes.items():
        setattr(record, key, value)
    record.updated_at = int(__import__("time").time())
    save_batch_record(record)
    return record


def save_cleanup_job(record: CleanupJobRecord) -> None:
    ensure_import_dirs()
    write_json(cleanup_job_path(record.cleanup_job_id), record.model_dump())


def load_cleanup_job(cleanup_job_id: str) -> CleanupJobRecord:
    return CleanupJobRecord.model_validate(read_json(cleanup_job_path(cleanup_job_id)))


def list_cleanup_job_ids() -> list[str]:
    ensure_import_dirs()
    return sorted([path.stem for path in IMPORT_CLEANUP_JOBS_DIR.glob("*.json") if path.is_file()])


def list_cleanup_jobs() -> list[CleanupJobRecord]:
    records: list[CleanupJobRecord] = []
    for cleanup_job_id in list_cleanup_job_ids():
        try:
            records.append(load_cleanup_job(cleanup_job_id))
        except Exception:
            continue
    records.sort(key=lambda item: (item.created_at, item.cleanup_job_id), reverse=True)
    return records


def write_cleanup_job_artifact(cleanup_job_id: str, filename: str, payload: Any) -> CleanupJobArtifactRecord:
    ensure_import_dirs()
    path = cleanup_job_artifact_path(cleanup_job_id, filename)
    write_json(path, payload)
    kind = "summary"
    if filename == "conflicts.json":
        kind = "conflicts"
    elif filename == "skipped_entities.json":
        kind = "skipped_entities"
    elif filename == "skipped_relations.json":
        kind = "skipped_relations"
    elif filename == "verify_summary.json":
        kind = "verify_summary"
    elif filename == "plan_summary.json":
        kind = "plan_summary"
    elif filename == "blocked_entities.json":
        kind = "blocked_entities"
    elif filename == "deletable_entities.json":
        kind = "deletable_entities"
    elif filename == "deletable_relations.json":
        kind = "deletable_relations"
    return CleanupJobArtifactRecord(kind=kind, filename=filename, path=str(path))


def list_job_ids() -> list[str]:
    ensure_import_dirs()
    return sorted([p.name for p in JOBS_DIR.iterdir() if p.is_dir()])


def list_job_states() -> list[ImportJobState]:
    states: list[ImportJobState] = []
    for job_id in list_job_ids():
        try:
            states.append(load_job_state(job_id))
        except Exception:
            continue
    states.sort(key=lambda item: (item.created_at, item.job_id), reverse=True)
    return states


def append_job_event(job_id: str, event: JobEvent) -> None:
    path = job_events_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _append_limited_text(
        path,
        json.dumps(event.model_dump(), ensure_ascii=False) + "\n",
        MAX_JOB_EVENTS_BYTES,
        '{"level":"warn","message":"events truncated due to size limit"}\n',
    )


def append_job_log(job_id: str, message: str) -> None:
    path = job_log_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    _append_limited_text(
        path,
        message.rstrip() + "\n",
        MAX_JOB_LOG_BYTES,
        "[truncated] job.log reached size limit\n",
    )


def copy_inputs_to_job(job_id: str, file_ids: list[str], draft_payload: dict[str, Any], compiled_plan: dict[str, Any]) -> None:
    base = job_dir(job_id)
    (base / "input").mkdir(parents=True, exist_ok=True)
    (base / "artifacts").mkdir(parents=True, exist_ok=True)
    # The job snapshot becomes the execution truth source. Workers must read the
    # frozen draft snapshot + compiled_plan copy under .run/import-jobs/<job_id>/.
    write_json(base / "draft_snapshot.json", draft_payload)
    write_json(job_compiled_plan_path(job_id), compiled_plan)
    for file_id in file_ids:
        record = load_file_record(file_id)
        dst_dir = job_input_dir(job_id) / file_id
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(staged_file_path(file_id), dst_dir / "source.csv")
        write_json(dst_dir / "meta.json", record.model_dump())


def touch_job_csv(path: Path, headers: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()


def append_csv_row(path: Path, headers: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writerow({key: row.get(key, "") for key in headers})


def append_csv_rows(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def _append_limited_text(path: Path, payload: str, max_bytes: int, truncation_marker: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    marker_bytes = truncation_marker.encode("utf-8")
    payload_bytes = payload.encode("utf-8")
    existing_size = path.stat().st_size if path.exists() else 0
    if existing_size >= max_bytes:
        return False
    mode = "ab" if path.exists() else "wb"
    with path.open(mode) as handle:
        if existing_size + len(payload_bytes) > max_bytes:
            handle.write(marker_bytes[: max(0, max_bytes - existing_size)])
            return False
        handle.write(payload_bytes)
    return True


def load_job_log_lines(job_id: str, limit: int = 200) -> list[str]:
    path = job_log_path(job_id)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[-max(1, int(limit)) :]


def write_compiled_plan_copy(job_id: str, payload: dict[str, Any]) -> None:
    write_json(job_compiled_plan_path(job_id), payload)


def read_compiled_plan_copy(job_id: str) -> dict[str, Any]:
    return read_json(job_compiled_plan_path(job_id))


def cleanup_staging_files(now_ts: Optional[int] = None) -> list[str]:
    ensure_import_dirs()
    cutoff = int(now_ts or __import__("time").time()) - STAGING_RETENTION_SEC
    referenced = {
        file_id
        for draft_path_item in DRAFTS_DIR.glob("*.json")
        for file_id in _safe_read_file_ids(draft_path_item)
    }
    removed: list[str] = []
    for path in STAGING_FILES_DIR.iterdir():
        if not path.is_dir():
            continue
        stat_mtime = int(path.stat().st_mtime)
        if path.name in referenced or stat_mtime >= cutoff:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
    if removed:
        logger.info("imports_cleanup staging_removed=%d file_ids=%s", len(removed), ",".join(sorted(removed)))
    return removed


def cleanup_job_artifacts(now_ts: Optional[int] = None) -> list[str]:
    ensure_import_dirs()
    cutoff = int(now_ts or __import__("time").time()) - JOB_ARTIFACT_RETENTION_SEC
    removed: list[str] = []
    terminal = {"succeeded", "failed_import", "failed_postprocess", "cancelled"}
    for path in JOBS_DIR.iterdir():
        if not path.is_dir():
            continue
        try:
            state = ImportJobState.model_validate(read_json(path / "state.json"))
        except Exception:
            continue
        if state.status not in terminal:
            continue
        if int((path / "state.json").stat().st_mtime) >= cutoff:
            continue
        for rel in ["input", "artifacts", "job.log", "events.jsonl", "failed_rows.csv", "normalized_rows.csv"]:
            target = path / rel
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            elif target.exists():
                target.unlink(missing_ok=True)
        removed.append(path.name)
    if removed:
        logger.info("imports_cleanup job_artifacts_removed=%d job_ids=%s", len(removed), ",".join(sorted(removed)))
    return removed


def _safe_read_file_ids(path: Path) -> list[str]:
    try:
        payload = read_json(path)
        return list(payload.get("file_ids") or [])
    except Exception:
        return []
