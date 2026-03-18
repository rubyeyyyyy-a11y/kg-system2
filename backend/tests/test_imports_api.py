import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.services.imports import executor_service, file_store, import_ngql_service
from app.services.imports.models import ImportBatchItemRecord, ImportBatchRecord, ImportJobState
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


def _batch_result(*, successes=None, failures=None, used_fallback=False):
    success_items = list(successes or [])
    failure_items = list(failures or [])
    return import_ngql_service.BatchImportResult(
        successes=success_items,
        failures=failure_items,
        batch_statement_count=max(1, len(success_items) + len(failure_items)) if (success_items or failure_items) else 0,
        used_fallback=used_fallback,
    )


class ImportApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="import-api-tests-")
        self._patch_run_root(self.tmpdir)
        self._patch_registry_root(self.tmpdir)
        file_store.ensure_import_dirs()
        registry_service.register_default_space()

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

    def _write_space(self, *, space_name: str, status: str, internal_status: str, last_error: str | None = None):
        registry_service.write_space(
            SpaceSummary(
                space_name=space_name,
                display_name=space_name,
                description="",
                template_type="entity_rel2_default",
                template_version="entity_rel2_default.v1",
                integration_scope="entity_rel2_core",
                status=status,
                internal_status=internal_status,
                created_by="tester",
                created_at="2026-03-11T00:00:00Z",
                ready_at="2026-03-11T00:00:01Z" if status == "ready" else None,
                last_error=last_error,
            )
        )

    def _client(self):
        return TestClient(app)

    def _upload_csv(self, client: TestClient, name: str, content: str):
        resp = client.post(
            "/api/import/files",
            files={"file": (name, content.encode("utf-8"), "text/csv")},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def _vertex_mapping(self):
        return [
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
        ]

    def _edge_mapping(self):
        return [
            {
                "object_type": "edge_type",
                "object_name": "REL2",
                "field_mappings": [
                    {"source_column": "srcVID", "target_field": "srcVID"},
                    {"source_column": "dstVID", "target_field": "dstVID"},
                    {"source_column": "relation", "target_field": "relation"},
                    {"source_column": "source", "target_field": "source"},
                ],
            }
        ]

    def _create_draft(self, client: TestClient, *, mode: str, file_ids: list[str], mapping: list[dict]):
        resp = client.post(
            "/api/import/drafts",
            json={
                "mode": mode,
                "file_ids": file_ids,
                "mapping": mapping,
                "update_strategy": {"mode": "merge_partial", "create_if_missing": True, "update_existing": True},
                "schema_options": {"allow_create_object": True, "allow_add_properties": True},
                "postprocess_options": {"refresh_metadata": True, "sync_entity_es": True},
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()

    def test_basic_api_chain_upload_preview_draft_validate_job(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.ensure_worker_running"),
            self._client() as client,
        ):
            uploaded = self._upload_csv(client, "vertex.csv", "ID,entity_name,entity_type,source\n1,Alpha,Disease,manual\n")
            self.assertNotIn("stored_path", uploaded)

            preview = client.post(
                "/api/import/preview",
                json={"file_ids": [uploaded["file_id"]], "sample_rows": 5, "mode_hint": "vertex"},
            )
            self.assertEqual(preview.status_code, 200, preview.text)
            self.assertEqual(preview.json()["columns"], ["ID", "entity_name", "entity_type", "source"])

            draft = self._create_draft(client, mode="vertex", file_ids=[uploaded["file_id"]], mapping=self._vertex_mapping())
            validate = client.post(f"/api/import/drafts/{draft['draft_id']}/validate", json={})
            self.assertEqual(validate.status_code, 200, validate.text)
            self.assertTrue(validate.json()["passed"])
            self.assertEqual(validate.json()["compiled_plan"]["mode"], "vertex")

            job = client.post("/api/import/jobs", json={"draft_id": draft["draft_id"], "created_by": "tester"})
            self.assertEqual(job.status_code, 200, job.text)
            self.assertEqual(job.json()["status"], "queued")
            self.assertEqual(job.json()["integration_level"], "fully_integrated")
            self.assertTrue(job.json()["batch_id"].startswith("batch_"))

    def test_batches_and_cleanup_job_endpoints(self):
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_api_1",
                space_id="demo_kg",
                draft_id="draft_api_1",
                job_id="job_api_1",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item(
            ImportBatchItemRecord(
                batch_id="batch_api_1",
                space_id="demo_kg",
                job_id="job_api_1",
                item_type="entity",
                vid=1,
                entity_name="Alpha",
            )
        )
        with (
            mock.patch("app.services.imports.cleanup_executor_service.ensure_worker_running"),
            self._client() as client,
        ):
            batches = client.get("/api/import/batches")
            self.assertEqual(batches.status_code, 200, batches.text)
            self.assertEqual(batches.json()[0]["batch_id"], "batch_api_1")

            items = client.get("/api/import/batches/batch_api_1/items")
            self.assertEqual(items.status_code, 200, items.text)
            self.assertEqual(items.json()[0]["vid"], 1)

            cleanup = client.post(
                "/api/import/batches/cleanup",
                json={"batch_ids": ["batch_api_1"], "scope": "full_batch", "created_by": "tester"},
            )
            self.assertEqual(cleanup.status_code, 200, cleanup.text)
            self.assertEqual(cleanup.json()["status"], "queued")

            cleanup_jobs = client.get("/api/import/cleanup-jobs")
            self.assertEqual(cleanup_jobs.status_code, 200, cleanup_jobs.text)
            self.assertEqual(cleanup_jobs.json()[0]["cleanup_job_id"], cleanup.json()["cleanup_job_id"])

    def test_cleanup_plan_preview_endpoint_happy_path_and_no_side_effects(self):
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_preview_api",
                space_id="demo_kg",
                draft_id="draft_preview_api",
                job_id="job_preview_api",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_preview_api",
                space_id="demo_kg",
                job_id="job_preview_api",
                item_type="relation",
                src_vid=11,
                dst_vid=12,
                relation="rel_preview",
                rank=0,
                edge_type="REL2",
                created_by_batch=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_preview_api",
                space_id="demo_kg",
                job_id="job_preview_api",
                item_type="entity",
                vid=11,
                entity_name="Alpha",
                entity_raw_id="alpha-11",
                created_by_batch=True,
            )
        )
        with (
            mock.patch(
                "app.services.imports.cleanup_planning_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": False,
                    "live_blocking_count": 0,
                    "scan_note": "scan_ok",
                    "scan_edge_type": "REL2",
                    "excluded_by_plan_count": 1,
                },
            ),
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_edge") as delete_edge_mock,
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_vertex") as delete_vertex_mock,
            self._client() as client,
        ):
            resp = client.post(
                "/api/import/batches/cleanup-plan",
                json={"batch_ids": ["batch_preview_api"], "scope": "full_batch", "created_by": "tester"},
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["scope"], "full_batch")
        self.assertEqual(payload["plan_summary"]["requested_entity_count"], 1)
        self.assertEqual(payload["plan_summary"]["requested_relation_count"], 1)
        self.assertEqual(payload["plan_summary"]["deletable_entity_count"], 1)
        self.assertEqual(payload["plan_summary"]["deletable_relation_count"], 1)
        self.assertFalse(payload["has_plan_artifacts"])
        self.assertEqual(file_store.list_cleanup_jobs(), [])
        delete_edge_mock.assert_not_called()
        delete_vertex_mock.assert_not_called()

    def test_cleanup_plan_preview_all_blocked_returns_stable_summary(self):
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_preview_blocked",
                space_id="demo_kg",
                draft_id="draft_preview_blocked",
                job_id="job_preview_blocked",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_preview_blocked",
                space_id="demo_kg",
                job_id="job_preview_blocked",
                item_type="entity",
                vid=21,
                entity_name="Blocked",
                entity_raw_id="blocked-21",
                created_by_batch=True,
            )
        )
        with (
            mock.patch(
                "app.services.imports.cleanup_planning_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": True,
                    "live_blocking_count": 2,
                    "scan_note": "blocked",
                    "scan_edge_type": "REL2",
                    "excluded_by_plan_count": 0,
                    "live_blocking_edges": [{"edge_type": "REL2", "src_vid": 99, "dst_vid": 21}],
                },
            ),
            self._client() as client,
        ):
            resp = client.post(
                "/api/import/batches/cleanup-plan",
                json={"batch_ids": ["batch_preview_blocked"], "scope": "full_batch", "created_by": "tester"},
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["plan_summary"]["blocked_entity_count"], 1)
        self.assertEqual(payload["plan_summary"]["deletable_entity_count"], 0)
        self.assertEqual(payload["plan_summary"]["deletable_relation_count"], 0)
        self.assertEqual(payload["blocked_entities"]["total_count"], 1)
        self.assertTrue(payload["warning_messages"])

    def test_cleanup_plan_preview_rejects_invalid_batches(self):
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_preview_not_test",
                space_id="demo_kg",
                draft_id="draft_preview_not_test",
                job_id="job_preview_not_test",
                status="succeeded",
                is_test_data=False,
                cleanup_status="not_supported",
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_preview_not_test",
                space_id="demo_kg",
                job_id="job_preview_not_test",
                item_type="entity",
                vid=31,
                entity_name="Gamma",
                created_by_batch=True,
            )
        )
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_preview_no_ledger",
                space_id="demo_kg",
                draft_id="draft_preview_no_ledger",
                job_id="job_preview_no_ledger",
                status="succeeded",
                is_test_data=True,
            )
        )
        with self._client() as client:
            not_test_resp = client.post(
                "/api/import/batches/cleanup-plan",
                json={"batch_ids": ["batch_preview_not_test"], "scope": "full_batch", "created_by": "tester"},
            )
            no_ledger_resp = client.post(
                "/api/import/batches/cleanup-plan",
                json={"batch_ids": ["batch_preview_no_ledger"], "scope": "full_batch", "created_by": "tester"},
            )
            missing_resp = client.post(
                "/api/import/batches/cleanup-plan",
                json={"batch_ids": ["batch_missing_preview"], "scope": "full_batch", "created_by": "tester"},
            )

        self.assertEqual(not_test_resp.status_code, 409, not_test_resp.text)
        self.assertEqual(no_ledger_resp.status_code, 409, no_ledger_resp.text)
        self.assertEqual(missing_resp.status_code, 404, missing_resp.text)

    def test_cleanup_artifact_download_endpoint(self):
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_api",
                space_id="demo_kg",
                draft_id="draft_cleanup_api",
                job_id="job_cleanup_api",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_api",
                space_id="demo_kg",
                job_id="job_cleanup_api",
                item_type="entity",
                vid=101,
                entity_name="Alpha",
                created_by_batch=True,
            )
        )
        with mock.patch("app.services.imports.cleanup_executor_service.ensure_worker_running"), self._client() as client:
            created = client.post(
                "/api/import/batches/cleanup",
                json={"batch_ids": ["batch_cleanup_api"], "scope": "full_batch", "created_by": "tester"},
            )
            self.assertEqual(created.status_code, 200, created.text)
            cleanup_job_id = created.json()["cleanup_job_id"]

        file_store.write_cleanup_job_artifact(cleanup_job_id, "summary.json", {"ok": True, "cleanup_job_id": cleanup_job_id})
        record = file_store.load_cleanup_job(cleanup_job_id)
        record.artifacts = [file_store.write_cleanup_job_artifact(cleanup_job_id, "summary.json", {"ok": True, "cleanup_job_id": cleanup_job_id})]
        file_store.save_cleanup_job(record)

        with self._client() as client:
            download = client.get(f"/api/import/cleanup-jobs/{cleanup_job_id}/artifacts/summary.json")
        self.assertEqual(download.status_code, 200, download.text)
        self.assertIn('"ok": true', download.text.lower())

    def test_entity_only_job_triggers_es_postprocess(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(successes=[{"kind": "vertex", "vid": 101, "row_index": 1}]),
            ),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.sync_entities",
                return_value={"space_name": "demo_kg", "docs": 1, "ok_count": 1, "fail_count": 0},
            ) as es_sync_mock,
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.post_verify_index",
                return_value={
                    "completion_summary": {
                        "nebula_write_success": True,
                        "post_es_sync_success": True,
                        "verify_success": True,
                        "registry_index_status_written": True,
                        "imported_docs_visible": True,
                        "searchable": True,
                    },
                    "index_status_snapshot": {"status": "verified_nonempty", "doc_count": 1},
                },
            ),
            mock.patch("app.services.imports.executor_service.ensure_worker_running", side_effect=executor_service.drain_queue),
            self._client() as client,
        ):
            uploaded = self._upload_csv(client, "vertex.csv", "ID,entity_name,entity_type,source\n1,Alpha,Disease,manual\n")
            draft = self._create_draft(client, mode="vertex", file_ids=[uploaded["file_id"]], mapping=self._vertex_mapping())
            job = client.post("/api/import/jobs", json={"draft_id": draft["draft_id"], "created_by": "tester"}).json()
            detail = client.get(f"/api/import/jobs/{job['job_id']}").json()

        self.assertEqual(detail["status"], "succeeded")
        self.assertFalse(detail["es_sync_skipped"])
        es_sync_mock.assert_called_once()

    def test_edge_only_job_skips_es_postprocess(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(successes=[{"kind": "edge", "src": 1, "dst": 2, "rank": 0, "row_index": 1}]),
            ),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.sync_entities") as es_sync_mock,
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.post_verify_index",
                return_value={
                    "completion_summary": {
                        "nebula_write_success": True,
                        "post_es_sync_success": True,
                        "verify_success": True,
                        "registry_index_status_written": True,
                        "imported_docs_visible": True,
                        "searchable": True,
                    },
                    "index_status_snapshot": {"status": "verified_empty", "doc_count": 0},
                },
            ),
            mock.patch("app.services.imports.executor_service.ensure_worker_running", side_effect=executor_service.drain_queue),
            self._client() as client,
        ):
            uploaded = self._upload_csv(client, "edge.csv", "srcVID,dstVID,relation,source\n1,2,rel,manual\n")
            draft = self._create_draft(client, mode="edge", file_ids=[uploaded["file_id"]], mapping=self._edge_mapping())
            job = client.post("/api/import/jobs", json={"draft_id": draft["draft_id"], "created_by": "tester"}).json()
            detail = client.get(f"/api/import/jobs/{job['job_id']}").json()

        self.assertEqual(detail["status"], "succeeded")
        self.assertTrue(detail["es_sync_skipped"])
        es_sync_mock.assert_not_called()

    def test_schema_plan_returns_integration_warning(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value={"tags": [], "edge_types": []}),
            self._client() as client,
        ):
            uploaded = self._upload_csv(client, "vertex.csv", "ID,name\n1,Alpha\n")
            resp = client.post(
                "/api/import/schema/plan",
                json={
                    "file_ids": [uploaded["file_id"]],
                    "mapping": [
                        {
                            "object_type": "tag",
                            "object_name": "NovelEntity",
                            "field_mappings": [
                                {"source_column": "ID", "target_field": "ID"},
                                {"source_column": "name", "target_field": "entity_name"},
                            ],
                        }
                    ],
                    "schema_options": {"allow_create_object": True, "allow_add_properties": True},
                },
            )

        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertTrue(resp.json()["integration_warnings"])

    def test_validate_fails_on_invalid_vid_and_src_dst(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            self._client() as client,
        ):
            vertex_file = self._upload_csv(client, "vertex.csv", "ID,entity_name,entity_type,source\nabc,Alpha,Disease,manual\n")
            vertex_draft = self._create_draft(
                client, mode="vertex", file_ids=[vertex_file["file_id"]], mapping=self._vertex_mapping()
            )
            vertex_validate = client.post(f"/api/import/drafts/{vertex_draft['draft_id']}/validate", json={})
            self.assertEqual(vertex_validate.status_code, 200, vertex_validate.text)
            self.assertFalse(vertex_validate.json()["passed"])
            self.assertIn("invalid numeric VID", " ".join(vertex_validate.json()["errors"]))

            edge_file = self._upload_csv(client, "edge.csv", "srcVID,dstVID,relation,source\nx,2,rel,manual\n")
            edge_draft = self._create_draft(client, mode="edge", file_ids=[edge_file["file_id"]], mapping=self._edge_mapping())
            edge_validate = client.post(f"/api/import/drafts/{edge_draft['draft_id']}/validate", json={})
            self.assertEqual(edge_validate.status_code, 200, edge_validate.text)
            self.assertFalse(edge_validate.json()["passed"])
            self.assertIn("invalid numeric srcVID/dstVID/rank", " ".join(edge_validate.json()["errors"]))

    def test_upload_error_response_uses_import_error_contract(self):
        with self._client() as client:
            resp = client.post(
                "/api/import/files",
                files={"file": ("not_csv.txt", b"hello", "text/plain")},
            )

        self.assertEqual(resp.status_code, 415, resp.text)
        payload = resp.json()
        self.assertEqual(payload["detail"]["error_code"], "IMPORT_UNSUPPORTED_FILE_TYPE")
        self.assertIn("only .csv files are supported", payload["detail"]["message"])

    def test_upload_rejects_file_over_max_size_with_structured_error(self):
        with mock.patch.object(file_store, "MAX_UPLOAD_BYTES", 16):
            with self._client() as client:
                resp = client.post(
                    "/api/import/files",
                    files={"file": ("vertex.csv", b"ID,name\n1,Alpha,manual\n", "text/csv")},
                )

        self.assertEqual(resp.status_code, 413, resp.text)
        payload = resp.json()
        self.assertEqual(payload["detail"]["error_code"], "IMPORT_UPLOAD_TOO_LARGE")
        self.assertEqual(payload["detail"]["extra"]["max_upload_bytes"], 16)

    def test_draft_total_size_limit_uses_backend_truth(self):
        with mock.patch.object(file_store, "MAX_DRAFT_TOTAL_BYTES", 24):
            with self._client() as client:
                uploaded_a = self._upload_csv(client, "part_a.csv", "ID,name\n1,Alpha\n")
                uploaded_b = self._upload_csv(client, "part_b.csv", "ID,name\n2,Beta\n")
                resp = client.post(
                    "/api/import/drafts",
                    json={
                        "mode": "vertex",
                        "file_ids": [uploaded_a["file_id"], uploaded_b["file_id"]],
                        "mapping": [],
                        "update_strategy": {"mode": "merge_partial", "create_if_missing": True, "update_existing": True},
                        "schema_options": {"allow_create_object": True, "allow_add_properties": True},
                        "postprocess_options": {"refresh_metadata": True, "sync_entity_es": True},
                    },
                )

        self.assertEqual(resp.status_code, 422, resp.text)
        payload = resp.json()
        self.assertEqual(payload["detail"]["error_code"], "IMPORT_DRAFT_TOTAL_SIZE_EXCEEDED")
        self.assertEqual(payload["detail"]["extra"]["max_draft_total_bytes"], 24)

    def test_preview_returns_only_requested_sample_rows(self):
        with self._client() as client:
            uploaded = self._upload_csv(
                client,
                "vertex.csv",
                "ID,entity_name,entity_type,source\n1,Alpha,Disease,manual\n2,Beta,Disease,manual\n3,Gamma,Disease,manual\n",
            )
            preview = client.post(
                "/api/import/preview",
                json={"file_ids": [uploaded["file_id"]], "sample_rows": 2, "mode_hint": "vertex"},
            )

        self.assertEqual(preview.status_code, 200, preview.text)
        payload = preview.json()
        self.assertEqual(len(payload["sample_rows"]), 2)
        self.assertEqual(payload["sample_rows"][0]["ID"], "1")
        self.assertEqual(payload["sample_rows"][1]["ID"], "2")
        self.assertTrue(any("sample-only" in warning for warning in payload["warnings"]))

    def test_download_missing_failed_rows_uses_import_error_contract(self):
        with self._client() as client:
            resp = client.get("/api/import/jobs/job_missing/failed_rows")

        self.assertEqual(resp.status_code, 404, resp.text)
        payload = resp.json()
        self.assertIn("error_code", payload["detail"])

    def test_import_endpoints_block_non_ready_space(self):
        self._write_space(space_name="space_pending", status="provisioning", internal_status="waiting_ready")
        with self._client() as client:
            resp = client.post(
                "/api/import/files",
                headers={"X-KG-Space": "space_pending"},
                files={"file": ("vertex.csv", b"ID,entity_name\n1,Alpha\n", "text/csv")},
            )

        self.assertEqual(resp.status_code, 409, resp.text)
        payload = resp.json()
        self.assertEqual(payload["detail"]["error_code"], "SPACE_NOT_READY")
        self.assertEqual(payload["detail"]["reason"], "provisioning")

    def test_failed_rows_download_endpoint(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(
                    successes=[{"kind": "vertex", "vid": 1, "row_index": 1}],
                    failures=[
                        (
                            import_ngql_service.BatchRowItem(row_index=2, row={"ID": "2", "entity_name": "Beta", "entity_type": "Disease", "source": "manual"}),
                            RuntimeError("bad row"),
                        )
                    ],
                    used_fallback=True,
                ),
            ),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.sync_entities"),
            mock.patch("app.services.imports.executor_service.ensure_worker_running", side_effect=executor_service.drain_queue),
            self._client() as client,
        ):
            uploaded = self._upload_csv(
                client,
                "vertex.csv",
                "ID,entity_name,entity_type,source\n1,Alpha,Disease,manual\n2,Beta,Disease,manual\n",
            )
            draft = self._create_draft(client, mode="vertex", file_ids=[uploaded["file_id"]], mapping=self._vertex_mapping())
            job = client.post("/api/import/jobs", json={"draft_id": draft["draft_id"], "created_by": "tester"}).json()
            download = client.get(f"/api/import/jobs/{job['job_id']}/failed_rows")

        self.assertEqual(download.status_code, 200, download.text)
        payload = download.text
        self.assertIn("__file_id", payload)
        self.assertIn("__row_number", payload)
        self.assertIn("bad row", payload)

    def test_cancel_job_api(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.ensure_worker_running"),
            self._client() as client,
        ):
            uploaded = self._upload_csv(client, "vertex.csv", "ID,entity_name,entity_type,source\n1,Alpha,Disease,manual\n")
            draft = self._create_draft(client, mode="vertex", file_ids=[uploaded["file_id"]], mapping=self._vertex_mapping())
            job = client.post("/api/import/jobs", json={"draft_id": draft["draft_id"], "created_by": "tester"}).json()
            cancel = client.post(f"/api/import/jobs/{job['job_id']}/cancel", json={})
            detail = client.get(f"/api/import/jobs/{job['job_id']}").json()

        self.assertEqual(cancel.status_code, 200, cancel.text)
        self.assertEqual(detail["status"], "cancelled")

    def test_startup_repairs_interrupted_jobs(self):
        job_running = ImportJobState(
            job_id="job_running",
            draft_id="draft_x",
            status="running",
            created_by="tester",
            mode="vertex",
            plan_id="plan_x",
            file_ids=[],
            compiled_plan_path=str(file_store.job_compiled_plan_path("job_running")),
            failed_rows_path=str(file_store.job_failed_rows_path("job_running")),
            normalized_rows_path=str(file_store.job_normalized_rows_path("job_running")),
        )
        job_post = ImportJobState(
            job_id="job_post",
            draft_id="draft_y",
            status="post_es_sync",
            created_by="tester",
            mode="edge",
            plan_id="plan_y",
            file_ids=[],
            compiled_plan_path=str(file_store.job_compiled_plan_path("job_post")),
            failed_rows_path=str(file_store.job_failed_rows_path("job_post")),
            normalized_rows_path=str(file_store.job_normalized_rows_path("job_post")),
        )
        file_store.save_job_state(job_running)
        file_store.save_job_state(job_post)

        with self._client() as client:
            resp = client.get("/api/import/jobs")

        self.assertEqual(resp.status_code, 200, resp.text)
        statuses = {item["job_id"]: item["status"] for item in resp.json()}
        self.assertEqual(statuses["job_running"], "failed_import")
        self.assertEqual(statuses["job_post"], "failed_postprocess")


if __name__ == "__main__":
    unittest.main()
