from typing import Dict, List, Literal, TypedDict

from app.object_meta import validation_service


FieldKind = Literal["string"]


class FieldSpec(TypedDict):
    name: str
    type: FieldKind
    maxLen: int
    multiline: bool
    required: bool


def entity_field_specs() -> List[FieldSpec]:
    return validation_service.editable_fields_payload()["entity"]["fields"]  # type: ignore[return-value]


def edge_field_specs() -> List[FieldSpec]:
    return validation_service.editable_fields_payload()["edge"]["fields"]  # type: ignore[return-value]


def editable_fields_payload() -> Dict[str, object]:
    return validation_service.editable_fields_payload()


def validate_node_patch_set(data: Dict[str, object]) -> Dict[str, str]:
    return validation_service.validate_patch_set("node", data)


def validate_edge_patch_set(data: Dict[str, object]) -> Dict[str, str]:
    return validation_service.validate_patch_set("edge", data)
