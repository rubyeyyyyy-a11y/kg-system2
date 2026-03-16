import shutil
import tempfile
import unittest
from pathlib import Path

from app.services.spaces import registry_service
from app.services.spaces.models import SpaceSummary
from scripts import backfill_es_spaces


class BackfillEsSpacesTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="backfill-es-tests-")
        self._patch_registry_root(self.tmpdir)
        registry_service.register_default_space()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_registry_root(self, root: str):
        root_path = Path(root) / "space-registry"
        registry_service.REGISTRY_ROOT = root_path
        registry_service.REGISTRY_PATH = root_path / "spaces.json"
        registry_service.LOCK_PATH = root_path / "spaces.lock"

    def _write_space(self, *, space_name: str, status: str):
        registry_service.write_space(
            SpaceSummary(
                space_name=space_name,
                display_name=space_name,
                description="",
                template_type="entity_rel2_default",
                template_version="entity_rel2_default.v1",
                integration_scope="entity_rel2_core",
                status=status,
                internal_status="ready" if status == "ready" else "failed",
                created_by="tester",
                created_at="2026-03-11T00:00:00Z",
                ready_at="2026-03-11T00:00:01Z" if status == "ready" else None,
                last_error="boom" if status == "failed" else None,
            )
        )

    def test_ready_managed_spaces_include_default_and_ready_only(self):
        self._write_space(space_name="space_ready", status="ready")
        self._write_space(space_name="space_failed", status="failed")

        spaces = backfill_es_spaces.ready_managed_spaces()

        self.assertIn("demo_kg", spaces)
        self.assertIn("space_ready", spaces)
        self.assertNotIn("space_failed", spaces)

    def test_resolve_target_spaces_rejects_non_ready_explicit_space(self):
        self._write_space(space_name="space_failed", status="failed")

        with self.assertRaises(RuntimeError):
            backfill_es_spaces.resolve_target_spaces(["space_failed"], include_all_ready=False)

    def test_update_space_state_buckets_progress_by_space(self):
        payload = {"format_version": "es-backfill-v1", "spaces": {}}

        backfill_es_spaces.update_space_state(payload, space_name="demo_kg", cursor=10, indexed_total=20, last_vid=100)
        backfill_es_spaces.update_space_state(payload, space_name="space_a", cursor=30, indexed_total=40, last_vid=300)

        self.assertEqual(payload["spaces"]["demo_kg"]["cursor"], 10)
        self.assertEqual(payload["spaces"]["demo_kg"]["last_vid"], 100)
        self.assertEqual(payload["spaces"]["space_a"]["cursor"], 30)
        self.assertEqual(payload["spaces"]["space_a"]["last_vid"], 300)
        self.assertNotEqual(payload["spaces"]["demo_kg"]["cursor"], payload["spaces"]["space_a"]["cursor"])

    def test_update_space_state_persists_completion_fields(self):
        payload = {"format_version": "es-backfill-v2", "spaces": {}}

        backfill_es_spaces.update_space_state(
            payload,
            space_name="demo_kg",
            cursor=10,
            indexed_total=20,
            last_vid=100,
            phase="verified_partial",
            status="verified_partial",
            note="still running",
            es_doc_count=20,
            nebula_entity_count=100,
            coverage_pct=20.0,
            full_completion=False,
            remaining_docs=80,
            verify_result={"ok": True},
        )

        bucket = payload["spaces"]["demo_kg"]
        self.assertEqual(bucket["phase"], "verified_partial")
        self.assertFalse(bucket["full_completion"])
        self.assertEqual(bucket["remaining_docs"], 80)
        self.assertEqual(bucket["verify"]["ok"], True)

    def test_classify_space_status_marks_empty_space_as_verified_empty(self):
        status, note = backfill_es_spaces.classify_space_status(
            dry_run=False,
            fail_count=0,
            verify_result={
                "ok": False,
                "doc_count": 0,
                "sample_ids_ok": True,
                "sample_space_ok": True,
                "sample_query_ok": False,
            },
            nebula_count=0,
            es_doc_count=0,
        )

        self.assertEqual(status, "verified_empty")
        self.assertIn("no entity documents", note)

    def test_classify_space_status_marks_verified_nonempty_on_success(self):
        status, note = backfill_es_spaces.classify_space_status(
            dry_run=False,
            fail_count=0,
            verify_result={
                "ok": True,
                "doc_count": 2,
                "sample_ids_ok": True,
                "sample_space_ok": True,
                "sample_query_ok": True,
            },
            nebula_count=2,
            es_doc_count=2,
        )

        self.assertEqual(status, "verified_nonempty")
        self.assertIn("canonical ES contract", note)

    def test_classify_space_status_marks_failed_on_verify_mismatch(self):
        status, note = backfill_es_spaces.classify_space_status(
            dry_run=False,
            fail_count=0,
            verify_result={
                "ok": False,
                "doc_count": 3,
                "sample_ids_ok": True,
                "sample_space_ok": False,
                "sample_query_ok": False,
            },
            nebula_count=5,
            es_doc_count=3,
        )

        self.assertEqual(status, "failed")
        self.assertIn("sample_space_mismatch", note)
        self.assertIn("sample_query_failed", note)

    def test_classify_space_status_marks_verified_partial_when_counts_do_not_align(self):
        status, note = backfill_es_spaces.classify_space_status(
            dry_run=False,
            fail_count=0,
            verify_result={
                "ok": True,
                "doc_count": 80,
                "sample_ids_ok": True,
                "sample_space_ok": True,
                "sample_query_ok": True,
            },
            nebula_count=100,
            es_doc_count=80,
        )

        self.assertEqual(status, "verified_partial")
        self.assertIn("es_doc_count=80", note)
        self.assertIn("nebula_entity_count=100", note)

    def test_completion_snapshot_requires_full_coverage(self):
        snapshot = backfill_es_spaces.index_status_service.build_completion_snapshot(
            status="verified_partial",
            nebula_entity_count=100,
            es_doc_count=80,
            coverage_pct=80.0,
        )

        self.assertFalse(snapshot["full_completion"])
        self.assertEqual(snapshot["remaining_docs"], 20)

        full_snapshot = backfill_es_spaces.index_status_service.build_completion_snapshot(
            status="verified_nonempty",
            nebula_entity_count=100,
            es_doc_count=100,
            coverage_pct=100.0,
        )
        self.assertTrue(full_snapshot["full_completion"])

    def test_classify_space_status_keeps_verified_vocab_when_verify_is_skipped(self):
        status, note = backfill_es_spaces.classify_space_status(
            dry_run=False,
            fail_count=0,
            verify_result=None,
            nebula_count=100,
            es_doc_count=80,
        )

        self.assertEqual(status, "verified_partial")
        self.assertIn("es_doc_count=80", note)

    def test_classify_space_status_dry_run_does_not_introduce_new_status_words(self):
        status, note = backfill_es_spaces.classify_space_status(
            dry_run=True,
            fail_count=0,
            verify_result=None,
            nebula_count=10,
            es_doc_count=0,
        )

        self.assertEqual(status, "verified_partial")
        self.assertNotEqual(status, "dry_run")

    def test_reset_space_state_removes_only_requested_space(self):
        payload = {
            "format_version": "es-backfill-v1",
            "spaces": {
                "demo_kg": {"cursor": 10, "indexed_total": 20, "last_vid": 100},
                "space_a": {"cursor": 30, "indexed_total": 40, "last_vid": 300},
            },
        }

        removed = backfill_es_spaces.reset_space_state(payload, space_name="demo_kg")

        self.assertTrue(removed)
        self.assertNotIn("demo_kg", payload["spaces"])
        self.assertIn("space_a", payload["spaces"])


if __name__ == "__main__":
    unittest.main()
