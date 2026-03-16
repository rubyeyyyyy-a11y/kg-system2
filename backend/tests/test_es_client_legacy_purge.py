import unittest
from unittest import mock

from app.clients.es_client import ElasticsearchClient


class ElasticsearchLegacyPurgeTest(unittest.TestCase):
    def test_delete_missing_space_uses_global_delete_by_query_contract(self):
        client = ElasticsearchClient(index="kg_entity")
        captured = {}

        def fake_request(method, path, payload=None, query=None, **_kwargs):
            captured["method"] = method
            captured["path"] = path
            captured["payload"] = payload
            captured["query"] = query
            return {"deleted": 5}, 12.3

        with mock.patch.object(client, "_request_json", side_effect=fake_request):
            data, took_ms = client.delete_documents_missing_space()

        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/kg_entity/_delete_by_query")
        self.assertEqual(
            captured["payload"],
            {
                "query": {
                    "bool": {
                        "must_not": [
                            {"exists": {"field": "space_name"}},
                        ]
                    }
                }
            },
        )
        self.assertEqual(captured["query"]["conflicts"], "proceed")
        self.assertEqual(captured["query"]["refresh"], "true")
        self.assertEqual(captured["query"]["wait_for_completion"], "true")
        self.assertEqual(captured["query"]["slices"], "auto")
        self.assertEqual(data["deleted"], 5)
        self.assertEqual(took_ms, 12.3)


if __name__ == "__main__":
    unittest.main()
