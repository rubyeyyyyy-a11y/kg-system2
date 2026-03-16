import json
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.spaces import registry_service
from app.services.spaces.models import SpaceSummary


class SpaceContextTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="space-context-tests-")
        self._patch_registry(self.tmpdir)
        registry_service.register_default_space()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_registry(self, root: str):
        root_path = Path(root)
        registry_service.REGISTRY_ROOT = root_path
        registry_service.REGISTRY_PATH = root_path / "spaces.json"
        registry_service.LOCK_PATH = root_path / "spaces.lock"

    def _client(self):
        return TestClient(app, raise_server_exceptions=False)

    def test_missing_header_falls_back_default_space(self):
        with self._client() as client:
            resp = client.get("/api/spaces/current")

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["source"], "default")
        self.assertEqual(payload["space_name"], "demo_kg")

    def test_invalid_header_rejected(self):
        with self._client() as client:
            resp = client.get("/api/spaces/current", headers={"X-KG-Space": "bad space"})

        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["detail"]["error_code"], "SPACE_HEADER_INVALID")

    def test_unregistered_header_rejected(self):
        with self._client() as client:
            resp = client.get("/api/spaces/current", headers={"X-KG-Space": "ghost_space"})

        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(resp.json()["detail"]["error_code"], "SPACE_NOT_REGISTERED")

    def test_registered_header_resolves(self):
        registry_service.write_space(
            SpaceSummary(
                space_name="test_space_a",
                display_name="Test Space A",
                description="",
                template_type="entity_rel2_default",
                template_version="entity_rel2_default.v1",
                integration_scope="entity_rel2_core",
                status="ready",
                internal_status="ready",
                created_by="tester",
                created_at="2026-03-11T00:00:00Z",
                ready_at="2026-03-11T00:00:01Z",
            )
        )
        with self._client() as client:
            resp = client.get("/api/spaces/current", headers={"X-KG-Space": "test_space_a"})

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json()["space_name"], "test_space_a")
        self.assertEqual(resp.json()["source"], "header")


if __name__ == "__main__":
    unittest.main()
