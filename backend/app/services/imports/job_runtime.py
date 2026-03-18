from __future__ import annotations

import time
from threading import Lock, Thread
from typing import Callable, Generic, TypeVar

RecordT = TypeVar("RecordT")


class QueuedWorkerRuntime(Generic[RecordT]):
    def __init__(
        self,
        *,
        worker_name: str,
        list_records: Callable[[], list[RecordT]],
        run_record: Callable[[RecordT], None],
        record_id: Callable[[RecordT], str],
        sort_key: Callable[[RecordT], tuple],
        queued_status: str = "queued",
        poll_interval_sec: float = 0.3,
    ):
        self._worker_name = worker_name
        self._list_records = list_records
        self._run_record = run_record
        self._record_id = record_id
        self._sort_key = sort_key
        self._queued_status = queued_status
        self._poll_interval_sec = poll_interval_sec
        self._worker_lock = Lock()
        self._worker_thread: Thread | None = None

    def _is_queued(self, record: RecordT) -> bool:
        return str(getattr(record, "status", "")) == self._queued_status

    def next_queued_record(self) -> RecordT | None:
        for record in sorted(self._list_records(), key=self._sort_key):
            if self._is_queued(record):
                return record
        return None

    def has_queued_records(self) -> bool:
        return any(self._is_queued(record) for record in self._list_records())

    def drain_queue(self) -> None:
        if not self._worker_lock.acquire(blocking=False):
            return
        try:
            while True:
                next_record = self.next_queued_record()
                if next_record is None:
                    return
                self._run_record(next_record)
        finally:
            self._worker_lock.release()

    def _worker_main(self) -> None:
        while True:
            if not self.has_queued_records():
                return
            self.drain_queue()
            time.sleep(self._poll_interval_sec)

    def ensure_worker_running(self) -> None:
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_thread = Thread(target=self._worker_main, name=self._worker_name, daemon=True)
        self._worker_thread.start()

    def startup_recover_and_start(self, *, recover_interrupted: Callable[[], list[RecordT]]) -> list[RecordT]:
        repaired = recover_interrupted()
        if self.has_queued_records():
            self.ensure_worker_running()
        return repaired

    def running(self) -> bool:
        return bool(self._worker_thread and self._worker_thread.is_alive())
