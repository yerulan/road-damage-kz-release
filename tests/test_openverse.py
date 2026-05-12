import unittest
from unittest.mock import patch

from road_damage_kz.openverse import (
    canonical_openverse_license,
    collect_openverse_search,
    manifest_row_from_openverse_result,
)


class OpenverseTests(unittest.TestCase):
    def test_canonical_openverse_license_normalizes_cc_fields(self):
        self.assertEqual(canonical_openverse_license("by-sa", "4.0"), "CC-BY-SA-4.0")
        self.assertEqual(canonical_openverse_license("cc0", "1.0"), "CC0-1.0")
        self.assertEqual(canonical_openverse_license("pdm", ""), "PDM")

    def test_manifest_row_is_unverified_by_default(self):
        row = manifest_row_from_openverse_result(
            {
                "id": "abc",
                "title": "Cracked road in Kazakhstan",
                "url": "https://images.example/road.jpg",
                "foreign_landing_url": "https://source.example/road",
                "license": "by",
                "license_version": "4.0",
                "creator": "Author",
                "source": "flickr",
            },
            query="Kazakhstan cracked road",
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["license"], "CC-BY-4.0")
        self.assertEqual(row["license_ok"], "false")
        self.assertEqual(row["privacy_checked"], "false")
        self.assertIn("Openverse license metadata must be verified", row["notes"])

    def test_manifest_row_can_trust_openverse_license_explicitly(self):
        row = manifest_row_from_openverse_result(
            {
                "id": "abc",
                "url": "https://images.example/road.jpg",
                "foreign_landing_url": "https://source.example/road",
                "license": "by-sa",
                "license_version": "4.0",
                "creator": "Author",
                "source": "wikimedia",
            },
            query="Kazakhstan road damage",
            trust_openverse_license=True,
        )

        self.assertEqual(row["license_ok"], "true")

    def test_collect_openverse_search_paginates_results(self):
        first_payload = {
            "next": "https://api.example/page=2",
            "results": [
                {
                    "id": "one",
                    "url": "https://images.example/one.jpg",
                    "foreign_landing_url": "https://source.example/one",
                    "license": "by",
                    "license_version": "4.0",
                    "creator": "Author",
                    "source": "flickr",
                }
            ],
        }
        second_payload = {
            "next": None,
            "results": [
                {
                    "id": "two",
                    "url": "https://images.example/two.jpg",
                    "foreign_landing_url": "https://source.example/two",
                    "license": "by",
                    "license_version": "4.0",
                    "creator": "Author",
                    "source": "flickr",
                }
            ],
        }

        with patch("road_damage_kz.openverse._api_get", side_effect=[first_payload, second_payload]):
            rows = collect_openverse_search("Kazakhstan pothole", limit=2)

        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["image_id"].startswith("openverse_"))


if __name__ == "__main__":
    unittest.main()
