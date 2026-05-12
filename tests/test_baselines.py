import unittest

from road_damage_kz.baselines import baseline_commands, run_name_for_model


class BaselineRunnerTests(unittest.TestCase):
    def test_run_name_for_model_is_stable(self):
        self.assertEqual(run_name_for_model("yolov8n.pt"), "rdd_yolov8n")

    def test_baseline_commands_include_import_train_eval_and_recording(self):
        commands = baseline_commands(
            rdd_root="external/RDD",
            rdd_output_dir="processed/rdd",
            kz_config="configs/kz.yaml",
            experiments="experiments.csv",
            epochs=1,
            imgsz=320,
            batch=8,
            device="mps",
            workers=0,
            fraction=0.1,
            models=["yolov8n.pt"],
        )
        rendered = [" ".join(command) for command in commands]

        self.assertIn("check-rdd", rendered[0])
        self.assertIn("import-rdd-voc", rendered[1])
        self.assertIn("prepare", rendered[2])
        self.assertTrue(any("yolo detect train" in command for command in rendered))
        self.assertTrue(any("evaluate-recorded" in command for command in rendered))
        self.assertTrue(any("device=mps" in command for command in rendered))
        self.assertTrue(any("--device mps" in command for command in rendered))
        self.assertTrue(any("batch=8" in command for command in rendered))
        self.assertTrue(any("--batch 8" in command for command in rendered))
        self.assertTrue(any("fraction=0.1" in command for command in rendered))
        self.assertTrue(any("exist_ok=True" in command for command in rendered))
        self.assertTrue(any("--paper-eligible" in command for command in rendered))
        self.assertTrue(any("figures --paper" in command for command in rendered))


if __name__ == "__main__":
    unittest.main()
