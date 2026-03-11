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

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

from app import config as app_config
from app.api import routes_edit
from app.core.config import ensure_audit_log_dir
from app.db import nebula as nebula_db
from app.db.nebula import execute_ngql
from app.routers import detail, graph, imports, search, search_v2
from app.services.imports import executor_service

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
    r = execute_ngql("SHOW HOSTS;")
    if not r.is_succeeded():
        raise HTTPException(status_code=500, detail=r.error_msg())
    return {"ok": True, "hosts_rows": len(r.rows())}


@app.on_event("startup")
def startup_prepare():
    ensure_audit_log_dir()
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
    response = await call_next(request)
    if DEV_INSTANCE_TRACE:
        response.headers["X-Instance-Id"] = INSTANCE_ID
    return response


app.include_router(search.router)
app.include_router(search_v2.router)
app.include_router(graph.router)
app.include_router(detail.router)
app.include_router(routes_edit.router)
app.include_router(imports.router)
