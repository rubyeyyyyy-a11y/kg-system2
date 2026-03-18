from dataclasses import dataclass, field


@dataclass(frozen=True)
class LongTextRule:
    preview_chars: int = 220


@dataclass(frozen=True)
class FieldRule:
    name: str
    label: str
    group: str
    order: int
    max_len: int = 4096
    multiline: bool = False
    required: bool = False
    read_only: bool = False
    high_risk: bool = False
    aliases: tuple[str, ...] = ()
    long_text: LongTextRule | None = None


@dataclass(frozen=True)
class FieldGroup:
    key: str
    title: str
    order: int


@dataclass(frozen=True)
class ObjectLayout:
    object_type: str
    groups: tuple[FieldGroup, ...]
    fields: tuple[FieldRule, ...]
    layout_key: str = ""
    unregistered_fields: tuple[str, ...] = field(default_factory=tuple)
