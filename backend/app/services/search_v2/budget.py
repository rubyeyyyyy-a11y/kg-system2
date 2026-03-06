import os
from dataclasses import dataclass

from app import config as app_config


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


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class SearchV2Budget:
    min_query_len: int
    suggest_min_query_len: int
    search_topk: int
    es_topk: int
    suggest_limit_max: int
    suggest_raw_id_limit_max: int
    include_edges_default: bool
    include_edges_allow: bool
    include_edges_node_cap: int
    include_edges_edge_limit: int
    es_health_ttl_sec: float
    es_timeout_ms: int


search_budget = SearchV2Budget(
    min_query_len=max(1, _env_int("SEARCH_V2_MIN_QUERY_LEN", app_config.settings.search_min_query_len)),
    suggest_min_query_len=max(1, _env_int("SEARCH_V2_SUGGEST_MIN_QUERY_LEN", 2)),
    search_topk=max(1, _env_int("SEARCH_V2_TOPK", app_config.settings.search_topk)),
    es_topk=max(1, min(_env_int("SEARCH_V2_ES_TOPK", app_config.settings.es_topk), 500)),
    suggest_limit_max=max(1, min(_env_int("SEARCH_V2_SUGGEST_LIMIT_MAX", 20), 100)),
    suggest_raw_id_limit_max=max(1, min(_env_int("SEARCH_V2_SUGGEST_RAW_ID_LIMIT_MAX", 50), 100)),
    include_edges_default=_env_bool("SEARCH_V2_INCLUDE_EDGES_DEFAULT", False),
    include_edges_allow=_env_bool("SEARCH_V2_INCLUDE_EDGES_ALLOW", True),
    include_edges_node_cap=max(1, min(_env_int("SEARCH_V2_INCLUDE_EDGES_NODE_CAP", 40), 200)),
    include_edges_edge_limit=max(1, min(_env_int("SEARCH_V2_INCLUDE_EDGES_EDGE_LIMIT", 1200), 5000)),
    es_health_ttl_sec=max(0.0, _env_float("SEARCH_V2_ES_HEALTH_TTL_SEC", 3.0)),
    es_timeout_ms=max(100, _env_int("SEARCH_V2_ES_TIMEOUT_MS", app_config.settings.es_timeout_ms)),
)

