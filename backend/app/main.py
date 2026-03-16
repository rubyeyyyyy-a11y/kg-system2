import logging
import os
import socket
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response
from fastapi.responses import JSONResponse

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

from app import config as app_config
from app.api import routes_edit
from app.core.config import ensure_audit_log_dir
from app.core.space_context import bind_request_space, reset_current_space
from app.db import nebula as nebula_db
from app.db.nebula import execute_ngql
from app.routers import detail, graph, imports, search, search_v2, spaces
from app.services.imports import executor_service
from app.services.spaces import registry_service

app = FastAPI(title="KG Entity Search API")
logger = logging.getLogger(__name__)


DEV_INSTANCE_TRACE = app_config.settings.dev_instance_trace
INSTANCE_ID = f"{Path(__file__).resolve().parents[2].name}:{uuid.uuid4().hex[:12]}"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    r = execute_ngql("SHOW HOSTS;", use_space=False)
    if not r.is_succeeded():
        raise HTTPException(status_code=500, detail=r.error_msg())
    return {"ok": True, "hosts_rows": len(r.rows())}


@app.on_event("startup")
def startup_prepare():
    ensure_audit_log_dir()
    registry_service.register_default_space()
    logger.warning(
        "instance_start instance_id=%s repo=%s host=%s edge_type=%s nebula=%s:%s space=%s pid=%d",
        INSTANCE_ID,
        str(Path(__file__).resolve().parents[2]),
        socket.gethostname(),
        nebula_db.EDGE_TYPE,
        nebula_db.NEBULA_HOST,
        nebula_db.NEBULA_PORT,
        nebula_db.NEBULA_SPACE,
        os.getpid(),
    )
    executor_service.startup_recover_and_start()


@app.middleware("http")
async def add_instance_header(request: Request, call_next) -> Response:
    try:
        token = bind_request_space(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    try:
        resolved = getattr(request.state, "space_resolution", None)
        logger.warning(
            "request_space method=%s path=%s space=%s source=%s registry_status=%s",
            request.method,
            request.url.path,
            getattr(request.state, "space_name", app_config.settings.nebula_space),
            getattr(resolved, "source", "unknown"),
            getattr(resolved, "registry_status", None),
        )
        response = await call_next(request)
    finally:
        reset_current_space(token)
    if DEV_INSTANCE_TRACE:
        response.headers["X-Instance-Id"] = INSTANCE_ID
    response.headers["X-KG-Space"] = getattr(request.state, "space_name", app_config.settings.nebula_space)
    return response


app.include_router(search.router)
app.include_router(search_v2.router)
app.include_router(graph.router)
app.include_router(detail.router)
app.include_router(routes_edit.router)
app.include_router(imports.router)
app.include_router(spaces.router)
