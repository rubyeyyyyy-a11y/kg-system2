from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


SubmissionStatus = Literal["accepted", "running", "succeeded", "failed", "conflicted"]


class TeamIngestionSubmissionResp(BaseModel):
    submission_id: str
    status: SubmissionStatus
    searchable: bool = False
    reused_existing_submission: bool = False
    source_system: str
    batch_id: str
    idempotency_key: str
    created_by: str
    submitted_at: str
    updated_at: Optional[str] = None
    job_id: Optional[str] = Field(
        default=None,
        description="Internal tracking field only. `submission_id` is the public primary key.",
    )
    draft_id: Optional[str] = Field(
        default=None,
        description="Internal tracking field only. `submission_id` is the public primary key.",
    )
    import_batch_id: Optional[str] = Field(
        default=None,
        description="Internal tracking field for imports batch registry linkage.",
    )
    job_status: Optional[str] = Field(
        default=None,
        description="Internal imports job status surfaced for debugging.",
    )
    failure_stage: Optional[str] = None
    completion_summary: Optional[Dict[str, Any]] = None
    index_status_snapshot: Optional[Dict[str, Any]] = None


class TeamIngestionFailureItem(BaseModel):
    row_number: Optional[int] = None
    raw_error: str = ""
    row_payload: Dict[str, str] = Field(default_factory=dict)
    target_id: Optional[str] = None
    target_object: Optional[str] = None
    source_id: Optional[str] = None
    truncated: bool = False


class TeamIngestionFailuresResp(BaseModel):
    submission_id: str
    job_id: Optional[str] = None
    total_failed_rows: int = 0
    items: list[TeamIngestionFailureItem] = Field(default_factory=list)


class TeamIngestionFailureSummary(BaseModel):
    failed_rows: int = 0
    failure_stage: Optional[str] = None
    error_message: Optional[str] = None


class TeamIngestionSubmissionRecord(BaseModel):
    submission_id: str
    source_system: str
    batch_id: str
    idempotency_key: str
    file_sha256: str
    request_fingerprint: str
    created_by: str
    principal: str
    space_name: str
    draft_id: Optional[str] = None
    job_id: Optional[str] = None
    import_batch_id: Optional[str] = None
    status: SubmissionStatus = "accepted"
    job_status_snapshot: Optional[str] = None
    searchable_snapshot: bool = False
    submitted_at: str
    updated_at: str
    template_version: Optional[str] = None
    contract_kind: Optional[Literal["entity_csv", "rel2_csv"]] = None
    failure_summary: Optional[TeamIngestionFailureSummary] = None


class TeamIngestionIdempotencyRecord(BaseModel):
    idempotency_key: str
    submission_id: str
    source_system: str
    batch_id: str
    file_sha256: str
    request_fingerprint: str
    created_at: str
    updated_at: str
