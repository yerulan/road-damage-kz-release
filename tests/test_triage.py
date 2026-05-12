from pathlib import Path
import tempfile
import unittest

from road_damage_kz.triage import apply_triage, generate_gallery, promotion_blocker


class TriageTests(unittest.TestCase):
    def test_promotion_blocker_requires_damage_label_when_damage_visible(self):
        manifest = {"license_ok": "true"}
        triage = {
            "is_photo_candidate": "true",
            "road_surface_visible": "true",
            "privacy_ok": "true",
            "target_damage_visible": "true",
            "damage_labels": "unknown",
        }

        self.assertIn("damage_labels", promotion_blocker(manifest, triage))

    def test_apply_triage_promotes_clean_normal_row(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "images.csv"
            triage = root / "triage.csv"
            output = root / "images_out.csv"
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "commons_1,https://example.com/file,https://example.com/file.jpg,CC-BY-4.0,"
                "Author,Kazakhstan,,,commons,unknown,,true,false,\n",
                encoding="utf-8",
            )
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "commons_1,https://example.com/file,https://example.com/file.jpg,CC-BY-4.0,"
                "Author,commons,unknown,true,false,true,true,false,true,include,tester,clear road\n",
                encoding="utf-8",
            )

            report = apply_triage(manifest, triage, output)

            self.assertEqual(report["promoted"], 1)
            text = output.read_text(encoding="utf-8")
            self.assertIn("normal", text)
            self.assertIn("true", text)

    def test_generate_gallery_writes_candidate_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            triage = root / "triage.csv"
            output = root / "gallery.html"
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "commons_1,https://example.com/file,https://example.com/file.jpg,CC-BY-4.0,"
                "Author,commons,unknown,true,false,true,,,,,,\n",
                encoding="utf-8",
            )

            summary = generate_gallery(triage, output)

            self.assertEqual(summary["rows"], 1)
            self.assertIn("Road Damage KZ Triage Gallery", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
