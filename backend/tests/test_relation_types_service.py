import time
import unittest

from app.services import metadata_service


class RelationTypesQueryTest(unittest.TestCase):
    def setUp(self):
        self.prev_cache = {
            "ts": metadata_service._RELATION_CACHE["ts"],
            "data": [dict(x) for x in metadata_service._RELATION_CACHE["data"]],
        }
        metadata_service._RELATION_CACHE["ts"] = time.time()
        metadata_service._RELATION_CACHE["data"] = [
            {"relation_type": "interacts_with", "count": 120},
            {"relation_type": "treats", "count": 90},
            {"relation_type": "associated_with", "count": 60},
            {"relation_type": "causes", "count": 40},
        ]

    def tearDown(self):
        metadata_service._RELATION_CACHE["ts"] = self.prev_cache["ts"]
        metadata_service._RELATION_CACHE["data"] = [dict(x) for x in self.prev_cache["data"]]

    def test_query_relation_types_returns_top_n_page(self):
        resp = metadata_service.query_relation_types(limit=2, offset=0)
        self.assertEqual(resp["matched_total"], 4)
        self.assertTrue(resp["has_more"])
        self.assertEqual(resp["next_offset"], 2)
        self.assertEqual(
            [item["relation_type"] for item in resp["items"]],
            ["interacts_with", "treats"],
        )

    def test_query_relation_types_filters_by_keyword(self):
        resp = metadata_service.query_relation_types(q="with", limit=10, offset=0)
        self.assertEqual(resp["matched_total"], 2)
        self.assertFalse(resp["has_more"])
        self.assertEqual(
            [item["relation_type"] for item in resp["items"]],
            ["interacts_with", "associated_with"],
        )


if __name__ == "__main__":
    unittest.main()
