"""
Team-ingestion V1 is a thin automation gateway over the existing formal imports
pipeline. It only supports `demo_kg`, requires auth, rejects external
`X-KG-Space`, and preserves the imports completion standard:

- internal `job_status == succeeded`
- `completion_summary.searchable == true`

V1 also inherits the current executor runtime model: the imports executor is a
single-process in-memory worker queue. Multi-process or multi-replica
deployment will require a future job claim/lease mechanism before this gateway
can promise safe distributed execution semantics.
"""

from fastapi import APIRouter, File, Form, HTTPException, Request, Security, UploadFile

from app.core.space_context import SPACE_HEADER, use_space
from app.schemas.team_ingestion import TeamIngestionFailuresResp, TeamIngestionSubmissionResp
from app.services.team_ingestion import auth, failures_service, gateway_service, idempotency_store
from app.services.team_ingestion.contract_service import reject_blank_text


router = APIRouter(prefix="/api/v1/team-ingestion", tags=["team-ingestion"])


def _bind_demo_space(request: Request) -> None:
    if request.headers.get(SPACE_HEADER) is not None:
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "TEAM_INGESTION_SPACE_HEADER_REJECTED",
                "message": "team-ingestion V1 rejects external X-KG-Space and always executes in demo_kg",
                "field": SPACE_HEADER,
            },
        )
    request.state.space_name = gateway_service.TEAM_INGESTION_SPACE_NAME


@router.post("/submissions", response_model=TeamIngestionSubmissionResp)
async def create_submission(
    request: Request,
    file: UploadFile = File(...),
    source_system: str = Form(...),
    batch_id: str = Form(...),
    idempotency_key: str = Form(...),
    created_by: str = Form(...),
    template_version: str | None = Form(default=None),
    auth_principal: auth.TeamIngestionPrincipal = Security(auth.require_team_ingestion_principal),
):
    _bind_demo_space(request)
    with use_space(gateway_service.TEAM_INGESTION_SPACE_NAME):
        return await gateway_service.create_submission(
            upload=file,
            source_system=reject_blank_text(source_system, field="source_system"),
            batch_id=reject_blank_text(batch_id, field="batch_id"),
            idempotency_key=reject_blank_text(idempotency_key, field="idempotency_key"),
            created_by=reject_blank_text(created_by, field="created_by"),
            principal=auth_principal.principal,
            template_version=template_version,
        )


@router.get("/submissions/{submission_id}", response_model=TeamIngestionSubmissionResp)
def get_submission(
    submission_id: str,
    request: Request,
    _auth_principal: auth.TeamIngestionPrincipal = Security(auth.require_team_ingestion_principal),
):
    _bind_demo_space(request)
    with use_space(gateway_service.TEAM_INGESTION_SPACE_NAME):
        return gateway_service.get_submission(submission_id)


@router.get("/submissions/{submission_id}/failures", response_model=TeamIngestionFailuresResp)
def get_submission_failures(
    submission_id: str,
    request: Request,
    _auth_principal: auth.TeamIngestionPrincipal = Security(auth.require_team_ingestion_principal),
):
    _bind_demo_space(request)
    with use_space(gateway_service.TEAM_INGESTION_SPACE_NAME):
        record = idempotency_store.load_submission(submission_id)
        return failures_service.build_failures_response(record)
