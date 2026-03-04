from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_edit
from app.core.config import ensure_audit_log_dir
from app.db.nebula import get_session
from app.routers import detail, graph, search

app = FastAPI(title="KG Entity Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    s = get_session()
    r = s.execute("SHOW HOSTS;")
    if not r.is_succeeded():
        raise HTTPException(status_code=500, detail=r.error_msg())
    return {"ok": True, "hosts_rows": len(r.rows())}


@app.on_event("startup")
def startup_prepare():
    ensure_audit_log_dir()


app.include_router(search.router)
app.include_router(graph.router)
app.include_router(detail.router)
app.include_router(routes_edit.router)
