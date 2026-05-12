"""Experiment result ledger helpers."""

from __future__ import annotations

from pathlib import Path
import csv
import hashlib

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

from .schema import EXPERIMENT_FIELDS, read_csv, write_csv


METRIC_ALIASES = {
    "precision": ["metrics/precision(B)", "precision", "metrics/precision"],
    "recall": ["metrics/recall(B)", "recall", "metrics/recall"],
    "map50": ["metrics/mAP50(B)", "mAP50", "map50", "metrics/mAP50"],
    "map50_95": ["metrics/mAP50-95(B)", "mAP50-95", "map50_95", "metrics/mAP50-95"],
}


def record_experiment(
    run_dir: Path,
    output_path: Path,
    *,
    phase: str,
    eval_split: str = "",
    training_dataset: str = "",
    evaluation_dataset: str = "",
    paper_eligible: bool = False,
    notes: str = "",
) -> dict[str, str]:
    """Append or update one experiment record from an Ultralytics run directory."""

    args = read_args_yaml(run_dir / "args.yaml")
    metrics = read_last_metrics_row(run_dir / "results.csv")
    if paper_eligible and (not args or not metrics):
        missing = []
        if not args:
            missing.append("args.yaml")
        if not metrics:
            missing.append("results.csv")
        raise ValueError(f"Cannot record paper-eligible experiment without {', '.join(missing)} in {run_dir}")
    record = experiment_record(
        run_dir,
        args,
        metrics,
        phase=phase,
        eval_split=eval_split,
        training_dataset=training_dataset,
        evaluation_dataset=evaluation_dataset,
        paper_eligible=paper_eligible,
        notes=notes,
    )

    rows = read_csv(output_path) if output_path.exists() else []
    rows = [row for row in rows if row.get("experiment_id") != record["experiment_id"]]
    rows.append(record)
    write_csv(output_path, rows, EXPERIMENT_FIELDS)
    return record


def experiment_record(
    run_dir: Path,
    args: dict[str, str],
    metrics: dict[str, str],
    *,
    phase: str,
    eval_split: str = "",
    training_dataset: str = "",
    evaluation_dataset: str = "",
    paper_eligible: bool = False,
    notes: str = "",
) -> dict[str, str]:
    model = str(args.get("model_label") or args.get("model", ""))
    dataset_config = str(args.get("data", ""))
    split = eval_split or str(args.get("split", ""))
    weights = str(args.get("weights") or args.get("model", ""))
    experiment_id = stable_experiment_id(run_dir, phase, dataset_config, split, model)

    return {
        "experiment_id": experiment_id,
        "phase": phase,
        "training_dataset": training_dataset,
        "evaluation_dataset": evaluation_dataset,
        "model": model,
        "dataset_config": dataset_config,
        "eval_split": split,
        "weights": weights,
        "epochs": str(args.get("epochs", "")),
        "imgsz": str(args.get("imgsz", "")),
        "precision": metric_value(metrics, "precision"),
        "recall": metric_value(metrics, "recall"),
        "map50": metric_value(metrics, "map50"),
        "map50_95": metric_value(metrics, "map50_95"),
        "paper_eligible": str(paper_eligible).lower(),
        "source_run_dir": str(run_dir),
        "notes": notes,
    }


def read_last_metrics_row(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    return {key.strip(): (value or "").strip() for key, value in rows[-1].items()}


def read_args_yaml(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    if yaml is None:
        return read_simple_yaml_scalars(path)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(key): str(value) for key, value in payload.items()}


def read_simple_yaml_scalars(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def metric_value(metrics: dict[str, str], name: str) -> str:
    for key in METRIC_ALIASES[name]:
        if key in metrics:
            return metrics[key]
    return ""


def stable_experiment_id(run_dir: Path, phase: str, dataset_config: str, eval_split: str, model: str) -> str:
    seed = "|".join([str(run_dir), phase, dataset_config, eval_split, model])
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
