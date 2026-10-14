import unittest

from scripts.backfill_history import metadata_item
from tests.test_publish import _metadata, _manifest_item


class BackfillHistoryTests(unittest.TestCase):
    def test_reconstructed_item_matches_publisher_contract(self):
        metadata = _metadata("run-1", "sunny").with_outputs(image_s3_key="run-1.svg")
        actual = metadata_item(metadata.to_dict(), "run-1.json", "https://example.test")
        self.assertEqual(actual, _manifest_item("run-1").to_dict())

    def test_missing_image_fails_instead_of_publishing_broken_record(self):
        with self.assertRaises(KeyError):
            metadata_item(_metadata("run-1", "sunny").to_dict(), "run-1.json", "https://example.test")
