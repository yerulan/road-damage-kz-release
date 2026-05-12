from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from road_damage_kz.cli import best_experiments_by_model_split, main


class CliTests(unittest.TestCase):
    def test_collect_creates_manifest_from_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            sources = tmp_path / "sources.csv"
            output = tmp_path / "images.csv"
            sources.write_text(
                "source_id,source_name,source_url,source_type,license_policy,notes\n"
                "commons,Commons,https://commons.wikimedia.org/wiki/Category:Roads_in_Kazakhstan,"
                "open-license-candidate,per-file-license-required,\n",
                encoding="utf-8",
            )

            exit_code = main(["collect", "--sources", str(sources), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("lead_commons", text)
            self.assertIn("Kazakhstan", text)

    def test_collect_mapillary_writes_manifest_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            output = tmp_path / "images.csv"
            report = tmp_path / "mapillary.json"
            rows = [
                {
                    "image_id": "mapillary_1",
                    "source_url": "https://www.mapillary.com/app/?pKey=1",
                    "download_url": "https://images.example/1.jpg",
                    "license": "CC-BY-SA-4.0",
                    "author": "user",
                    "country": "Kazakhstan",
                    "region": "",
                    "city": "almaty",
                    "capture_context": "mapillary;city:almaty",
                    "damage_labels": "unknown",
                    "split": "",
                    "license_ok": "true",
                    "privacy_checked": "false",
                    "notes": "test",
                }
            ]

            with patch("road_damage_kz.cli.collect_mapillary_bbox", return_value=rows):
                exit_code = main(
                    [
                        "collect-mapillary",
                        "--city",
                        "almaty",
                        "--access-token",
                        "token",
                        "--output",
                        str(output),
                        "--report",
                        str(report),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("mapillary_1", output.read_text(encoding="utf-8"))
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["collected"], 1)
            self.assertEqual(payload["license_ready"], 1)

    def test_download_candidates_accepts_image_id_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            triage = tmp_path / "triage.csv"
            cache = tmp_path / "local_files.csv"
            output_dir = tmp_path / "raw"
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,target_damage_visible,"
                "privacy_ok,recommended_action,reviewer,notes\n"
                "mapillary_1,https://example.com/1,https://example.com/1.jpg,CC-BY-SA-4.0,"
                "Author,mapillary,unknown,true,false,true,,,,,,\n"
                "commons_1,https://example.com/2,https://example.com/2.jpg,CC-BY-4.0,"
                "Author,commons,unknown,true,false,true,,,,,,\n",
                encoding="utf-8",
            )

            with patch(
                "road_damage_kz.cli.download_candidates",
                return_value={
                    "candidates": 1,
                    "downloaded": 1,
                    "skipped_existing": 0,
                    "skipped_failed_cache": 0,
                    "failed": 0,
                },
            ) as mocked:
                exit_code = main(
                    [
                        "download-candidates",
                        "--triage",
                        str(triage),
                        "--cache-manifest",
                        str(cache),
                        "--output-dir",
                        str(output_dir),
                        "--image-id-prefix",
                        "mapillary_",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(mocked.call_args.kwargs["image_id_prefix"], "mapillary_")

    def test_train_dry_run_prints_command(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                ["train", "--config", "configs/dataset.yaml", "--model", "yolov8n.pt", "--dry-run"]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("yolo detect train", stdout.getvalue())

    def test_import_rdd_voc_calls_importer(self):
        stdout = io.StringIO()
        with patch(
            "road_damage_kz.cli.import_rdd_voc_dataset",
            return_value={"discovered": 1, "imported": 1, "boxes": 2, "skipped_empty": 0},
        ) as mocked:
            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "import-rdd-voc",
                        "--rdd-root",
                        "data/external/RDD2022",
                        "--output-dir",
                        "data/processed/rdd_yolo",
                    ]
                )

        self.assertEqual(exit_code, 0)
        mocked.assert_called_once()
        self.assertIn("RDD import complete", stdout.getvalue())

    def test_check_rdd_writes_readiness_report(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            report = tmp_path / "rdd.json"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["check-rdd", "--rdd-root", str(tmp_path), "--report", str(report)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(report.exists())
            self.assertIn("no_xml", report.read_text(encoding="utf-8"))
            self.assertIn("RDD readiness", stdout.getvalue())

    def test_rdd_download_plan_writes_script(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            script = tmp_path / "download.sh"

            exit_code = main(
                [
                    "rdd-download-plan",
                    "--country",
                    "india",
                    "--script",
                    str(script),
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("RDD2022_India.zip", script.read_text(encoding="utf-8"))

    def test_run_baseline_dry_run_prints_commands(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "run-baseline",
                    "--model",
                    "yolov8n.pt",
                    "--epochs",
                    "1",
                    "--imgsz",
                    "320",
                    "--batch",
                    "8",
                    "--workers",
                    "0",
                    "--fraction",
                    "0.1",
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 0)
        text = stdout.getvalue()
        self.assertIn("Baseline dry run", text)
        self.assertIn("check-rdd", text)
        self.assertIn("yolo detect train", text)
        self.assertIn("batch=8", text)
        self.assertIn("fraction=0.1", text)
        self.assertIn("record-experiment", text)

    def test_evaluate_maps_kz_test_to_ultralytics_test_split(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exit_code = main(
                [
                    "evaluate",
                    "--config",
                    "configs/dataset.yaml",
                    "--model",
                    "best.pt",
                    "--split",
                    "kz-test",
                    "--dry-run",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("split=test", stdout.getvalue())

    def test_record_experiment_reports_output(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            run_dir = tmp_path / "run"
            run_dir.mkdir()
            output = tmp_path / "experiments.csv"
            stdout = io.StringIO()

            with patch(
                "road_damage_kz.cli.record_experiment",
                return_value={"experiment_id": "abc123", "phase": "eval", "eval_split": "kz-test"},
            ):
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "record-experiment",
                            "--run-dir",
                            str(run_dir),
                            "--output",
                            str(output),
                            "--eval-split",
                            "kz-test",
                            "--training-dataset",
                            "RDD2022",
                            "--evaluation-dataset",
                            "Kazakhstan gold set",
                            "--paper-eligible",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn("Recorded experiment abc123", stdout.getvalue())

    def test_evaluate_recorded_reports_output(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            model = tmp_path / "best.pt"
            config = tmp_path / "dataset.yaml"
            model.write_text("weights", encoding="utf-8")
            config.write_text("path: .\n", encoding="utf-8")
            stdout = io.StringIO()

            with patch(
                "road_damage_kz.cli.evaluate_and_record",
                return_value={"experiment_id": "eval123", "model": "yolov8n.pt", "eval_split": "kz-test"},
            ):
                with redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "evaluate-recorded",
                            "--model",
                            str(model),
                            "--config",
                            str(config),
                            "--split",
                            "kz-test",
                            "--name",
                            "eval",
                            "--paper-eligible",
                        ]
                    )

        self.assertEqual(exit_code, 0)
        self.assertIn("Recorded evaluation eval123", stdout.getvalue())

    def test_figures_includes_experiments_when_paper_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            manifest = tmp_path / "images.csv"
            annotations = tmp_path / "annotations.csv"
            experiments = tmp_path / "experiments.csv"
            rdd_summary = tmp_path / "import_summary.json"
            output = tmp_path / "paper_summary.json"
            table = tmp_path / "experiment_table.csv"
            card = tmp_path / "dataset_card.md"
            figures = tmp_path / "figures"
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
            experiments.write_text(
                "experiment_id,phase,training_dataset,evaluation_dataset,model,dataset_config,"
                "eval_split,weights,epochs,imgsz,precision,recall,map50,map50_95,paper_eligible,"
                "source_run_dir,notes\n"
                "exp1,eval,RDD2022,Kazakhstan gold set,yolov8n.pt,configs/dataset.yaml,kz-test,"
                "best.pt,50,640,0.1,0.2,0.3,0.4,true,runs/detect/val,test\n",
                encoding="utf-8",
            )
            rdd_summary.write_text('{"imported": 10, "boxes": 20}', encoding="utf-8")

            exit_code = main(
                [
                    "figures",
                    "--paper",
                    "--manifest",
                    str(manifest),
                    "--annotations",
                    str(annotations),
                    "--experiments",
                    str(experiments),
                    "--rdd-summary",
                    str(rdd_summary),
                    "--output",
                    str(output),
                    "--experiment-table",
                    str(table),
                    "--dataset-card",
                    str(card),
                    "--figures-dir",
                    str(figures),
                ]
            )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["publishable_rows"], 1)
            self.assertEqual(payload["paper_eligible_experiment_count"], 1)
            self.assertIn("yolov8n.pt", table.read_text(encoding="utf-8"))
            self.assertIn("Kazakhstan Road Damage Benchmark", card.read_text(encoding="utf-8"))
            self.assertTrue((figures / "dataset_summary_table.csv").exists())

    def test_experiment_table_prefers_final_sized_cohort_before_metric(self):
        rows = [
            {
                "experiment_id": "old",
                "phase": "eval",
                "training_dataset": "RDD2022",
                "evaluation_dataset": "Kazakhstan gold set",
                "model": "yolov8n.pt",
                "eval_split": "kz-test",
                "imgsz": "320",
                "precision": "0.9",
                "recall": "0.9",
                "map50": "0.9",
                "map50_95": "0.9",
            },
            {
                "experiment_id": "aws",
                "phase": "eval",
                "training_dataset": "RDD2022",
                "evaluation_dataset": "Kazakhstan gold set",
                "model": "yolov8n.pt",
                "eval_split": "kz-test",
                "imgsz": "640",
                "precision": "0.0",
                "recall": "0.0",
                "map50": "0.0",
                "map50_95": "0.0",
            },
        ]

        table = best_experiments_by_model_split(rows)

        self.assertEqual(table[0]["experiment_id"], "aws")

    def test_project_status_writes_blocker_report(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            manifest = tmp_path / "missing_images.csv"
            annotations = tmp_path / "annotations.csv"
            cache = tmp_path / "cache.csv"
            experiments = tmp_path / "experiments.csv"
            output = tmp_path / "status.json"
            annotations.write_text(
                "image_id,class_name,x_min,y_min,x_max,y_max,annotator,review_status,notes\n",
                encoding="utf-8",
            )
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n",
                encoding="utf-8",
            )
            experiments.write_text(
                "experiment_id,phase,training_dataset,evaluation_dataset,model,dataset_config,"
                "eval_split,weights,epochs,imgsz,precision,recall,map50,map50_95,paper_eligible,"
                "source_run_dir,notes\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(
                    [
                        "project-status",
                        "--manifest",
                        str(manifest),
                        "--annotations",
                        str(annotations),
                        "--cache-manifest",
                        str(cache),
                        "--experiments",
                        str(experiments),
                        "--rdd-root",
                        str(tmp_path / "RDD2022"),
                        "--paper-dir",
                        str(tmp_path / "paper"),
                        "--reports-dir",
                        str(tmp_path / "reports"),
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("Project status", stdout.getvalue())

    def test_triage_sheet_skips_source_leads(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            manifest = tmp_path / "images.csv"
            output = tmp_path / "triage.csv"
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "lead_source,https://example.com,,,,Kazakhstan,,,lead,unknown,,false,false,\n"
                "commons_1,https://example.com/file,https://example.com/file.jpg,CC-BY-4.0,"
                "Author,Kazakhstan,,,commons,unknown,,true,false,\n",
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "triage-sheet",
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(output),
                    "--license-ready-only",
                ]
            )

            self.assertEqual(exit_code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("commons_1", text)
            self.assertNotIn("lead_source", text)

    def test_triage_sheet_merge_existing_preserves_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            manifest = tmp_path / "images.csv"
            output = tmp_path / "triage.csv"
            manifest.write_text(
                "image_id,source_url,download_url,license,author,country,region,city,"
                "capture_context,damage_labels,split,license_ok,privacy_checked,notes\n"
                "commons_1,https://example.com/new,https://example.com/new.jpg,CC-BY-4.0,"
                "Author,Kazakhstan,,,commons,unknown,,true,false,new note\n"
                "commons_2,https://example.com/two,https://example.com/two.jpg,CC-BY-4.0,"
                "Author,Kazakhstan,,,commons,unknown,,true,false,\n",
                encoding="utf-8",
            )
            output.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "commons_1,https://example.com/old,https://example.com/old.jpg,CC-BY-4.0,"
                "Author,commons,normal,true,false,true,true,false,true,include,tester,keep me\n",
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "triage-sheet",
                    "--manifest",
                    str(manifest),
                    "--output",
                    str(output),
                    "--license-ready-only",
                    "--merge-existing",
                ]
            )

            self.assertEqual(exit_code, 0)
            text = output.read_text(encoding="utf-8")
            self.assertIn("commons_1,https://example.com/new,https://example.com/new.jpg", text)
            self.assertIn("include,tester,keep me", text)
            self.assertIn("commons_2", text)

    def test_collect_commons_batch_collects_category_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            categories = tmp_path / "commons_categories.csv"
            output = tmp_path / "images.csv"
            report = tmp_path / "report.json"
            categories.write_text(
                "category,limit,include_subcategories,max_depth,notes\n"
                "Category:Roads in Test,5,true,1,test\n",
                encoding="utf-8",
            )
            mocked_rows = [
                {
                    "image_id": "commons_1",
                    "source_url": "https://commons.wikimedia.org/wiki/File:Road.jpg",
                    "download_url": "https://upload.wikimedia.org/road.jpg",
                    "license": "CC-BY-4.0",
                    "author": "Author",
                    "country": "Kazakhstan",
                    "region": "",
                    "city": "",
                    "capture_context": "wikimedia-commons:Roads in Test",
                    "damage_labels": "unknown",
                    "split": "",
                    "license_ok": "true",
                    "privacy_checked": "false",
                    "notes": "test",
                }
            ]

            with patch("road_damage_kz.cli.collect_commons_category", return_value=mocked_rows):
                exit_code = main(
                    [
                        "collect-commons-batch",
                        "--categories",
                        str(categories),
                        "--output",
                        str(output),
                        "--report",
                        str(report),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("commons_1", output.read_text(encoding="utf-8"))
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["total_added"], 1)

    def test_collect_openverse_search_writes_unverified_leads(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            output = tmp_path / "images.csv"
            report = tmp_path / "report.json"
            mocked_rows = [
                {
                    "image_id": "openverse_abc",
                    "source_url": "https://source.example/road",
                    "download_url": "https://images.example/road.jpg",
                    "license": "CC-BY-4.0",
                    "author": "Author",
                    "country": "Kazakhstan",
                    "region": "",
                    "city": "",
                    "capture_context": "openverse-search:Kazakhstan pothole;source:flickr",
                    "damage_labels": "unknown",
                    "split": "",
                    "license_ok": "false",
                    "privacy_checked": "false",
                    "notes": "Openverse lead",
                }
            ]

            with patch("road_damage_kz.cli.collect_openverse_search", return_value=mocked_rows) as mocked:
                exit_code = main(
                    [
                        "collect-openverse-search",
                        "--query",
                        "Kazakhstan pothole",
                        "--output",
                        str(output),
                        "--report",
                        str(report),
                    ]
                )

            self.assertEqual(exit_code, 0)
            mocked.assert_called_once_with(
                "Kazakhstan pothole",
                limit=50,
                trust_openverse_license=False,
            )
            self.assertIn("openverse_abc", output.read_text(encoding="utf-8"))
            payload = json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(payload["total_license_ready"], 0)

    def test_triage_gallery_writes_html(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            triage = tmp_path / "triage.csv"
            output = tmp_path / "gallery.html"
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "commons_1,https://example.com/file,https://example.com/file.jpg,CC-BY-4.0,"
                "Author,commons,unknown,true,false,true,,,,,,\n",
                encoding="utf-8",
            )

            exit_code = main(["triage-gallery", "--triage", str(triage), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            self.assertIn("commons_1", output.read_text(encoding="utf-8"))

    def test_batch_intake_dry_run_prints_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            triage = tmp_path / "triage.csv"
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n",
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["batch-intake", "--triage", str(triage), "--dry-run"])

            self.assertEqual(exit_code, 0)
            self.assertIn("Batch intake dry run", stdout.getvalue())
            self.assertIn("Stop before applying triage", stdout.getvalue())

    def test_batch_intake_can_run_without_network_or_privacy(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp_path = Path(directory)
            image = tmp_path / "road.jpg"
            image.write_bytes(b"not a real image but keyword scoring does not decode it")
            triage = tmp_path / "triage.csv"
            cache = tmp_path / "local_files.csv"
            scores = tmp_path / "scores.csv"
            queue = tmp_path / "review_queue.csv"
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "road,https://example.com/road,https://example.com/road.jpg,CC-BY-4.0,A,ctx,"
                "unknown,true,false,true,,,,,,\n",
                encoding="utf-8",
            )
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                f"road,https://example.com/road,https://example.com/road.jpg,{image},abc,4,downloaded,\n",
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "batch-intake",
                    "--triage",
                    str(triage),
                    "--cache-manifest",
                    str(cache),
                    "--scores",
                    str(scores),
                    "--review-queue",
                    str(queue),
                    "--backend",
                    "keyword",
                    "--skip-download",
                    "--skip-privacy",
                ]
            )

            self.assertEqual(exit_code, 0)
            self.assertTrue(scores.exists())
            self.assertTrue(queue.exists())
            self.assertIn("road", queue.read_text(encoding="utf-8"))
            self.assertIn("needs_review", triage.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
