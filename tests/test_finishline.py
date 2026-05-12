from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from road_damage_kz.finishline import project_status, publication_strategy_summary, validate_yolo_annotation_export


class FinishLineTests(unittest.TestCase):
    def test_validate_yolo_annotation_export_accepts_prepared_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annotations = root / "annotations.csv"
            labels = root / "yolo" / "labels" / "kz-test"
            labels.mkdir(parents=True)
            annotations.write_text(
                "image_id,class_name,x_min,y_min,x_max,y_max,annotator,review_status,notes\n"
                "kz1,pothole,1,2,3,4,test,gold,\n",
                encoding="utf-8",
            )
            (root / "yolo" / "images" / "kz-test").mkdir(parents=True)
            (labels / "kz1.txt").write_text("3 0.5 0.5 0.2 0.2\n", encoding="utf-8")

            summary = validate_yolo_annotation_export(annotations, root / "yolo")

            self.assertEqual(summary["errors"], 0)
            self.assertEqual(summary["checked"], 1)

    def test_project_status_uses_yolo_export_when_raw_cache_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "images.csv"
            annotations = root / "annotations.csv"
            cache = root / "privacy_safe_files.csv"
            experiments = root / "experiments.csv"
            paper = root / "paper"
            reports = root / "reports"
            yolo = root / "data" / "processed" / "yolo"
            (paper / "Definitions").mkdir(parents=True)
            reports.mkdir()
            (yolo / "images" / "kz-test").mkdir(parents=True)
            (yolo / "labels" / "kz-test").mkdir(parents=True)
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "kz1,https://example.com,https://example.com/a.jpg,CC-BY-4.0,Author,Kazakhstan,,,"
                "road,pothole,kz-test,true,true,\n",
                encoding="utf-8",
            )
            annotations.write_text(
                "image_id,class_name,x_min,y_min,x_max,y_max,annotator,review_status,notes\n"
                "kz1,pothole,1,2,3,4,test,gold,\n",
                encoding="utf-8",
            )
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "kz1,https://example.com,https://example.com/a.jpg,missing.jpg,abc,10,downloaded,\n",
                encoding="utf-8",
            )
            experiments.write_text(
                "experiment_id,phase,training_dataset,evaluation_dataset,model,dataset_config,"
                "eval_split,weights,epochs,imgsz,precision,recall,map50,map50_95,paper_eligible,"
                "source_run_dir,notes\n"
                "exp1,eval,RDD2022,Kazakhstan gold set,yolov8n.pt,configs/dataset.yaml,kz-test,"
                "best.pt,,640,0,0,0,0,true,runs/detect/eval,test\n",
                encoding="utf-8",
            )
            (yolo / "labels" / "kz-test" / "kz1.txt").write_text("3 0.5 0.5 0.2 0.2\n", encoding="utf-8")

            with patch(
                "road_damage_kz.finishline.check_rdd_readiness",
                return_value={
                    "status": "ready",
                    "xml_files": 1,
                    "matched_images": 1,
                    "usable_images": 1,
                    "boxes": 1,
                    "class_distribution": {},
                    "messages": [],
                },
            ):
                status = project_status(
                    manifest_path=manifest,
                    annotations_path=annotations,
                    cache_manifest_path=cache,
                    experiments_path=experiments,
                    rdd_root=root / "RDD2022",
                    paper_dir=paper,
                    reports_dir=reports,
                    yolo_dir=yolo,
                )

            self.assertNotIn("Annotation validation has errors.", status["blockers"])
            self.assertEqual(status["annotations"]["readiness_source"], "prepared_yolo_export")
            self.assertEqual(status["publication_strategy"]["primary_target"], "MDPI Applied Sciences Article")

    def test_publication_strategy_flags_small_zero_metric_benchmark(self):
        annotations = [
            {
                "image_id": "kz1",
                "class_name": "pothole",
                "x_min": "1",
                "y_min": "2",
                "x_max": "3",
                "y_max": "4",
                "annotator": "test",
                "review_status": "gold",
                "notes": "",
            }
        ]
        kz_eval_rows = [
            {
                "precision": "0.0",
                "recall": "0.0",
                "map50": "0.0",
                "map50_95": "0.0",
            }
        ]

        summary = publication_strategy_summary(
            publishable_rows=31,
            damaged_rows=6,
            annotations=annotations,
            kz_eval_rows=kz_eval_rows,
        )

        self.assertFalse(summary["ready_for_applied_sciences_full_article"])
        self.assertFalse(summary["ready_for_data_journal"])
        self.assertTrue(summary["current"]["kazakhstan_eval_all_zero"])
        self.assertEqual(
            summary["recommended_positioning"],
            "Kazakhstan road-damage benchmark with Ghost-CA-YOLO adaptation and external validation",
        )


if __name__ == "__main__":
    unittest.main()
