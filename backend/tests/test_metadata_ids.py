import unittest

from app.services.metadata_ids import (
    ENTITY_TYPE_META_VID_BASE,
    RELATION_TYPE_META_VID_BASE,
    metadata_stat_vid,
)


class MetadataVidTest(unittest.TestCase):
    def test_stable_vid_for_same_key(self):
        a = metadata_stat_vid("entity_type", "gene")
        b = metadata_stat_vid("entity_type", "gene")
        self.assertEqual(a, b)

    def test_entity_and_relation_are_isolated(self):
        entity_vid = metadata_stat_vid("entity_type", "interacts_with")
        relation_vid = metadata_stat_vid("relation_type", "interacts_with")
        self.assertNotEqual(entity_vid, relation_vid)
        self.assertLess(entity_vid, 0)
        self.assertLess(relation_vid, 0)

    def test_vid_in_reserved_negative_range(self):
        vid = metadata_stat_vid("entity_type", "disease")
        self.assertGreaterEqual(vid, ENTITY_TYPE_META_VID_BASE)
        self.assertLess(vid, 0)
        vid2 = metadata_stat_vid("relation_type", "treats")
        self.assertGreaterEqual(vid2, RELATION_TYPE_META_VID_BASE)
        self.assertLess(vid2, 0)


if __name__ == "__main__":
    unittest.main()
