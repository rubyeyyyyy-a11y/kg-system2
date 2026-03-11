import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services.imports import (
    draft_service,
    es_postprocess_service,
    executor_service,
    file_store,
    job_service,
    metadata_postprocess_service,
    validation_service,
)
from app.services.imports.models import (
    CompiledImportPlan,
    CompiledTargetPlan,
    ImportDraft,
    ImportFileRecord,
    ImportJobState,
    ImportTargetConfig,
    SchemaOptions,
)


class ImportServiceTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="import-tests-")
        self._patch_run_root(self.tmpdir)
        file_store.ensure_import_dirs()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _patch_run_root(self, root: str):
        root_path = Path(root)
        file_store.RUN_ROOT = root_path
        file_store.STAGING_FILES_DIR = root_path / "import-staging" / "files"
        file_store.DRAFTS_DIR = root_path / "import-drafts"
        file_store.JOBS_DIR = root_path / "import-jobs"

    def _create_csv_file(self, *, file_id: str, content: str):
        record = ImportFileRecord(
            file_id=file_id,
            original_name=f"{file_id}.csv",
            size_bytes=len(content.encode("utf-8")),
            detected_delimiter=",",
            detected_encoding="utf-8",
        )
        file_store.ensure_import_dirs()
        file_store._file_dir(file_id).mkdir(parents=True, exist_ok=True)
        file_store.staged_file_path(file_id).write_text(content, encoding="utf-8")
        file_store.write_json(file_store.file_meta_path(file_id), record.model_dump())
        return record

    def _compiled_plan(self, *, mode: str, object_type: str, object_name: str, field_mappings: dict[str, str]):
        return CompiledImportPlan(
            plan_id="plan_test",
            mode=mode,
            file_ids=["file_1"],
            targets=[
                CompiledTargetPlan(
                    object_type=object_type,
                    object_name=object_name,
                    field_mappings=field_mappings,
                    property_types={
                        "entity_name": "string",
                        "entity_type": "string",
                        "source": "string",
                        "relation": "string",
                        "version": "int64",
                        "updated_at": "int64",
                        "updated_by": "string",
                    },
                    identity_fields=["ID"] if object_type == "tag" else ["srcVID", "dstVID", "rank"],
                    update_fields=["entity_name", "entity_type", "source"]
                    if object_type == "tag"
                    else ["relation", "source"],
                    create_fields=list(field_mappings.values()),
                    integration_level="fully_integrated" if object_name == "Entity" else "partially_integrated",
                )
            ],
            schema_create_plan=[],
        )

    def test_draft_validate_generates_compiled_plan(self):
        self._create_csv_file(
            file_id="file_1",
            content="ID,entity_name,entity_type,source\n1,Alpha,Disease,manual\n",
        )
        draft = ImportDraft(
            draft_id="draft_1",
            status="mapped",
            mode="vertex",
            file_ids=["file_1"],
            mapping=[
                ImportTargetConfig(
                    object_type="tag",
                    object_name="Entity",
                    field_mappings=[
                        {"source_column": "ID", "target_field": "ID"},
                        {"source_column": "entity_name", "target_field": "entity_name"},
                        {"source_column": "entity_type", "target_field": "entity_type"},
                        {"source_column": "source", "target_field": "source"},
                    ],
                )
            ],
        )
        with mock.patch(
            "app.services.imports.schema_service.introspect_schema",
            return_value={
                "tags": [{"name": "Entity", "properties": [{"name": "entity_name", "type": "string"}]}],
                "edge_types": [{"name": "REL2", "properties": [{"name": "relation", "type": "string"}]}],
            },
        ):
            result = validation_service.validate_draft(draft)

        self.assertTrue(result.passed)
        self.assertIsNotNone(result.compiled_plan)
        self.assertEqual(result.compiled_plan.mode, "vertex")
        self.assertEqual(result.compiled_plan.targets[0].object_name, "Entity")
        self.assertEqual(result.compiled_plan.integration_level, "fully_integrated")

    def test_schema_create_plan_stays_non_destructive(self):
        plan_schema = {
            "tags": [{"name": "Entity", "properties": [{"name": "entity_name", "type": "string"}]}],
            "edge_types": [],
        }
        target = ImportTargetConfig(
            object_type="tag",
            object_name="Entity",
            field_mappings=[
                {"source_column": "ID", "target_field": "ID"},
                {"source_column": "entity_name", "target_field": "entity_name"},
                {"source_column": "description", "target_field": "description"},
            ],
        )
        schema_plan, warnings, _integration = __import__(
            "app.services.imports.schema_service", fromlist=["schema_service"]
        ).build_schema_plan(
            schema=plan_schema,
            mapping=[target],
            all_columns=["ID", "entity_name", "description"],
            schema_options=SchemaOptions(allow_create_object=True, allow_add_properties=True),
        )

        self.assertEqual(warnings, [])
        self.assertEqual(len(schema_plan), 1)
        self.assertEqual([item.name for item in schema_plan[0].add_properties], ["description", "version", "updated_at", "updated_by"])

    def test_job_snapshot_freezes_compiled_plan_and_inputs(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n")
        compiled_plan = self._compiled_plan(
            mode="vertex",
            object_type="tag",
            object_name="Entity",
            field_mappings={"ID": "ID", "entity_name": "entity_name"},
        )
        draft = ImportDraft(
            draft_id="draft_1",
            status="validated",
            mode="vertex",
            file_ids=["file_1"],
            mapping=[
                ImportTargetConfig(
                    object_type="tag",
                    object_name="Entity",
                    field_mappings=[
                        {"source_column": "ID", "target_field": "ID"},
                        {"source_column": "entity_name", "target_field": "entity_name"},
                    ],
                )
            ],
            validation={
                "passed": True,
                "errors": [],
                "warnings": [],
                "integration_warnings": [],
                "compiled_plan": compiled_plan,
            },
        )
        file_store.save_draft(draft)

        with mock.patch("app.services.imports.job_service.draft_service.validate_and_persist", return_value=draft):
            state = job_service.create_job(draft_id="draft_1", created_by="tester")
        compiled_snapshot = file_store.read_json(file_store.job_compiled_plan_path(state.job_id))
        input_snapshot = (file_store.job_input_dir(state.job_id) / "file_1" / "source.csv").read_text(encoding="utf-8")

        file_store.staged_file_path("file_1").write_text("ID,entity_name\n2,Beta\n", encoding="utf-8")

        self.assertEqual(compiled_snapshot["plan_id"], "plan_test")
        self.assertIn("1,Alpha", input_snapshot)
        self.assertNotIn("2,Beta", input_snapshot)

    def test_cancel_only_takes_effect_at_batch_boundary(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n2,Beta\n3,Gamma\n")
        plan = self._compiled_plan(
            mode="vertex",
            object_type="tag",
            object_name="Entity",
            field_mappings={"ID": "ID", "entity_name": "entity_name"},
        )
        job_id = "job_cancel_batch"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_cancel"}, plan.model_dump())
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_cancel",
            status="queued",
            created_by="tester",
            mode="vertex",
            plan_id=plan.plan_id,
            file_ids=["file_1"],
            compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
            failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
            normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
        )
        file_store.save_job_state(state)
        call_count = {"n": 0}

        def import_side_effect(_target, _row, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                job_service.cancel_job(job_id)
            return {"kind": "vertex", "vid": call_count["n"]}

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service._BATCH_SIZE", 2),
            mock.patch("app.services.imports.executor_service.import_ngql_service.import_row", side_effect=import_side_effect),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.sync_entities"),
        ):
            result = executor_service.run_job(job_id)

        self.assertEqual(result.status, "cancelled")
        self.assertTrue(result.cancel_effective_at_batch)
        self.assertEqual(result.processed_rows, 2)

    def test_startup_marks_interrupted_jobs(self):
        statuses = {
            "job_q": "queued",
            "job_r": "running",
            "job_m": "post_metadata_refresh",
            "job_e": "post_es_sync",
        }
        for job_id, status in statuses.items():
            state = ImportJobState(
                job_id=job_id,
                draft_id="draft_x",
                status=status,
                created_by="tester",
                mode="vertex",
                plan_id="plan_x",
                file_ids=[],
                compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
                failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
                normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
            )
            file_store.save_job_state(state)

        repaired = job_service.mark_interrupted_jobs()
        repaired_map = {state.job_id: state.status for state in repaired}
        self.assertEqual(repaired_map["job_q"], "failed_import")
        self.assertEqual(repaired_map["job_r"], "failed_import")
        self.assertEqual(repaired_map["job_m"], "failed_postprocess")
        self.assertEqual(repaired_map["job_e"], "failed_postprocess")

    def test_metadata_postprocess_forces_db_source(self):
        with (
            mock.patch("app.services.imports.metadata_postprocess_service._query_entity_type_counts_db", return_value=[("disease", 2)]),
            mock.patch("app.services.imports.metadata_postprocess_service._query_relation_type_counts_db", return_value=[("rel", 3)]),
            mock.patch("app.services.imports.metadata_postprocess_service._ensure_metadata_schema"),
            mock.patch("app.services.imports.metadata_postprocess_service._clear_tag"),
            mock.patch("app.services.imports.metadata_postprocess_service._insert_stats"),
            mock.patch("app.services.imports.metadata_postprocess_service.metadata_service.invalidate_metadata_cache") as invalidate_mock,
        ):
            resp = metadata_postprocess_service.refresh_from_db(actor="tester")

        self.assertEqual(resp["source"], "db")
        invalidate_mock.assert_called_once()

    def test_entity_only_es_sync(self):
        with (
            mock.patch("app.services.imports.es_postprocess_service.NebulaClient") as nebula_cls,
            mock.patch("app.services.imports.es_postprocess_service.ElasticsearchClient") as es_cls,
        ):
            nebula_cls.return_value.fetch_entity_props.return_value = (
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
            es_cls.return_value.ensure_index.return_value = (True, "exists")
            es_cls.return_value.bulk_upsert.return_value = (1, 0, 5.0)
            resp = es_postprocess_service.sync_entities([1, 1, 2])

        self.assertFalse(resp["skipped"])
        self.assertEqual(resp["docs"], 1)
        es_cls.return_value.bulk_upsert.assert_called_once()

    def test_edge_only_job_skips_es(self):
        self._create_csv_file(file_id="file_1", content="srcVID,dstVID,relation\n1,2,rel\n")
        plan = self._compiled_plan(
            mode="edge",
            object_type="edge_type",
            object_name="REL2",
            field_mappings={"srcVID": "srcVID", "dstVID": "dstVID", "relation": "relation"},
        )
        job_id = "job_edge"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_edge"}, plan.model_dump())
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_edge",
            status="queued",
            created_by="tester",
            mode="edge",
            plan_id=plan.plan_id,
            file_ids=["file_1"],
            compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
            failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
            normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
        )
        file_store.save_job_state(state)

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service.import_ngql_service.import_row", return_value={"kind": "edge"}),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.sync_entities") as es_sync_mock,
        ):
            result = executor_service.run_job(job_id)

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.es_sync_skipped)
        es_sync_mock.assert_not_called()

    def test_failed_rows_csv_is_written(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n2,Beta\n")
        plan = self._compiled_plan(
            mode="vertex",
            object_type="tag",
            object_name="Entity",
            field_mappings={"ID": "ID", "entity_name": "entity_name"},
        )
        job_id = "job_failed"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_failed"}, plan.model_dump())
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_failed",
            status="queued",
            created_by="tester",
            mode="vertex",
            plan_id=plan.plan_id,
            file_ids=["file_1"],
            compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
            failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
            normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
        )
        file_store.save_job_state(state)

        def import_side_effect(_target, row, **_kwargs):
            if row["ID"] == "2":
                raise RuntimeError("bad row")
            return {"kind": "vertex", "vid": 1}

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service.import_ngql_service.import_row", side_effect=import_side_effect),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.sync_entities"),
        ):
            result = executor_service.run_job(job_id)

        failed_rows_text = file_store.job_failed_rows_path(job_id).read_text(encoding="utf-8")
        self.assertEqual(result.status, "failed_import")
        self.assertIn("__error", failed_rows_text)
        self.assertIn("bad row", failed_rows_text)


if __name__ == "__main__":
    unittest.main()
