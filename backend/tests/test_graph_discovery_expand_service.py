import unittest
from unittest.mock import patch

from app.schemas.discovery import DiscoveryDroppedReason, GraphDiscoveryExpandRequest
from app.services import graph_discovery_expand_service


class GraphDiscoveryExpandServiceTest(unittest.TestCase):
    @patch("app.services.graph_discovery_expand_service._fetch_entity_nodes")
    @patch("app.services.graph_discovery_expand_service._go_edges_from")
    def test_expand_returns_incremental_nodes_and_structured_drop_reasons(
        self,
        mock_go_edges_from,
        mock_fetch_entity_nodes,
    ):
        mock_go_edges_from.return_value = (
            [
                {"source": 1, "target": 11, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
                {"source": 1, "target": 12, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
                {"source": 1, "target": 13, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
                {"source": 1, "target": 14, "rank": "0", "edge_type": "REL2", "relation": "related_to", "source_db": "db"},
                {"source": 1, "target": 15, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
            ],
            {"scanned_rows": 5, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
        )
        mock_fetch_entity_nodes.return_value = {
            11: {"id": 11, "label": "A", "entity_type": "gene", "raw_id": "G11", "source": "db", "snippet": ""},
            12: {"id": 12, "label": "B", "entity_type": "gene", "raw_id": "G12", "source": "db", "snippet": ""},
            13: {"id": 13, "label": "C", "entity_type": "phenotype", "raw_id": "P13", "source": "db", "snippet": ""},
            14: {"id": 14, "label": "D", "entity_type": "gene", "raw_id": "G14", "source": "db", "snippet": ""},
            15: {"id": 15, "label": "E", "entity_type": "gene", "raw_id": "G15", "source": "db", "snippet": ""},
        }

        resp = graph_discovery_expand_service.expand(
            GraphDiscoveryExpandRequest(
                target_node_id=1,
                rendered_node_ids=[1],
                rendered_edge_ids=[],
                allowed_entity_types=["gene"],
                allowed_relation_types=["treats"],
                expand_max_new_nodes=1,
                expand_max_new_edges=1,
                expand_top_k_per_type=8,
                expand_max_hop=1,
            )
        )

        self.assertEqual([node["id"] for node in resp["new_nodes"]], [11])
        self.assertEqual(len(resp["new_edges"]), 1)
        self.assertEqual(resp["support_edges"], [])
        reason_map = {item["node_id"]: item["reason"] for item in resp["dropped_candidates"]}
        self.assertEqual(reason_map[13], DiscoveryDroppedReason.TYPE_FILTER)
        self.assertEqual(reason_map[14], DiscoveryDroppedReason.RELATION_FILTER)
        self.assertEqual(reason_map[12], DiscoveryDroppedReason.BUDGET)
        self.assertEqual(reason_map[15], DiscoveryDroppedReason.BUDGET)
        self.assertTrue(resp["has_more_candidates_before_budget"])
        self.assertTrue(resp["has_more_candidates_after_filters"])
        self.assertFalse(resp["terminal"])

    @patch("app.services.graph_discovery_expand_service._fetch_entity_nodes")
    @patch("app.services.graph_discovery_expand_service._go_edges_from")
    def test_expand_probe_marks_terminal_when_filters_remove_all_candidates(
        self,
        mock_go_edges_from,
        mock_fetch_entity_nodes,
    ):
        mock_go_edges_from.return_value = (
            [
                {"source": 1, "target": 11, "rank": "0", "edge_type": "REL2", "relation": "related_to", "source_db": "db"},
            ],
            {"scanned_rows": 1, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
        )
        mock_fetch_entity_nodes.return_value = {
            11: {"id": 11, "label": "A", "entity_type": "gene", "raw_id": "G11", "source": "db", "snippet": ""},
        }

        resp = graph_discovery_expand_service.expand(
            GraphDiscoveryExpandRequest(
                target_node_id=1,
                rendered_node_ids=[1],
                rendered_edge_ids=[],
                allowed_entity_types=["gene"],
                allowed_relation_types=["treats"],
                expand_max_new_nodes=0,
                expand_max_new_edges=0,
                expand_top_k_per_type=8,
                expand_max_hop=1,
            )
        )

        self.assertEqual(resp["new_nodes"], [])
        self.assertEqual(resp["new_edges"], [])
        self.assertEqual(resp["support_edges"], [])
        self.assertTrue(resp["has_more_candidates_before_budget"])
        self.assertFalse(resp["has_more_candidates_after_filters"])
        self.assertTrue(resp["terminal"])
        self.assertEqual(resp["stats"]["dropped_by_relation_filter"], 1)

    @patch("app.services.graph_discovery_expand_service._fetch_entity_nodes")
    @patch("app.services.graph_discovery_expand_service._go_edges_from")
    def test_expand_does_not_return_already_rendered_nodes(
        self,
        mock_go_edges_from,
        mock_fetch_entity_nodes,
    ):
        mock_go_edges_from.return_value = (
            [
                {"source": 1, "target": 11, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
            ],
            {"scanned_rows": 1, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
        )
        mock_fetch_entity_nodes.return_value = {
            11: {"id": 11, "label": "A", "entity_type": "gene", "raw_id": "G11", "source": "db", "snippet": ""},
        }

        resp = graph_discovery_expand_service.expand(
            GraphDiscoveryExpandRequest(
                target_node_id=1,
                rendered_node_ids=[1, 11],
                rendered_edge_ids=["1**11**0"],
                allowed_entity_types=["gene"],
                allowed_relation_types=["treats"],
                expand_max_new_nodes=20,
                expand_max_new_edges=30,
                expand_top_k_per_type=8,
                expand_max_hop=1,
            )
        )

        self.assertEqual(resp["new_nodes"], [])
        self.assertEqual(resp["new_edges"], [])
        self.assertEqual(resp["support_edges"], [])
        self.assertFalse(resp["has_more_candidates_before_budget"])
        self.assertFalse(resp["has_more_candidates_after_filters"])
        self.assertTrue(resp["terminal"])

    @patch("app.services.graph_discovery_expand_service._fetch_entity_nodes")
    @patch("app.services.graph_discovery_expand_service._go_edges_from")
    def test_expand_returns_support_edges_for_selected_nodes_not_promoted_to_new_edges(
        self,
        mock_go_edges_from,
        mock_fetch_entity_nodes,
    ):
        mock_go_edges_from.return_value = (
            [
                {"source": 11, "target": 1, "rank": "0", "edge_type": "REL2", "relation": "treats", "source_db": "db"},
                {"source": 11, "target": 1, "rank": "1", "edge_type": "REL2", "relation": "related_to", "source_db": "db"},
            ],
            {"scanned_rows": 2, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 0},
        )
        mock_fetch_entity_nodes.return_value = {
            11: {"id": 11, "label": "A", "entity_type": "gene", "raw_id": "G11", "source": "db", "snippet": ""},
        }

        resp = graph_discovery_expand_service.expand(
            GraphDiscoveryExpandRequest(
                target_node_id=1,
                rendered_node_ids=[1],
                rendered_edge_ids=[],
                allowed_entity_types=["gene"],
                allowed_relation_types=[],
                expand_max_new_nodes=1,
                expand_max_new_edges=1,
                expand_top_k_per_type=8,
                expand_max_hop=1,
            )
        )

        self.assertEqual([node["id"] for node in resp["new_nodes"]], [11])
        self.assertEqual(len(resp["new_edges"]), 1)
        self.assertEqual(len(resp["support_edges"]), 1)
        incident_edges = resp["new_edges"] + resp["support_edges"]
        self.assertTrue(all(1 in (int(edge["source"]), int(edge["target"])) for edge in incident_edges))


if __name__ == "__main__":
    unittest.main()
