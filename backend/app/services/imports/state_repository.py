from __future__ import annotations

from typing import Any, Protocol

from app.services.imports import file_store
from app.services.imports.models import CleanupJobArtifactRecord, CleanupJobRecord, ImportBatchItemRecord, ImportBatchRecord, ImportJobState


class ImportJobStateRepository(Protocol):
    def list(self) -> list[ImportJobState]: ...

    def load(self, job_id: str) -> ImportJobState: ...

    def save(self, state: ImportJobState) -> None: ...


class ImportBatchRepository(Protocol):
    def list(self) -> list[ImportBatchRecord]: ...

    def list_for_space(self, space_id: str) -> list[ImportBatchRecord]: ...

    def load(self, batch_id: str) -> ImportBatchRecord: ...

    def save(self, record: ImportBatchRecord) -> None: ...

    def update(self, batch_id: str, **changes) -> ImportBatchRecord: ...

    def load_items(self, batch_id: str) -> list[ImportBatchItemRecord]: ...

    def load_items_for_batches(self, batch_ids: list[str]) -> dict[str, list[ImportBatchItemRecord]]: ...

    def list_relation_items_for_space(self, space_id: str) -> list[ImportBatchItemRecord]: ...

    def batch_items_exist(self, batch_id: str) -> bool: ...


class CleanupJobRepository(Protocol):
    def list(self) -> list[CleanupJobRecord]: ...

    def list_for_space(self, space_id: str) -> list[CleanupJobRecord]: ...

    def load(self, cleanup_job_id: str) -> CleanupJobRecord: ...

    def save(self, record: CleanupJobRecord) -> None: ...

    def update(self, cleanup_job_id: str, **changes) -> CleanupJobRecord: ...


class CleanupStateRepository(Protocol):
    def next_cleanup_job_id(self) -> str: ...

    def list_batches(self, *, space_id: str | None = None) -> list[ImportBatchRecord]: ...

    def load_batch(self, batch_id: str) -> ImportBatchRecord: ...

    def load_batch_items(self, batch_id: str) -> list[ImportBatchItemRecord]: ...

    def load_batch_items_for_batches(self, batch_ids: list[str]) -> dict[str, list[ImportBatchItemRecord]]: ...

    def list_relation_items(self, *, space_id: str | None = None) -> list[ImportBatchItemRecord]: ...

    def batch_items_exist(self, batch_id: str) -> bool: ...

    def update_batch(self, batch_id: str, **changes) -> ImportBatchRecord: ...

    def update_batch_cleanup_statuses(self, batch_ids: list[str], cleanup_status: str) -> None: ...

    def list_cleanup_jobs(self, *, space_id: str | None = None) -> list[CleanupJobRecord]: ...

    def load_cleanup_job(self, cleanup_job_id: str) -> CleanupJobRecord: ...

    def save_cleanup_job(self, record: CleanupJobRecord) -> None: ...

    def update_cleanup_job(self, cleanup_job_id: str, **changes) -> CleanupJobRecord: ...

    def find_active_cleanup_job(self, *, space_id: str, request_key: str) -> CleanupJobRecord | None: ...

    def write_cleanup_job_artifact(
        self,
        cleanup_job_id: str,
        filename: str,
        payload: Any,
    ) -> CleanupJobArtifactRecord: ...


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

    def list_for_space(self, space_id: str) -> list[ImportBatchRecord]:
        return [record for record in self.list() if str(record.space_id or "") == str(space_id or "")]

    def load(self, batch_id: str) -> ImportBatchRecord:
        return file_store.load_batch_record(batch_id)

    def save(self, record: ImportBatchRecord) -> None:
        file_store.save_batch_record(record)

    def update(self, batch_id: str, **changes) -> ImportBatchRecord:
        return file_store.update_batch_record(batch_id, **changes)

    def load_items(self, batch_id: str) -> list[ImportBatchItemRecord]:
        return file_store.load_batch_items(batch_id)

    def load_items_for_batches(self, batch_ids: list[str]) -> dict[str, list[ImportBatchItemRecord]]:
        return {batch_id: self.load_items(batch_id) for batch_id in batch_ids}

    def list_relation_items_for_space(self, space_id: str) -> list[ImportBatchItemRecord]:
        relation_items: list[ImportBatchItemRecord] = []
        for batch in self.list_for_space(space_id):
            relation_items.extend([item for item in self.load_items(batch.batch_id) if item.item_type == "relation"])
        return relation_items

    def batch_items_exist(self, batch_id: str) -> bool:
        return file_store.batch_items_exist(batch_id)


class FileCleanupJobRepository:
    def list(self) -> list[CleanupJobRecord]:
        return file_store.list_cleanup_jobs()

    def list_for_space(self, space_id: str) -> list[CleanupJobRecord]:
        return [record for record in self.list() if str(record.space_id or "") == str(space_id or "")]

    def load(self, cleanup_job_id: str) -> CleanupJobRecord:
        return file_store.load_cleanup_job(cleanup_job_id)

    def save(self, record: CleanupJobRecord) -> None:
        file_store.save_cleanup_job(record)

    def update(self, cleanup_job_id: str, **changes) -> CleanupJobRecord:
        record = self.load(cleanup_job_id)
        for key, value in changes.items():
            setattr(record, key, value)
        file_store.save_cleanup_job(record)
        return record


class FileCleanupStateRepository:
    def next_cleanup_job_id(self) -> str:
        return file_store.new_id("cleanup")

    def list_batches(self, *, space_id: str | None = None) -> list[ImportBatchRecord]:
        if space_id is None:
            return import_batches.list()
        return import_batches.list_for_space(space_id)

    def load_batch(self, batch_id: str) -> ImportBatchRecord:
        return import_batches.load(batch_id)

    def load_batch_items(self, batch_id: str) -> list[ImportBatchItemRecord]:
        return import_batches.load_items(batch_id)

    def load_batch_items_for_batches(self, batch_ids: list[str]) -> dict[str, list[ImportBatchItemRecord]]:
        return import_batches.load_items_for_batches(batch_ids)

    def list_relation_items(self, *, space_id: str | None = None) -> list[ImportBatchItemRecord]:
        if space_id is None:
            relation_items: list[ImportBatchItemRecord] = []
            for batch in import_batches.list():
                relation_items.extend([item for item in import_batches.load_items(batch.batch_id) if item.item_type == "relation"])
            return relation_items
        return import_batches.list_relation_items_for_space(space_id)

    def batch_items_exist(self, batch_id: str) -> bool:
        return import_batches.batch_items_exist(batch_id)

    def update_batch(self, batch_id: str, **changes) -> ImportBatchRecord:
        return import_batches.update(batch_id, **changes)

    def update_batch_cleanup_statuses(self, batch_ids: list[str], cleanup_status: str) -> None:
        for batch_id in batch_ids:
            try:
                import_batches.update(batch_id, cleanup_status=cleanup_status)
            except Exception:
                continue

    def list_cleanup_jobs(self, *, space_id: str | None = None) -> list[CleanupJobRecord]:
        if space_id is None:
            return cleanup_jobs.list()
        return cleanup_jobs.list_for_space(space_id)

    def load_cleanup_job(self, cleanup_job_id: str) -> CleanupJobRecord:
        return cleanup_jobs.load(cleanup_job_id)

    def save_cleanup_job(self, record: CleanupJobRecord) -> None:
        cleanup_jobs.save(record)

    def update_cleanup_job(self, cleanup_job_id: str, **changes) -> CleanupJobRecord:
        return cleanup_jobs.update(cleanup_job_id, **changes)

    def find_active_cleanup_job(self, *, space_id: str, request_key: str) -> CleanupJobRecord | None:
        return next(
            (
                record
                for record in self.list_cleanup_jobs(space_id=space_id)
                if record.request_key == request_key and record.status in {"queued", "running"}
            ),
            None,
        )

    def write_cleanup_job_artifact(
        self,
        cleanup_job_id: str,
        filename: str,
        payload: Any,
    ) -> CleanupJobArtifactRecord:
        return file_store.write_cleanup_job_artifact(cleanup_job_id, filename, payload)


import_job_states: ImportJobStateRepository = FileImportJobStateRepository()
import_batches: ImportBatchRepository = FileImportBatchRepository()
cleanup_jobs: CleanupJobRepository = FileCleanupJobRepository()
cleanup_state: CleanupStateRepository = FileCleanupStateRepository()
