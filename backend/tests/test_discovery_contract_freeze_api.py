import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.services.spaces import registry_service


DISCOVERY_SPACE_META = {
    "space_name": "demo_kg",
    "graph_status": "ready",
    "search_status": "full",
    "coverage_pct": 100.0,
    "index_status": {
        "status": "verified_nonempty",
        "doc_count": 42,
        "nebula_entity_count": None,
        "coverage_pct": 100.0,
        "note": "",
        "updated_at": None,
    },
}


def _normalize_discovery_run(payload: dict) -> dict:
    return {
        **payload,
        "nodes": sorted(payload.get("nodes") or [], key=lambda item: int(item["id"])),
        "edges": sorted(
            payload.get("edges") or [],
            key=lambda item: (
                int(item["source"]),
                int(item["target"]),
                int(item.get("rank") or 0),
                str(item.get("relation") or ""),
            ),
        ),
        "dropped_candidates": sorted(
            payload.get("dropped_candidates") or [],
            key=lambda item: (str(item.get("reason") or ""), int(item.get("node_id") or 0)),
        ),
        "node_capabilities": sorted(payload.get("node_capabilities") or [], key=lambda item: int(item["node_id"])),
        "facets": {
            **(payload.get("facets") or {}),
            "entity_types": sorted(
                (payload.get("facets") or {}).get("entity_types") or [],
                key=lambda item: str(item.get("entity_type") or ""),
            ),
            "relation_types": sorted(
                (payload.get("facets") or {}).get("relation_types") or [],
                key=lambda item: str(item.get("relation_type") or ""),
            ),
            "layers": sorted(
                (payload.get("facets") or {}).get("layers") or [],
                key=lambda item: str(item.get("layer") or ""),
            ),
            "seeds": sorted(
                (payload.get("facets") or {}).get("seeds") or [],
                key=lambda item: int(item.get("seed_vid") or 0),
            ),
        },
    }


def _normalize_discovery_expand(payload: dict) -> dict:
    return {
        **payload,
        "new_nodes": sorted(payload.get("new_nodes") or [], key=lambda item: int(item["id"])),
        "new_edges": sorted(
            payload.get("new_edges") or [],
            key=lambda item: (
                int(item["source"]),
                int(item["target"]),
                int(item.get("rank") or 0),
                str(item.get("relation") or ""),
            ),
        ),
        "support_edges": sorted(
            payload.get("support_edges") or [],
            key=lambda item: (
                int(item["source"]),
                int(item["target"]),
                int(item.get("rank") or 0),
                str(item.get("relation") or ""),
            ),
        ),
        "dropped_candidates": sorted(
            payload.get("dropped_candidates") or [],
            key=lambda item: (str(item.get("reason") or ""), int(item.get("node_id") or 0)),
        ),
    }


class DiscoveryApiContractFreezeTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="discovery-contract-api-")
        root_path = Path(self.tmpdir) / "space-registry"
        registry_service.REGISTRY_ROOT = root_path
        registry_service.REGISTRY_PATH = root_path / "spaces.json"
        registry_service.LOCK_PATH = root_path / "spaces.lock"
        registry_service.register_default_space()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _client(self):
        return TestClient(app)

    def test_discovery_run_contract_freeze(self):
        frozen_payload = {
            "nodes": [
                {
                    "id": 20,
                    "label": "Candidate Beta",
                    "entity_type": "gene",
                    "raw_id": "HGNC:20",
                    "source": "demo",
                    "score": None,
                    "snippet": "candidate beta",
                    "role": "candidate",
                    "layer": "shared",
                    "priority_score": 9.25,
                    "min_seed_distance": 1,
                    "bridge_seed_count": 2,
                    "local_anchor_seed": None,
                    "matched_seed_pairs": ["1::2"],
                    "seed_support_count": 2,
                    "seed_support_vids": [1, 2],
                    "score_breakdown": {"is_valid_shared_bridge": True},
                },
                {
                    "id": 1,
                    "label": "Seed Alpha",
                    "entity_type": "disease",
                    "raw_id": "MONDO:1",
                    "source": "demo",
                    "score": None,
                    "snippet": "seed alpha",
                    "role": "seed",
                    "layer": "core",
                    "priority_score": 100.0,
                    "min_seed_distance": 0,
                    "bridge_seed_count": 0,
                    "local_anchor_seed": None,
                    "matched_seed_pairs": [],
                    "seed_support_count": 1,
                    "seed_support_vids": [1],
                    "score_breakdown": {"seed_rank": 1},
                },
            ],
            "edges": [
                {
                    "source": 20,
                    "target": 1,
                    "rank": "0",
                    "edge_type": "REL2",
                    "relation": "associated_with",
                    "source_db": "demo",
                    "role": "seed_candidate",
                    "layer": "shared",
                    "priority_score": 8.5,
                    "seed_support_vids": [1, 2],
                    "path_pair": "1::2",
                    "is_backbone": True,
                }
            ],
            "facets": {
                "entity_types": [
                    {
                        "entity_type": "gene",
                        "count": 1,
                        "seed_count": 0,
                        "candidate_count": 1,
                        "core_count": 0,
                        "shared_count": 1,
                        "local_count": 0,
                        "supplement_count": 0,
                    },
                    {
                        "entity_type": "disease",
                        "count": 1,
                        "seed_count": 1,
                        "candidate_count": 0,
                        "core_count": 1,
                        "shared_count": 0,
                        "local_count": 0,
                        "supplement_count": 0,
                    },
                ],
                "relation_types": [
                    {
                        "relation_type": "associated_with",
                        "count": 1,
                        "seed_candidate_count": 1,
                        "candidate_candidate_count": 0,
                        "seed_seed_count": 0,
                        "core_count": 0,
                        "shared_count": 1,
                        "local_count": 0,
                        "supplement_count": 0,
                    }
                ],
                "query_summary": {
                    "search_type": "graph_discovery",
                    "selected_seed_count": 1,
                    "selected_seeds": [{"id": 1, "label": "Seed Alpha", "entity_type": "disease"}],
                    "total_entities": 2,
                    "total_relationships": 1,
                },
                "layers": [
                    {"layer": "shared", "node_count": 1, "edge_count": 1},
                    {"layer": "core", "node_count": 1, "edge_count": 0},
                ],
                "seeds": [
                    {
                        "seed_vid": 1,
                        "label": "Seed Alpha",
                        "entity_type": "disease",
                        "local_count": 0,
                        "shared_touch_count": 1,
                        "core_path_count": 0,
                    }
                ],
            },
            "stats": {
                "ranking_mode": "layered_multiseed",
                "seed_count": 1,
                "seeds_count": 1,
                "candidate_count": 1,
                "node_count": 2,
                "edge_count": 1,
                "final_nodes": 2,
                "final_edges": 1,
                "truncated": False,
                "core_count": 1,
                "shared_count": 1,
                "local_count": 0,
                "supplement_count": 0,
                "dropped_nodes": 0,
                "dropped_edges": 0,
                "dropped_neighbors": 0,
                "dropped_by_budget": 0,
                "dropped_by_type_budget": 0,
                "dropped_generic_hubs": 0,
                "recall_candidate_count": 1,
                "kept_candidate_count": 1,
                "budget_applied": {"max_nodes": 90, "max_edges": 140},
            },
            "warnings": [],
            "dropped_candidates": [
                {
                    "node_id": 30,
                    "label": "Dropped Gamma",
                    "entity_type": "phenotype",
                    "raw_id": "HP:30",
                    "source": "demo",
                    "snippet": "dropped gamma",
                    "reason": "budget",
                    "source_node_id": 20,
                    "support_edges": [
                        {
                            "source": 20,
                            "target": 30,
                            "rank": "0",
                            "edge_type": "REL2",
                            "relation": "related_to",
                            "source_db": "demo",
                        }
                    ],
                }
            ],
            "node_capabilities": [
                {"node_id": 1, "expandable": True, "terminal": False},
                {"node_id": 20, "expandable": False, "terminal": True},
            ],
        }

        with (
            mock.patch("app.services.graph_discovery_service.discovery", return_value=frozen_payload),
            mock.patch("app.routers.graph.current_space_meta_payload", return_value=dict(DISCOVERY_SPACE_META)),
            self._client() as client,
        ):
            response = client.post("/api/graph/discovery", json={"seed_vids": [1]})

        self.assertEqual(response.status_code, 200, response.text)
        payload = _normalize_discovery_run(response.json())
        self.assertEqual(
            payload,
            _normalize_discovery_run(
                {
                    **frozen_payload,
                    "request_space": "demo_kg",
                    "space_meta": dict(DISCOVERY_SPACE_META),
                }
            ),
        )

    def test_discovery_expand_contract_freeze(self):
        frozen_payload = {
            "new_nodes": [
                {
                    "id": 11,
                    "label": "Expand Node",
                    "entity_type": "gene",
                    "raw_id": "HGNC:11",
                    "source": "demo",
                    "score": None,
                    "snippet": "expand node",
                    "role": "candidate",
                    "layer": "local",
                    "priority_score": 7.0,
                    "min_seed_distance": 1,
                    "bridge_seed_count": 0,
                    "local_anchor_seed": 1,
                    "matched_seed_pairs": [],
                    "seed_support_count": 1,
                    "seed_support_vids": [1],
                    "score_breakdown": {"expand_rank": 1},
                }
            ],
            "new_edges": [
                {
                    "source": 1,
                    "target": 11,
                    "rank": "0",
                    "edge_type": "REL2",
                    "relation": "treats",
                    "source_db": "demo",
                    "role": "seed_candidate",
                    "layer": "local",
                    "priority_score": 7.0,
                    "seed_support_vids": [1],
                    "path_pair": "",
                    "is_backbone": False,
                }
            ],
            "support_edges": [
                {
                    "source": 11,
                    "target": 1,
                    "rank": "1",
                    "edge_type": "REL2",
                    "relation": "related_to",
                    "source_db": "demo",
                    "role": "candidate_candidate",
                    "layer": "supplement",
                    "priority_score": 1.0,
                    "seed_support_vids": [1],
                    "path_pair": "",
                    "is_backbone": False,
                }
            ],
            "dropped_candidates": [
                {
                    "node_id": 12,
                    "label": "Filtered Type",
                    "entity_type": "phenotype",
                    "raw_id": "HP:12",
                    "source": "demo",
                    "snippet": "filtered type",
                    "reason": "type_filter",
                    "source_node_id": 1,
                    "support_edges": [],
                },
                {
                    "node_id": 13,
                    "label": "Filtered Budget",
                    "entity_type": "gene",
                    "raw_id": "HGNC:13",
                    "source": "demo",
                    "snippet": "filtered budget",
                    "reason": "budget",
                    "source_node_id": 1,
                    "support_edges": [],
                },
            ],
            "has_more_candidates_before_budget": True,
            "has_more_candidates_after_filters": True,
            "terminal": False,
            "warnings": [],
            "stats": {
                "candidate_neighbor_count": 4,
                "filtered_candidate_count": 2,
                "new_nodes_count": 1,
                "new_edges_count": 1,
                "dropped_by_budget": 1,
                "dropped_by_type_filter": 1,
                "dropped_by_relation_filter": 0,
                "dropped_neighbors": 0,
                "scanned_rows": 4,
                "budget_applied": {"expand_max_new_nodes": 1, "expand_max_new_edges": 1},
            },
        }

        with (
            mock.patch("app.services.graph_discovery_expand_service.expand", return_value=frozen_payload),
            mock.patch("app.routers.graph.current_space_meta_payload", return_value=dict(DISCOVERY_SPACE_META)),
            self._client() as client,
        ):
            response = client.post(
                "/api/graph/discovery/expand",
                json={
                    "target_node_id": 1,
                    "rendered_node_ids": [1],
                    "rendered_edge_ids": [],
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = _normalize_discovery_expand(response.json())
        self.assertEqual(
            payload,
            _normalize_discovery_expand(
                {
                    **frozen_payload,
                    "request_space": "demo_kg",
                    "space_meta": dict(DISCOVERY_SPACE_META),
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
