from typing import Dict, Iterable, List, Literal, TypedDict

from app.core import config
from app.core.escape import raise_validation_error


FieldKind = Literal["string"]


class FieldSpec(TypedDict):
    name: str
    type: FieldKind
    maxLen: int
    multiline: bool
    required: bool


def entity_field_specs() -> List[FieldSpec]:
    out: List[FieldSpec] = []
    for field_name in sorted(config.ENTITY_EDITABLE_FIELDS):
        out.append(
            {
                "name": field_name,
                "type": "string",
                "maxLen": config.ENTITY_FIELD_MAX_LEN[field_name],
                "multiline": field_name in config.ALLOW_MULTILINE_FIELDS,
                "required": False,
            }
        )
    return out


def edge_field_specs() -> List[FieldSpec]:
    out: List[FieldSpec] = []
    for field_name in sorted(config.EDGE_EDITABLE_FIELDS):
        out.append(
            {
                "name": field_name,
                "type": "string",
                "maxLen": config.EDGE_FIELD_MAX_LEN[field_name],
                "multiline": field_name in config.ALLOW_MULTILINE_FIELDS,
                "required": False,
            }
        )
    return out


def editable_fields_payload() -> Dict[str, object]:
    return {
        "entity": {"fields": entity_field_specs()},
        "edge": {"fields": edge_field_specs()},
        "forbidden_fields": sorted(config.ENTITY_FORBIDDEN_FIELDS),
    }


def _check_field_names(
    incoming: Iterable[str],
    allowed: set[str],
    forbidden: set[str] | None = None,
) -> None:
    forbidden = forbidden or set()
    for key in incoming:
        if key in forbidden:
            raise_validation_error(f"field '{key}' is forbidden", field=key)
        if key not in allowed:
            raise_validation_error(f"field '{key}' is not editable", field=key)


def validate_node_patch_set(data: Dict[str, object]) -> Dict[str, str]:
    if not isinstance(data, dict) or len(data) == 0:
        raise_validation_error("'set' must be a non-empty object", field="set")
    _check_field_names(data.keys(), config.ENTITY_EDITABLE_FIELDS, config.ENTITY_FORBIDDEN_FIELDS)
    out: Dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(v, str):
            raise_validation_error(f"field '{k}' must be string", field=k)
        out[k] = v
    return out


def validate_edge_patch_set(data: Dict[str, object]) -> Dict[str, str]:
    if not isinstance(data, dict) or len(data) == 0:
        raise_validation_error("'set' must be a non-empty object", field="set")
    _check_field_names(data.keys(), config.EDGE_EDITABLE_FIELDS)
    out: Dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(v, str):
            raise_validation_error(f"field '{k}' must be string", field=k)
        out[k] = v
    return out
