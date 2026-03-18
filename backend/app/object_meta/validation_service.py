from typing import Any

from app.core.escape import raise_validation_error, validate_text

from .edge_rules import EDGE_FIELD_GROUPS, EDGE_FIELD_RULES, edge_kind_rule_overrides
from .models import FieldRule
from .node_rules import NODE_FIELD_GROUPS, NODE_FIELD_RULES

_DEFAULT_FIELD_MAX_LEN = 4096


def _object_type_key(object_type: str) -> str:
    text = str(object_type or "").strip().lower()
    if text not in {"node", "edge"}:
        raise ValueError(f"unsupported object_type: {object_type}")
    return text


def _groups_for_object(object_type: str):
    return EDGE_FIELD_GROUPS if _object_type_key(object_type) == "edge" else NODE_FIELD_GROUPS


def _base_rules_for_object(object_type: str) -> dict[str, FieldRule]:
    return dict(EDGE_FIELD_RULES) if _object_type_key(object_type) == "edge" else dict(NODE_FIELD_RULES)


def canonical_field_name(object_type: str, field_name: str) -> str:
    key = str(field_name or "").strip()
    if not key:
        return ""
    rules = _base_rules_for_object(object_type)
    if key in rules:
        return key
    for rule in rules.values():
        if key in rule.aliases:
            return rule.name
    return key


def _fallback_group(object_type: str) -> str:
    return "other" if _object_type_key(object_type) == "node" else "other"


def get_field_rule(object_type: str, field_name: str, current_snapshot: dict[str, Any] | None = None) -> FieldRule:
    object_key = _object_type_key(object_type)
    canonical = canonical_field_name(object_key, field_name)
    rules = _base_rules_for_object(object_key)
    if object_key == "edge":
        edge_kind = str((current_snapshot or {}).get("edge_kind") or "").strip()
        rules.update(edge_kind_rule_overrides(edge_kind))
    rule = rules.get(canonical)
    if rule is not None:
        return rule
    return FieldRule(
        name=canonical,
        label=canonical,
        group=_fallback_group(object_key),
        order=9000,
        max_len=_DEFAULT_FIELD_MAX_LEN,
        multiline=True,
    )


def is_read_only_field(object_type: str, field_name: str, current_snapshot: dict[str, Any] | None = None) -> bool:
    return get_field_rule(object_type, field_name, current_snapshot=current_snapshot).read_only


def is_editable_field(object_type: str, field_name: str, current_snapshot: dict[str, Any] | None = None) -> bool:
    return not is_read_only_field(object_type, field_name, current_snapshot=current_snapshot)


def validate_patch_set(
    object_type: str,
    data: dict[str, object],
    *,
    current_snapshot: dict[str, Any] | None = None,
) -> dict[str, str]:
    if not isinstance(data, dict) or len(data) == 0:
        raise_validation_error("'set' must be a non-empty object", field="set")

    out: dict[str, str] = {}
    for raw_field_name, raw_value in data.items():
        field_name = canonical_field_name(object_type, str(raw_field_name))
        if not field_name:
            raise_validation_error("field name is required", field=str(raw_field_name))
        rule = get_field_rule(object_type, field_name, current_snapshot=current_snapshot)
        if rule.read_only:
            raise_validation_error(f"field '{field_name}' is read-only", field=field_name)
        if not isinstance(raw_value, str):
            raise_validation_error(f"field '{field_name}' must be string", field=field_name)
        out[field_name] = validate_text(
            field_name=field_name,
            value=raw_value,
            max_len=rule.max_len,
            multiline=rule.multiline,
        )
    return out


def _editable_field_specs(object_type: str) -> list[dict[str, object]]:
    groups = {item.key: item.order for item in _groups_for_object(object_type)}
    rules = [rule for rule in _base_rules_for_object(object_type).values() if not rule.read_only]
    rules.sort(key=lambda item: (groups.get(item.group, 999), item.order, item.name))
    return [
        {
            "name": rule.name,
            "type": "string",
            "maxLen": rule.max_len,
            "multiline": rule.multiline,
            "required": rule.required,
        }
        for rule in rules
    ]


def editable_fields_payload() -> dict[str, object]:
    return {
        "entity": {"fields": _editable_field_specs("node")},
        "edge": {"fields": _editable_field_specs("edge")},
        "forbidden_fields": [],
    }
