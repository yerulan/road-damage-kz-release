from pathlib import Path
import base64
import tempfile
import unittest

from road_damage_kz.dataset import (
    assign_dataset_splits,
    export_annotation_queue,
    export_classification_dataset,
    prepare_yolo_dataset,
    validate_box_annotations,
)
from road_damage_kz.annotations import draft_annotations


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lRx7"
    "vQAAAABJRU5ErkJggg=="
)


class DatasetTests(unittest.TestCase):
    def test_export_classification_dataset_copies_publishable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "source.jpg"
            image.write_bytes(b"image")
            manifest = root / "images.csv"
            cache = root / "local_files.csv"
            output = root / "classification"
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "commons_1,https://example.com,https://example.com/1.jpg,CC-BY-4.0,"
                "Author,Kazakhstan,,,commons,normal,,true,true,\n",
                encoding="utf-8",
            )
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                f"commons_1,https://example.com,https://example.com/1.jpg,{image},abc,5,downloaded,\n",
                encoding="utf-8",
            )

            summary = export_classification_dataset(manifest, cache, output)

            self.assertEqual(summary["exported"], 1)
            self.assertTrue((output / "images" / "commons_1.jpg").exists())
            self.assertIn("normal", (output / "labels.csv").read_text(encoding="utf-8"))

    def test_export_annotation_queue_includes_only_damaged_publishable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "images.csv"
            cache = root / "local_files.csv"
            output = root / "annotation_queue.csv"
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "normal_1,https://example.com/n,,CC-BY-4.0,Author,Kazakhstan,,,commons,normal,,true,true,\n"
                "damage_1,https://example.com/d,,CC-BY-4.0,Author,Kazakhstan,,,commons,longitudinal_crack,,true,true,\n",
                encoding="utf-8",
            )
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "normal_1,https://example.com/n,,normal.jpg,abc,5,downloaded,\n"
                "damage_1,https://example.com/d,,damage.jpg,def,5,downloaded,\n",
                encoding="utf-8",
            )

            summary = export_annotation_queue(manifest, cache, output)

            self.assertEqual(summary["queued"], 1)
            text = output.read_text(encoding="utf-8")
            self.assertIn("damage_1", text)
            self.assertNotIn("normal_1", text)

    def test_prepare_yolo_dataset_writes_box_and_empty_normal_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            damage_image = root / "damage.png"
            normal_image = root / "normal.png"
            damage_image.write_bytes(PNG_1X1)
            normal_image.write_bytes(PNG_1X1)
            manifest = root / "images.csv"
            cache = root / "local_files.csv"
            annotations = root / "annotations.csv"
            output = root / "yolo"
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "damage_1,https://example.com/d,,CC-BY-4.0,Author,Kazakhstan,,,commons,longitudinal_crack,kz-test,true,true,\n"
                "normal_1,https://example.com/n,,CC-BY-4.0,Author,Kazakhstan,,,commons,normal,kz-test,true,true,\n",
                encoding="utf-8",
            )
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                f"damage_1,https://example.com/d,,{damage_image},abc,5,downloaded,\n"
                f"normal_1,https://example.com/n,,{normal_image},def,5,downloaded,\n",
                encoding="utf-8",
            )
            annotations.write_text(
                "image_id,class_name,x_min,y_min,x_max,y_max,annotator,review_status,notes\n"
                "damage_1,longitudinal_crack,0,0,1,1,tester,draft,\n",
                encoding="utf-8",
            )
            stale = output / "images" / "kz-test" / "stale.jpg"
            stale.parent.mkdir(parents=True, exist_ok=True)
            stale.write_bytes(b"stale")

            summary = prepare_yolo_dataset(manifest, cache, annotations, output)

            self.assertEqual(summary["copied_images"], 2)
            self.assertEqual(summary["skipped_missing_annotations"], 0)
            self.assertFalse(stale.exists())
            damage_label = output / "labels" / "kz-test" / "damage_1.txt"
            normal_label = output / "labels" / "kz-test" / "normal_1.txt"
            self.assertEqual(damage_label.read_text(encoding="utf-8"), "0 0.500000 0.500000 1.000000 1.000000\n")
            self.assertEqual(normal_label.read_text(encoding="utf-8"), "")

    def test_assign_dataset_splits_stratifies_publishable_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "images.csv"
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "d1,https://example.com/d1,,CC-BY-4.0,A,Kazakhstan,,,commons,longitudinal_crack,,true,true,\n"
                "d2,https://example.com/d2,,CC-BY-4.0,A,Kazakhstan,,,commons,transverse_crack,,true,true,\n"
                "d3,https://example.com/d3,,CC-BY-4.0,A,Kazakhstan,,,commons,longitudinal_crack,,true,true,\n"
                "n1,https://example.com/n1,,CC-BY-4.0,A,Kazakhstan,,,commons,normal,,true,true,\n"
                "n2,https://example.com/n2,,CC-BY-4.0,A,Kazakhstan,,,commons,normal,,true,true,\n"
                "n3,https://example.com/n3,,CC-BY-4.0,A,Kazakhstan,,,commons,normal,,true,true,\n",
                encoding="utf-8",
            )

            summary = assign_dataset_splits(manifest, manifest, seed=1)

            self.assertEqual(summary["assigned"], 6)
            text = manifest.read_text(encoding="utf-8")
            self.assertIn(",train,", text)
            self.assertIn(",val,", text)
            self.assertIn(",kz-test,", text)

    def test_validate_box_annotations_reports_bad_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.png"
            image.write_bytes(PNG_1X1)
            cache = root / "local_files.csv"
            annotations = root / "annotations.csv"
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                f"damage_1,https://example.com/d,,{image},abc,5,downloaded,\n",
                encoding="utf-8",
            )
            annotations.write_text(
                "image_id,class_name,x_min,y_min,x_max,y_max,annotator,review_status,notes\n"
                "damage_1,pothole,0,0,1,1,tester,draft,\n"
                "damage_1,normal,0,0,1,1,tester,draft,\n",
                encoding="utf-8",
            )

            summary = validate_box_annotations(annotations, cache)

            self.assertEqual(summary["checked"], 2)
            self.assertEqual(summary["errors"], 1)

    def test_draft_annotations_writes_weak_box_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "damage.png"
            from PIL import Image

            Image.new("RGB", (8, 8), color="white").save(image)
            queue = root / "annotation_queue.csv"
            output = root / "annotations.csv"
            previews = root / "previews"
            queue.write_text(
                "image_id,local_path,source_url,damage_labels,annotation_needed,notes\n"
                f"damage_1,{image},https://example.com/d,longitudinal_crack,true,\n",
                encoding="utf-8",
            )

            summary = draft_annotations(queue, output, preview_dir=previews, overwrite=True)

            self.assertEqual(summary["queued"], 1)
            self.assertEqual(summary["boxes_written"], 1)
            self.assertIn("draft_auto", output.read_text(encoding="utf-8"))
            self.assertTrue((previews / "damage_1.jpg").exists())


if __name__ == "__main__":
    unittest.main()
