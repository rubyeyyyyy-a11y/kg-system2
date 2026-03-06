import unittest
from unittest import mock

from fastapi import HTTPException

from app.services import edit_service
from app.schemas.edit import EdgePatchRequest, NodePatchRequest


class _FakeResult:
    def __init__(self, columns):
        self._columns = columns

    def rows(self):
        first = next(iter(self._columns.values()), [])
        return [object()] * len(first)

    def column_values(self, name):
        return self._columns[name]


class NodeEditServiceTest(unittest.TestCase):
    def test_node_snapshot_uses_fetch_prop_and_defaults_missing_values(self):
        captured = {}

        def fake_execute(ngql):
            captured["ngql"] = ngql
            return _FakeResult(
                {
                    "vid": [1],
                    "entity_name": [None],
                    "entity_type": [None],
                    "source": [None],
                    "description": [None],
                    "entity_raw_id": [None],
                    "version": [None],
                    "updated_at": [None],
                    "updated_by": [None],
                }
            )

        with mock.patch("app.services.edit_service.execute_ngql_safe", side_effect=fake_execute):
            snapshot = edit_service._node_snapshot(1)

        self.assertIn("FETCH PROP ON `Entity` 1", captured["ngql"])
        self.assertNotIn("MATCH (v:`Entity`)", captured["ngql"])
        self.assertEqual(
            snapshot,
            {
                "vid": 1,
                "entity_name": "",
                "entity_type": "",
                "source": "",
                "description": "",
                "entity_raw_id": "",
                "version": 0,
                "updated_at": 0,
                "updated_by": "",
            },
        )

    def test_patch_node_uses_unqualified_vertex_fields(self):
        req = NodePatchRequest(set={"description": "new desc"}, expected_version=2, updated_by="tester")
        before = {
            "vid": 1,
            "entity_name": "n",
            "entity_type": "disease",
            "source": "old source",
            "description": "old desc",
            "entity_raw_id": "MONDO:1",
            "version": 2,
            "updated_at": 1,
            "updated_by": "old",
        }
        after = dict(before)
        after.update({"description": "new desc", "version": 3, "updated_at": 100, "updated_by": "tester"})

        with (
            mock.patch("app.services.edit_service._node_snapshot", side_effect=[before, after]),
            mock.patch("app.services.edit_service.execute_ngql_safe") as execute_mock,
            mock.patch("app.services.edit_service.validate_updated_by", return_value="tester"),
            mock.patch("app.services.edit_service._audit"),
            mock.patch("app.services.edit_service.time.time", return_value=100),
        ):
            resp = edit_service.patch_node(1, req)

        update_ngql = execute_mock.call_args[0][0]
        self.assertIn("UPDATE VERTEX ON `Entity` 1", update_ngql)
        self.assertIn('`description` = "new desc"', update_ngql)
        self.assertIn("`version` = 3", update_ngql)
        self.assertIn("`updated_at` = 100", update_ngql)
        self.assertIn('`updated_by` = "tester"', update_ngql)
        self.assertNotIn("`Entity`.`description`", update_ngql)
        self.assertNotIn("YIELD properties(vertex)", update_ngql)
        self.assertEqual(resp["version"], 3)
        self.assertEqual(resp["updated"]["description"], "new desc")

    def test_patch_node_returns_409_on_version_conflict(self):
        req = NodePatchRequest(set={"description": "new desc"}, expected_version=2, updated_by="tester")
        before = {
            "vid": 1,
            "entity_name": "n",
            "entity_type": "disease",
            "source": "src",
            "description": "old desc",
            "entity_raw_id": "MONDO:1",
            "version": 3,
            "updated_at": 1,
            "updated_by": "old",
        }

        with (
            mock.patch("app.services.edit_service._node_snapshot", return_value=before),
            mock.patch("app.services.edit_service.validate_updated_by", return_value="tester"),
            mock.patch("app.services.edit_service._audit"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                edit_service.patch_node(1, req)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.detail["error_code"], "VERSION_CONFLICT")

    def test_patch_node_returns_422_on_invalid_field(self):
        req = NodePatchRequest(set={"bad_field": "x"}, expected_version=0, updated_by="tester")

        with (
            mock.patch("app.services.edit_service.validate_updated_by", return_value="tester"),
            mock.patch("app.services.edit_service._audit"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                edit_service.patch_node(1, req)

        self.assertEqual(ctx.exception.status_code, 422)

    def test_patch_edge_uses_unqualified_fields_and_no_yield(self):
        req = EdgePatchRequest(
            src=1,
            dst=2,
            rank="0",
            set={"relation": "associate|codex"},
            expected_version=2,
            updated_by="tester",
        )
        before = {
            "src": 1,
            "dst": 2,
            "rank": "0",
            "relation": "associate",
            "source": "PubTator",
            "evidence": "",
            "version": 2,
            "updated_at": 1,
            "updated_by": "old",
            "edge_type": "REL2",
        }
        after = dict(before)
        after.update({"relation": "associate|codex", "version": 3, "updated_at": 100, "updated_by": "tester"})

        with (
            mock.patch("app.services.edit_service._edge_snapshot", side_effect=[before, after]),
            mock.patch("app.services.edit_service.execute_ngql_safe") as execute_mock,
            mock.patch("app.services.edit_service.validate_updated_by", return_value="tester"),
            mock.patch("app.services.edit_service._audit"),
            mock.patch("app.services.edit_service.time.time", return_value=100),
            mock.patch("app.services.edit_service.metadata_service.sync_relation_type_change"),
        ):
            resp = edit_service.patch_edge(req)

        update_ngql = execute_mock.call_args[0][0]
        self.assertIn("UPDATE EDGE ON `REL2` 1->2@0", update_ngql)
        self.assertIn('`relation` = "associate|codex"', update_ngql)
        self.assertIn("`version` = 3", update_ngql)
        self.assertNotIn("YIELD properties(edge)", update_ngql)
        self.assertEqual(resp["version"], 3)
        self.assertEqual(resp["updated"]["relation"], "associate|codex")


if __name__ == "__main__":
    unittest.main()
