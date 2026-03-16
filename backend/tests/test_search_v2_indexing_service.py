import unittest
from unittest import mock

from app.services.search_v2 import indexing_service


class SearchV2IndexingServiceTest(unittest.TestCase):
    def test_build_entity_doc_includes_space_contract(self):
        doc = indexing_service.build_entity_doc(
            {
                "vid": 42,
                "label": "Alpha",
                "description": "desc",
                "raw_id": "MONDO:42",
                "entity_type": "Disease",
                "source": "manual",
            },
            space_name="space_a",
        )

        self.assertEqual(doc["vid"], 42)
        self.assertEqual(doc["space_name"], "space_a")
        self.assertEqual(doc["entity_name"], "Alpha")
        self.assertEqual(doc["entity_raw_id"], "MONDO:42")
        self.assertEqual(doc["raw_id_norm"], "mondo42")

    def test_fetch_entity_rows_by_vids_uses_explicit_space(self):
        nebula = mock.Mock()
        nebula.fetch_entity_props.return_value = (
            [
                {
                    "vid": 1,
                    "label": "Alpha",
                    "entity_type": "Disease",
                    "raw_id": "MONDO:1",
                    "source": "manual",
                    "description": "desc",
                }
            ],
            1.2,
        )

        rows = indexing_service.fetch_entity_rows("space_b", vids=[1, 1, 2], nebula_client=nebula)

        self.assertEqual(len(rows), 1)
        nebula.fetch_entity_props.assert_called_once_with([1, 2], space_name="space_b")

    def test_bulk_upsert_reuses_existing_es_client(self):
        es = mock.Mock()
        es.bulk_upsert.return_value = (2, 0, 4.5)

        result = indexing_service.bulk_upsert(
            "space_c",
            [
                {"vid": 1, "space_name": "space_c", "entity_name": "A"},
                {"vid": 2, "entity_name": "B"},
            ],
            es_client=es,
            ensure_index=False,
        )

        self.assertEqual(result["ok_count"], 2)
        self.assertEqual(result["fail_count"], 0)
        es.ensure_index.assert_not_called()
        es.bulk_upsert.assert_called_once()
        submitted_docs = es.bulk_upsert.call_args.args[0]
        self.assertEqual(submitted_docs[0]["space_name"], "space_c")
        self.assertEqual(submitted_docs[1]["space_name"], "space_c")

    def test_iter_entity_doc_batches_advances_scan_cursor(self):
        with mock.patch(
            "app.services.search_v2.indexing_service.fetch_entity_rows",
            side_effect=[
                [
                    {"vid": 11, "label": "A", "raw_id": "RID:11", "entity_type": "Disease", "source": "manual", "description": ""},
                    {"vid": 12, "label": "B", "raw_id": "RID:12", "entity_type": "Disease", "source": "manual", "description": ""},
                ],
                [],
            ],
        ):
            batches = list(indexing_service.iter_entity_doc_batches("space_c", cursor=3, batch_size=2))

        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["cursor"], 3)
        self.assertEqual(batches[0]["next_cursor"], 5)
        self.assertEqual([doc["vid"] for doc in batches[0]["docs"]], [11, 12])

    def test_iter_entity_doc_batches_tracks_last_vid_for_stable_resume(self):
        with mock.patch(
            "app.services.search_v2.indexing_service.fetch_entity_rows",
            side_effect=[
                [
                    {"vid": 21, "label": "A", "raw_id": "RID:21", "entity_type": "Disease", "source": "manual", "description": ""},
                    {"vid": 25, "label": "B", "raw_id": "RID:25", "entity_type": "Disease", "source": "manual", "description": ""},
                ],
                [],
            ],
        ) as fetch_rows:
            batches = list(indexing_service.iter_entity_doc_batches("space_c", after_vid=20, batch_size=2))

        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["last_vid"], 25)
        self.assertEqual(batches[0]["next_after_vid"], 25)
        fetch_rows.assert_any_call(
            "space_c",
            cursor=0,
            after_vid=20,
            batch_size=2,
            vid_range=None,
            nebula_client=None,
        )

    def test_count_entities_uses_explicit_space(self):
        result = mock.Mock()
        result.column_values.return_value = [123]
        nebula = mock.Mock()
        nebula.execute.return_value = (result, 4.2)

        summary = indexing_service.count_entities("space_b", nebula_client=nebula)

        self.assertEqual(summary["count"], 123)
        nebula.execute.assert_called_once()
        self.assertEqual(nebula.execute.call_args.kwargs["space_name"], "space_b")

    def test_fetch_entity_rows_with_cursor_uses_stable_vid_order(self):
        result = mock.Mock()
        result.column_values.side_effect = lambda _name: []
        nebula = mock.Mock()
        nebula.execute.return_value = (result, 1.0)

        indexing_service.fetch_entity_rows("space_b", cursor=10, batch_size=20, nebula_client=nebula)

        ngql = nebula.execute.call_args.args[0]
        self.assertIn("ORDER BY vid ASC", ngql)
        self.assertIn("SKIP 10", ngql)
        self.assertIn("LIMIT 20", ngql)
        self.assertEqual(nebula.execute.call_args.kwargs["space_name"], "space_b")

    def test_verify_space_checks_sample_id_and_filtered_query(self):
        es = mock.Mock()
        es.count_documents_for_space.return_value = (1, 1.0)
        es.fetch_documents_for_space.return_value = (
            [
                {
                    "_id": "space_d:5",
                    "_source": {
                        "vid": 5,
                        "space_name": "space_d",
                        "entity_name": "Alpha",
                        "entity_raw_id": "MONDO:5",
                    },
                }
            ],
            2.0,
        )
        es.search_entity_vids_by_raw_id_norm.return_value = ([(5, 10.0)], 3.0)

        result = indexing_service.verify_space("space_d", es_client=es)

        self.assertTrue(result["ok"])
        self.assertEqual(result["doc_count"], 1)
        self.assertTrue(result["sample_query_ok"])
        es.search_entity_vids_by_raw_id_norm.assert_called_once()


if __name__ == "__main__":
    unittest.main()
