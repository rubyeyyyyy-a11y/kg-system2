import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List


def vw(x):
    """ValueWrapper -> python primitive (or None)."""
    if x is None:
        return None
    if hasattr(x, "cast_primitive"):
        return x.cast_primitive()
    return x


def esc(s: str) -> str:
    """Escape string for embedding into nGQL double-quoted string."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def norm_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_raw_id(s: str) -> str:
    """
    Normalize entity_raw_id for tolerant contains search:
    - NFKC (full-width -> half-width)
    - full-width colon -> half-width colon
    - remove all colons
    - remove all whitespace
    - casefold
    """
    v = unicodedata.normalize("NFKC", s or "")
    v = v.replace("：", ":")
    v = v.replace(":", "")
    v = re.sub(r"\s+", "", v)
    return v.casefold()


def normalize_raw_id_for_suggest_prefix(s: str) -> str:
    """
    Normalize for raw_id prefix suggest:
    - NFKC
    - full-width colon -> half-width colon
    - keep colons (strict prefix semantics)
    - casefold
    """
    v = unicodedata.normalize("NFKC", s or "")
    v = v.replace("：", ":")
    return v.strip().casefold()


def normalize_raw_id_fallback_raw_match(s: str) -> str:
    """
    Fallback normalization when querying original entity_raw_id:
    - NFKC
    - full-width colon -> half-width colon
    - keep colon
    - casefold
    """
    v = unicodedata.normalize("NFKC", s or "")
    v = v.replace("：", ":")
    return v.strip().casefold()


def text_score(q: str, name: str, desc: str) -> float:
    """
    Local fuzzy scoring (python-side), independent of Nebula functions.
    We do candidate retrieval by CONTAINS, then re-rank here.
    """
    qn = norm_text(q)
    nn = norm_text(name)
    dn = norm_text(desc)

    s1 = 1.0 if qn and qn in nn else SequenceMatcher(None, qn, nn).ratio()
    s2 = 1.0 if qn and qn in dn else SequenceMatcher(None, qn, dn).ratio()
    return 0.85 * s1 + 0.15 * s2


def uniq_edges(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    out = []
    for e in edges:
        k = (
            int(e["source"]),
            int(e["target"]),
            str(e.get("relation") or ""),
            str(e.get("source_db") or ""),
        )
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def build_degree(nodes: List[int], edges: List[Dict[str, Any]]) -> Dict[int, int]:
    deg = {int(v): 0 for v in nodes}
    for e in edges:
        s = int(e["source"])
        t = int(e["target"])
        if s in deg:
            deg[s] += 1
        if t in deg:
            deg[t] += 1
    return deg


def truncate_by_degree(
    root_vid: int,
    keep_forced: List[int],
    nodes_all: List[int],
    edges_all: List[Dict[str, Any]],
    max_nodes: int,
):
    """
    Policy:
      - root_vid must keep
      - keep_forced (e.g. existing nodes) keep first
      - remaining fill by degree desc
      - edges kept only if both ends kept
    """
    nodes_all = [int(x) for x in nodes_all]
    forced_set = set(int(x) for x in keep_forced)
    forced_set.add(int(root_vid))

    deg = build_degree(nodes_all, edges_all)

    kept = []
    for v in nodes_all:
        if v in forced_set and v not in kept:
            kept.append(v)
            if len(kept) >= max_nodes:
                break

    if len(kept) < max_nodes:
        rest = [v for v in nodes_all if v not in set(kept)]
        rest.sort(key=lambda x: deg.get(x, 0), reverse=True)
        kept.extend(rest[: max_nodes - len(kept)])

    kept_set = set(kept)
    edges_kept = [
        e for e in edges_all if int(e["source"]) in kept_set and int(e["target"]) in kept_set
    ]
    dropped_nodes = max(0, len(set(nodes_all)) - len(kept_set))
    return kept, edges_kept, dropped_nodes
