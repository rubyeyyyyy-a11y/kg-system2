from __future__ import annotations

import csv
import time
from typing import Any, Iterable, Protocol

from app.services.imports import file_store
from app.services.imports.models import (
    CleanupJobArtifactRecord,
    CleanupJobRecord,
    CompiledTargetPlan,
    DraftSource,
    ImportBatchItemRecord,
    ImportBatchRecord,
    ImportJobState,
    JobArtifact,
    JobEvent,
)


class ImportJobStateRepository(Protocol):
    def next_job_id(self) -> str: ...

    def next_batch_id(self) -> str: ...

    def list(self) -> list[ImportJobState]: ...

    def load(self, job_id: str) -> ImportJobState: ...

    def save(self, state: ImportJobState) -> None: ...

    def update(self, job_id: str, **changes) -> ImportJobState: ...

    def compiled_plan_path(self, job_id: str) -> str: ...

    def failed_rows_path(self, job_id: str) -> str: ...

    def normalized_rows_path(self, job_id: str) -> str: ...

    def write_execution_snapshot(
        self,
        job_id: str,
        *,
        file_ids: list[str],
        draft_payload: dict[str, Any],
        compiled_plan: dict[str, Any],
    ) -> None: ...

    def load_compiled_plan_payload(self, job_id: str) -> dict[str, Any]: ...

    def build_job_artifacts(self, job_id: str, targets: list[CompiledTargetPlan]) -> list[JobArtifact]: ...

    def append_event(self, job_id: str, event: JobEvent) -> None: ...

    def append_log(self, job_id: str, message: str) -> None: ...

    def load_input_source(self, job_id: str, file_id: str, source_id: str) -> DraftSource: ...

    def iter_input_rows(self, job_id: str, file_id: str) -> Iterable[tuple[dict[str, str], list[str]]]: ...


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

    def append_item_if_absent(self, record: ImportBatchItemRecord) -> file_store.BatchItemAppendResult: ...

    def get_ledger_consistency(self, batch_id: str) -> dict[str, Any]: ...

    def persist_ledger_summary(
        self,
        batch_id: str,
        *,
        entity_count: int,
        relation_count: int,
        ledger_summary: dict[str, Any],
        ledger_warnings: list[str],
        **changes,
    ) -> ImportBatchRecord: ...


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
    def next_job_id(self) -> str:
        return file_store.new_id("job")

    def next_batch_id(self) -> str:
        return file_store.new_id("batch")

    def list(self) -> list[ImportJobState]:
        return file_store.list_job_states()

    def load(self, job_id: str) -> ImportJobState:
        return file_store.load_job_state(job_id)

    def save(self, state: ImportJobState) -> None:
        file_store.save_job_state(state)

    def update(self, job_id: str, **changes) -> ImportJobState:
        state = self.load(job_id)
        for key, value in changes.items():
            setattr(state, key, value)
        state.updated_at = int(time.time())
        self.save(state)
        return state

    def compiled_plan_path(self, job_id: str) -> str:
        return str(file_store.job_compiled_plan_path(job_id))

    def failed_rows_path(self, job_id: str) -> str:
        return str(file_store.job_failed_rows_path(job_id))

    def normalized_rows_path(self, job_id: str) -> str:
        return str(file_store.job_normalized_rows_path(job_id))

    def write_execution_snapshot(
        self,
        job_id: str,
        *,
        file_ids: list[str],
        draft_payload: dict[str, Any],
        compiled_plan: dict[str, Any],
    ) -> None:
        file_store.copy_inputs_to_job(job_id, file_ids, draft_payload, compiled_plan)

    def load_compiled_plan_payload(self, job_id: str) -> dict[str, Any]:
        return file_store.read_compiled_plan_copy(job_id)

    def build_job_artifacts(self, job_id: str, targets: list[CompiledTargetPlan]) -> list[JobArtifact]:
        artifacts: list[JobArtifact] = []
        for target in targets:
            artifacts.extend(
                [
                    JobArtifact(
                        target_id=target.target_id,
                        source_id=target.source_id,
                        kind="normalized_rows",
                        filename=file_store.job_target_normalized_rows_path(job_id, target.target_id).name,
                        path=str(file_store.job_target_normalized_rows_path(job_id, target.target_id)),
                    ),
                    JobArtifact(
                        target_id=target.target_id,
                        source_id=target.source_id,
                        kind="failed_rows",
                        filename=file_store.job_target_failed_rows_path(job_id, target.target_id).name,
                        path=str(file_store.job_target_failed_rows_path(job_id, target.target_id)),
                    ),
                    JobArtifact(
                        target_id=target.target_id,
                        source_id=target.source_id,
                        kind="summary",
                        filename=file_store.job_target_summary_path(job_id, target.target_id).name,
                        path=str(file_store.job_target_summary_path(job_id, target.target_id)),
                    ),
                ]
            )
        return artifacts

    def append_event(self, job_id: str, event: JobEvent) -> None:
        file_store.append_job_event(job_id, event)

    def append_log(self, job_id: str, message: str) -> None:
        file_store.append_job_log(job_id, message)

    def load_input_source(self, job_id: str, file_id: str, source_id: str) -> DraftSource:
        meta = file_store.read_json(file_store.job_input_dir(job_id) / file_id / "meta.json")
        path = file_store.job_input_dir(job_id) / file_id / "source.csv"
        with path.open("r", encoding=str(meta.get("detected_encoding") or "utf-8"), errors="replace", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=str(meta.get("detected_delimiter") or ","))
            columns = list(reader.fieldnames or [])
        return DraftSource(
            source_id=source_id,
            file_id=file_id,
            filename=str(meta.get("original_name") or f"{file_id}.csv"),
            columns=columns,
            sample_rows=[],
            header_hash="",
            inferred_kind="unknown",
            warnings=[],
            alias_hints=[],
            recommended_object_type=None,
        )

    def iter_input_rows(self, job_id: str, file_id: str) -> Iterable[tuple[dict[str, str], list[str]]]:
        meta = file_store.read_json(file_store.job_input_dir(job_id) / file_id / "meta.json")
        path = file_store.job_input_dir(job_id) / file_id / "source.csv"
        handle = path.open("r", encoding=str(meta.get("detected_encoding") or "utf-8"), errors="replace", newline="")
        reader = csv.DictReader(handle, delimiter=str(meta.get("detected_delimiter") or ","))

        def _iter() -> Iterable[tuple[dict[str, str], list[str]]]:
            try:
                for row in reader:
                    yield {str(k or ""): str(v or "") for k, v in row.items()}, list(reader.fieldnames or [])
            finally:
                handle.close()

        return _iter()


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

    def append_item_if_absent(self, record: ImportBatchItemRecord) -> file_store.BatchItemAppendResult:
        return file_store.append_batch_item_if_absent(record)

    def get_ledger_consistency(self, batch_id: str) -> dict[str, Any]:
        return file_store.get_batch_ledger_consistency(batch_id)

    def persist_ledger_summary(
        self,
        batch_id: str,
        *,
        entity_count: int,
        relation_count: int,
        ledger_summary: dict[str, Any],
        ledger_warnings: list[str],
        **changes,
    ) -> ImportBatchRecord:
        record = self.load(batch_id)
        warning_messages = list(record.warning_messages or [])
        for warning in ledger_warnings:
            if warning not in warning_messages:
                warning_messages.append(warning)
        return self.update(
            batch_id,
            entity_count=entity_count,
            relation_count=relation_count,
            ledger_summary=ledger_summary,
            warning_messages=warning_messages,
            **changes,
        )


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
