from pathlib import Path
import tempfile
import unittest

from road_damage_kz.scoring import score_candidates, suggested_action


class ScoringTests(unittest.TestCase):
    def test_suggested_action_prioritizes_damage(self):
        action = suggested_action(
            road=0.55,
            damage=0.35,
            normal=0.10,
            non_road=0.05,
            privacy=0.05,
        )

        self.assertEqual(action, "review_damage_first")

    def test_keyword_scoring_writes_ranked_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "cracked_road.jpg"
            image.write_bytes(b"fake image bytes")
            cache = root / "local_files.csv"
            output = root / "scores.csv"
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                f"commons_1,https://example.com/crack-road,https://example.com/crack-road.jpg,"
                f"{image},abc,4,downloaded,\n",
                encoding="utf-8",
            )

            summary = score_candidates(cache, output, backend="keyword")

            self.assertEqual(summary["scored"], 1)
            text = output.read_text(encoding="utf-8")
            self.assertIn("review_damage_first", text)


if __name__ == "__main__":
    unittest.main()
