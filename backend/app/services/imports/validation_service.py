from app.services.imports import file_store, plan_service
from app.services.imports.models import DraftValidationResult, ImportDraft

VALIDATE_SEMANTIC_NOTE = (
    "Validate checks CSV format, mapping, and import rules only. "
    "It is not a Nebula existence preflight and does not guarantee final write success."
)


def _parse_int64(text: str) -> int:
    return int(str(text or "").strip())


def _select_target(draft: ImportDraft, row: dict[str, str]):
    if draft.mode != "mixed":
        return draft.mapping[0]
    discriminator = str(row.get(draft.discriminator_column or "", "")).strip()
    for target in draft.mapping:
        if str(target.discriminator_value or "") == discriminator:
            return target
    raise ValueError(f"unmapped discriminator value `{discriminator}`")


def _validate_row_identity(draft: ImportDraft, row_index: int, row: dict[str, str], target) -> list[str]:
    errors: list[str] = []
    reverse = {item.target_field: item.source_column for item in target.field_mappings}
    try:
        if target.object_type == "tag":
            _parse_int64(row.get(reverse["ID"], ""))
        else:
            _parse_int64(row.get(reverse["srcVID"], ""))
            _parse_int64(row.get(reverse["dstVID"], ""))
            if "rank" in reverse and str(row.get(reverse["rank"], "")).strip():
                _parse_int64(row.get(reverse["rank"], ""))
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

    if not draft.file_ids:
        errors.append("at least one uploaded CSV file is required")
    if not draft.mapping:
        errors.append("mapping targets are required")
    if draft.mode == "mixed" and not draft.discriminator_column:
        errors.append("mixed mode requires discriminator_column")
    if draft.mode != "mixed" and len(draft.mapping) != 1:
        errors.append("vertex/edge mode requires exactly one mapping target")

    all_columns: list[str] = []
    total_rows = 0
    if draft.file_ids:
        all_columns = file_store.read_csv_columns(draft.file_ids[0])
        total_rows = sum(file_store.count_csv_rows(file_id) for file_id in draft.file_ids)
        if total_rows > file_store.MAX_JOB_ROWS:
            errors.append(f"job row count exceeds max {file_store.MAX_JOB_ROWS}")

    for target in draft.mapping:
        if target.object_type == "tag":
            required = {"ID"}
        else:
            required = {"srcVID", "dstVID"}
        mapped_targets = {item.target_field for item in target.field_mappings}
        missing = sorted(required - mapped_targets)
        if missing:
            errors.append(f"{target.object_type} `{target.object_name}` missing required mappings: {', '.join(missing)}")
        missing_columns = [item.source_column for item in target.field_mappings if item.source_column not in all_columns]
        if missing_columns:
            errors.append(
                f"{target.object_type} `{target.object_name}` references missing source columns: {', '.join(sorted(missing_columns))}"
            )
        if target.object_type == "tag" and draft.mode == "edge":
            errors.append("edge mode cannot target tag objects")
        if target.object_type == "edge_type" and draft.mode == "vertex":
            errors.append("vertex mode cannot target edge type objects")

    if not errors and draft.file_ids:
        for file_id in draft.file_ids:
            _columns, rows, _record = file_store.read_csv_rows(file_id)
            for row_index, row in enumerate(rows, start=1):
                try:
                    target = _select_target(draft, row)
                except Exception as exc:
                    errors.append(f"row {row_index}: {exc}")
                    continue
                errors.extend(_validate_row_identity(draft, row_index, row, target))
                if len(errors) >= 20:
                    errors.append("validation stopped after 20 row-level errors")
                    break
            if errors:
                break

    compiled_plan = None
    if not errors:
        compiled_plan, plan_warnings, plan_integration_warnings = plan_service.compile_plan(draft, all_columns=all_columns)
        warnings.extend(plan_warnings)
        integration_warnings.extend(plan_integration_warnings)

    return DraftValidationResult(
        passed=not errors,
        errors=errors,
        warnings=warnings,
        integration_warnings=integration_warnings,
        semantic_notes=[VALIDATE_SEMANTIC_NOTE],
        compiled_plan=compiled_plan,
    )
