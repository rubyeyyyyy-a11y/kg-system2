import time
import unittest

from app.services import metadata_service


class RelationTypesQueryTest(unittest.TestCase):
    def setUp(self):
        self.space_name = "demo_kg"
        self.prev_cache = {
            "ts": metadata_service._RELATION_CACHE_BY_SPACE.get(self.space_name, {}).get("ts", 0.0),
            "data": [dict(x) for x in metadata_service._RELATION_CACHE_BY_SPACE.get(self.space_name, {}).get("data", [])],
        }
        metadata_service._RELATION_CACHE_BY_SPACE[self.space_name] = {
            "ts": time.time(),
            "data": [
            {"relation_type": "interacts_with", "count": 120},
            {"relation_type": "treats", "count": 90},
            {"relation_type": "associated_with", "count": 60},
            {"relation_type": "causes", "count": 40},
            ],
        }

    def tearDown(self):
        metadata_service._RELATION_CACHE_BY_SPACE[self.space_name] = {
            "ts": self.prev_cache["ts"],
            "data": [dict(x) for x in self.prev_cache["data"]],
        }

    def test_query_relation_types_returns_top_n_page(self):
        resp = metadata_service.query_relation_types(limit=2, offset=0, space_name=self.space_name)
        self.assertEqual(resp["matched_total"], 4)
        self.assertTrue(resp["has_more"])
        self.assertEqual(resp["next_offset"], 2)
        self.assertEqual(
            [item["relation_type"] for item in resp["items"]],
            ["interacts_with", "treats"],
        )

    def test_query_relation_types_filters_by_keyword(self):
        resp = metadata_service.query_relation_types(q="with", limit=10, offset=0, space_name=self.space_name)
        self.assertEqual(resp["matched_total"], 2)
        self.assertFalse(resp["has_more"])
        self.assertEqual(
            [item["relation_type"] for item in resp["items"]],
            ["interacts_with", "associated_with"],
        )


if __name__ == "__main__":
    unittest.main()
