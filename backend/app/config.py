import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _resolve_repo_path(raw: str, repo_root: Path) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    return repo_root / path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = "./runtime"
_RUNTIME_ROOT = _resolve_repo_path(os.getenv("RUN_ROOT", RUN_ROOT), REPO_ROOT)
_RUNTIME_RUN_DIR = _resolve_repo_path(os.getenv("RUNTIME_RUN_DIR", str(_RUNTIME_ROOT / ".run")), REPO_ROOT)
_RUNTIME_LOGS_DIR = _resolve_repo_path(os.getenv("RUNTIME_LOGS_DIR", str(_RUNTIME_ROOT / "logs")), REPO_ROOT)
_RUNTIME_ARTIFACTS_DIR = _resolve_repo_path(
    os.getenv("RUNTIME_ARTIFACTS_DIR", str(_RUNTIME_ROOT / "artifacts")),
    REPO_ROOT,
)
_AUDIT_LOG_PATH = _resolve_repo_path(
    os.getenv("AUDIT_LOG_PATH", str(_RUNTIME_LOGS_DIR / "edit_audit.jsonl")),
    REPO_ROOT,
)


@dataclass(frozen=True)
class Settings:
    nebula_host: str
    nebula_port: int
    nebula_user: str
    nebula_password: str
    nebula_admin_user: str
    nebula_admin_password: str
    nebula_space: str
    nebula_timeout_ms: int

    edge_type: str

    search_topk: int
    search_include_edges_default: bool
    search_min_query_len: int
    search_candidate_limit: int
    search_desc_candidate_limit: int

    es_enabled: bool
    es_url: str
    es_index: str
    es_timeout_ms: int
    es_bulk_timeout_ms: int
    es_bulk_upsert_batch_size: int
    es_bulk_upsert_max_bytes: int
    es_topk: int

    dev_instance_trace: bool
    runtime_root: Path
    runtime_run_dir: Path
    runtime_logs_dir: Path
    runtime_artifacts_dir: Path
    audit_log_path: Path


settings = Settings(
    nebula_host=os.getenv("NEBULA_HOST", "127.0.0.1"),
    nebula_port=_env_int("NEBULA_PORT", 9669),
    nebula_user=os.getenv("NEBULA_USER", "root"),
    nebula_password=os.getenv("NEBULA_PASSWORD", "nebula"),
    nebula_admin_user=os.getenv("NEBULA_ADMIN_USER", os.getenv("NEBULA_USER", "root")),
    nebula_admin_password=os.getenv("NEBULA_ADMIN_PASSWORD", os.getenv("NEBULA_PASSWORD", "nebula")),
    nebula_space=os.getenv("NEBULA_SPACE", "demo_kg"),
    nebula_timeout_ms=_env_int("NEBULA_TIMEOUT_MS", 5000),
    edge_type=os.getenv("EDGE_TYPE", "REL2").strip() or "REL2",
    search_topk=max(1, _env_int("TOPK", 100)),
    search_include_edges_default=_env_bool("SEARCH_INCLUDE_EDGES_DEFAULT", False),
    search_min_query_len=max(1, _env_int("SEARCH_MIN_QUERY_LEN", 3)),
    search_candidate_limit=max(1, _env_int("CANDIDATE_LIMIT", 300)),
    search_desc_candidate_limit=max(1, min(_env_int("DESC_CANDIDATE_LIMIT", 50), 50)),
    es_enabled=_env_bool("ES_ENABLED", True),
    es_url=os.getenv("ES_URL", "http://127.0.0.1:9200").rstrip("/"),
    es_index=os.getenv("ES_INDEX", "kg_entity"),
    es_timeout_ms=max(100, _env_int("ES_TIMEOUT_MS", 5000)),
    es_bulk_timeout_ms=max(100, _env_int("ES_BULK_TIMEOUT_MS", 12000)),
    es_bulk_upsert_batch_size=max(1, _env_int("ES_BULK_UPSERT_BATCH_SIZE", 250)),
    es_bulk_upsert_max_bytes=max(16 * 1024, _env_int("ES_BULK_UPSERT_MAX_BYTES", 2 * 1024 * 1024)),
    es_topk=max(1, min(_env_int("ES_TOPK", _env_int("TOPK", 100)), 500)),
    dev_instance_trace=_env_bool("DEV_INSTANCE_TRACE", True),
    runtime_root=_RUNTIME_ROOT,
    runtime_run_dir=_RUNTIME_RUN_DIR,
    runtime_logs_dir=_RUNTIME_LOGS_DIR,
    runtime_artifacts_dir=_RUNTIME_ARTIFACTS_DIR,
    audit_log_path=_AUDIT_LOG_PATH,
)
