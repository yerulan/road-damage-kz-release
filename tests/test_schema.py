import unittest

from road_damage_kz.schema import audit_image_row, is_open_license


class SchemaTests(unittest.TestCase):
    def test_open_license_labels_are_accepted(self):
        self.assertTrue(is_open_license("CC-BY-4.0"))
        self.assertTrue(is_open_license("cc-by-sa-4.0"))
        self.assertTrue(is_open_license("CC-BY-SA-2.5"))
        self.assertTrue(is_open_license("explicit permission"))

    def test_audit_requires_license_and_privacy_flags(self):
        row = {
            "image_id": "kz_0001",
            "source_url": "https://commons.wikimedia.org/example",
            "download_url": "https://upload.wikimedia.org/example.jpg",
            "license": "CC-BY-4.0",
            "author": "Example Author",
            "country": "Kazakhstan",
            "region": "Almaty",
            "city": "Almaty",
            "capture_context": "street",
            "damage_labels": "pothole",
            "split": "kz-test",
            "license_ok": "true",
            "privacy_checked": "false",
            "notes": "",
        }

        findings = audit_image_row(row)

        self.assertTrue(any(finding.field == "privacy_checked" for finding in findings))

    def test_audit_accepts_publishable_row(self):
        row = {
            "image_id": "kz_0001",
            "source_url": "https://commons.wikimedia.org/example",
            "download_url": "https://upload.wikimedia.org/example.jpg",
            "license": "CC-BY-4.0",
            "author": "Example Author",
            "country": "Kazakhstan",
            "region": "Almaty",
            "city": "Almaty",
            "capture_context": "street",
            "damage_labels": "pothole",
            "split": "kz-test",
            "license_ok": "true",
            "privacy_checked": "true",
            "notes": "",
        }

        self.assertEqual(audit_image_row(row), [])


if __name__ == "__main__":
    unittest.main()
