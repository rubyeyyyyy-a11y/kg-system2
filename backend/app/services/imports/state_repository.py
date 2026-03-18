from __future__ import annotations

from typing import Protocol

from app.services.imports import file_store
from app.services.imports.models import CleanupJobRecord, ImportBatchItemRecord, ImportBatchRecord, ImportJobState


class ImportJobStateRepository(Protocol):
    def list(self) -> list[ImportJobState]: ...

    def load(self, job_id: str) -> ImportJobState: ...

    def save(self, state: ImportJobState) -> None: ...


class ImportBatchRepository(Protocol):
    def list(self) -> list[ImportBatchRecord]: ...

    def load(self, batch_id: str) -> ImportBatchRecord: ...

    def save(self, record: ImportBatchRecord) -> None: ...

    def update(self, batch_id: str, **changes) -> ImportBatchRecord: ...

    def load_items(self, batch_id: str) -> list[ImportBatchItemRecord]: ...

    def batch_items_exist(self, batch_id: str) -> bool: ...


class CleanupJobRepository(Protocol):
    def list(self) -> list[CleanupJobRecord]: ...

    def load(self, cleanup_job_id: str) -> CleanupJobRecord: ...

    def save(self, record: CleanupJobRecord) -> None: ...


class FileImportJobStateRepository:
    def list(self) -> list[ImportJobState]:
        return file_store.list_job_states()

    def load(self, job_id: str) -> ImportJobState:
        return file_store.load_job_state(job_id)

    def save(self, state: ImportJobState) -> None:
        file_store.save_job_state(state)


class FileImportBatchRepository:
    def list(self) -> list[ImportBatchRecord]:
        return file_store.list_batch_records()

    def load(self, batch_id: str) -> ImportBatchRecord:
        return file_store.load_batch_record(batch_id)

    def save(self, record: ImportBatchRecord) -> None:
        file_store.save_batch_record(record)

    def update(self, batch_id: str, **changes) -> ImportBatchRecord:
        return file_store.update_batch_record(batch_id, **changes)

    def load_items(self, batch_id: str) -> list[ImportBatchItemRecord]:
        return file_store.load_batch_items(batch_id)

    def batch_items_exist(self, batch_id: str) -> bool:
        return file_store.batch_items_exist(batch_id)


class FileCleanupJobRepository:
    def list(self) -> list[CleanupJobRecord]:
        return file_store.list_cleanup_jobs()

    def load(self, cleanup_job_id: str) -> CleanupJobRecord:
        return file_store.load_cleanup_job(cleanup_job_id)

    def save(self, record: CleanupJobRecord) -> None:
        file_store.save_cleanup_job(record)


import_job_states: ImportJobStateRepository = FileImportJobStateRepository()
import_batches: ImportBatchRepository = FileImportBatchRepository()
cleanup_jobs: CleanupJobRepository = FileCleanupJobRepository()
