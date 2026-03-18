from .models import FieldGroup, FieldRule, LongTextRule

EDGE_FIELD_GROUPS = (
    FieldGroup(key="connection", title="连接信息", order=10),
    FieldGroup(key="common", title="公共属性", order=20),
    FieldGroup(key="other", title="其他属性", order=30),
    FieldGroup(key="system", title="系统信息", order=40),
    FieldGroup(key="advanced", title="高级属性", order=50),
)

EDGE_READ_ONLY_FIELDS = {"src", "dst", "rank", "edge_type", "relation", "version", "updated_at", "updated_by"}
EDGE_LONG_TEXT_FIELDS = {"evidence"}
EDGE_DEFAULT_DISPLAY_ORDER = (
    "edge_kind",
    "relation",
    "src",
    "dst",
    "rank",
    "edge_type",
    "source",
    "evidence",
    "version",
    "updated_at",
    "updated_by",
)

EDGE_KIND_FIELD_OVERRIDES: dict[str, dict[str, FieldRule]] = {}

EDGE_FIELD_RULES = {
    "edge_kind": FieldRule(name="edge_kind", label="Edge Kind", group="common", order=10, max_len=128),
    "src": FieldRule(name="src", label="Source", group="connection", order=20, max_len=64, read_only=True),
    "dst": FieldRule(name="dst", label="Destination", group="connection", order=30, max_len=64, read_only=True),
    "rank": FieldRule(name="rank", label="Rank", group="connection", order=40, max_len=64, read_only=True),
    "edge_type": FieldRule(name="edge_type", label="Physical Edge Type", group="connection", order=50, max_len=64, read_only=True),
    "relation": FieldRule(name="relation", label="关系类型", group="common", order=60, max_len=256, read_only=True),
    "source": FieldRule(
        name="source",
        label="来源",
        group="common",
        order=70,
        max_len=256,
        aliases=("source_db",),
    ),
    "evidence": FieldRule(
        name="evidence",
        label="证据",
        group="common",
        order=80,
        max_len=4096,
        multiline=True,
        long_text=LongTextRule(preview_chars=240),
    ),
    "version": FieldRule(name="version", label="Version", group="system", order=90, max_len=32, read_only=True),
    "updated_at": FieldRule(name="updated_at", label="Updated At", group="system", order=100, max_len=32, read_only=True),
    "updated_by": FieldRule(name="updated_by", label="Updated By", group="system", order=110, max_len=64, read_only=True),
}


def edge_kind_rule_overrides(edge_kind: str | None) -> dict[str, FieldRule]:
    key = str(edge_kind or "").strip().lower()
    if not key:
        return {}
    return EDGE_KIND_FIELD_OVERRIDES.get(key, {})
