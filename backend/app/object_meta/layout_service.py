from typing import Any

from .edge_rules import EDGE_FIELD_GROUPS, EDGE_FIELD_RULES, edge_kind_rule_overrides
from .models import FieldRule, ObjectLayout
from .node_rules import NODE_FIELD_GROUPS, NODE_FIELD_RULES
from .validation_service import canonical_field_name, get_field_rule


def _normalized_props(props: dict[str, Any] | None, object_type: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in dict(props or {}).items():
        canonical = canonical_field_name(object_type, str(key))
        out[canonical] = value
    return out


def build_object_layout(
    *,
    object_type: str,
    top_level: dict[str, Any] | None = None,
    props: dict[str, Any] | None = None,
) -> ObjectLayout:
    raw_top_level = dict(top_level or {})
    merged: dict[str, Any] = {}
    for key, value in raw_top_level.items():
        merged[canonical_field_name(object_type, str(key))] = value
    for key, value in _normalized_props(props, object_type).items():
        merged.setdefault(key, value)

    if object_type == "edge":
        edge_kind = merged.get("edge_kind")
        rules_index: dict[str, FieldRule] = {**EDGE_FIELD_RULES, **edge_kind_rule_overrides(str(edge_kind or ""))}
        groups = EDGE_FIELD_GROUPS
        layout_key = f"REL2:{str(edge_kind or '').strip() or '_default'}"
    else:
        rules_index = dict(NODE_FIELD_RULES)
        groups = NODE_FIELD_GROUPS
        layout_key = "Entity"

    realized_rules: list[FieldRule] = []
    unregistered_fields: list[str] = []
    for key in merged.keys():
        rule = rules_index.get(key) or get_field_rule(object_type, key)
        if key not in rules_index:
            unregistered_fields.append(key)
        realized_rules.append(rule)

    realized_rules.sort(key=lambda item: (next((g.order for g in groups if g.key == item.group), 999), item.order, item.name))
    return ObjectLayout(
        object_type=object_type,
        groups=groups,
        fields=tuple(realized_rules),
        layout_key=layout_key,
        unregistered_fields=tuple(sorted(set(unregistered_fields))),
    )
