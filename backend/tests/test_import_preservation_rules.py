import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services.imports import draft_service, file_store, import_ngql_service, plan_service, source_service
from app.services.imports.models import CompiledTargetPlan, ImportFileRecord
from app.services.team_ingestion import contract_service
from app.services.team_ingestion.adapters.standard_csv_to_draft import build_system_managed_draft_payload


class ImportPreservationRulesTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="import-preservation-tests-")
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

    def _create_csv_file(self, *, file_id: str, original_name: str, content: str):
        record = ImportFileRecord(
            file_id=file_id,
            original_name=original_name,
            size_bytes=len(content.encode("utf-8")),
            detected_delimiter=",",
            detected_encoding="utf-8",
        )
        file_store.ensure_import_dirs()
        file_store._file_dir(file_id).mkdir(parents=True, exist_ok=True)
        file_store.staged_file_path(file_id).write_text(content, encoding="utf-8")
        file_store.write_json(file_store.file_meta_path(file_id), record.model_dump())
        return record

    def test_vertex_default_mapping_keeps_synonyms_and_unknown_columns(self):
        self._create_csv_file(
            file_id="file_vertex",
            original_name="entities.csv",
            content=(
                "ID,entity_type,entity_name,entity_raw_id,description,source,synonyms,custom_note\n"
                '1,disease,Alpha,MONDO:1,"Alpha desc",manual,"A1|A2",retain me\n'
            ),
        )

        source = source_service.build_source_snapshot("file_vertex", sample_rows=5)
        target = source_service.build_default_target(source=source, object_type="tag", object_name="Entity")
        mapped = {item.source_column: item.target_field for item in target.property_mappings}

        self.assertEqual(target.identity_mapping.id_column, "ID")
        self.assertEqual(mapped["entity_type"], "entity_type")
        self.assertEqual(mapped["entity_name"], "entity_name")
        self.assertEqual(mapped["entity_raw_id"], "entity_raw_id")
        self.assertEqual(mapped["description"], "description")
        self.assertEqual(mapped["source"], "source")
        self.assertEqual(mapped["synonyms"], "synonyms")
        self.assertEqual(mapped["custom_note"], "custom_note")

    def test_edge_default_mapping_keeps_edge_specific_columns_and_no_longer_compresses_aliases(self):
        self._create_csv_file(
            file_id="file_edge",
            original_name="treats.csv",
            content=(
                "srcVID,dstVID,rank,relation,source,evidence,pmid,relation_detail,mechanism\n"
                '1,2,7,treats,manual,"paper text",12345,"detail text","small molecule"\n'
            ),
        )

        source = source_service.build_source_snapshot("file_edge", sample_rows=5)
        target = source_service.build_default_target(source=source, object_type="edge_type", object_name="REL2")
        mapped = {item.source_column: item.target_field for item in target.property_mappings}

        self.assertEqual(target.identity_mapping.src_column, "srcVID")
        self.assertEqual(target.identity_mapping.dst_column, "dstVID")
        self.assertEqual(target.identity_mapping.rank_column, "rank")
        self.assertEqual(mapped["relation"], "relation")
        self.assertEqual(mapped["source"], "source")
        self.assertEqual(mapped["evidence"], "evidence")
        self.assertEqual(mapped["pmid"], "pmid")
        self.assertEqual(mapped["relation_detail"], "relation_detail")
        self.assertEqual(mapped["mechanism"], "mechanism")
        self.assertEqual(target.target_options["edge_kind"], "treats")

    def test_plan_injects_edge_kind_from_context_when_source_has_no_explicit_edge_kind_column(self):
        self._create_csv_file(
            file_id="file_edge_context",
            original_name="treats.csv",
            content=(
                "srcVID,dstVID,rank,relation,source,evidence,pmid\n"
                '1,2,7,related_to,manual,"paper text",12345\n'
            ),
        )

        draft = draft_service.upsert_draft(
            {
                "workspace_mode": "edge",
                "file_ids": ["file_edge_context"],
                "mapping": [
                    {
                        "object_type": "edge_type",
                        "object_name": "REL2",
                    }
                ],
            }
        )

        with mock.patch(
            "app.services.imports.schema_service.introspect_schema",
            return_value={
                "tags": [],
                "edge_types": [{"name": "REL2", "properties": [{"name": "relation", "type": "string"}]}],
            },
        ):
            plan, _warnings, _integration = plan_service.compile_plan(draft)

        compiled_target = plan.targets[0]
        edge_kind_mapping = next(item for item in compiled_target.property_mappings if item.target_field == "edge_kind")
        edge_kind_schema_prop = next(item for item in plan.schema_create_plan[0].add_properties if item.name == "edge_kind")

        self.assertEqual(edge_kind_mapping.default_value, "treats")
        self.assertEqual(edge_kind_mapping.source_column, "")
        self.assertEqual(edge_kind_schema_prop.type, "string")
        self.assertEqual(draft.mapping[0].target_options["edge_kind_resolution"]["source"], "target_options.edge_kind")

    def test_system_managed_draft_payload_uses_same_preservation_rules_as_default_source_mapping(self):
        self._create_csv_file(
            file_id="file_team",
            original_name="entity.csv",
            content=(
                "ID,entity_type,entity_name,entity_raw_id,description,source,synonyms,custom_note,version,updated_at,updated_by\n"
                '1,disease,Alpha,MONDO:1,"Alpha desc",manual,"A1|A2",retain me,0,0,importer\n'
            ),
        )

        source = source_service.build_source_snapshot("file_team", sample_rows=5)
        payload = build_system_managed_draft_payload(
            file_id="file_team",
            contract_kind="entity_csv",
            space_name="demo_kg",
        )
        target = payload["mapping"][0]
        mapped = {item["source_column"]: item["target_field"] for item in target["property_mappings"]}
        default_target = source_service.build_default_target(source=source, object_type="tag", object_name="Entity")

        self.assertEqual(target["identity_mapping"], default_target.identity_mapping.model_dump())
        self.assertEqual(mapped["synonyms"], "synonyms")
        self.assertEqual(mapped["custom_note"], "custom_note")
        self.assertEqual(mapped["version"], "version")
        self.assertEqual(mapped["updated_at"], "updated_at")
        self.assertEqual(mapped["updated_by"], "updated_by")

    def test_team_ingestion_contract_accepts_trailing_synonyms_and_unknown_columns(self):
        record = self._create_csv_file(
            file_id="file_team_contract",
            original_name="entity.csv",
            content=(
                "ID,entity_type,entity_name,entity_raw_id,description,source,synonyms,custom_note,version,updated_at,updated_by\n"
                '1,disease,Alpha,MONDO:1,"Alpha desc",manual,"A1|A2",retain me,0,0,importer\n'
            ),
        )

        result = contract_service.preflight_saved_csv(
            file_store.staged_file_path("file_team_contract"),
            upload=mock.Mock(filename="entity.csv", content_type="text/csv"),
            size_bytes=record.size_bytes,
            detected_encoding="utf-8",
            template_version=None,
        )

        self.assertEqual(result.contract_kind, "entity_csv")
        self.assertEqual(result.headers[6], "synonyms")
        self.assertEqual(result.headers[7], "custom_note")

    def test_import_ngql_uses_default_value_for_injected_edge_kind(self):
        target = CompiledTargetPlan(
            object_type="edge_type",
            object_name="REL2",
            source_id="source_1",
            create_fields=["relation", "edge_kind"],
            update_fields=["relation", "edge_kind"],
            property_types={"relation": "string", "edge_kind": "string"},
            identity_mapping={"src_column": "srcVID", "dst_column": "dstVID", "rank_column": "rank"},
            property_mappings=[
                {"source_column": "relation", "target_field": "relation"},
                {"source_column": "", "target_field": "edge_kind", "default_value": "treats"},
            ],
        )

        statement, _meta = import_ngql_service.build_row_statement(
            target,
            {"srcVID": "1", "dstVID": "2", "rank": "7", "relation": "related_to"},
            row_index=1,
            actor="tester",
        )

        self.assertIn('`edge_kind` = "treats"', statement)


if __name__ == "__main__":
    unittest.main()
