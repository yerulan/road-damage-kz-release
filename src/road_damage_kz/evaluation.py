"""Recorded YOLO evaluation helpers."""

from __future__ import annotations

from pathlib import Path
import csv
import os
import re
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from .experiments import read_args_yaml, record_experiment


METRIC_FIELDS = [
    "metrics/precision(B)",
    "metrics/recall(B)",
    "metrics/mAP50(B)",
    "metrics/mAP50-95(B)",
    "fitness",
]


def evaluate_and_record(
    *,
    model_path: Path,
    config_path: Path,
    split: str,
    name: str,
    project: Path,
    experiments_path: Path,
    imgsz: int,
    batch: int | None = None,
    workers: int | None = None,
    device: str = "",
    model_label: str = "",
    training_dataset: str = "",
    evaluation_dataset: str = "",
    paper_eligible: bool = False,
    notes: str = "",
) -> dict[str, str]:
    """Run Ultralytics validation, persist machine-readable metrics, and record the run."""

    ensure_runtime_cache_dirs()
    try:
        from ultralytics import YOLO
    except ModuleNotFoundError as error:  # pragma: no cover - environment dependent
        raise RuntimeError('Ultralytics is not installed. Install with: python -m pip install -e ".[ml]"') from error

    yolo_split = "test" if split == "kz-test" else split
    kwargs: dict[str, Any] = {
        "data": str(config_path),
        "split": yolo_split,
        "imgsz": imgsz,
        "project": str(project),
        "name": name,
        "exist_ok": True,
        "verbose": False,
    }
    if batch is not None:
        kwargs["batch"] = batch
    if workers is not None:
        kwargs["workers"] = workers
    if device:
        kwargs["device"] = device

    metrics = YOLO(str(model_path)).val(**kwargs)
    run_dir = relative_to_cwd(Path(getattr(metrics, "save_dir", project / name)))
    metrics_row = normalize_metrics_dict(getattr(metrics, "results_dict", {}) or {})
    if not metrics_row:
        box_metrics = getattr(metrics, "box", None)
        metrics_row = metrics_from_box(box_metrics)

    label = model_label or infer_model_label(model_path)
    write_eval_artifacts(
        run_dir=run_dir,
        model_path=model_path,
        model_label=label,
        config_path=config_path,
        split=split,
        imgsz=imgsz,
        batch=batch,
        workers=workers,
        device=device,
        metrics_row=metrics_row,
    )
    return record_experiment(
        run_dir,
        experiments_path,
        phase="eval",
        eval_split=split,
        training_dataset=training_dataset,
        evaluation_dataset=evaluation_dataset,
        paper_eligible=paper_eligible,
        notes=notes,
    )


def ensure_runtime_cache_dirs() -> None:
    """Keep Ultralytics/Matplotlib cache writes inside ignored local directories."""

    cache_root = Path("data") / "external" / "runtime-cache"
    mpl = cache_root / "matplotlib"
    ultra = cache_root / "ultralytics"
    mpl.mkdir(parents=True, exist_ok=True)
    ultra.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl))
    os.environ.setdefault("YOLO_CONFIG_DIR", str(ultra))


def infer_model_label(model_path: Path) -> str:
    """Recover the base model name from a training run args.yaml when available."""

    if model_path.name == "best.pt" and model_path.parent.name == "weights":
        train_args = read_args_yaml(model_path.parent.parent / "args.yaml")
        if train_args.get("model"):
            return str(train_args["model"])
        return model_path.parent.parent.name
    return model_path.name


def relative_to_cwd(path: Path) -> Path:
    try:
        return path.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        return path


def normalize_metrics_dict(metrics: dict[str, Any]) -> dict[str, str]:
    row: dict[str, str] = {}
    for field in METRIC_FIELDS:
        if field in metrics:
            row[field] = str(metrics[field])
    return row


def metrics_from_box(box_metrics: Any) -> dict[str, str]:
    if box_metrics is None:
        return {}
    values = {
        "metrics/precision(B)": getattr(box_metrics, "mp", ""),
        "metrics/recall(B)": getattr(box_metrics, "mr", ""),
        "metrics/mAP50(B)": getattr(box_metrics, "map50", ""),
        "metrics/mAP50-95(B)": getattr(box_metrics, "map", ""),
    }
    values["fitness"] = values["metrics/mAP50-95(B)"]
    return {key: str(value) for key, value in values.items() if value != ""}


def write_eval_artifacts(
    *,
    run_dir: Path,
    model_path: Path,
    model_label: str,
    config_path: Path,
    split: str,
    imgsz: int,
    batch: int | None,
    workers: int | None,
    device: str,
    metrics_row: dict[str, str],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    args = {
        "model": model_label,
        "model_label": model_label,
        "weights": str(model_path),
        "data": str(config_path),
        "split": split,
        "imgsz": imgsz,
    }
    if batch is not None:
        args["batch"] = batch
    if workers is not None:
        args["workers"] = workers
    if device:
        args["device"] = device
    write_yaml(run_dir / "args.yaml", args)
    with (run_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=METRIC_FIELDS)
        writer.writeheader()
        writer.writerow({field: metrics_row.get(field, "") for field in METRIC_FIELDS})


def write_yaml(path: Path, values: dict[str, Any]) -> None:
    if yaml is not None:
        path.write_text(yaml.safe_dump(values, sort_keys=False), encoding="utf-8")
        return
    lines = [f"{key}: {quote_yaml_scalar(value)}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def quote_yaml_scalar(value: Any) -> str:
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", text):
        return text
    return "'" + text.replace("'", "''") + "'"
