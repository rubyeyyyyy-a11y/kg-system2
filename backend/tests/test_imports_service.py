import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services.imports import (
    cleanup_executor_service,
    cleanup_planning_service,
    cleanup_service,
    draft_service,
    es_postprocess_service,
    executor_service,
    file_store,
    import_ngql_service,
    job_service,
    metadata_postprocess_service,
    postprocess_reconcile_service,
    validation_service,
)
from app.services.imports.models import (
    CompiledImportPlan,
    CompiledTargetPlan,
    ImportBatchRecord,
    ImportDraft,
    ImportFileRecord,
    ImportJobState,
    ImportTargetConfig,
    SchemaOptions,
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
        file_store.IMPORT_BATCHES_DIR = root_path / "import-batches"
        file_store.IMPORT_CLEANUP_JOBS_DIR = root_path / "import-cleanup-jobs"

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
            space_name="demo_kg",
            template_type="entity_rel2_default",
            integration_scope="entity_rel2_core",
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
        self.assertEqual(compiled_snapshot["space_name"], "demo_kg")
        self.assertIn("1,Alpha", input_snapshot)
        self.assertNotIn("2,Beta", input_snapshot)

    def test_create_job_generates_batch_id_and_persists_batch_record(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n")
        compiled_plan = self._compiled_plan(
            mode="vertex",
            object_type="tag",
            object_name="Entity",
            field_mappings={"ID": "ID", "entity_name": "entity_name"},
        )
        draft = ImportDraft(
            draft_id="draft_batch",
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
            state = job_service.create_job(draft_id="draft_batch", created_by="tester")

        self.assertTrue(state.batch_id.startswith("batch_"))
        batch_record = file_store.load_batch_record(state.batch_id)
        self.assertEqual(batch_record.job_id, state.job_id)
        self.assertEqual(batch_record.draft_id, "draft_batch")
        self.assertEqual(batch_record.status, "queued")
        self.assertTrue(batch_record.is_test_data)

    def test_job_and_draft_freeze_space_name(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n")
        draft = draft_service.upsert_draft(
            {
                "mode": "vertex",
                "file_ids": ["file_1"],
                "mapping": [
                    {
                        "object_type": "tag",
                        "object_name": "Entity",
                        "field_mappings": [
                            {"source_column": "ID", "target_field": "ID"},
                            {"source_column": "entity_name", "target_field": "entity_name"},
                        ],
                    }
                ],
            }
        )
        self.assertEqual(draft.space_name, "demo_kg")

    def test_edge_exists_uses_fetch_prop_not_match_scan(self):
        mock_res = mock.Mock()
        mock_res.rows.return_value = [{"src": 1}]
        with mock.patch("app.services.imports.import_ngql_service.execute_ngql_safe", return_value=mock_res) as execute_mock:
            exists = import_ngql_service._fetch_edge_exists("REL2", 1, 2, 3, space_name="demo_kg")

        self.assertTrue(exists)
        execute_mock.assert_called_once_with(
            "FETCH PROP ON `REL2` 1->2@3 YIELD src(edge) AS src;",
            space_name="demo_kg",
        )

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

        def batch_side_effect(_target, rows, **_kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                job_service.cancel_job(job_id)
            return _batch_result(
                successes=[
                    {"kind": "vertex", "vid": index + 1, "row_index": item.row_index}
                    for index, item in enumerate(rows)
                ]
            )

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service._BATCH_SIZE", 2),
            mock.patch("app.services.imports.executor_service.import_ngql_service.import_batch", side_effect=batch_side_effect),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.sync_entities",
                return_value={"fail_count": 0},
            ),
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
                    "index_status_snapshot": {"status": "verified_nonempty", "doc_count": 2},
                },
            ),
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
            "job_v": "post_verify_index",
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
        self.assertEqual(repaired_map["job_v"], "failed_postprocess")

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

    def test_metadata_postprocess_batches_large_delete_and_insert_queries(self):
        large_key = "rel" * 200
        executed_queries: list[str] = []

        def fake_execute(query, *, space_name=None):
            executed_queries.append(query)
            result = mock.Mock()
            if query.startswith("MATCH (m:`RelationTypeStat`)"):
                result.column_values.return_value = list(range(1, 600))
            else:
                result.column_values.return_value = []
            return result

        with (
            mock.patch("app.services.imports.metadata_postprocess_service._ensure_metadata_schema"),
            mock.patch("app.services.imports.metadata_postprocess_service._query_entity_type_counts_db", return_value=[]),
            mock.patch(
                "app.services.imports.metadata_postprocess_service._query_relation_type_counts_db",
                return_value=[(f"{large_key}_{idx}", idx + 1) for idx in range(600)],
            ),
            mock.patch("app.services.imports.metadata_postprocess_service.metadata_service.invalidate_metadata_cache"),
            mock.patch("app.services.imports.metadata_postprocess_service._NEBULA_QUERY_BUDGET_BYTES", 2200),
            mock.patch("app.services.imports.metadata_postprocess_service.execute_ngql_safe", side_effect=fake_execute),
        ):
            resp = metadata_postprocess_service.refresh_from_db(actor="tester", space_name="demo_kg")

        delete_queries = [query for query in executed_queries if query.startswith("DELETE VERTEX ")]
        insert_queries = [query for query in executed_queries if query.startswith("INSERT VERTEX `RelationTypeStat`")]
        self.assertEqual(resp["relation_type_count"], 600)
        self.assertGreater(len(delete_queries), 1)
        self.assertGreater(len(insert_queries), 1)
        self.assertTrue(all(len(query.encode("utf-8")) <= 2200 for query in delete_queries + insert_queries))

    def test_entity_only_es_sync(self):
        with (
            mock.patch(
                "app.services.imports.es_postprocess_service.indexing_service.sync_entities",
                return_value={
                    "skipped": False,
                    "space_name": "demo_kg",
                    "input_vids": 2,
                    "docs": 1,
                    "ok_count": 1,
                    "fail_count": 0,
                    "bulk_ms": 5.0,
                },
            ) as sync_mock,
        ):
            resp = es_postprocess_service.sync_entities([1, 1, 2])

        self.assertFalse(resp["skipped"])
        self.assertEqual(resp["docs"], 1)
        sync_mock.assert_called_once_with([1, 1, 2], space_name="demo_kg", refresh="wait_for")

    def test_executor_writes_batch_item_ledger_and_batch_counts(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name,entity_raw_id\n1,Alpha,raw-1\n")
        plan = CompiledImportPlan(
            plan_id="plan_items",
            space_name="demo_kg",
            template_type="entity_rel2_default",
            integration_scope="entity_rel2_core",
            mode="vertex",
            file_ids=["file_1"],
            targets=[
                CompiledTargetPlan(
                    object_type="tag",
                    object_name="Entity",
                    field_mappings={"ID": "ID", "entity_name": "entity_name", "entity_raw_id": "entity_raw_id"},
                    property_types={"entity_name": "string", "entity_raw_id": "string", "updated_by": "string", "updated_at": "int64"},
                    identity_fields=["ID"],
                    update_fields=["entity_name", "entity_raw_id"],
                    create_fields=["ID", "entity_name", "entity_raw_id"],
                    integration_level="fully_integrated",
                )
            ],
            schema_create_plan=[],
        )
        job_id = "job_items"
        batch_id = "batch_items"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_items"}, plan.model_dump())
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id=batch_id,
                space_id="demo_kg",
                draft_id="draft_items",
                job_id=job_id,
                status="queued",
            )
        )
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_items",
            batch_id=batch_id,
            status="queued",
            created_by="tester",
            mode="vertex",
            plan_id=plan.plan_id,
            file_ids=["file_1"],
            space_name="demo_kg",
            compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
            failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
            normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
        )
        file_store.save_job_state(state)

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service.import_ngql_service.vertex_exists", return_value=False),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(successes=[{"kind": "vertex", "vid": 1, "row_index": 1}]),
            ),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.sync_entities",
                return_value={"fail_count": 0},
            ),
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
        ):
            result = executor_service.run_job(job_id)

        self.assertEqual(result.status, "succeeded")
        items = file_store.load_batch_items(batch_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].vid, 1)
        batch_record = file_store.load_batch_record(batch_id)
        self.assertEqual(batch_record.entity_count, 1)
        self.assertEqual(batch_record.relation_count, 0)
        self.assertTrue(batch_record.searchable)

    def test_batch_item_ledger_append_is_persistently_idempotent(self):
        from app.services.imports.models import ImportBatchItemRecord

        first = file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_idem",
                space_id="demo_kg",
                job_id="job_idem",
                item_type="entity",
                vid=101,
                entity_name="Alpha",
            )
        )
        second = file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_idem",
                space_id="demo_kg",
                job_id="job_idem",
                item_type="entity",
                vid=101,
                entity_name="Alpha",
            )
        )

        self.assertTrue(first.appended)
        self.assertFalse(second.appended)
        self.assertEqual(len(file_store.load_batch_items("batch_idem")), 1)
        key_index = file_store.read_json(file_store.batch_item_keys_path("batch_idem"))
        self.assertEqual(key_index["keys"], ["entity:101"])

    def test_executor_batch_fallback_does_not_duplicate_ledger_items(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n1,Alpha again\n")
        plan = self._compiled_plan(
            mode="vertex",
            object_type="tag",
            object_name="Entity",
            field_mappings={"ID": "ID", "entity_name": "entity_name"},
        )
        job_id = "job_fallback_idem"
        batch_id = "batch_fallback_idem"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_fallback"}, plan.model_dump())
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id=batch_id,
                space_id="demo_kg",
                draft_id="draft_fallback",
                job_id=job_id,
                status="queued",
            )
        )
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_fallback",
            batch_id=batch_id,
            status="queued",
            created_by="tester",
            mode="vertex",
            plan_id=plan.plan_id,
            file_ids=["file_1"],
            space_name="demo_kg",
            compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
            failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
            normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
        )
        file_store.save_job_state(state)

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service.import_ngql_service.vertex_exists", return_value=False),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(
                    successes=[
                        {"kind": "vertex", "vid": 1, "row_index": 1},
                        {"kind": "vertex", "vid": 1, "row_index": 2},
                    ],
                    used_fallback=True,
                ),
            ),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.sync_entities", return_value={"fail_count": 0}),
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
        ):
            result = executor_service.run_job(job_id)

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(file_store.load_batch_items(batch_id)), 1)
        batch_record = file_store.load_batch_record(batch_id)
        self.assertEqual(batch_record.ledger_summary["entity"]["requested_count"], 2)
        self.assertEqual(batch_record.ledger_summary["entity"]["appended_count"], 1)
        self.assertEqual(batch_record.ledger_summary["entity"]["skipped_existing_count"], 1)

    def test_post_verify_index_writes_completion_summary(self):
        with (
            mock.patch(
                "app.services.imports.es_postprocess_service._verify_imported_entities_visible",
                return_value={
                    "ok": True,
                    "expected_docs": 1,
                    "found_docs": 1,
                    "missing_vids": [],
                    "sample_query_ok": True,
                },
            ),
            mock.patch(
                "app.services.imports.es_postprocess_service.calculate_space_index_status_summary",
                return_value={
                    "space_name": "demo_kg",
                    "status": "verified_nonempty",
                    "note": "ok",
                    "es_doc_count": 1,
                    "nebula_entity_count": 1,
                    "coverage_pct": 100.0,
                    "verify": {"ok": True},
                },
            ),
            mock.patch(
                "app.services.imports.es_postprocess_service.update_index_status_from_summary",
                return_value=mock.Mock(model_dump=mock.Mock(return_value={"status": "verified_nonempty", "doc_count": 1})),
            ),
            mock.patch(
                "app.services.imports.es_postprocess_service.readiness_service.space_meta_payload_for_space",
                return_value={"space_name": "demo_kg", "graph_status": "ready", "search_status": "full", "coverage_pct": 100.0, "index_status": {"status": "verified_nonempty", "doc_count": 1}},
            ),
        ):
            resp = es_postprocess_service.post_verify_index([1, 2])

        self.assertTrue(resp["completion_summary"]["searchable"])
        self.assertEqual(resp["completion_summary"]["index_status"], "verified_nonempty")
        self.assertEqual(resp["index_status_snapshot"]["status"], "verified_nonempty")

    def test_post_verify_index_surfaces_registry_write_failure(self):
        with (
            mock.patch(
                "app.services.imports.es_postprocess_service._verify_imported_entities_visible",
                return_value={"ok": True, "expected_docs": 1, "found_docs": 1, "missing_vids": [], "sample_query_ok": True},
            ),
            mock.patch(
                "app.services.imports.es_postprocess_service.calculate_space_index_status_summary",
                return_value={"status": "verified_nonempty", "es_doc_count": 1, "nebula_entity_count": 1, "coverage_pct": 100.0, "verify": {"ok": True}, "note": "ok"},
            ),
            mock.patch(
                "app.services.imports.es_postprocess_service.update_index_status_from_summary",
                side_effect=RuntimeError("registry unavailable"),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "registry_write_failed: registry unavailable"):
                es_postprocess_service.post_verify_index([1], space_name="demo_kg")

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
            ) as verify_mock,
        ):
            result = executor_service.run_job(job_id)

        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.es_sync_skipped)
        es_sync_mock.assert_not_called()
        verify_mock.assert_called_once()

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

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(
                    successes=[{"kind": "vertex", "vid": 1, "row_index": 1}],
                    failures=[
                        (
                            import_ngql_service.BatchRowItem(row_index=2, row={"ID": "2", "entity_name": "Beta"}),
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
        ):
            result = executor_service.run_job(job_id)

        failed_rows_text = file_store.job_failed_rows_path(job_id).read_text(encoding="utf-8")
        self.assertEqual(result.status, "failed_import")
        self.assertIn("__error", failed_rows_text)
        self.assertIn("bad row", failed_rows_text)

    def test_validate_streaming_does_not_use_full_row_list_read(self):
        self._create_csv_file(
            file_id="file_1",
            content="ID,entity_name,entity_type,source\n1,Alpha,Disease,manual\n2,Beta,Disease,manual\n",
        )
        draft = ImportDraft(
            draft_id="draft_streaming",
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

        with (
            mock.patch(
                "app.services.imports.schema_service.introspect_schema",
                return_value={
                    "tags": [{"name": "Entity", "properties": [{"name": "entity_name", "type": "string"}]}],
                    "edge_types": [{"name": "REL2", "properties": [{"name": "relation", "type": "string"}]}],
                },
            ),
            mock.patch("app.services.imports.file_store.read_csv_rows", side_effect=AssertionError("should not load full row list")),
        ):
            result = validation_service.validate_draft(draft)

        self.assertTrue(result.passed)
        self.assertEqual(result.scanned_rows, 2)
        self.assertEqual(result.error_rows, 0)
        self.assertFalse(result.errors_truncated)

    def test_failed_rows_truncation_semantics_preserved(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n2,Beta\n3,Gamma\n")
        plan = self._compiled_plan(
            mode="vertex",
            object_type="tag",
            object_name="Entity",
            field_mappings={"ID": "ID", "entity_name": "entity_name"},
        )
        job_id = "job_failed_truncated"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_failed_truncated"}, plan.model_dump())
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_failed_truncated",
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

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service._MAX_FAILED_ROWS_WRITTEN", 1),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(
                    failures=[
                        (import_ngql_service.BatchRowItem(row_index=1, row={"ID": "1", "entity_name": "Alpha"}), RuntimeError("bad row")),
                        (import_ngql_service.BatchRowItem(row_index=2, row={"ID": "2", "entity_name": "Beta"}), RuntimeError("bad row")),
                        (import_ngql_service.BatchRowItem(row_index=3, row={"ID": "3", "entity_name": "Gamma"}), RuntimeError("bad row")),
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
        ):
            result = executor_service.run_job(job_id)

        failed_rows_text = file_store.job_failed_rows_path(job_id).read_text(encoding="utf-8")
        self.assertEqual(result.status, "failed_import")
        self.assertTrue(result.failed_rows_truncated)
        self.assertIn("failed_rows truncated after 1 rows", failed_rows_text)

    def test_job_status_progress_includes_postprocess_phases(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n")
        plan = self._compiled_plan(
            mode="vertex",
            object_type="tag",
            object_name="Entity",
            field_mappings={"ID": "ID", "entity_name": "entity_name"},
        )
        job_id = "job_phases"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_phases"}, plan.model_dump())
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_phases",
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
        seen_statuses: list[str] = []
        original_update_state = executor_service._update_state

        def tracking_update(state, **changes):
            next_state = original_update_state(state, **changes)
            if "status" in changes:
                seen_statuses.append(changes["status"])
            return next_state

        with (
            mock.patch("app.services.imports.executor_service._update_state", side_effect=tracking_update),
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch(
                "app.services.imports.executor_service.import_ngql_service.import_batch",
                return_value=_batch_result(successes=[{"kind": "vertex", "vid": 101, "row_index": 1}]),
            ),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch(
                "app.services.imports.executor_service.es_postprocess_service.sync_entities",
                return_value={"fail_count": 0},
            ),
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
        ):
            result = executor_service.run_job(job_id)

        self.assertEqual(result.status, "succeeded")
        self.assertIn("post_metadata_refresh", seen_statuses)
        self.assertIn("post_es_sync", seen_statuses)
        self.assertIn("post_verify_index", seen_statuses)

    def test_executor_failure_stage_parser_prefers_explicit_prefixes(self):
        self.assertEqual(
            executor_service._failure_stage_from_error("es_sync_failed: ES request timed out", current_status="post_es_sync"),
            "es_sync_failed",
        )
        self.assertEqual(
            executor_service._failure_stage_from_error("registry_write_failed: boom", current_status="post_verify_index"),
            "registry_write_failed",
        )
        self.assertEqual(
            executor_service._failure_stage_from_error("plain failure", current_status="post_metadata_refresh"),
            "metadata_failed",
        )

    def test_reconcile_postprocess_updates_job_and_registry_snapshot(self):
        job_id = "job_reconcile"
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_reconcile",
            status="failed_postprocess",
            created_by="tester",
            mode="vertex",
            plan_id="plan_reconcile",
            file_ids=[],
            space_name="demo_kg",
            compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
            failed_rows_path=str(file_store.job_failed_rows_path(job_id)),
            normalized_rows_path=str(file_store.job_normalized_rows_path(job_id)),
            affected_entity_vids=[1, 2, 2],
            metadata_refreshed=True,
            error_message="es_sync_failed: timed out",
            failure_stage="es_sync_failed",
        )
        file_store.save_job_state(state)

        with (
            mock.patch(
                "app.services.imports.postprocess_reconcile_service.es_postprocess_service.sync_entities",
                return_value={"space_name": "demo_kg", "ok_count": 2, "fail_count": 0, "docs": 2},
            ),
            mock.patch(
                "app.services.imports.postprocess_reconcile_service.es_postprocess_service.post_verify_index",
                return_value={
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
                    "index_status_snapshot": {"status": "verified_nonempty", "doc_count": 2},
                },
            ),
        ):
            result = postprocess_reconcile_service.reconcile_postprocess(job_id=job_id, sync_scope="auto")

        updated = file_store.load_job_state(job_id)
        self.assertEqual(result["sync_scope"], "job")
        self.assertTrue(result["completion_summary"]["searchable"])
        self.assertEqual(updated.status, "succeeded")
        self.assertIsNone(updated.failure_stage)
        self.assertEqual(updated.index_status_snapshot.status, "verified_nonempty")

    def test_import_batch_prefers_single_insert_statement(self):
        target = CompiledTargetPlan(
            object_type="tag",
            object_name="Entity",
            source_id="source_1",
            create_fields=["entity_name"],
            update_fields=["entity_name"],
            property_types={"entity_name": "string"},
            identity_mapping={"id_column": "ID"},
            property_mappings=[{"source_column": "entity_name", "target_field": "entity_name"}],
        )
        rows = [
            import_ngql_service.BatchRowItem(row_index=1, row={"ID": "1", "entity_name": "Alpha"}),
            import_ngql_service.BatchRowItem(row_index=2, row={"ID": "2", "entity_name": "Beta"}),
        ]
        with mock.patch("app.services.imports.import_ngql_service.execute_ngql_safe") as execute_mock:
            result = import_ngql_service.import_batch(target, rows, actor="tester", space_name="demo_kg")

        self.assertFalse(result.used_fallback)
        self.assertEqual(len(result.successes), 2)
        self.assertEqual(execute_mock.call_count, 1)
        self.assertIn("INSERT VERTEX", execute_mock.call_args.args[0])
        self.assertIn("VALUES 1:", execute_mock.call_args.args[0])
        self.assertIn("2:(", execute_mock.call_args.args[0])

    def test_executor_writes_batch_summary_per_target(self):
        self._create_csv_file(file_id="file_1", content="ID,entity_name\n1,Alpha\n2,Beta\n3,Gamma\n")
        source = {
            "source_id": "source_1",
            "file_id": "file_1",
            "filename": "file_1.csv",
            "columns": ["ID", "entity_name"],
            "sample_rows": [],
            "header_hash": "h1",
            "inferred_kind": "vertex",
        }
        plan = CompiledImportPlan(
            plan_id="plan_batch",
            space_name="demo_kg",
            mode="vertex",
            workspace_mode="vertex",
            file_ids=["file_1"],
            sources=[source],
            targets=[
                CompiledTargetPlan(
                    target_id="target_1",
                    object_type="tag",
                    object_name="Entity",
                    source_id="source_1",
                    source_file_id="file_1",
                    source_filename="file_1.csv",
                    source_columns=["ID", "entity_name"],
                    create_fields=["entity_name"],
                    update_fields=["entity_name"],
                    property_types={"entity_name": "string"},
                    identity_mapping={"id_column": "ID"},
                    property_mappings=[{"source_column": "entity_name", "target_field": "entity_name"}],
                    integration_level="fully_integrated",
                )
            ],
            schema_create_plan=[],
        )
        job_id = "job_batch_summary"
        file_store.copy_inputs_to_job(job_id, ["file_1"], {"draft_id": "draft_batch"}, plan.model_dump())
        state = ImportJobState(
            job_id=job_id,
            draft_id="draft_batch",
            status="queued",
            created_by="tester",
            mode="vertex",
            workspace_mode="vertex",
            plan_id=plan.plan_id,
            file_ids=["file_1"],
            sources=[source],
            targets=plan.targets,
            artifacts=[],
            compiled_plan_path=str(file_store.job_compiled_plan_path(job_id)),
        )
        file_store.save_job_state(state)

        def batch_side_effect(target, rows, **_kwargs):
            return import_ngql_service.BatchImportResult(
                successes=[
                    {"kind": "vertex", "vid": int(item.row["ID"]), "target": target.object_name, "row_index": item.row_index}
                    for item in rows
                ],
                failures=[],
                batch_statement_count=1,
                used_fallback=False,
            )

        with (
            mock.patch("app.services.imports.executor_service.schema_service.apply_schema_plan"),
            mock.patch("app.services.imports.executor_service._BATCH_SIZE", 2),
            mock.patch("app.services.imports.executor_service.import_ngql_service.import_batch", side_effect=batch_side_effect),
            mock.patch("app.services.imports.executor_service.metadata_postprocess_service.refresh_from_db"),
            mock.patch("app.services.imports.executor_service.es_postprocess_service.sync_entities", return_value={"fail_count": 0}),
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
                    "index_status_snapshot": {"status": "verified_nonempty", "doc_count": 3},
                },
            ),
        ):
            result = executor_service.run_job(job_id)

        summary = file_store.read_json(file_store.job_target_summary_path(job_id, "target_1"))
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(summary["batches_total"], 2)
        self.assertEqual(summary["batches_succeeded"], 2)
        self.assertEqual(summary["processed_rows"], 3)
        self.assertEqual(summary["status"], "completed")

    def test_cleanup_job_creation_and_non_test_rejection(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_a",
                space_id="demo_kg",
                draft_id="draft_cleanup_a",
                job_id="job_cleanup_a",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_a",
                space_id="demo_kg",
                job_id="job_cleanup_a",
                item_type="entity",
                vid=1,
            )
        )
        job = cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_a"], scope="full_batch", created_by="tester")
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.requested_entity_count, 1)

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_b",
                space_id="demo_kg",
                draft_id="draft_cleanup_b",
                job_id="job_cleanup_b",
                status="succeeded",
                is_test_data=False,
                cleanup_status="not_supported",
            )
        )
        file_store.append_batch_item(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_b",
                space_id="demo_kg",
                job_id="job_cleanup_b",
                item_type="entity",
                vid=2,
            )
        )
        with self.assertRaisesRegex(Exception, "cannot be cleaned up"):
            cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_b"], scope="full_batch", created_by="tester")

    def test_cleanup_deletes_relations_before_entities_and_conflicts_partial_succeeded(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_main",
                space_id="demo_kg",
                draft_id="draft_cleanup_main",
                job_id="job_cleanup_main",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_other",
                space_id="demo_kg",
                draft_id="draft_cleanup_other",
                job_id="job_cleanup_other",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_main",
                space_id="demo_kg",
                job_id="job_cleanup_main",
                item_type="relation",
                src_vid=1,
                dst_vid=2,
                rank=0,
                relation="rel_a",
                edge_type="REL2",
                created_by_batch=True,
            )
        )
        file_store.append_batch_item(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_main",
                space_id="demo_kg",
                job_id="job_cleanup_main",
                item_type="entity",
                vid=1,
                entity_name="Alpha",
                entity_raw_id="raw-1",
                created_by_batch=True,
            )
        )
        file_store.append_batch_item(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_main",
                space_id="demo_kg",
                job_id="job_cleanup_main",
                item_type="entity",
                vid=2,
                entity_name="Beta",
                entity_raw_id="raw-2",
                created_by_batch=True,
            )
        )
        file_store.append_batch_item(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_other",
                space_id="demo_kg",
                job_id="job_cleanup_other",
                item_type="relation",
                src_vid=9,
                dst_vid=2,
                rank=1,
                relation="rel_b",
                edge_type="REL2",
                created_by_batch=True,
            )
        )

        cleanup_job = cleanup_service.create_cleanup_job(
            batch_ids=["batch_cleanup_main"],
            scope="full_batch",
            created_by="tester",
        )
        call_order: list[str] = []
        with (
            mock.patch(
                "app.services.imports.cleanup_executor_service.import_ngql_service.delete_edge",
                side_effect=lambda *args, **kwargs: call_order.append("relation"),
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.import_ngql_service.delete_vertex",
                side_effect=lambda *args, **kwargs: call_order.append("entity"),
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.es_postprocess_service.delete_entities_from_index",
                return_value={"fail_count": 0},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.metadata_postprocess_service.refresh_from_db",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.postprocess_reconcile_service.reconcile_postprocess",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service._verify_deleted_entities",
                return_value={"ok": True, "deleted_entity_count": 1},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": False,
                    "live_blocking_edges": [],
                    "live_blocking_count": 0,
                    "scan_note": "mocked",
                    "truncated": False,
                    "warning": None,
                    "scanned_incident_edge_count": 0,
                    "excluded_by_plan_count": 0,
                    "scan_edge_type": "REL2",
                    "took_ms": 1.0,
                },
            ),
        ):
            result = cleanup_executor_service.run_cleanup_job(cleanup_job.cleanup_job_id)

        self.assertEqual(result.status, "partial_succeeded")
        self.assertEqual(call_order[0], "relation")
        self.assertEqual(call_order[1], "entity")
        self.assertEqual(result.deleted_relation_count, 1)
        self.assertEqual(result.deleted_entity_count, 1)
        self.assertEqual(len(result.conflicts), 1)
        self.assertEqual(result.conflicts[0].vid, 2)
        self.assertEqual(result.phase, "completed")
        self.assertEqual(result.final_phase, "completed")
        self.assertTrue(any(artifact.filename == "summary.json" for artifact in result.artifacts))
        self.assertTrue(any(artifact.filename == "plan_summary.json" for artifact in result.artifacts))
        self.assertTrue(result.has_plan_artifacts)
        self.assertGreaterEqual(result.plan_summary.ledger_blocked_entity_count, 1)

    def test_cleanup_planning_generates_plan_summary_and_artifacts(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_plan",
                space_id="demo_kg",
                draft_id="draft_cleanup_plan",
                job_id="job_cleanup_plan",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_plan",
                space_id="demo_kg",
                job_id="job_cleanup_plan",
                item_type="relation",
                src_vid=11,
                dst_vid=12,
                rank=0,
                relation="rel_plan",
                edge_type="REL2",
                created_by_batch=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_plan",
                space_id="demo_kg",
                job_id="job_cleanup_plan",
                item_type="entity",
                vid=11,
                entity_name="Plan Alpha",
                entity_raw_id="plan-11",
                created_by_batch=True,
            )
        )

        cleanup_job = cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_plan"], scope="full_batch", created_by="tester")
        with (
            mock.patch(
                "app.services.imports.cleanup_executor_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": False,
                    "live_blocking_edges": [],
                    "live_blocking_count": 0,
                    "scan_note": "mocked",
                    "truncated": False,
                    "warning": None,
                    "scanned_incident_edge_count": 0,
                    "excluded_by_plan_count": 0,
                    "scan_edge_type": "REL2",
                    "took_ms": 1.0,
                },
            ),
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_edge"),
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_vertex"),
            mock.patch(
                "app.services.imports.cleanup_executor_service.es_postprocess_service.delete_entities_from_index",
                return_value={"fail_count": 0},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.metadata_postprocess_service.refresh_from_db",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.postprocess_reconcile_service.reconcile_postprocess",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service._verify_deleted_entities",
                return_value={"ok": True, "deleted_entity_count": 1},
            ),
        ):
            result = cleanup_executor_service.run_cleanup_job(cleanup_job.cleanup_job_id)

        artifact_names = {artifact.filename for artifact in result.artifacts}
        self.assertEqual(result.status, "succeeded")
        self.assertIn("plan_summary.json", artifact_names)
        self.assertIn("blocked_entities.json", artifact_names)
        self.assertIn("deletable_entities.json", artifact_names)
        self.assertIn("deletable_relations.json", artifact_names)
        self.assertTrue(result.has_plan_artifacts)
        self.assertEqual(result.plan_summary.requested_entity_count, 1)
        self.assertEqual(result.plan_summary.requested_relation_count, 1)
        self.assertEqual(result.plan_summary.deletable_entity_count, 1)
        self.assertEqual(result.plan_summary.deletable_relation_count, 1)

    def test_cleanup_preview_and_execute_share_same_planning_core(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_shared_plan",
                space_id="demo_kg",
                draft_id="draft_cleanup_shared_plan",
                job_id="job_cleanup_shared_plan",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_shared_plan",
                space_id="demo_kg",
                job_id="job_cleanup_shared_plan",
                item_type="relation",
                src_vid=61,
                dst_vid=62,
                rank=0,
                relation="rel_shared",
                edge_type="REL2",
                created_by_batch=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_shared_plan",
                space_id="demo_kg",
                job_id="job_cleanup_shared_plan",
                item_type="entity",
                vid=61,
                entity_name="Shared Alpha",
                entity_raw_id="shared-61",
                created_by_batch=True,
            )
        )

        real_plan_cleanup = cleanup_planning_service.plan_cleanup
        with (
            mock.patch(
                "app.services.imports.cleanup_planning_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": False,
                    "live_blocking_edges": [],
                    "live_blocking_count": 0,
                    "scan_note": "mocked",
                    "truncated": False,
                    "warning": None,
                    "scanned_incident_edge_count": 0,
                    "excluded_by_plan_count": 0,
                    "scan_edge_type": "REL2",
                    "took_ms": 1.0,
                },
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": False,
                    "live_blocking_edges": [],
                    "live_blocking_count": 0,
                    "scan_note": "mocked",
                    "truncated": False,
                    "warning": None,
                    "scanned_incident_edge_count": 0,
                    "excluded_by_plan_count": 0,
                    "scan_edge_type": "REL2",
                    "took_ms": 1.0,
                },
            ),
            mock.patch(
                "app.services.imports.cleanup_planning_service.plan_cleanup",
                wraps=real_plan_cleanup,
            ) as planning_spy,
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_edge"),
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_vertex"),
            mock.patch(
                "app.services.imports.cleanup_executor_service.es_postprocess_service.delete_entities_from_index",
                return_value={"fail_count": 0},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.metadata_postprocess_service.refresh_from_db",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.postprocess_reconcile_service.reconcile_postprocess",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service._verify_deleted_entities",
                return_value={"ok": True, "deleted_entity_count": 1},
            ),
        ):
            preview_context, preview_plan = cleanup_service.preview_cleanup_plan(
                batch_ids=["batch_cleanup_shared_plan"],
                scope="full_batch",
                created_by="tester",
            )
            cleanup_job = cleanup_service.create_cleanup_job(
                batch_ids=["batch_cleanup_shared_plan"],
                scope="full_batch",
                created_by="tester",
            )
            result = cleanup_executor_service.run_cleanup_job(cleanup_job.cleanup_job_id)

        self.assertEqual(preview_context.scope, "full_batch")
        self.assertGreaterEqual(planning_spy.call_count, 2)
        self.assertEqual(preview_plan.plan_summary.requested_entity_count, result.plan_summary.requested_entity_count)
        self.assertEqual(preview_plan.plan_summary.requested_relation_count, result.plan_summary.requested_relation_count)
        self.assertEqual(preview_plan.plan_summary.deletable_entity_count, result.plan_summary.deletable_entity_count)
        self.assertEqual(preview_plan.plan_summary.deletable_relation_count, result.plan_summary.deletable_relation_count)

    def test_cleanup_runtime_startup_recovery_shell_keeps_interrupted_semantics(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_runtime",
                space_id="demo_kg",
                draft_id="draft_cleanup_runtime",
                job_id="job_cleanup_runtime",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_runtime",
                space_id="demo_kg",
                job_id="job_cleanup_runtime",
                item_type="entity",
                vid=71,
                entity_name="Runtime Alpha",
                created_by_batch=True,
            )
        )
        queued_job = cleanup_service.create_cleanup_job(
            batch_ids=["batch_cleanup_runtime"],
            scope="full_batch",
            created_by="tester",
        )

        with mock.patch.object(cleanup_executor_service._RUNTIME, "ensure_worker_running") as ensure_worker_mock:
            cleanup_executor_service.startup_recover_and_start()

        updated = file_store.load_cleanup_job(queued_job.cleanup_job_id)
        updated_batch = file_store.load_batch_record("batch_cleanup_runtime")
        self.assertEqual(updated.status, "failed")
        self.assertEqual(updated.failure_kind, "process_interrupted")
        self.assertEqual(updated_batch.cleanup_status, "failed")
        ensure_worker_mock.assert_not_called()

    def test_cleanup_live_graph_blocker_blocks_entity_even_if_ledger_allows(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_live",
                space_id="demo_kg",
                draft_id="draft_cleanup_live",
                job_id="job_cleanup_live",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_live",
                space_id="demo_kg",
                job_id="job_cleanup_live",
                item_type="relation",
                src_vid=31,
                dst_vid=32,
                rank=0,
                relation="rel_live",
                edge_type="REL2",
                created_by_batch=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_live",
                space_id="demo_kg",
                job_id="job_cleanup_live",
                item_type="entity",
                vid=31,
                entity_name="Live Blocked",
                entity_raw_id="live-31",
                created_by_batch=True,
            )
        )

        cleanup_job = cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_live"], scope="full_batch", created_by="tester")
        with (
            mock.patch(
                "app.services.imports.cleanup_executor_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": True,
                    "live_blocking_edges": [{"edge_type": "REL2", "src_vid": 777, "dst_vid": 31, "rank": 1, "relation": "outside"}],
                    "live_blocking_count": 1,
                    "scan_note": "mocked_live",
                    "truncated": False,
                    "warning": None,
                    "scanned_incident_edge_count": 1,
                    "excluded_by_plan_count": 0,
                    "scan_edge_type": "REL2",
                    "took_ms": 2.5,
                },
            ),
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_edge"),
            mock.patch("app.services.imports.cleanup_executor_service.import_ngql_service.delete_vertex") as delete_vertex_mock,
            mock.patch(
                "app.services.imports.cleanup_executor_service.metadata_postprocess_service.refresh_from_db",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.postprocess_reconcile_service.reconcile_postprocess",
                return_value={"ok": True},
            ),
        ):
            result = cleanup_executor_service.run_cleanup_job(cleanup_job.cleanup_job_id)

        self.assertEqual(result.status, "partial_succeeded")
        self.assertEqual(result.deleted_entity_count, 0)
        self.assertEqual(result.deleted_relation_count, 1)
        self.assertEqual(result.plan_summary.live_graph_blocked_entity_count, 1)
        self.assertTrue(any(conflict.source == "live_graph" for conflict in result.conflicts))
        self.assertTrue(any(conflict.reason == "referenced_in_live_graph" for conflict in result.conflicts))
        delete_vertex_mock.assert_not_called()

    def test_cleanup_planning_failure_records_planning_phase(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_plan_fail",
                space_id="demo_kg",
                draft_id="draft_cleanup_plan_fail",
                job_id="job_cleanup_plan_fail",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_plan_fail",
                space_id="demo_kg",
                job_id="job_cleanup_plan_fail",
                item_type="entity",
                vid=51,
                entity_name="PlanFail",
                created_by_batch=True,
            )
        )

        cleanup_job = cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_plan_fail"], scope="full_batch", created_by="tester")
        with mock.patch(
            "app.services.imports.cleanup_executor_service.cleanup_graph_scan_service.check_entity_live_references",
            side_effect=RuntimeError("nebula down"),
        ):
            result = cleanup_executor_service.run_cleanup_job(cleanup_job.cleanup_job_id)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_phase, "planning")
        self.assertEqual(result.failure_kind, "live_graph_scan_failed")
        self.assertEqual(result.phase, "failed")
        self.assertEqual(result.final_phase, "failed")

    def test_cleanup_all_blocked_is_stable_and_explainable(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_all_blocked",
                space_id="demo_kg",
                draft_id="draft_cleanup_all_blocked",
                job_id="job_cleanup_all_blocked",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_all_blocked",
                space_id="demo_kg",
                job_id="job_cleanup_all_blocked",
                item_type="entity",
                vid=81,
                entity_name="BlockedOnly",
                created_by_batch=True,
            )
        )

        cleanup_job = cleanup_service.create_cleanup_job(
            batch_ids=["batch_cleanup_all_blocked"],
            scope="full_batch",
            created_by="tester",
        )
        with (
            mock.patch(
                "app.services.imports.cleanup_executor_service.cleanup_graph_scan_service.check_entity_live_references",
                return_value={
                    "has_blockers": True,
                    "live_blocking_edges": [{"edge_type": "REL2", "src_vid": 90, "dst_vid": 81, "rank": 0, "relation": "hold"}],
                    "live_blocking_count": 1,
                    "scan_note": "mocked_live",
                    "truncated": False,
                    "warning": None,
                    "scanned_incident_edge_count": 1,
                    "excluded_by_plan_count": 0,
                    "scan_edge_type": "REL2",
                    "took_ms": 2.0,
                },
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.metadata_postprocess_service.refresh_from_db",
                return_value={"ok": True},
            ),
            mock.patch(
                "app.services.imports.cleanup_executor_service.postprocess_reconcile_service.reconcile_postprocess",
                return_value={"ok": True},
            ),
        ):
            result = cleanup_executor_service.run_cleanup_job(cleanup_job.cleanup_job_id)

        self.assertEqual(result.status, "partial_succeeded")
        self.assertEqual(result.deleted_entity_count, 0)
        self.assertEqual(result.deleted_relation_count, 0)
        self.assertEqual(result.plan_summary.deletable_entity_count, 0)
        self.assertEqual(result.plan_summary.deletable_relation_count, 0)
        self.assertTrue(any("no deletable relations or entities" in message for message in result.warning_messages))
        self.assertEqual(result.phase, "completed")
        self.assertTrue(any(phase.phase == "planning" for phase in result.phase_history))
        self.assertTrue(any(artifact.filename == "blocked_entities.json" for artifact in result.artifacts))

    def test_cleanup_failure_records_failure_phase_and_kind(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_fail",
                space_id="demo_kg",
                draft_id="draft_cleanup_fail",
                job_id="job_cleanup_fail",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_fail",
                space_id="demo_kg",
                job_id="job_cleanup_fail",
                item_type="relation",
                src_vid=1,
                dst_vid=2,
                rank=0,
                relation="rel_a",
                edge_type="REL2",
                created_by_batch=True,
            )
        )

        cleanup_job = cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_fail"], scope="relations_only", created_by="tester")
        with mock.patch(
            "app.services.imports.cleanup_executor_service.import_ngql_service.delete_edge",
            side_effect=RuntimeError("boom"),
        ):
            result = cleanup_executor_service.run_cleanup_job(cleanup_job.cleanup_job_id)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.failure_phase, "deleting_relations")
        self.assertEqual(result.failure_kind, "delete_failed")
        self.assertEqual(result.phase, "failed")
        self.assertEqual(result.final_phase, "failed")

    def test_cleanup_job_rejects_already_succeeded_batch(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_done",
                space_id="demo_kg",
                draft_id="draft_cleanup_done",
                job_id="job_cleanup_done",
                status="succeeded",
                is_test_data=True,
                cleanup_status="succeeded",
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_done",
                space_id="demo_kg",
                job_id="job_cleanup_done",
                item_type="entity",
                vid=1,
                created_by_batch=True,
            )
        )

        with self.assertRaisesRegex(Exception, "already cleanup_succeeded"):
            cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_done"], scope="full_batch", created_by="tester")

    def test_cleanup_job_duplicate_submit_reuses_same_active_job(self):
        from app.services.imports.models import ImportBatchItemRecord

        file_store.save_batch_record(
            ImportBatchRecord(
                batch_id="batch_cleanup_dup",
                space_id="demo_kg",
                draft_id="draft_cleanup_dup",
                job_id="job_cleanup_dup",
                status="succeeded",
                is_test_data=True,
            )
        )
        file_store.append_batch_item_if_absent(
            ImportBatchItemRecord(
                batch_id="batch_cleanup_dup",
                space_id="demo_kg",
                job_id="job_cleanup_dup",
                item_type="entity",
                vid=1,
                created_by_batch=True,
            )
        )

        first = cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_dup"], scope="full_batch", created_by="tester")
        second = cleanup_service.create_cleanup_job(batch_ids=["batch_cleanup_dup"], scope="full_batch", created_by="tester")

        self.assertEqual(first.cleanup_job_id, second.cleanup_job_id)


if __name__ == "__main__":
    unittest.main()
