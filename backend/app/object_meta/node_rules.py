from .models import FieldGroup, FieldRule, LongTextRule

NODE_FIELD_GROUPS = (
    FieldGroup(key="basic", title="基础信息", order=10),
    FieldGroup(key="text", title="文本信息", order=20),
    FieldGroup(key="other", title="其他属性", order=30),
    FieldGroup(key="system", title="系统信息", order=40),
    FieldGroup(key="advanced", title="高级属性", order=50),
)

NODE_READ_ONLY_FIELDS = {"vid", "entity_raw_id", "version", "updated_at", "updated_by"}
NODE_LONG_TEXT_FIELDS = {"description", "synonyms"}
NODE_DEFAULT_DISPLAY_ORDER = (
    "entity_name",
    "entity_type",
    "vid",
    "entity_raw_id",
    "source",
    "hop_level",
    "description",
    "synonyms",
    "version",
    "updated_at",
    "updated_by",
)

NODE_FIELD_RULES = {
    "vid": FieldRule(name="vid", label="VID", group="basic", order=10, max_len=64, read_only=True),
    "entity_name": FieldRule(name="entity_name", label="名称", group="basic", order=20, max_len=256),
    "entity_type": FieldRule(
        name="entity_type",
        label="实体类型",
        group="basic",
        order=30,
        max_len=128,
        high_risk=True,
    ),
    "entity_raw_id": FieldRule(name="entity_raw_id", label="原始 ID", group="basic", order=40, max_len=256, read_only=True),
    "source": FieldRule(name="source", label="来源", group="basic", order=50, max_len=256),
    "hop_level": FieldRule(name="hop_level", label="Hop Level", group="basic", order=60, max_len=64, read_only=True),
    "description": FieldRule(
        name="description",
        label="描述",
        group="text",
        order=70,
        max_len=4096,
        multiline=True,
        long_text=LongTextRule(preview_chars=240),
    ),
    "synonyms": FieldRule(
        name="synonyms",
        label="同义词",
        group="text",
        order=80,
        max_len=4096,
        multiline=True,
        long_text=LongTextRule(preview_chars=240),
    ),
    "version": FieldRule(name="version", label="Version", group="system", order=90, max_len=32, read_only=True),
    "updated_at": FieldRule(name="updated_at", label="Updated At", group="system", order=100, max_len=32, read_only=True),
    "updated_by": FieldRule(name="updated_by", label="Updated By", group="system", order=110, max_len=64, read_only=True),
}
