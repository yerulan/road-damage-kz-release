from pathlib import Path
import tempfile
import unittest

from road_damage_kz.auto_triage import auto_triage_scores


class AutoTriageTests(unittest.TestCase):
    def test_auto_triage_excludes_non_road_and_marks_review_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scores = root / "scores.csv"
            triage = root / "triage.csv"
            output = root / "triage_out.csv"
            scores.write_text(
                "image_id,local_path,source_url,road_surface_score,damage_score,normal_road_score,"
                "non_road_score,privacy_context_score,review_priority,suggested_action,model,notes\n"
                "nonroad,a.jpg,https://example.com/a,0.10,0.01,0.02,0.70,0.01,-0.60,review_exclude,clip,\n"
                "damage,b.jpg,https://example.com/b,0.45,0.30,0.10,0.05,0.03,0.72,review_damage_first,clip,\n"
                "normal,c.jpg,https://example.com/c,0.40,0.02,0.70,0.03,0.02,0.37,review_normal_candidate,clip,\n"
                "privacy,d.jpg,https://example.com/d,0.35,0.05,0.20,0.05,0.60,0.25,review_privacy,clip,\n",
                encoding="utf-8",
            )
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "nonroad,https://example.com/a,,CC-BY-4.0,A,ctx,unknown,true,false,true,,,,,,\n"
                "damage,https://example.com/b,,CC-BY-4.0,A,ctx,unknown,true,false,true,,,,,,\n"
                "normal,https://example.com/c,,CC-BY-4.0,A,ctx,unknown,true,false,true,,,,,,\n"
                "privacy,https://example.com/d,,CC-BY-4.0,A,ctx,unknown,true,false,true,,,,,,\n",
                encoding="utf-8",
            )

            summary = auto_triage_scores(scores, triage, output)

            self.assertEqual(summary["updated"], 4)
            self.assertEqual(summary["auto_exclude"], 1)
            self.assertEqual(summary["needs_review"], 3)
            text = output.read_text(encoding="utf-8")
            self.assertIn("nonroad,https://example.com/a,,CC-BY-4.0,A,ctx,unknown,true,false,true,false,false,false,exclude,auto_triage_v1", text)
            self.assertIn("damage,https://example.com/b,,CC-BY-4.0,A,ctx,unknown,true,false,true,true,true,,needs_review,auto_triage_v1", text)
            self.assertIn("normal,https://example.com/c,,CC-BY-4.0,A,ctx,normal,true,false,true,true,false,,needs_review,auto_triage_v1", text)
            self.assertIn("privacy,https://example.com/d,,CC-BY-4.0,A,ctx,unknown,true,false,true,true,false,false,needs_review,auto_triage_v1", text)

    def test_dry_run_does_not_write_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scores = root / "scores.csv"
            triage = root / "triage.csv"
            output = root / "triage_out.csv"
            scores.write_text(
                "image_id,local_path,source_url,road_surface_score,damage_score,normal_road_score,"
                "non_road_score,privacy_context_score,review_priority,suggested_action,model,notes\n"
                "nonroad,a.jpg,https://example.com/a,0.10,0.01,0.02,0.70,0.01,-0.60,review_exclude,clip,\n",
                encoding="utf-8",
            )
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "nonroad,https://example.com/a,,CC-BY-4.0,A,ctx,unknown,true,false,true,,,,,,\n",
                encoding="utf-8",
            )

            summary = auto_triage_scores(scores, triage, output, dry_run=True)

            self.assertEqual(summary["updated"], 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
