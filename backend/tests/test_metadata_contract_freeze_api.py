import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.core.space_context import get_current_space
from app.main import app
from app.services import metadata_service, search_service
from app.services.spaces import registry_service
from app.services.spaces.models import SpaceSummary


class MetadataApiContractFreezeTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="metadata-contract-api-")
        root_path = Path(self.tmpdir) / "space-registry"
        registry_service.REGISTRY_ROOT = root_path
        registry_service.REGISTRY_PATH = root_path / "spaces.json"
        registry_service.LOCK_PATH = root_path / "spaces.lock"
        registry_service.register_default_space()
        registry_service.write_space(
            SpaceSummary(
                space_name="it_space_218354",
                display_name="it_space_218354",
                description="",
                template_type="entity_rel2_default",
                template_version="entity_rel2_default.v1",
                integration_scope="entity_rel2_core",
                status="ready",
                internal_status="ready",
                created_by="tester",
                created_at="2026-03-16T00:00:00Z",
                ready_at="2026-03-16T00:00:01Z",
            )
        )
        self._relation_cache_snapshot = {
            "demo_kg": metadata_service._RELATION_CACHE_BY_SPACE.get("demo_kg"),
            "it_space_218354": metadata_service._RELATION_CACHE_BY_SPACE.get("it_space_218354"),
        }
        metadata_service._RELATION_CACHE_BY_SPACE["demo_kg"] = {
            "ts": time.time(),
            "data": [
                {"relation_type": "interacts_with", "count": 120},
                {"relation_type": "treats", "count": 90},
                {"relation_type": "associated_with", "count": 60},
                {"relation_type": "causes", "count": 40},
            ],
        }

    def tearDown(self):
        for space_name, snapshot in self._relation_cache_snapshot.items():
            if snapshot is None:
                metadata_service._RELATION_CACHE_BY_SPACE.pop(space_name, None)
            else:
                metadata_service._RELATION_CACHE_BY_SPACE[space_name] = snapshot
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _client(self):
        return TestClient(app)

    def test_entity_types_contract_freeze(self):
        def fake_list_entity_types(limit: int = 200, *, space_name=None):
            self.assertEqual(limit, 200)
            current_space = str(space_name or get_current_space())
            if current_space == "demo_kg":
                return [
                    {"entity_type": "zeta", "count": 2},
                    {"entity_type": "alpha", "count": 9},
                ]
            if current_space == "it_space_218354":
                return []
            raise RuntimeError(f"unexpected space {current_space}")

        with (
            mock.patch("app.services.search_service.metadata_service.list_entity_types", side_effect=fake_list_entity_types),
            self._client() as client,
        ):
            demo_response = client.get("/api/entity_types")
            empty_response = client.get("/api/entity_types", headers={"X-KG-Space": "it_space_218354"})

        self.assertEqual(demo_response.status_code, 200, demo_response.text)
        self.assertEqual(
            demo_response.json(),
            [
                {"entity_type": "zeta", "count": 2},
                {"entity_type": "alpha", "count": 9},
            ],
        )
        self.assertEqual(empty_response.status_code, 200, empty_response.text)
        self.assertEqual(empty_response.json(), search_service.FALLBACK_ENTITY_TYPES)

    def test_entity_types_contract_freeze_fallback_list_on_error(self):
        with (
            mock.patch("app.services.search_service.metadata_service.list_entity_types", side_effect=RuntimeError("metadata down")),
            self._client() as client,
        ):
            response = client.get("/api/entity_types")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), search_service.FALLBACK_ENTITY_TYPES)

    def test_relation_types_contract_freeze(self):
        with self._client() as client:
            response = client.get("/api/relation_types?q=with&limit=2&offset=0")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {"relation_type": "interacts_with", "count": 120},
                    {"relation_type": "associated_with", "count": 60},
                ],
                "q": "with",
                "limit": 2,
                "offset": 0,
                "next_offset": None,
                "has_more": False,
                "matched_total": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
