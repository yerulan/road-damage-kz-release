from pathlib import Path
import tempfile
import unittest

from road_damage_kz.review import export_review_queue


class ReviewTests(unittest.TestCase):
    def test_review_queue_skips_reviewed_and_excluded_suggestions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scores = root / "scores.csv"
            triage = root / "triage.csv"
            output = root / "queue.csv"
            scores.write_text(
                "image_id,local_path,source_url,road_surface_score,damage_score,normal_road_score,"
                "non_road_score,privacy_context_score,review_priority,suggested_action,model,notes\n"
                "a,a.jpg,https://example.com/a,0.9,0.1,0.1,0.0,0.0,1.0,review_normal_candidate,clip,\n"
                "b,b.jpg,https://example.com/b,0.1,0.1,0.1,0.9,0.0,-0.8,review_exclude,clip,\n"
                "c,c.jpg,https://example.com/c,0.8,0.1,0.1,0.0,0.0,0.9,review_normal_candidate,clip,\n",
                encoding="utf-8",
            )
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "a,https://example.com/a,,CC-BY-4.0,A,ctx,unknown,true,false,true,,,,,,\n"
                "b,https://example.com/b,,CC-BY-4.0,A,ctx,unknown,true,false,true,,,,,,\n"
                "c,https://example.com/c,,CC-BY-4.0,A,ctx,normal,true,true,true,true,false,true,include,R,\n",
                encoding="utf-8",
            )

            summary = export_review_queue(scores, triage, output, exclude_suggested={"review_exclude"})

            self.assertEqual(summary["queued"], 1)
            text = output.read_text(encoding="utf-8")
            self.assertIn("a", text)
            self.assertNotIn("b.jpg", text)
            self.assertNotIn("c.jpg", text)


if __name__ == "__main__":
    unittest.main()
