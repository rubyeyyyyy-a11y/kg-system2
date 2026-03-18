import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.main import app
from app.services.imports import executor_service, file_store, import_ngql_service, job_service
from app.services.spaces import registry_service


SCHEMA_FIXTURE = {
    "tags": [
        {
            "name": "Entity",
            "properties": [
                {"name": "entity_name", "type": "string"},
                {"name": "entity_type", "type": "string"},
                {"name": "entity_raw_id", "type": "string"},
                {"name": "description", "type": "string"},
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
                {"name": "evidence", "type": "string"},
            ],
        }
    ],
}

ENTITY_CSV = (
    "ID,entity_type,entity_name,entity_raw_id,description,source,version,updated_at,updated_by\n"
    "1,disease,Alpha,MONDO:1,Alpha desc,manual,0,0,importer\n"
)
ENTITY_CSV_TWO_ROWS = (
    "ID,entity_type,entity_name,entity_raw_id,description,source,version,updated_at,updated_by\n"
    "1,disease,Alpha,MONDO:1,Alpha desc,manual,0,0,importer\n"
    "2,disease,Beta,MONDO:2,Beta desc,manual,0,0,importer\n"
)


def _batch_result(*, successes=None, failures=None, used_fallback=False):
    success_items = list(successes or [])
    failure_items = list(failures or [])
    return import_ngql_service.BatchImportResult(
        successes=success_items,
        failures=failure_items,
        batch_statement_count=max(1, len(success_items) + len(failure_items)) if (success_items or failure_items) else 0,
        used_fallback=used_fallback,
    )


class TeamIngestionApiTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="team-ingestion-tests-")
        self._patch_run_root(self.tmpdir)
        self._patch_registry_root(self.tmpdir)
        file_store.ensure_import_dirs()
        registry_service.register_default_space()
        self._env = {
            "TEAM_INGESTION_BEARER_TOKEN": os.environ.get("TEAM_INGESTION_BEARER_TOKEN"),
            "TEAM_INGESTION_BEARER_TOKENS": os.environ.get("TEAM_INGESTION_BEARER_TOKENS"),
        }
        os.environ["TEAM_INGESTION_BEARER_TOKEN"] = "test-token"
        os.environ.pop("TEAM_INGESTION_BEARER_TOKENS", None)

    def tearDown(self):
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
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

    def _client(self):
        return TestClient(app)

    def _auth_headers(self, **extra):
        return {"Authorization": "Bearer test-token", **extra}

    def _post_submission(self, client: TestClient, *, csv_text: str, idempotency_key: str, batch_id: str = "batch-1", headers=None):
        return client.post(
            "/api/v1/team-ingestion/submissions",
            headers=headers or self._auth_headers(),
            files={"file": ("entity.csv", csv_text.encode("utf-8"), "text/csv")},
            data={
                "source_system": "pubmed-bot",
                "batch_id": batch_id,
                "idempotency_key": idempotency_key,
                "created_by": "bot_user",
            },
        )

    def test_submission_creates_system_managed_import_job_in_demo_kg(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.ensure_worker_running"),
            self._client() as client,
        ):
            resp = self._post_submission(client, csv_text=ENTITY_CSV, idempotency_key="idem-1")

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["created_by"], "bot_user")
        self.assertFalse(payload["searchable"])
        self.assertIsNotNone(payload["submission_id"])
        self.assertIsNotNone(payload["draft_id"])
        self.assertIsNotNone(payload["job_id"])

        submission_path = file_store.RUN_ROOT / "team-ingestion" / "submissions" / f"{payload['submission_id']}.json"
        self.assertTrue(submission_path.exists())
        stored = submission_path.read_text(encoding="utf-8")
        self.assertIn('"space_name": "demo_kg"', stored)

    def test_submission_reuses_existing_idempotent_request(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.ensure_worker_running"),
            mock.patch("app.services.team_ingestion.gateway_service.job_service.create_job", wraps=job_service.create_job) as create_job_mock,
            self._client() as client,
        ):
            first = self._post_submission(client, csv_text=ENTITY_CSV, idempotency_key="idem-2")
            second = self._post_submission(client, csv_text=ENTITY_CSV, idempotency_key="idem-2")

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        first_payload = first.json()
        second_payload = second.json()
        self.assertEqual(first_payload["submission_id"], second_payload["submission_id"])
        self.assertFalse(first_payload["reused_existing_submission"])
        self.assertTrue(second_payload["reused_existing_submission"])
        self.assertEqual(create_job_mock.call_count, 1)

    def test_submission_conflicts_when_idempotency_key_reused_with_different_file(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.ensure_worker_running"),
            self._client() as client,
        ):
            first = self._post_submission(client, csv_text=ENTITY_CSV, idempotency_key="idem-3")
            second = self._post_submission(
                client,
                csv_text=ENTITY_CSV.replace("Alpha", "Gamma"),
                idempotency_key="idem-3",
            )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 409, second.text)
        self.assertEqual(second.json()["detail"]["error_code"], "TEAM_INGESTION_IDEMPOTENCY_CONFLICT")

    def test_submission_failures_endpoint_returns_raw_error_rows(self):
        with (
            mock.patch("app.services.imports.schema_service.introspect_schema", return_value=SCHEMA_FIXTURE),
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(
                    successes=[{"kind": "vertex", "vid": 1, "row_index": 1}],
                    failures=[
                        (
                            import_ngql_service.BatchRowItem(
                                row_index=2,
                                row={
                                    "ID": "2",
                                    "entity_type": "disease",
                                    "entity_name": "Beta",
                                    "entity_raw_id": "MONDO:2",
                                    "description": "Beta desc",
                                    "source": "manual",
                                    "version": "0",
                                    "updated_at": "0",
                                    "updated_by": "importer",
                                },
                            ),
                            RuntimeError("bad row"),
                        )
                    ],
                    used_fallback=True,
                ),
            ),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.sync_entities",
                return_value={"fail_count": 0},
            ),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.post_verify_index"),
            mock.patch("app.services.imports.executor_service.ensure_worker_running", side_effect=executor_service.drain_queue),
            self._client() as client,
        ):
            created = self._post_submission(client, csv_text=ENTITY_CSV_TWO_ROWS, idempotency_key="idem-4")
            self.assertEqual(created.status_code, 200, created.text)
            payload = created.json()
            failures = client.get(
                f"/api/v1/team-ingestion/submissions/{payload['submission_id']}/failures",
                headers=self._auth_headers(),
            )

        self.assertEqual(failures.status_code, 200, failures.text)
        body = failures.json()
        self.assertEqual(body["submission_id"], payload["submission_id"])
        self.assertEqual(body["total_failed_rows"], 1)
        self.assertEqual(body["items"][0]["row_number"], 2)
        self.assertEqual(body["items"][0]["raw_error"], "bad row")
        self.assertEqual(body["items"][0]["target_object"], "Entity")

    def test_submission_rejects_external_space_header(self):
        with self._client() as client:
            resp = self._post_submission(
                client,
                csv_text=ENTITY_CSV,
                idempotency_key="idem-5",
                headers=self._auth_headers(**{"X-KG-Space": "other_space"}),
            )

        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["detail"]["error_code"], "TEAM_INGESTION_SPACE_HEADER_REJECTED")
