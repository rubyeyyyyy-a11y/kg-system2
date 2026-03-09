import unittest
from unittest.mock import patch

from app.models.search_models import CandidateNode
from app.schemas.discovery import DiscoveryEntityCandidatesRequest
from app.services import discovery_entity_candidate_service


class DiscoveryEntityCandidateServiceTest(unittest.TestCase):
    def test_request_defaults_match_discovery_contract(self):
        req = DiscoveryEntityCandidatesRequest()

        self.assertEqual(req.page, 1)
        self.assertEqual(req.page_size, 100)
        self.assertTrue(req.search_in_name)
        self.assertTrue(req.search_in_description)
        self.assertFalse(req.search_in_type)
        self.assertFalse(req.search_in_raw_id)

    @patch("app.services.discovery_entity_candidate_service.search_v2_service.search_candidates_page")
    def test_entity_candidates_returns_paginated_payload(self, mock_search_candidates_page):
        mock_search_candidates_page.return_value = {
            "nodes": [
                CandidateNode(
                    vid=101,
                    label="Entity A",
                    entity_type="disease",
                    raw_id="RID:101",
                    source="UMLS",
                    description="A" * 200,
                    score=12.3456789,
                )
            ],
            "has_more": True,
            "meta": {"request_id": "req-1", "reason": "es_ok"},
        }

        resp = discovery_entity_candidate_service.entity_candidates(
            DiscoveryEntityCandidatesRequest(
                q="entity",
                page=2,
                page_size=100,
                search_in_name=True,
            )
        )

        self.assertEqual(resp["page"], 2)
        self.assertEqual(resp["page_size"], 100)
        self.assertEqual(resp["returned"], 1)
        self.assertTrue(resp["has_more"])
        self.assertEqual(resp["next_page"], 3)
        self.assertEqual(resp["meta"]["request_id"], "req-1")
        self.assertEqual(resp["items"][0]["id"], 101)
        self.assertEqual(resp["items"][0]["vid"], 101)
        self.assertEqual(resp["items"][0]["raw_id"], "RID:101")
        self.assertEqual(resp["items"][0]["source"], "UMLS")
        self.assertEqual(resp["items"][0]["score"], 12.345679)
        self.assertEqual(resp["items"][0]["description"], "A" * 200)
        self.assertTrue(resp["items"][0]["snippet"].endswith("…"))

        mock_search_candidates_page.assert_called_once()
        called_req = mock_search_candidates_page.call_args.kwargs
        self.assertEqual(called_req["offset"], 100)
        self.assertEqual(called_req["limit"], 100)

        search_req = mock_search_candidates_page.call_args.args[0]
        self.assertTrue(search_req.search_in_name)
        self.assertTrue(search_req.search_in_description)
        self.assertFalse(search_req.search_in_type)
        self.assertFalse(search_req.search_in_raw_id)

    @patch("app.services.discovery_entity_candidate_service.search_v2_service.search_candidates_page")
    def test_entity_candidates_clamps_page_and_page_size(self, mock_search_candidates_page):
        mock_search_candidates_page.return_value = {
            "nodes": [],
            "has_more": False,
            "meta": {"request_id": "req-2", "reason": "es_no_hits"},
        }

        resp = discovery_entity_candidate_service.entity_candidates(
            DiscoveryEntityCandidatesRequest(
                q="entity",
                page=0,
                page_size=999,
            )
        )

        self.assertEqual(resp["page"], 1)
        self.assertEqual(resp["page_size"], 100)
        self.assertEqual(resp["returned"], 0)
        self.assertFalse(resp["has_more"])
        self.assertIsNone(resp["next_page"])

        called_req = mock_search_candidates_page.call_args.kwargs
        self.assertEqual(called_req["offset"], 0)
        self.assertEqual(called_req["limit"], 100)


if __name__ == "__main__":
    unittest.main()
