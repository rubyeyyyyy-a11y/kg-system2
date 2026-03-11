from typing import Any

from app.services.imports import file_store


VERTEX_HINT_COLUMNS = {"id", "entity_type", "entity_name", "entity_raw_id", "description", "source"}
EDGE_HINT_COLUMNS = {
    "subject_our_defined_id",
    "object_our_defined_id",
    "srcvid",
    "dstvid",
    "rank",
    "relation",
    "direction",
    "score",
}


def build_preview(*, file_ids: list[str], sample_rows: int, mode_hint: str | None = None) -> dict[str, Any]:
    if not file_ids:
        return {"columns": [], "sample_rows": [], "inferred_mode_candidates": [], "warnings": ["no files uploaded"]}

    columns: list[str] = []
    preview_rows: list[dict[str, str]] = []
    warnings: list[str] = []
    for idx, file_id in enumerate(file_ids):
        file_columns = file_store.read_csv_columns(file_id) if idx > 0 else []
        if idx == 0:
            columns, preview_rows, _record = file_store.read_csv_sample(file_id, sample_rows)
        elif file_columns != columns:
            warnings.append(f"file {file_id} columns differ from the first uploaded file")
    if sample_rows > file_store.MAX_SAMPLE_ROWS:
        warnings.append(f"sample_rows capped at {file_store.MAX_SAMPLE_ROWS}")

    inferred = infer_mode_candidates(columns, mode_hint=mode_hint)
    if not inferred:
        inferred = ["vertex", "edge"]
    return {
        "columns": columns,
        "sample_rows": preview_rows,
        "inferred_mode_candidates": inferred,
        "warnings": warnings,
    }


def infer_mode_candidates(columns: list[str], mode_hint: str | None = None) -> list[str]:
    normalized = {str(col or "").strip().lower() for col in columns}
    vertex_hits = len(normalized & VERTEX_HINT_COLUMNS)
    edge_hits = len(normalized & EDGE_HINT_COLUMNS)
    candidates: list[str] = []
    if mode_hint in {"vertex", "edge", "mixed"}:
        candidates.append(str(mode_hint))
    if vertex_hits > 0:
        candidates.append("vertex")
    if edge_hits > 0:
        candidates.append("edge")
    if vertex_hits > 0 and edge_hits > 0:
        candidates.append("mixed")
    deduped: list[str] = []
    for candidate in candidates:
        if candidate not in deduped:
            deduped.append(candidate)
    return deduped
