"""Baseline experiment orchestration helpers."""

from __future__ import annotations

from pathlib import Path
import sys


DEFAULT_MODELS = ["yolov8n.pt", "yolov8s.pt"]


def baseline_commands(
    *,
    rdd_root: str = "data/external/RDD2022",
    rdd_output_dir: str = "data/processed/rdd_yolo",
    kz_config: str = "configs/dataset.yaml",
    experiments: str = "data/manifests/experiments.csv",
    epochs: int = 50,
    imgsz: int = 640,
    batch: int | None = None,
    device: str = "",
    workers: int | None = None,
    fraction: float | None = None,
    models: list[str] | None = None,
) -> list[list[str]]:
    """Build the reproducible RDD-train/Kazakhstan-eval command sequence."""

    python = sys.executable
    active_models = models or DEFAULT_MODELS
    commands: list[list[str]] = [
        [
            python,
            "-m",
            "road_damage_kz.cli",
            "check-rdd",
            "--rdd-root",
            rdd_root,
            "--fail-on-not-ready",
        ],
        [
            python,
            "-m",
            "road_damage_kz.cli",
            "import-rdd-voc",
            "--rdd-root",
            rdd_root,
            "--output-dir",
            rdd_output_dir,
        ],
        [
            python,
            "-m",
            "road_damage_kz.cli",
            "prepare",
            "--format",
            "yolo",
            "--config",
            kz_config,
        ],
    ]
    for model in active_models:
        run_name = run_name_for_model(model)
        train_command = [
            "yolo",
            "detect",
            "train",
            f"data={Path(rdd_output_dir) / 'dataset.yaml'}",
            f"model={model}",
            f"epochs={epochs}",
            f"imgsz={imgsz}",
            f"name={run_name}",
            "exist_ok=True",
        ]
        if batch is not None:
            train_command.append(f"batch={batch}")
        if device:
            train_command.append(f"device={device}")
        if workers is not None:
            train_command.append(f"workers={workers}")
        if fraction is not None:
            train_command.append(f"fraction={fraction}")
        commands.append(train_command)
        train_run_dir = f"runs/detect/{run_name}"
        commands.append(
            [
                python,
                "-m",
                "road_damage_kz.cli",
                "record-experiment",
                "--run-dir",
                train_run_dir,
                "--output",
                experiments,
                "--phase",
                "train",
                "--training-dataset",
                "RDD2022",
                "--evaluation-dataset",
                "RDD2022-val",
                "--eval-split",
                "val",
                "--paper-eligible",
                "--notes",
                f"{model} trained on imported RDD2022 YOLO dataset.",
            ]
        )
        weights = f"{train_run_dir}/weights/best.pt"
        val_name = f"{run_name}_kz_eval"
        val_command = [
            python,
            "-m",
            "road_damage_kz.cli",
            "evaluate-recorded",
            "--config",
            kz_config,
            "--model",
            weights,
            "--model-label",
            model,
            "--split",
            "kz-test",
            "--name",
            val_name,
            "--imgsz",
            str(imgsz),
            "--experiments",
            experiments,
            "--training-dataset",
            "RDD2022",
            "--evaluation-dataset",
            "Kazakhstan gold set",
            "--paper-eligible",
            "--notes",
            f"{model} trained on RDD2022 and evaluated on Kazakhstan gold set.",
        ]
        if batch is not None:
            val_command.extend(["--batch", str(batch)])
        if device:
            val_command.extend(["--device", device])
        if workers is not None:
            val_command.extend(["--workers", str(workers)])
        commands.append(val_command)
    commands.append(
        [
            python,
            "-m",
            "road_damage_kz.cli",
            "figures",
            "--paper",
            "--experiments",
            experiments,
        ]
    )
    return commands


def run_name_for_model(model: str) -> str:
    stem = Path(model).stem.replace(".", "_")
    return f"rdd_{stem}"
