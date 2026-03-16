import unittest
from unittest import mock

from app.services import graph_service


class _FakeGraphResult:
    def __init__(self, columns):
        self._columns = columns

    def is_succeeded(self):
        return True

    def error_msg(self):
        return ""

    def column_values(self, name):
        return self._columns[name]


class GraphTraversalHelperCharacterizationTest(unittest.TestCase):
    def test_go_edges_from_applies_relation_filter_and_neighbor_cap(self):
        fake_result = _FakeGraphResult(
            {
                "src": [1, 1, 3, 5],
                "dst": [2, 3, 1, 6],
                "rank": [0, 0, 1, 0],
                "relation": ["kept_rel", "filtered_rel", "kept_rel", "kept_rel"],
                "esource": ["demo", "demo", "demo", "demo"],
            }
        )

        with mock.patch("app.services.graph_service.execute_ngql", return_value=fake_result):
            edges, meta = graph_service._go_edges_from(
                frontier=[1],
                rel_filter={"kept_rel"},
                query_scan_limit=50,
                per_root_neighbor_cap=1,
                ignore_direction=True,
            )

        self.assertEqual(
            edges,
            [
                {
                    "source": 1,
                    "target": 2,
                    "rank": "0",
                    "edge_type": "REL2",
                    "relation": "kept_rel",
                    "source_db": "demo",
                }
            ],
        )
        self.assertEqual(
            meta,
            {
                "scanned_rows": 4,
                "dropped_by_relation": 1,
                "dropped_by_neighbor_cap": 1,
            },
        )

    def test_go_edges_from_ignore_direction_semantics_are_frozen(self):
        fake_result = _FakeGraphResult(
            {
                "src": [3],
                "dst": [1],
                "rank": [7],
                "relation": ["reverse_rel"],
                "esource": ["demo"],
            }
        )

        with mock.patch("app.services.graph_service.execute_ngql", return_value=fake_result):
            directed_edges, directed_meta = graph_service._go_edges_from(
                frontier=[1],
                rel_filter=set(),
                query_scan_limit=50,
                per_root_neighbor_cap=3,
                ignore_direction=False,
            )
            bidirectional_edges, bidirectional_meta = graph_service._go_edges_from(
                frontier=[1],
                rel_filter=set(),
                query_scan_limit=50,
                per_root_neighbor_cap=3,
                ignore_direction=True,
            )

        self.assertEqual(directed_edges, [])
        self.assertEqual(directed_meta["dropped_by_relation"], 0)
        self.assertEqual(directed_meta["dropped_by_neighbor_cap"], 0)
        self.assertEqual(
            bidirectional_edges,
            [
                {
                    "source": 3,
                    "target": 1,
                    "rank": "7",
                    "edge_type": "REL2",
                    "relation": "reverse_rel",
                    "source_db": "demo",
                }
            ],
        )
        self.assertEqual(bidirectional_meta["scanned_rows"], 1)

    def test_find_shortest_path_candidates_bfs_freezes_ordering_limit_and_meta_aggregation(self):
        with mock.patch(
            "app.services.graph_service._go_edges_from",
            side_effect=[
                (
                    [
                        {"source": 1, "target": 3, "rank": "0", "edge_type": "REL2", "relation": "r13", "source_db": "demo"},
                        {"source": 1, "target": 2, "rank": "0", "edge_type": "REL2", "relation": "r12", "source_db": "demo"},
                    ],
                    {"scanned_rows": 2, "dropped_by_relation": 1, "dropped_by_neighbor_cap": 0},
                ),
                (
                    [
                        {"source": 3, "target": 4, "rank": "0", "edge_type": "REL2", "relation": "r34", "source_db": "demo"},
                        {"source": 2, "target": 4, "rank": "0", "edge_type": "REL2", "relation": "r24", "source_db": "demo"},
                    ],
                    {"scanned_rows": 3, "dropped_by_relation": 0, "dropped_by_neighbor_cap": 2},
                ),
            ],
        ):
            paths, meta = graph_service._find_shortest_path_candidates_bfs(
                src=1,
                dst=4,
                max_hop=2,
                rel_filter=set(),
                query_scan_limit=20,
                per_root_neighbor_cap=4,
                ignore_direction=True,
                candidate_limit=1,
            )

        self.assertEqual(
            paths,
            [
                {
                    "nodes": [1, 2, 4],
                    "edges": [
                        {"source": 1, "target": 2, "rank": "0", "edge_type": "REL2", "relation": "r12", "source_db": "demo"},
                        {"source": 2, "target": 4, "rank": "0", "edge_type": "REL2", "relation": "r24", "source_db": "demo"},
                    ],
                }
            ],
        )
        self.assertEqual(
            meta,
            {
                "scanned_rows": 5,
                "dropped_by_relation": 1,
                "dropped_by_neighbor_cap": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
