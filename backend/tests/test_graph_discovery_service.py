import unittest

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


if __name__ == "__main__":
    unittest.main()
