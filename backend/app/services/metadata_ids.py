import hashlib

ENTITY_TYPE_META_VID_BASE = -9000000000000000000
RELATION_TYPE_META_VID_BASE = -8990000000000000000
_META_VID_SPAN = 900000000000000


def metadata_stat_vid(kind: str, key_norm: str, salt: int = 0) -> int:
    key = str(key_norm or "").strip().lower()
    if not key:
        raise ValueError("key_norm is required")

    if kind == "entity_type":
        base = ENTITY_TYPE_META_VID_BASE
    elif kind == "relation_type":
        base = RELATION_TYPE_META_VID_BASE
    else:
        raise ValueError(f"unsupported metadata kind: {kind}")

    raw = f"{kind}:{key}:{int(salt)}".encode("utf-8")
    digest = hashlib.sha1(raw).digest()
    offset = int.from_bytes(digest[:8], byteorder="big", signed=False) % _META_VID_SPAN
    return int(base + offset)
