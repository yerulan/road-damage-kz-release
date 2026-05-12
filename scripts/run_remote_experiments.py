#!/usr/bin/env python
"""Run paper experiments on a GPU server and record metrics.

This script intentionally keeps custom Ghost-CA-YOLO registration in-process,
because Ultralytics must know about CoordAtt before parsing the model YAML or
loading Ghost-CA weights.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from road_damage_kz.evaluation import evaluate_and_record
from road_damage_kz.experiments import record_experiment
from road_damage_kz.ghost_ca import register_ultralytics_modules


def main() -> int:
    args = parse_args()
    register_ultralytics_modules()

    try:
        from ultralytics import YOLO
    except ModuleNotFoundError as error:
        raise SystemExit('Ultralytics is not installed. Run: python -m pip install -e ".[ml]"') from error

    model_label = "Ghost-CA-YOLO" if args.model_kind == "ghost-ca" else "YOLO11s"
    run_stem = "ghost_ca_yolo11s" if args.model_kind == "ghost-ca" else "yolo11s"
    project = Path(args.project)
    experiments = Path(args.experiments)

    rdd_name = f"rdd_{run_stem}"
    rdd_run = find_run_dir(rdd_name, project)
    if not args.skip_rdd_train:
        model = YOLO(args.model_config if args.model_kind == "ghost-ca" else args.baseline_model)
        if args.model_kind == "ghost-ca" and args.init_weights:
            model.load(args.init_weights)
        model.train(
            data=args.rdd_data,
            epochs=args.rdd_epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            workers=args.workers,
            project=str(project),
            name=rdd_name,
            exist_ok=True,
        )
        rdd_run = resolved_train_run_dir(model, rdd_name, project)
    ensure_args_model_label(rdd_run, model_label)
    record_experiment(
        rdd_run,
        experiments,
        phase="train",
        eval_split="val",
        training_dataset="RDD2022",
        evaluation_dataset="RDD2022-val",
        paper_eligible=True,
        notes=f"{model_label} trained on RDD2022 at imgsz={args.imgsz}.",
    )

    rdd_weights = rdd_run / "weights" / "best.pt"
    if not rdd_weights.exists():
        raise SystemExit(f"Cannot find RDD weights at {rdd_weights}. Check --project or completed training output.")

    if not args.skip_kz_eval:
        evaluate_and_record(
            model_path=rdd_weights,
            config_path=Path(args.kz_data),
            split="kz-test",
            name=f"{run_stem}_rdd_only_kz_test",
            project=project,
            experiments_path=experiments,
            imgsz=args.imgsz,
            batch=args.batch,
            workers=args.workers,
            device=args.device,
            model_label=model_label,
            training_dataset="RDD2022",
            evaluation_dataset="Kazakhstan test",
            paper_eligible=True,
            notes=f"{model_label} trained on RDD2022 and evaluated on Kazakhstan test.",
        )

    kz_name = f"kz_adapt_{run_stem}"
    kz_run = find_run_dir(kz_name, project)
    if not args.skip_kz_adapt:
        model = YOLO(str(rdd_weights))
        model.train(
            data=args.kz_data,
            epochs=args.kz_epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            workers=args.workers,
            project=str(project),
            name=kz_name,
            exist_ok=True,
            lr0=args.kz_lr0,
            patience=args.patience,
        )
        kz_run = resolved_train_run_dir(model, kz_name, project)
        ensure_args_model_label(kz_run, model_label)
        record_experiment(
            kz_run,
            experiments,
            phase="train",
            eval_split="val",
            training_dataset="RDD2022+Kazakhstan",
            evaluation_dataset="Kazakhstan-val",
            paper_eligible=True,
            notes=f"{model_label} fine-tuned on Kazakhstan training split.",
        )
    elif has_recordable_artifacts(kz_run):
        ensure_args_model_label(kz_run, model_label)
        record_experiment(
            kz_run,
            experiments,
            phase="train",
            eval_split="val",
            training_dataset="RDD2022+Kazakhstan",
            evaluation_dataset="Kazakhstan-val",
            paper_eligible=True,
            notes=f"{model_label} fine-tuned on Kazakhstan training split.",
        )

    kz_weights = kz_run / "weights" / "best.pt"
    if not kz_weights.exists():
        raise SystemExit(f"Cannot find Kazakhstan-adapted weights at {kz_weights}.")
    evaluate_and_record(
        model_path=kz_weights,
        config_path=Path(args.kz_data),
        split="kz-test",
        name=f"{run_stem}_adapted_kz_test",
        project=project,
        experiments_path=experiments,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device=args.device,
        model_label=model_label,
        training_dataset="RDD2022+Kazakhstan",
        evaluation_dataset="Kazakhstan test",
        paper_eligible=True,
        notes=f"{model_label} fine-tuned on Kazakhstan and evaluated on Kazakhstan test.",
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-kind", choices=["yolo11s", "ghost-ca"], required=True)
    parser.add_argument("--baseline-model", default="yolo11s.pt")
    parser.add_argument("--model-config", default="configs/ghost_ca_yolo11s.yaml")
    parser.add_argument("--init-weights", default="yolo11s.pt")
    parser.add_argument("--rdd-data", default="data/processed/rdd_yolo/dataset.yaml")
    parser.add_argument("--kz-data", default="configs/dataset.yaml")
    parser.add_argument("--experiments", default="data/manifests/experiments.csv")
    parser.add_argument("--project", default="runs/detect")
    parser.add_argument("--rdd-epochs", type=int, default=50)
    parser.add_argument("--kz-epochs", type=int, default=30)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--kz-lr0", type=float, default=0.001)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--skip-rdd-train", action="store_true")
    parser.add_argument("--skip-kz-eval", action="store_true")
    parser.add_argument("--skip-kz-adapt", action="store_true")
    return parser.parse_args()


def resolved_train_run_dir(model, run_name: str, project: Path) -> Path:
    """Return Ultralytics' actual save directory, falling back to a search."""

    trainer = getattr(model, "trainer", None)
    save_dir = getattr(trainer, "save_dir", None)
    if save_dir:
        return relative_to_cwd(Path(save_dir))
    return find_run_dir(run_name, project)


def find_run_dir(run_name: str, project: Path) -> Path:
    """Find a run directory even when Ultralytics nests project paths."""

    candidates = [
        project / run_name,
        Path("runs") / "detect" / run_name,
    ]
    candidates.extend(Path(".").glob(f"**/{run_name}"))
    existing = [path for path in candidates if path.exists()]
    recordable = [path for path in existing if has_recordable_artifacts(path) or (path / "weights" / "best.pt").exists()]
    if recordable:
        return max(recordable, key=lambda path: path.stat().st_mtime)
    return project / run_name


def has_recordable_artifacts(run_dir: Path) -> bool:
    return (run_dir / "args.yaml").exists() and (run_dir / "results.csv").exists()


def ensure_args_model_label(run_dir: Path, model_label: str) -> None:
    """Add a stable model label to Ultralytics args.yaml for clearer ledgers."""

    args_path = run_dir / "args.yaml"
    if not args_path.exists():
        return
    text = args_path.read_text(encoding="utf-8")
    lines = [line for line in text.splitlines() if not line.startswith("model_label:")]
    lines.append(f"model_label: {model_label}")
    args_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def relative_to_cwd(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path


if __name__ == "__main__":
    raise SystemExit(main())
