from app.services.imports import file_store, plan_service, source_service
from app.services.imports.models import DraftValidationResult, ImportDraft, TargetValidationResult

VALIDATE_SEMANTIC_NOTE = (
    "Validate checks CSV format, mapping, and import rules only. "
    "It is not a Nebula existence preflight and does not guarantee final write success."
)
MAX_VALIDATION_ERROR_SAMPLES = 20


def _parse_int64(text: str) -> int:
    return int(str(text or "").strip())


def _row_matches_selector(row: dict[str, str], selector) -> bool:
    if selector is None:
        return True
    return str(row.get(selector.column, "")).strip() == str(selector.equals or "").strip()


def _validate_target_identity(row_index: int, row: dict[str, str], target) -> list[str]:
    errors: list[str] = []
    try:
        if target.object_type == "tag":
            _parse_int64(row.get(target.identity_mapping.id_column or "", ""))
        else:
            _parse_int64(row.get(target.identity_mapping.src_column or "", ""))
            _parse_int64(row.get(target.identity_mapping.dst_column or "", ""))
            if target.identity_mapping.rank_column and str(row.get(target.identity_mapping.rank_column, "")).strip():
                _parse_int64(row.get(target.identity_mapping.rank_column or "", ""))
    except Exception:
        if target.object_type == "tag":
            errors.append(f"row {row_index}: invalid numeric VID")
        else:
            errors.append(f"row {row_index}: invalid numeric srcVID/dstVID/rank")
    return errors


def validate_draft(draft: ImportDraft) -> DraftValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    integration_warnings: list[str] = []
    target_results: list[TargetValidationResult] = []
    scanned_rows = 0
    error_rows = 0
    errors_truncated = False

    if draft.sources:
        effective_sources = list(draft.sources)
    elif draft.file_ids:
        effective_sources = source_service.build_sources(list(draft.file_ids), sample_rows=20)
    else:
        effective_sources = []
    sources_by_id = {source.source_id: source for source in effective_sources}
    if not effective_sources:
        errors.append("at least one uploaded CSV source is required")
    if not draft.mapping:
        errors.append("mapping targets are required")

    def append_error(message: str) -> None:
        nonlocal errors_truncated
        if len(errors) < MAX_VALIDATION_ERROR_SAMPLES:
            errors.append(message)
            return
        errors_truncated = True

    for target in draft.mapping:
        source = sources_by_id.get(target.source_id)
        if source is None and len(effective_sources) == 1:
            source = effective_sources[0]
            target.source_id = source.source_id
        target_errors: list[str] = []
        target_warnings: list[str] = []
        target_hints: list[str] = []
        target_scanned_rows = 0
        target_error_rows = 0
        if source is None:
            target_errors.append(f"missing source `{target.source_id}`")
            append_error(f"{target.object_type} `{target.object_name}` references missing source `{target.source_id}`")
            target_results.append(
                TargetValidationResult(
                    target_id=target.target_id,
                    source_id=target.source_id,
                    object_type=target.object_type,
                    object_name=target.object_name,
                    source_columns=[],
                    passed=False,
                    errors=target_errors,
                    warnings=target_warnings,
                    hints=target_hints,
                )
            )
            continue

        source_errors, source_warnings = source_service.validate_source_kind_hint(
            object_type=target.object_type,
            inferred_kind=source.inferred_kind,
        )
        target_errors.extend(source_errors)
        target_warnings.extend(source_warnings)
        target_hints.extend(source_service.missing_identity_hints(object_type=target.object_type, source=source))
        for message in source_errors:
            append_error(f"{target.object_type} `{target.object_name}`: {message}")
        warnings.extend(source_warnings)

        source_columns = set(source.columns)
        if target.object_type == "tag":
            if not target.identity_mapping.id_column:
                target_errors.append("identity_mapping.id_column is required")
                append_error(f"tag `{target.object_name}` missing required identity mapping: id_column")
        else:
            missing_identity = []
            if not target.identity_mapping.src_column:
                missing_identity.append("src_column")
            if not target.identity_mapping.dst_column:
                missing_identity.append("dst_column")
            if missing_identity:
                target_errors.append(f"missing required identity mapping: {', '.join(missing_identity)}")
                append_error(
                    f"edge_type `{target.object_name}` missing required identity mappings: {', '.join(missing_identity)}"
                )
        mapped_columns = set(target.identity_mapping.mapped_columns()) | {
            item.source_column for item in target.property_mappings if item.source_column
        }
        missing_columns = sorted(column for column in mapped_columns if column not in source_columns)
        if missing_columns:
            target_errors.append(f"references missing source columns: {', '.join(missing_columns)}")
            append_error(
                f"{target.object_type} `{target.object_name}` references missing source columns: {', '.join(missing_columns)}"
            )

        if not target_errors:
            row_count = 0
            _columns, rows, _record = file_store.iter_csv_rows(source.file_id)
            for row_index, row in enumerate(rows, start=1):
                row_count = row_index
                if not _row_matches_selector(row, target.row_selector):
                    continue
                scanned_rows += 1
                target_scanned_rows += 1
                if scanned_rows > file_store.MAX_JOB_ROWS:
                    append_error(f"job row count exceeds max {file_store.MAX_JOB_ROWS}")
                    target_errors.append(f"job row count exceeds max {file_store.MAX_JOB_ROWS}")
                    break
                row_errors = _validate_target_identity(row_index, row, target)
                if row_errors:
                    target_error_rows += 1
                    error_rows += 1
                for row_error in row_errors:
                    append_error(f"{target.object_type} `{target.object_name}`: {row_error}")
            file_store.update_file_row_count(source.file_id, row_count)

        target_results.append(
            TargetValidationResult(
                target_id=target.target_id,
                source_id=target.source_id,
                object_type=target.object_type,
                object_name=target.object_name,
                source_columns=list(source.columns),
                passed=not target_errors,
                errors=target_errors,
                warnings=target_warnings,
                hints=target_hints,
                scanned_rows=target_scanned_rows,
                error_rows=target_error_rows,
            )
        )

    compiled_plan = None
    if not errors:
        if effective_sources != list(draft.sources):
            draft.sources = effective_sources
            draft.file_ids = [source.file_id for source in effective_sources]
        compiled_plan, plan_warnings, plan_integration_warnings = plan_service.compile_plan(draft)
        warnings.extend(plan_warnings)
        integration_warnings.extend(plan_integration_warnings)
    elif errors_truncated:
        errors.append(f"validation kept only the first {MAX_VALIDATION_ERROR_SAMPLES} error samples")

    return DraftValidationResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        integration_warnings=integration_warnings,
        semantic_notes=[VALIDATE_SEMANTIC_NOTE],
        scanned_rows=scanned_rows,
        error_rows=error_rows,
        errors_truncated=errors_truncated,
        target_results=target_results,
        compiled_plan=compiled_plan,
    )
