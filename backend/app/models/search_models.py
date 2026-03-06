from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CandidateNode:
    vid: int
    label: str
    entity_type: str = ""
    raw_id: str = ""
    source: str = ""
    description: str = ""
    score: Optional[float] = None

    def to_node_payload(self) -> Dict[str, Any]:
        snippet = self.description or ""
        if snippet and len(snippet) > 160:
            snippet = snippet[:160] + "…"
        return {
            "id": int(self.vid),
            "label": self.label,
            "entity_type": self.entity_type,
            "raw_id": self.raw_id,
            "source": self.source,
            "score": None if self.score is None else round(float(self.score), 6),
            "snippet": snippet,
        }


@dataclass
class SearchDiagnostics:
    strategy: str
    request_id: str
    es_ms: float = 0.0
    candidate_ms: float = 0.0
    fetch_ms: float = 0.0
    serialize_ms: float = 0.0
    total_ms: float = 0.0
    reason: str = ""


@dataclass
class SearchResultBundle:
    nodes: List[CandidateNode] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    total_candidates: int = 0
    truncated: bool = False
    reason: str = ""
