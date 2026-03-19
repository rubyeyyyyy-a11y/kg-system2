import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.services.imports import executor_service, file_store
from app.services.spaces import registry_service
from app.services.spaces.models import SpaceSummary


SCHEMA_FIXTURE = {
    "tags": [
        {
            "name": "Entity",
            "properties": [
                {"name": "entity_name", "type": "string"},
                {"name": "entity_type", "type": "string"},
                {"name": "source", "type": "string"},
            ],
        }
    ],
    "edge_types": [
        {
            "name": "REL2",
            "properties": [
                {"name": "relation", "type": "string"},
                {"name": "source", "type": "string"},
            ],
        }
    ],
}


class ImportJobClosureContractTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="import-job-closure-")
        self._patch_run_root(self.tmpdir)
        self._patch_registry_root(self.tmpdir)
        file_store.ensure_import_dirs()
        registry_service.register_default_space()
        self._write_space("it_space_218354")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_run_root(self, root: str):
        root_path = Path(root)
        file_store.RUN_ROOT = root_path
        file_store.STAGING_FILES_DIR = root_path / "import-staging" / "files"
        file_store.DRAFTS_DIR = root_path / "import-drafts"
        file_store.JOBS_DIR = root_path / "import-jobs"
        file_store.IMPORT_BATCHES_DIR = root_path / "import-batches"
        file_store.IMPORT_CLEANUP_JOBS_DIR = root_path / "import-cleanup-jobs"

    def _patch_registry_root(self, root: str):
        root_path = Path(root) / "space-registry"
        registry_service.REGISTRY_ROOT = root_path
        registry_service.REGISTRY_PATH = root_path / "spaces.json"
        registry_service.LOCK_PATH = root_path / "spaces.lock"

    def _write_space(self, space_name: str):
        registry_service.write_space(
            SpaceSummary(
                space_name=space_name,
                display_name=space_name,
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

    def _client(self):
        return TestClient(app)

    def _upload_csv(self, client: TestClient, headers: dict[str, str], name: str, content: str):
        response = client.post(
            "/api/import/files",
            headers=headers,
            files={"file": (name, content.encode("utf-8"), "text/csv")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_vertex_draft(self, client: TestClient, headers: dict[str, str], *, file_id: str):
        response = client.post(
            "/api/import/drafts",
            headers=headers,
            json={
                "mode": "vertex",
                "file_ids": [file_id],
                "mapping": [
                    {
                        "object_type": "tag",
                        "object_name": "Entity",
                        "field_mappings": [
                            {"source_column": "ID", "target_field": "ID"},
                            {"source_column": "entity_name", "target_field": "entity_name"},
                            {"source_column": "entity_type", "target_field": "entity_type"},
                            {"source_column": "source", "target_field": "source"},
                        ],
                    }
                ],
                "update_strategy": {"mode": "merge_partial", "create_if_missing": True, "update_existing": True},
                "schema_options": {"allow_create_object": True, "allow_add_properties": True},
                "postprocess_options": {"refresh_metadata": True, "sync_entity_es": True},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_import_job_searchable_closure_contract(self):
        def post_verify_side_effect(vids, *, space_name=None, batch_id=None):
            doc_count = 1 if str(space_name or "") == "demo_kg" else 2
            return {
                "completion_summary": {
                    "nebula_write_success": True,
                    "post_es_sync_success": True,
                    "verify_success": True,
                    "registry_index_status_written": True,
                    "imported_docs_visible": True,
                    "searchable": True,
                    "index_status": "verified_nonempty",
                    "failure_stage": None,
                },
                "index_status_snapshot": {
                    "status": "verified_nonempty",
                    "doc_count": doc_count,
                },
            }

        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service.import_ngql_service.import_row", return_value={"kind": "vertex", "vid": 101}),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.sync_entities",
                return_value={"space_name": "demo_kg", "docs": 1, "ok_count": 1, "fail_count": 0},
            ),
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.post_verify_index",
                side_effect=post_verify_side_effect,
            ),
            mock.patch("app.services.imports.executor_service.ensure_worker_running", side_effect=executor_service.drain_queue),
            self._client() as client,
        ):
            demo_headers = {}
            small_headers = {"X-KG-Space": "it_space_218354"}

            demo_file = self._upload_csv(
                client,
                demo_headers,
                "demo.csv",
                "ID,entity_name,entity_type,source\n1,Demo Entity,Disease,manual\n",
            )
            demo_draft = self._create_vertex_draft(client, demo_headers, file_id=demo_file["file_id"])
            demo_job = client.post(
                "/api/import/jobs",
                headers=demo_headers,
                json={"draft_id": demo_draft["draft_id"], "created_by": "tester"},
            )
            self.assertEqual(demo_job.status_code, 200, demo_job.text)
            demo_job_id = demo_job.json()["job_id"]

            small_file = self._upload_csv(
                client,
                small_headers,
                "small.csv",
                "ID,entity_name,entity_type,source\n2,Small Entity,Gene,manual\n",
            )
            small_draft = self._create_vertex_draft(client, small_headers, file_id=small_file["file_id"])
            small_job = client.post(
                "/api/import/jobs",
                headers=small_headers,
                json={"draft_id": small_draft["draft_id"], "created_by": "tester"},
            )
            self.assertEqual(small_job.status_code, 200, small_job.text)
            small_job_id = small_job.json()["job_id"]

            demo_detail = client.get(f"/api/import/jobs/{demo_job_id}", headers=demo_headers)
            small_detail = client.get(f"/api/import/jobs/{small_job_id}", headers=small_headers)
            demo_list = client.get("/api/import/jobs", headers=demo_headers)
            small_list = client.get("/api/import/jobs", headers=small_headers)
            cross_space_get = client.get(f"/api/import/jobs/{demo_job_id}", headers=small_headers)

        self.assertEqual(demo_detail.status_code, 200, demo_detail.text)
        self.assertEqual(small_detail.status_code, 200, small_detail.text)
        self.assertEqual(demo_detail.json()["status"], "succeeded")
        self.assertEqual(
            demo_detail.json()["completion_summary"],
            {
                "nebula_write_success": True,
                "post_es_sync_success": True,
                "verify_success": True,
                "registry_index_status_written": True,
                "imported_docs_visible": True,
                "searchable": True,
                "affected_entity_count": 0,
                "search_status": None,
                "index_status": "verified_nonempty",
                "coverage_pct": None,
                "note": "",
                "completed_at": None,
                "failure_stage": None,
            },
        )
        self.assertEqual(
            demo_detail.json()["index_status_snapshot"],
            {
                "status": "verified_nonempty",
                "doc_count": 1,
                "nebula_entity_count": None,
                "coverage_pct": None,
                "note": "",
                "updated_at": None,
            },
        )
        self.assertEqual(demo_detail.json()["space_name"], "demo_kg")
        self.assertEqual(small_detail.json()["status"], "succeeded")
        self.assertEqual(
            small_detail.json()["completion_summary"],
            {
                "nebula_write_success": True,
                "post_es_sync_success": True,
                "verify_success": True,
                "registry_index_status_written": True,
                "imported_docs_visible": True,
                "searchable": True,
                "affected_entity_count": 0,
                "search_status": None,
                "index_status": "verified_nonempty",
                "coverage_pct": None,
                "note": "",
                "completed_at": None,
                "failure_stage": None,
            },
        )
        self.assertEqual(
            small_detail.json()["index_status_snapshot"],
            {
                "status": "verified_nonempty",
                "doc_count": 2,
                "nebula_entity_count": None,
                "coverage_pct": None,
                "note": "",
                "updated_at": None,
            },
        )
        self.assertEqual(small_detail.json()["space_name"], "it_space_218354")

        self.assertEqual(demo_list.status_code, 200, demo_list.text)
        self.assertEqual([item["job_id"] for item in demo_list.json()], [demo_job_id])
        self.assertEqual([item["space_name"] for item in demo_list.json()], ["demo_kg"])
        self.assertEqual(small_list.status_code, 200, small_list.text)
        self.assertEqual([item["job_id"] for item in small_list.json()], [small_job_id])
        self.assertEqual([item["space_name"] for item in small_list.json()], ["it_space_218354"])

        self.assertEqual(cross_space_get.status_code, 404, cross_space_get.text)
        self.assertEqual(cross_space_get.json()["detail"]["error_code"], "IMPORT_JOB_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
