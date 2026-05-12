from pathlib import Path
import tempfile
import unittest

from road_damage_kz.privacy import (
    Detection,
    apply_privacy_report_to_triage,
    detections_from_json,
    export_privacy_safe_cache,
    scan_privacy,
)


class FakeDetector:
    def detect(self, image_path):
        if image_path.name == "face.jpg":
            return [Detection("face", 1, 2, 30, 40, 0.9)]
        return []


class PrivacyTests(unittest.TestCase):
    def test_scan_privacy_writes_clear_and_needs_blur_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clear = root / "clear.jpg"
            face = root / "face.jpg"
            clear.write_bytes(b"clear")
            face.write_bytes(b"face")
            cache = root / "local_files.csv"
            report = root / "privacy.csv"
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                f"clear,https://example.com/clear,,{clear},abc,5,downloaded,\n"
                f"face,https://example.com/face,,{face},def,4,downloaded,\n",
                encoding="utf-8",
            )

            summary = scan_privacy(cache, report, detector=FakeDetector())

            self.assertEqual(summary["scanned"], 2)
            self.assertEqual(summary["clear"], 1)
            self.assertEqual(summary["needs_blur"], 1)
            text = report.read_text(encoding="utf-8")
            self.assertIn("clear,", text)
            self.assertIn("needs_blur,1,0,1,true", text)
            self.assertEqual(detections_from_json('[{"kind":"face","x":1,"y":2,"width":3,"height":4}]')[0].kind, "face")

    def test_apply_privacy_report_updates_triage_conservatively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            triage = root / "triage.csv"
            report = root / "privacy.csv"
            blur_manifest = root / "blurred.csv"
            output = root / "triage_out.csv"
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "clear,https://example.com/clear,,CC-BY-4.0,A,ctx,normal,true,false,true,true,false,,,,\n"
                "blurred,https://example.com/blurred,,CC-BY-4.0,A,ctx,normal,true,false,true,true,false,,,,\n"
                "sensitive,https://example.com/sensitive,,CC-BY-4.0,A,ctx,unknown,true,false,true,true,false,,,,\n",
                encoding="utf-8",
            )
            report.write_text(
                "image_id,local_path,source_url,status,face_count,plate_candidate_count,total_regions,"
                "blur_required,detections_json,notes\n"
                "clear,clear.jpg,https://example.com/clear,clear,0,0,0,false,[],clear\n"
                "blurred,blurred.jpg,https://example.com/blurred,needs_blur,1,0,1,true,[],needs blur\n"
                "sensitive,sensitive.jpg,https://example.com/sensitive,needs_blur,1,0,1,true,[],needs blur\n",
                encoding="utf-8",
            )
            blur_manifest.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "blurred,https://example.com/blurred,,blurred.jpg,abc,1,blurred,\n",
                encoding="utf-8",
            )

            summary = apply_privacy_report_to_triage(
                triage,
                report,
                output,
                blurred_manifest=blur_manifest,
                trust_clear=True,
            )

            self.assertEqual(summary["updated"], 3)
            text = output.read_text(encoding="utf-8")
            self.assertIn("clear,https://example.com/clear,,CC-BY-4.0,A,ctx,normal,true,true,true,true,false,true,,privacy_scan_v1", text)
            self.assertIn("blurred,https://example.com/blurred,,CC-BY-4.0,A,ctx,normal,true,true,true,true,false,true,,privacy_scan_v1", text)
            self.assertIn("sensitive,https://example.com/sensitive,,CC-BY-4.0,A,ctx,unknown,true,false,true,true,false,false,needs_review,privacy_scan_v1", text)

    def test_export_privacy_safe_cache_replaces_blurred_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "local_files.csv"
            blurred = root / "blurred.csv"
            output = root / "safe.csv"
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "a,https://example.com/a,,raw_a.jpg,raw,10,downloaded,\n"
                "b,https://example.com/b,,raw_b.jpg,raw,10,downloaded,\n",
                encoding="utf-8",
            )
            blurred.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "a,https://example.com/a,,blurred_a.jpg,blur,12,blurred,\n",
                encoding="utf-8",
            )

            summary = export_privacy_safe_cache(cache, blurred, output)

            self.assertEqual(summary["replaced"], 1)
            text = output.read_text(encoding="utf-8")
            self.assertIn("a,https://example.com/a,,blurred_a.jpg,blur,12,blurred,", text)
            self.assertIn("b,https://example.com/b,,raw_b.jpg,raw,10,downloaded,", text)

    def test_export_privacy_safe_cache_merges_extra_cache_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / "local_files.csv"
            extra = root / "mapillary_files.csv"
            blurred = root / "blurred.csv"
            output = root / "safe.csv"
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "a,https://example.com/a,,raw_a.jpg,raw,10,downloaded,\n",
                encoding="utf-8",
            )
            extra.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "m,https://example.com/m,,raw_m.jpg,rawm,20,downloaded,\n",
                encoding="utf-8",
            )
            blurred.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n",
                encoding="utf-8",
            )

            summary = export_privacy_safe_cache(cache, blurred, output, extra_cache_manifests=[extra])

            self.assertEqual(summary["rows"], 2)
            text = output.read_text(encoding="utf-8")
            self.assertIn("a,https://example.com/a,,raw_a.jpg,raw,10,downloaded,", text)
            self.assertIn("m,https://example.com/m,,raw_m.jpg,rawm,20,downloaded,", text)


if __name__ == "__main__":
    unittest.main()
