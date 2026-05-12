from pathlib import Path
import tempfile
import unittest

from road_damage_kz.experiments import record_experiment


class ExperimentLedgerTests(unittest.TestCase):
    def test_record_experiment_reads_ultralytics_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "runs" / "detect" / "val"
            run_dir.mkdir(parents=True)
            (run_dir / "args.yaml").write_text(
                "model: runs/detect/train/weights/best.pt\n"
                "data: configs/dataset.yaml\n"
                "epochs: 50\n"
                "imgsz: 640\n",
                encoding="utf-8",
            )
            (run_dir / "results.csv").write_text(
                "epoch,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n"
                "0,0.1,0.2,0.3,0.4\n"
                "1,0.5,0.6,0.7,0.8\n",
                encoding="utf-8",
            )
            output = root / "experiments.csv"

            record = record_experiment(
                run_dir,
                output,
                phase="eval",
                eval_split="kz-test",
                training_dataset="RDD2022",
                evaluation_dataset="Kazakhstan gold set",
                paper_eligible=True,
                notes="smoke",
            )

            self.assertEqual(record["precision"], "0.5")
            self.assertEqual(record["recall"], "0.6")
            self.assertEqual(record["map50"], "0.7")
            self.assertEqual(record["map50_95"], "0.8")
            self.assertEqual(record["eval_split"], "kz-test")
            self.assertEqual(record["training_dataset"], "RDD2022")
            self.assertEqual(record["evaluation_dataset"], "Kazakhstan gold set")
            self.assertEqual(record["paper_eligible"], "true")
            self.assertIn("smoke", output.read_text(encoding="utf-8"))

    def test_record_experiment_uses_model_label_and_weights(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "runs" / "detect" / "val"
            run_dir.mkdir(parents=True)
            (run_dir / "args.yaml").write_text(
                "model: yolov8n.pt\n"
                "model_label: yolov8n.pt\n"
                "weights: runs/detect/rdd_yolov8n/weights/best.pt\n"
                "data: configs/dataset.yaml\n"
                "imgsz: 320\n",
                encoding="utf-8",
            )
            (run_dir / "results.csv").write_text(
                "metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B)\n"
                "0.1,0.2,0.3,0.4\n",
                encoding="utf-8",
            )

            record = record_experiment(
                run_dir,
                root / "experiments.csv",
                phase="eval",
                eval_split="kz-test",
                paper_eligible=True,
            )

            self.assertEqual(record["model"], "yolov8n.pt")
            self.assertEqual(record["weights"], "runs/detect/rdd_yolov8n/weights/best.pt")

    def test_paper_eligible_record_requires_metrics_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "empty_run"
            run_dir.mkdir()

            with self.assertRaises(ValueError):
                record_experiment(
                    run_dir,
                    root / "experiments.csv",
                    phase="eval",
                    paper_eligible=True,
                )


if __name__ == "__main__":
    unittest.main()
