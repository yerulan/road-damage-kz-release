import unittest

from road_damage_kz.commons import (
    append_rows,
    canonical_license,
    clean_download_url,
    collect_commons_search,
    commons_file_url,
    is_likely_non_photo,
    manifest_row_from_page,
)
from unittest.mock import patch


class CommonsTests(unittest.TestCase):
    def test_canonical_license_normalizes_commons_label(self):
        self.assertEqual(canonical_license("CC BY-SA 4.0"), "CC-BY-SA-4.0")
        self.assertEqual(canonical_license("Public domain"), "PDM")

    def test_file_url_quotes_file_title(self):
        url = commons_file_url("File:P-11 Road in Kazakhstan.jpg")
        self.assertEqual(url, "https://commons.wikimedia.org/wiki/File:P-11_Road_in_Kazakhstan.jpg")

    def test_download_url_drops_tracking_query(self):
        url = clean_download_url("https://upload.wikimedia.org/file.jpg?utm_source=commons")
        self.assertEqual(url, "https://upload.wikimedia.org/file.jpg")

    def test_manifest_row_from_page_marks_privacy_unchecked(self):
        page = {
            "pageid": 123,
            "title": "File:P-11 Road in Kazakhstan.jpg",
            "imageinfo": [
                {
                    "url": "https://upload.wikimedia.org/example.jpg",
                    "mime": "image/jpeg",
                    "extmetadata": {
                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "Artist": {"value": "<span>Chris</span>"},
                    },
                }
            ],
        }

        row = manifest_row_from_page(page, "Category:Roads in Kazakhstan")

        self.assertIsNotNone(row)
        self.assertEqual(row["image_id"], "commons_123")
        self.assertEqual(row["license"], "CC-BY-SA-4.0")
        self.assertEqual(row["author"], "Chris")
        self.assertEqual(row["license_ok"], "true")
        self.assertEqual(row["privacy_checked"], "false")

    def test_non_photo_assets_are_flagged(self):
        self.assertTrue(is_likely_non_photo("File:A1 kazakistan ita.png", "image/png"))
        self.assertFalse(is_likely_non_photo("File:P-11 Road in Kazakhstan.jpg", "image/jpeg"))

    def test_collect_commons_search_fetches_imageinfo(self):
        search_payload = {
            "query": {
                "search": [
                    {"title": "File:Cracked road Kazakhstan.jpg"},
                ]
            }
        }
        info_payload = {
            "query": {
                "pages": {
                    "1": {
                        "pageid": 1,
                        "title": "File:Cracked road Kazakhstan.jpg",
                        "imageinfo": [
                            {
                                "url": "https://upload.wikimedia.org/example.jpg",
                                "mime": "image/jpeg",
                                "extmetadata": {
                                    "LicenseShortName": {"value": "CC BY 4.0"},
                                    "Artist": {"value": "Author"},
                                },
                            }
                        ],
                    }
                }
            }
        }

        with patch("road_damage_kz.commons._api_get", side_effect=[search_payload, info_payload]):
            rows = collect_commons_search("Kazakhstan cracked road", limit=5)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["image_id"], "commons_1")
        self.assertIn("Search:Kazakhstan cracked road", rows[0]["notes"])

    def test_append_rows_updates_unreviewed_candidate(self):
        existing = [
            {
                "image_id": "commons_1",
                "source_url": "https://example.com/file",
                "download_url": "https://example.com/file.jpg?utm_source=old",
                "license": "CC-BY-4.0",
                "author": "Author",
                "country": "Kazakhstan",
                "region": "",
                "city": "",
                "capture_context": "old",
                "damage_labels": "unknown",
                "split": "",
                "license_ok": "true",
                "privacy_checked": "false",
                "notes": "old",
            }
        ]
        incoming = [dict(existing[0], download_url="https://example.com/file.jpg", notes="new")]

        with self.subTest("updates existing row"):
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as directory:
                added, updated = append_rows(Path(directory) / "images.csv", existing, incoming)

        self.assertEqual(added, 0)
        self.assertEqual(updated, 1)


if __name__ == "__main__":
    unittest.main()
