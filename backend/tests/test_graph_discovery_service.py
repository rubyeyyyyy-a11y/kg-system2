import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.schemas.discovery import GraphDiscoveryRequest
from app.services import graph_discovery_service


class GraphDiscoveryServiceTest(unittest.TestCase):
    def test_select_candidates_applies_per_type_limit_then_global_cap(self):
        candidates = [
            {"id": 1, "entity_type_norm": "gene", "score": 3000.0, "matched_seed_count": 3, "seed_edge_count": 1},
            {"id": 2, "entity_type_norm": "gene", "score": 2000.0, "matched_seed_count": 2, "seed_edge_count": 1},
            {"id": 3, "entity_type_norm": "gene", "score": 1000.0, "matched_seed_count": 1, "seed_edge_count": 1},
            {"id": 4, "entity_type_norm": "drug", "score": 2500.0, "matched_seed_count": 2, "seed_edge_count": 5},
            {"id": 5, "entity_type_norm": "drug", "score": 1500.0, "matched_seed_count": 1, "seed_edge_count": 5},
        ]

        kept = graph_discovery_service._select_candidates(
            candidates,
            top_k_per_type=2,
            candidate_cap=3,
        )

        self.assertEqual([item["id"] for item in kept], [1, 4, 2])

    def test_trim_edges_with_priority_prefers_seed_candidate(self):
        edges = [
            {"source": 10, "target": 11, "rank": "0", "relation": "r3", "source_db": "", "role": "candidate_candidate", "_priority_score": 20.0},
            {"source": 1, "target": 10, "rank": "0", "relation": "r1", "source_db": "", "role": "seed_candidate", "_priority_score": 100.0},
            {"source": 2, "target": 10, "rank": "0", "relation": "r2", "source_db": "", "role": "seed_candidate", "_priority_score": 90.0},
            {"source": 1, "target": 2, "rank": "0", "relation": "r4", "source_db": "", "role": "seed_seed", "_priority_score": 0.0},
        ]

        kept, dropped = graph_discovery_service._trim_edges_with_priority(edges, max_edges=2)

        self.assertEqual(dropped, 2)
        self.assertEqual([edge["role"] for edge in kept], ["seed_candidate", "seed_candidate"])

    def test_build_facets_counts_node_and_edge_roles(self):
        facets = graph_discovery_service._build_facets(
            nodes=[
                {"id": 1, "entity_type": "drug", "role": "seed"},
                {"id": 2, "entity_type": "drug", "role": "candidate"},
                {"id": 3, "entity_type": "gene", "role": "candidate"},
            ],
            edges=[
                {"source": 1, "target": 2, "rank": "0", "relation": "treats", "role": "seed_candidate"},
                {"source": 2, "target": 3, "rank": "0", "relation": "interacts_with", "role": "candidate_candidate"},
                {"source": 1, "target": 1, "rank": "0", "relation": "self", "role": "seed_seed"},
            ],
        )

        self.assertEqual(facets["entity_types"][0]["entity_type"], "drug")
        self.assertEqual(facets["entity_types"][0]["seed_count"], 1)
        self.assertEqual(facets["entity_types"][0]["candidate_count"], 1)
        rel_map = {item["relation_type"]: item for item in facets["relation_types"]}
        self.assertEqual(rel_map["treats"]["seed_candidate_count"], 1)
        self.assertEqual(rel_map["interacts_with"]["candidate_candidate_count"], 1)
        self.assertEqual(rel_map["self"]["seed_seed_count"], 1)
        self.assertEqual(rel_map["self"]["core_count"], 0)

    def test_discovery_rejects_max_nodes_smaller_than_seed_count(self):
        req = GraphDiscoveryRequest(
            seed_vids=[1, 2],
            max_nodes=1,
            max_edges=10,
            top_k_per_type=2,
            hop=1,
        )

        with self.assertRaises(HTTPException) as ctx:
            graph_discovery_service.discovery(req)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail["code"], "graph_discovery_max_nodes_invalid")

    @patch("app.services.graph_discovery_service._fetch_entity_nodes")
    @patch("app.services.graph_discovery_service._find_shortest_path_candidates_bfs")
    @patch("app.services.graph_discovery_service._go_edges_from")
    def test_layered_discovery_returns_core_shared_local_and_facets(
        self,
        mock_go_edges_from,
        mock_find_shortest_path_candidates_bfs,
        mock_fetch_entity_nodes,
    ):
        mock_go_edges_from.side_effect = [
            (
                [
                    {"source": 1, "target": 2, "rank": "0", "edge_type": "REL2", "relation": "direct_rel", "source_db": "db"},
                    {"source": 1, "target": 10, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
                    {"source": 2, "target": 10, "rank": "0", "edge_type": "REL2", "relation": "associated_with", "source_db": "db"},
                    {"source": 2, "target": 20, "rank": "0", "edge_type": "REL2", "relation": "binds", "source_db": "db"},
                    {"source": 3, "target": 30, "rank": "0", "edge_type": "REL2", "relation": "causes", "source_db": "db"},
                ],
                {"scanned_rows": 5, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
            (
                [
                    {"source": 10, "target": 20, "rank": "0", "edge_type": "REL2", "relation": "interacts_with", "source_db": "db"},
                ],
                {"scanned_rows": 1, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
        ]
        mock_find_shortest_path_candidates_bfs.side_effect = [
            (
                [
                    {
                        "nodes": [1, 40, 3],
                        "edges": [
                            {"source": 1, "target": 40, "rank": "0", "edge_type": "REL2", "relation": "path_a", "source_db": "db"},
                            {"source": 40, "target": 3, "rank": "0", "edge_type": "REL2", "relation": "path_b", "source_db": "db"},
                        ],
                    }
                ],
                {"scanned_rows": 2, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
            (
                [],
                {"scanned_rows": 0, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
        ]

        def fetch_side_effect(node_ids):
            ids = set(int(v) for v in node_ids)
            data = {
                1: {"id": 1, "label": "Seed1", "entity_type": "disease", "raw_id": "S1", "source": "db", "snippet": ""},
                2: {"id": 2, "label": "Seed2", "entity_type": "gene", "raw_id": "S2", "source": "db", "snippet": ""},
                3: {"id": 3, "label": "Seed3", "entity_type": "drug", "raw_id": "S3", "source": "db", "snippet": ""},
                10: {"id": 10, "label": "Shared10", "entity_type": "gene", "raw_id": "C10", "source": "db", "snippet": ""},
                20: {"id": 20, "label": "Local20", "entity_type": "drug", "raw_id": "C20", "source": "db", "snippet": ""},
                30: {"id": 30, "label": "Local30", "entity_type": "phenotype", "raw_id": "C30", "source": "db", "snippet": ""},
                40: {"id": 40, "label": "Core40", "entity_type": "protein", "raw_id": "C40", "source": "db", "snippet": ""},
            }
            return {vid: item for vid, item in data.items() if vid in ids}

        mock_fetch_entity_nodes.side_effect = fetch_side_effect

        req = GraphDiscoveryRequest(
            seed_vids=[1, 2, 3],
            max_nodes=8,
            max_edges=12,
            top_k_per_type=3,
            hop=3,
            ranking_mode="layered_multiseed",
            include_candidate_candidate_edges=True,
        )

        resp = graph_discovery_service.discovery(req)

        self.assertEqual(resp["stats"]["ranking_mode"], "layered_multiseed")
        self.assertEqual(resp["stats"]["seed_count"], 3)
        self.assertEqual(resp["stats"]["seeds_count"], 3)
        node_map = {node["id"]: node for node in resp["nodes"]}
        self.assertEqual(node_map[40]["layer"], "core")
        self.assertEqual(node_map[10]["layer"], "shared")
        self.assertEqual(node_map[20]["layer"], "local")
        self.assertEqual(node_map[30]["layer"], "local")
        self.assertTrue(bool(node_map[10]["score_breakdown"]["is_valid_shared_bridge"]))
        self.assertEqual(resp["facets"]["query_summary"]["selected_seed_count"], 3)
        self.assertEqual(resp["facets"]["query_summary"]["total_entities"], len(resp["nodes"]))
        self.assertEqual(resp["facets"]["query_summary"]["total_relationships"], len(resp["edges"]))
        layer_map = {item["layer"]: item for item in resp["facets"]["layers"]}
        self.assertGreaterEqual(layer_map["core"]["node_count"], 1)
        self.assertGreaterEqual(layer_map["shared"]["node_count"], 1)
        self.assertEqual(resp["stats"]["core_count"], 1)
        self.assertEqual(resp["stats"]["shared_count"], 1)
        self.assertEqual(resp["stats"]["local_count"], 2)
        self.assertEqual(resp["stats"]["supplement_count"], 0)
        seed_map = {item["seed_vid"]: item for item in resp["facets"]["seeds"]}
        self.assertEqual(seed_map[2]["local_count"], 1)
        self.assertEqual(seed_map[3]["local_count"], 1)
        self.assertGreaterEqual(seed_map[1]["core_path_count"], 1)
        rel_map = {item["relation_type"]: item for item in resp["facets"]["relation_types"]}
        self.assertEqual(rel_map["direct_rel"]["seed_seed_count"], 1)
        self.assertGreaterEqual(rel_map["path_a"]["core_count"], 1)
        self.assertGreaterEqual(rel_map["treats"]["shared_count"], 1)
        self.assertEqual(resp["stats"]["dropped_generic_hubs"], 0)

    @patch("app.services.graph_discovery_service._fetch_entity_nodes")
    @patch("app.services.graph_discovery_service._find_shortest_path_candidates_bfs")
    @patch("app.services.graph_discovery_service._go_edges_from")
    def test_layered_discovery_suppresses_generic_hub_and_tracks_drop_reasons(
        self,
        mock_go_edges_from,
        mock_find_shortest_path_candidates_bfs,
        mock_fetch_entity_nodes,
    ):
        mock_go_edges_from.side_effect = [
            (
                [
                    {"source": 1, "target": 10, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
                    {"source": 2, "target": 10, "rank": "0", "edge_type": "REL2", "relation": "associated_with", "source_db": "db"},
                    {"source": 1, "target": 20, "rank": "0", "edge_type": "REL2", "relation": "binds", "source_db": "db"},
                    {"source": 3, "target": 30, "rank": "0", "edge_type": "REL2", "relation": "causes", "source_db": "db"},
                    {"source": 1, "target": 50, "rank": "0", "edge_type": "REL2", "relation": "mentions", "source_db": "db"},
                ],
                {"scanned_rows": 5, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
            (
                [
                    {"source": 10, "target": 20, "rank": "0", "edge_type": "REL2", "relation": "interacts_with", "source_db": "db"},
                    {"source": 20, "target": 30, "rank": "0", "edge_type": "REL2", "relation": "coexists_with", "source_db": "db"},
                ],
                {"scanned_rows": 2, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
        ]
        mock_find_shortest_path_candidates_bfs.side_effect = [
            (
                [
                    {
                        "nodes": [1, 40, 3],
                        "edges": [
                            {"source": 1, "target": 40, "rank": "0", "edge_type": "REL2", "relation": "path_a", "source_db": "db"},
                            {"source": 40, "target": 3, "rank": "0", "edge_type": "REL2", "relation": "path_b", "source_db": "db"},
                        ],
                    }
                ],
                {"scanned_rows": 2, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
            (
                [],
                {"scanned_rows": 0, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
            (
                [],
                {"scanned_rows": 0, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
            ),
        ]

        def fetch_side_effect(node_ids):
            ids = set(int(v) for v in node_ids)
            data = {
                1: {"id": 1, "label": "Seed1", "entity_type": "gene", "raw_id": "S1", "source": "db", "snippet": ""},
                2: {"id": 2, "label": "Seed2", "entity_type": "drug", "raw_id": "S2", "source": "db", "snippet": ""},
                3: {"id": 3, "label": "Seed3", "entity_type": "phenotype", "raw_id": "S3", "source": "db", "snippet": ""},
                10: {"id": 10, "label": "Shared10", "entity_type": "gene", "raw_id": "C10", "source": "db", "snippet": ""},
                20: {"id": 20, "label": "Local20", "entity_type": "drug", "raw_id": "C20", "source": "db", "snippet": ""},
                30: {"id": 30, "label": "Local30", "entity_type": "phenotype", "raw_id": "C30", "source": "db", "snippet": ""},
                40: {"id": 40, "label": "Core40", "entity_type": "protein", "raw_id": "C40", "source": "db", "snippet": ""},
                50: {"id": 50, "label": "disease", "entity_type": "disease", "raw_id": "C50", "source": "db", "snippet": ""},
            }
            return {vid: item for vid, item in data.items() if vid in ids}

        mock_fetch_entity_nodes.side_effect = fetch_side_effect

        req = GraphDiscoveryRequest(
            seed_vids=[1, 2, 3],
            max_nodes=8,
            max_edges=12,
            top_k_per_type=3,
            hop=3,
            ranking_mode="layered_multiseed",
            include_candidate_candidate_edges=True,
        )

        resp = graph_discovery_service.discovery(req)

        node_ids = {node["id"] for node in resp["nodes"]}
        self.assertNotIn(50, node_ids)
        self.assertEqual(resp["stats"]["core_count"], 1)
        self.assertEqual(resp["stats"]["shared_count"], 1)
        self.assertEqual(resp["stats"]["local_count"], 2)
        self.assertEqual(resp["stats"]["supplement_count"], 0)
        self.assertEqual(resp["stats"]["dropped_generic_hubs"], 1)
        self.assertEqual(resp["stats"]["dropped_by_budget"], 0)
        self.assertEqual(resp["stats"]["budget_applied"]["ranking_mode"], "layered_multiseed")
        self.assertEqual(resp["stats"]["budget_applied"]["dropped"]["generic_hubs"], 1)


if __name__ == "__main__":
    unittest.main()
