from typing import Any

from app.services.imports import file_store, source_service


def build_preview(*, file_ids: list[str], sample_rows: int, mode_hint: str | None = None) -> dict[str, Any]:
    if not file_ids:
        return {"sources": [], "workspace_mode_candidates": [], "warnings": ["no files uploaded"]}

    warnings = ["preview is sample-only and does not guarantee full-file validate/import success"]
    sources = source_service.build_sources(file_ids, sample_rows=sample_rows)
    kinds = {source.inferred_kind for source in sources}
    candidates: list[str] = []
    if mode_hint in {"vertex", "edge", "mixed"}:
        candidates.append(str(mode_hint))
    if "vertex" in kinds:
        candidates.append("vertex")
    if "edge" in kinds:
        candidates.append("edge")
    if "mixed" in kinds or {"vertex", "edge"} <= kinds:
        candidates.append("mixed")
    if not candidates:
        candidates = ["vertex", "edge"]
    deduped_candidates: list[str] = []
    for candidate in candidates:
        if candidate not in deduped_candidates:
            deduped_candidates.append(candidate)
    if sample_rows > file_store.MAX_SAMPLE_ROWS:
        warnings.append(f"sample_rows capped at {file_store.MAX_SAMPLE_ROWS}")
    for source in sources:
        warnings.extend(source_service.preview_hints(source))
    return {
        "sources": [source.model_dump() for source in sources],
        "workspace_mode_candidates": deduped_candidates,
        "warnings": warnings,
        "columns": sources[0].columns if sources else [],
        "sample_rows": sources[0].sample_rows if sources else [],
        "inferred_mode_candidates": deduped_candidates,
    }
