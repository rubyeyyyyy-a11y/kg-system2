import csv
import json
import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import HTTPException
from fastapi import UploadFile

from app.services.imports.errors import raise_import_http_error
from app.services.imports.models import ImportDraft, ImportFileRecord, ImportJobState, JobEvent

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
RUN_ROOT = Path(__import__("os").getenv("IMPORT_RUN_ROOT", str(REPO_ROOT / ".run")))
STAGING_FILES_DIR = RUN_ROOT / "import-staging" / "files"
DRAFTS_DIR = RUN_ROOT / "import-drafts"
JOBS_DIR = RUN_ROOT / "import-jobs"
MAX_UPLOAD_BYTES = int(os.getenv("IMPORT_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
MAX_DRAFT_FILES = int(os.getenv("IMPORT_MAX_DRAFT_FILES", "5"))
MAX_JOB_ROWS = int(os.getenv("IMPORT_MAX_JOB_ROWS", "5000"))
MAX_SAMPLE_ROWS = int(os.getenv("IMPORT_MAX_SAMPLE_ROWS", "50"))
STAGING_RETENTION_SEC = int(os.getenv("IMPORT_STAGING_RETENTION_SEC", str(3 * 24 * 3600)))
JOB_ARTIFACT_RETENTION_SEC = int(os.getenv("IMPORT_JOB_ARTIFACT_RETENTION_SEC", str(7 * 24 * 3600)))
MAX_JOB_LOG_BYTES = int(os.getenv("IMPORT_MAX_JOB_LOG_BYTES", str(512 * 1024)))
MAX_JOB_EVENTS_BYTES = int(os.getenv("IMPORT_MAX_JOB_EVENTS_BYTES", str(512 * 1024)))
ALLOWED_UPLOAD_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "text/plain",
    "application/octet-stream",
}


def ensure_import_dirs() -> None:
    STAGING_FILES_DIR.mkdir(parents=True, exist_ok=True)
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


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


def job_compiled_plan_path(job_id: str) -> Path:
    return job_dir(job_id) / "compiled_plan.json"


def job_input_dir(job_id: str) -> Path:
    return job_dir(job_id) / "input"


def job_artifacts_dir(job_id: str) -> Path:
    return job_dir(job_id) / "artifacts"


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
    raw = await upload.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        shutil.rmtree(file_dir, ignore_errors=True)
        raise_import_http_error(
            status_code=413,
            error_code="IMPORT_UPLOAD_TOO_LARGE",
            message=f"upload exceeds max size {MAX_UPLOAD_BYTES} bytes",
            field="file",
            extra={"max_upload_bytes": MAX_UPLOAD_BYTES},
        )
    encoding = _detect_encoding(raw)
    decoded = raw.decode(encoding, errors="replace")
    delimiter = _detect_delimiter(decoded[:8192])
    staged = staged_file_path(file_id)
    staged.write_bytes(raw)
    row_count = _count_csv_rows_from_text(decoded, delimiter)
    if row_count > MAX_JOB_ROWS:
        shutil.rmtree(file_dir, ignore_errors=True)
        raise_import_http_error(
            status_code=413,
            error_code="IMPORT_ROW_LIMIT_EXCEEDED",
            message=f"csv row count exceeds max limit {MAX_JOB_ROWS}",
            field="file",
            extra={"max_job_rows": MAX_JOB_ROWS, "row_count": row_count},
        )
    record = ImportFileRecord(
        file_id=file_id,
        original_name=upload.filename or "upload.csv",
        size_bytes=len(raw),
        detected_delimiter=delimiter,
        detected_encoding=encoding,
        row_count=row_count,
    )
    write_json(file_meta_path(file_id), record.model_dump())
    return record


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


def _count_csv_rows_from_text(text: str, delimiter: str) -> int:
    import io

    handle = io.StringIO(text)
    reader = csv.DictReader(handle, delimiter=delimiter or ",")
    count = 0
    for _row in reader:
        count += 1
        if count > MAX_JOB_ROWS:
            return count
    return count


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


def iter_csv_rows(file_id: str) -> tuple[list[str], Iterable[dict[str, str]], ImportFileRecord]:
    record = load_file_record(file_id)
    path = staged_file_path(file_id)
    handle = path.open("r", encoding=record.detected_encoding, newline="")
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
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        return list(reader.fieldnames or [])


def read_csv_sample(file_id: str, sample_rows: int) -> tuple[list[str], list[dict[str, str]], ImportFileRecord]:
    record = load_file_record(file_id)
    out: list[dict[str, str]] = []
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        columns = list(reader.fieldnames or [])
        for index, row in enumerate(reader):
            if index >= max(1, min(int(sample_rows), MAX_SAMPLE_ROWS)):
                break
            out.append({str(k or ""): str(v or "") for k, v in row.items()})
    return columns, out, record


def count_csv_rows(file_id: str) -> int:
    record = load_file_record(file_id)
    if record.row_count > 0:
        return int(record.row_count)
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        count = sum(1 for _ in reader)
    record.row_count = count
    write_json(file_meta_path(file_id), record.model_dump())
    return count


def read_csv_rows(file_id: str) -> tuple[list[str], list[dict[str, str]], ImportFileRecord]:
    record = load_file_record(file_id)
    rows: list[dict[str, str]] = []
    with staged_file_path(file_id).open("r", encoding=record.detected_encoding, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=record.detected_delimiter or ",")
        columns = list(reader.fieldnames or [])
        for row in reader:
            rows.append({str(k or ""): str(v or "") for k, v in row.items()})
    return columns, rows, record


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
