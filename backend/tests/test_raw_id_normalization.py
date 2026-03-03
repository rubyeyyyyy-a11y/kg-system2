import unittest

from app.services.common import normalize_raw_id


class RawIdNormalizationTest(unittest.TestCase):
    def test_full_width_colon_and_missing_colon_are_equivalent(self):
        a = normalize_raw_id("MONDO：0005148")
        b = normalize_raw_id("MONDO0005148")
        self.assertEqual(a, b)
        self.assertEqual(a, "mondo0005148")

    def test_full_width_digits(self):
        self.assertEqual(normalize_raw_id("１２３４"), "1234")


if __name__ == "__main__":
    unittest.main()
