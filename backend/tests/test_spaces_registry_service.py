import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

from app.services.spaces import provisioning_service, registry_service
from app.services.spaces.models import SpaceSummary


class SpacesRegistryServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="space-registry-tests-")
        self._patch_registry(self.tmpdir)
        registry_service.register_default_space()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_registry(self, root: str):
        root_path = Path(root)
        registry_service.REGISTRY_ROOT = root_path
        registry_service.REGISTRY_PATH = root_path / "spaces.json"
        registry_service.LOCK_PATH = root_path / "spaces.lock"

    def test_atomic_write_and_read_registry(self):
        summary = SpaceSummary(
            space_name="space_a",
            display_name="Space A",
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
        registry_service.write_space(summary)

        payload = registry_service.read_registry()
        self.assertEqual(payload.format_version, "spaces-v1")
        self.assertIn("space_a", payload.spaces)
        self.assertFalse(any(path.name.startswith("tmp") for path in Path(self.tmpdir).glob("*")))

    def test_provision_failure_marks_registry_failed(self):
        with (
            mock.patch("app.services.spaces.admin_executor.create_space", side_effect=RuntimeError("boom")),
            self.assertRaises(HTTPException),
        ):
            provisioning_service.create_space(
                space_name="space_fail",
                display_name="Space Fail",
                description="",
                template_type="entity_rel2_default",
                created_by="tester",
            )

        summary = registry_service.get_space("space_fail")
        self.assertIsNotNone(summary)
        self.assertEqual(summary.status, "failed")
        self.assertEqual(summary.internal_status, "failed")
        self.assertIn("boom", summary.last_error or "")

    def test_provision_success_creates_ready_space(self):
        with (
            mock.patch("app.services.spaces.admin_executor.create_space"),
            mock.patch("app.services.spaces.admin_executor.wait_until_space_ready"),
            mock.patch("app.services.spaces.admin_executor.apply_statements"),
            mock.patch("app.services.spaces.admin_executor.wait_until_statements_succeed") as wait_schema_ready_mock,
            mock.patch("app.services.imports.metadata_postprocess_service.refresh_from_db"),
        ):
            summary, warnings = provisioning_service.create_space(
                space_name="space_ready",
                display_name="Space Ready",
                description="",
                template_type="entity_rel2_default",
                created_by="tester",
            )

        self.assertEqual(summary.status, "ready")
        self.assertEqual(summary.internal_status, "ready")
        self.assertTrue(warnings)
        wait_schema_ready_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
