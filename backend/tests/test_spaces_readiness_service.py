import unittest

from app.services.spaces import readiness_service
from app.services.spaces.models import SpaceIndexStatus, SpaceSummary


class SpacesReadinessServiceTest(unittest.TestCase):
    def _summary(self, *, index_status: SpaceIndexStatus | None = None, status: str = "ready", internal_status: str = "ready"):
        return SpaceSummary(
            space_name="space_a",
            display_name="Space A",
            description="",
            template_type="entity_rel2_default",
            template_version="entity_rel2_default.v1",
            integration_scope="entity_rel2_core",
            status=status,
            internal_status=internal_status,
            created_by="tester",
            created_at="2026-03-13T00:00:00Z",
            ready_at="2026-03-13T00:00:01Z",
            index_status=index_status,
        )

    def test_ready_space_without_index_snapshot_is_search_unavailable(self):
        readiness = readiness_service.derive_readiness(self._summary(index_status=None))

        self.assertEqual(readiness.graph_status, "ready")
        self.assertEqual(readiness.search_status, "unavailable")

    def test_verified_empty_maps_to_empty(self):
        readiness = readiness_service.derive_readiness(
            self._summary(index_status=SpaceIndexStatus(status="verified_empty", doc_count=0, coverage_pct=100.0))
        )

        self.assertEqual(readiness.search_status, "empty")

    def test_verified_partial_maps_to_partial(self):
        readiness = readiness_service.derive_readiness(
            self._summary(index_status=SpaceIndexStatus(status="verified_partial", doc_count=10, coverage_pct=12.5))
        )

        self.assertEqual(readiness.search_status, "partial")

    def test_verified_nonempty_maps_to_full(self):
        readiness = readiness_service.derive_readiness(
            self._summary(index_status=SpaceIndexStatus(status="verified_nonempty", doc_count=10, coverage_pct=100.0))
        )

        self.assertEqual(readiness.search_status, "full")

    def test_failed_index_maps_to_failed(self):
        readiness = readiness_service.derive_readiness(
            self._summary(index_status=SpaceIndexStatus(status="failed", doc_count=10, coverage_pct=10.0))
        )

        self.assertEqual(readiness.search_status, "failed")

    def test_non_ready_space_is_graph_and_search_unavailable(self):
        readiness = readiness_service.derive_readiness(
            self._summary(
                status="provisioning",
                internal_status="waiting_ready",
                index_status=SpaceIndexStatus(status="verified_nonempty", doc_count=10, coverage_pct=100.0),
            )
        )

        self.assertEqual(readiness.graph_status, "unavailable")
        self.assertEqual(readiness.search_status, "unavailable")


if __name__ == "__main__":
    unittest.main()
