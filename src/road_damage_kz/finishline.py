"""Finish-line reporting helpers for the paper submission package."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import shutil

from .dataset import validate_box_annotations
from .external import check_rdd_readiness
from .schema import audit_image_row, normalize_bool, read_csv


DETECTION_CLASSES = {
    "longitudinal_crack",
    "transverse_crack",
    "alligator_crack",
    "pothole",
}

MIN_APPLSCI_DAMAGED_IMAGES = 30
HIGH_APPLSCI_DAMAGED_IMAGES = 50
MIN_APPLSCI_BOXES = 100
MIN_APPLSCI_CLASSES = 3
PREFERRED_APPLSCI_DAMAGED_IMAGES = 100
DATA_JOURNAL_MIN_IMAGES = 800


def project_status(
    *,
    manifest_path: Path,
    annotations_path: Path,
    cache_manifest_path: Path,
    experiments_path: Path,
    rdd_root: Path,
    paper_dir: Path,
    reports_dir: Path,
    yolo_dir: Path = Path("data/processed/yolo"),
) -> dict:
    """Return a submission-oriented project status summary."""

    manifest_rows = read_csv(manifest_path) if manifest_path.exists() else []
    annotations = read_csv(annotations_path) if annotations_path.exists() else []
    experiments = read_csv(experiments_path) if experiments_path.exists() else []
    publishable = [row for row in manifest_rows if is_publishable_manifest_row(row)]
    damaged = [row for row in publishable if row.get("damage_labels") != "normal"]
    paper_eligible = [row for row in experiments if normalize_bool(row.get("paper_eligible", ""))]
    kz_eval_rows = [
        row
        for row in paper_eligible
        if row.get("evaluation_dataset") == "Kazakhstan gold set" or row.get("eval_split") == "kz-test"
    ]
    rdd = check_rdd_readiness(rdd_root)
    annotation_validation = (
        validate_box_annotations(annotations_path, cache_manifest_path)
        if annotations_path.exists() and cache_manifest_path.exists()
        else {"checked": 0, "errors": 1, "messages": ["Missing annotations or privacy-safe cache manifest."]}
    )
    yolo_validation = validate_yolo_annotation_export(annotations_path, yolo_dir) if annotations_path.exists() else {
        "checked": 0,
        "errors": 1,
        "messages": ["Missing annotations file."],
    }

    required_reports = {
        "paper_summary": reports_dir / "paper_summary.json",
        "experiment_table": reports_dir / "experiment_table.csv",
        "dataset_card": reports_dir / "dataset_card.md",
    }
    required_docs = {
        "final_workflow": Path("docs/final-workflow.md"),
        "submission_checklist": Path("docs/submission-checklist.md"),
        "cover_letter": paper_dir / "cover-letter.md",
        "manuscript": paper_dir / "main.tex",
    }

    blockers: list[str] = []
    warnings: list[str] = []
    if not manifest_rows:
        blockers.append(f"Missing or empty image manifest: {manifest_path}")
    if len(publishable) == 0:
        blockers.append("No publishable Kazakhstan rows are available.")
    if len(damaged) == 0:
        blockers.append("No publishable damaged Kazakhstan rows are available.")
    if not annotations:
        blockers.append(f"Missing or empty annotations file: {annotations_path}")
    annotation_ready = annotation_validation.get("errors", 0) == 0 or yolo_validation.get("errors", 0) == 0
    if not annotation_ready:
        blockers.append("Annotation validation has errors.")
    if rdd.get("status") != "ready":
        blockers.append(f"RDD dataset is not ready: {rdd.get('status')}")
    if not paper_eligible:
        blockers.append("No paper-eligible baseline experiments are recorded.")
    if not (paper_dir / "Definitions").exists():
        blockers.append("MDPI LaTeX template Definitions directory is missing under paper/.")
    if not any(shutil.which(name) for name in ["latexmk", "pdflatex", "tectonic"]):
        warnings.append("No local LaTeX compiler was found; compile the manuscript in Overleaf or install TeX Live/MacTeX.")
    warnings.extend(
        publication_readiness_warnings(
            publishable_rows=len(publishable),
            damaged_rows=len(damaged),
            annotations=annotations,
            kz_eval_rows=kz_eval_rows,
        )
    )
    for name, path in required_reports.items():
        if not path.exists():
            warnings.append(f"Missing report artifact {name}: {path}")
    for name, path in required_docs.items():
        if not path.exists():
            warnings.append(f"Missing document artifact {name}: {path}")

    return {
        "status": "blocked" if blockers else "ready",
        "manifest": {
            "rows": len(manifest_rows),
            "publishable_rows": len(publishable),
            "publishable_damaged_rows": len(damaged),
            "by_split": dict(Counter(row.get("split", "unsplit") or "unsplit" for row in publishable)),
            "by_label": dict(label_counter(publishable)),
        },
        "annotations": {
            "rows": len(annotations),
            "by_class": dict(Counter(row.get("class_name", "unknown") or "unknown" for row in annotations)),
            "validation": annotation_validation,
            "yolo_export_validation": yolo_validation,
            "readiness_source": "raw_privacy_cache"
            if annotation_validation.get("errors", 0) == 0
            else ("prepared_yolo_export" if yolo_validation.get("errors", 0) == 0 else "not_ready"),
        },
        "rdd": rdd,
        "experiments": {
            "rows": len(experiments),
            "paper_eligible_rows": len(paper_eligible),
            "kazakhstan_eval_rows": len(kz_eval_rows),
        },
        "publication_strategy": publication_strategy_summary(
            publishable_rows=len(publishable),
            damaged_rows=len(damaged),
            annotations=annotations,
            kz_eval_rows=kz_eval_rows,
        ),
        "artifacts": {
            "reports": {name: str(path) for name, path in required_reports.items()},
            "docs": {name: str(path) for name, path in required_docs.items()},
        },
        "blockers": blockers,
        "warnings": warnings,
    }


def validate_yolo_annotation_export(annotations_path: Path, yolo_dir: Path) -> dict[str, int | list[str]]:
    """Check that annotation rows are represented in a prepared YOLO export."""

    annotations = read_csv(annotations_path) if annotations_path.exists() else []
    checked = len(annotations)
    messages: list[str] = []
    if checked == 0:
        return {"checked": 0, "errors": 1, "messages": ["No annotation rows to validate."]}

    label_counts: Counter[str] = Counter()
    for label_path in sorted((yolo_dir / "labels").glob("*/*.txt")):
        image_id = label_path.stem
        try:
            lines = [line for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError as error:
            messages.append(f"{image_id}: cannot read YOLO label file {label_path}: {error}")
            continue
        label_counts[image_id] += len(lines)

    annotation_counts = Counter(row.get("image_id", "").strip() for row in annotations if row.get("image_id", "").strip())
    for image_id, expected_count in sorted(annotation_counts.items()):
        actual_count = label_counts.get(image_id, 0)
        if actual_count < expected_count:
            messages.append(
                f"{image_id}: prepared YOLO export has {actual_count} label rows; expected at least {expected_count}"
            )

    if not (yolo_dir / "images").exists() or not (yolo_dir / "labels").exists():
        messages.append(f"Missing prepared YOLO export directories under {yolo_dir}")

    return {"checked": checked, "errors": len(messages), "messages": messages}


def dataset_summary(manifest_rows: list[dict[str, str]], annotations: list[dict[str, str]]) -> dict:
    publishable = [row for row in manifest_rows if is_publishable_manifest_row(row)]
    damaged = [row for row in publishable if row.get("damage_labels") != "normal"]
    annotation_classes = Counter(row.get("class_name", "unknown") or "unknown" for row in annotations)
    annotation_review_status = Counter(row.get("review_status", "unknown") or "unknown" for row in annotations)
    return {
        "total_rows": len(manifest_rows),
        "publishable_rows": len(publishable),
        "publishable_damaged_rows": len(damaged),
        "publishable_normal_rows": len(publishable) - len(damaged),
        "annotation_rows": len(annotations),
        "annotation_class_count": len([name for name in annotation_classes if name in DETECTION_CLASSES]),
        "by_split": dict(Counter(row.get("split", "unsplit") or "unsplit" for row in publishable)),
        "by_label": dict(label_counter(publishable)),
        "by_annotation_class": dict(annotation_classes),
        "by_annotation_review_status": dict(annotation_review_status),
        "by_license": dict(Counter(row.get("license", "unknown") or "unknown" for row in publishable)),
        "applied_sciences_minimum": {
            "damaged_images": MIN_APPLSCI_DAMAGED_IMAGES,
            "damaged_images_high": HIGH_APPLSCI_DAMAGED_IMAGES,
            "boxes": MIN_APPLSCI_BOXES,
            "classes": MIN_APPLSCI_CLASSES,
        },
        "applied_sciences_preferred": {
            "damaged_images": PREFERRED_APPLSCI_DAMAGED_IMAGES,
        },
        "data_journal_minimum": {
            "redistributable_images": DATA_JOURNAL_MIN_IMAGES,
        },
    }


def write_dataset_card(path: Path, summary: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# Kazakhstan Road Damage Benchmark Dataset Card

## Dataset Purpose

This benchmark supports external validation for road-damage detection models on license-audited Kazakhstan road imagery. It is not currently framed as a large standalone Kazakhstan training dataset.

## Current Contents

- Manifest rows: {summary['total_rows']}
- Publishable rows: {summary['publishable_rows']}
- Publishable damaged rows: {summary['publishable_damaged_rows']}
- Publishable normal rows: {summary['publishable_normal_rows']}
- Bounding boxes: {summary['annotation_rows']}
- Annotation review status:

{markdown_counts(summary.get('by_annotation_review_status', {}))}

## Class Distribution

{markdown_counts(summary['by_annotation_class'] or summary['by_label'])}

## Split Distribution

{markdown_counts(summary['by_split'])}

## Source And License Policy

Images enter the publishable benchmark only when `license_ok=true`, source URL, author/owner attribution, reusable license metadata, and `privacy_checked=true` are recorded in `data/manifests/images.csv`. Web search and Openverse rows are discovery leads until source-page licensing is verified.

## Privacy Handling

Faces, readable license plates, and other personal identifiers must be blurred or the image is excluded. Publishable exports should use `data/manifests/privacy_safe_files.csv`.

## Redistribution Rule

The public release contains code, manifests, annotations, and reports. Raw third-party images are not redistributed by default. Reusers should reconstruct local image caches from recorded source URLs and respect each source license.

## Known Limitations

The Kazakhstan damaged subset is small and class-imbalanced. It is suitable for external validation and domain-shift analysis, not for claims of broad Kazakhstan road-damage coverage without further data collection.

## Publication Readiness

Applied Sciences remains the primary target, but the current benchmark is below the preferred strength for submission as a full domain-shift study.

- Minimum Applied Sciences target before submission: {summary['applied_sciences_minimum']['damaged_images']}--{summary['applied_sciences_minimum']['damaged_images_high']} damaged Kazakhstan images, {summary['applied_sciences_minimum']['boxes']} strict reviewed boxes, and {summary['applied_sciences_minimum']['classes']} represented damage classes.
- Preferred Applied Sciences target: {summary['applied_sciences_preferred']['damaged_images']} or more damaged Kazakhstan images plus normal hard negatives.
- Data-journal fallback target: {summary['data_journal_minimum']['redistributable_images']} or more redistributable license-clean Kazakhstan images with repository DOI.

Current status: {summary['publishable_damaged_rows']} damaged images, {summary['annotation_rows']} bounding boxes, and {summary['annotation_class_count']} represented detection classes. Boxes marked as provisional require strict second-pass review before final manuscript claims.
"""
    path.write_text(content, encoding="utf-8")


def publication_readiness_warnings(
    *,
    publishable_rows: int,
    damaged_rows: int,
    annotations: list[dict[str, str]],
    kz_eval_rows: list[dict[str, str]],
) -> list[str]:
    """Return non-blocking warnings about scientific publication strength."""

    warnings: list[str] = []
    classes = represented_detection_classes(annotations)
    if damaged_rows < MIN_APPLSCI_DAMAGED_IMAGES:
        warnings.append(
            "Applied Sciences strength warning: "
            f"{damaged_rows} damaged Kazakhstan images are available; target at least "
            f"{MIN_APPLSCI_DAMAGED_IMAGES}-{HIGH_APPLSCI_DAMAGED_IMAGES} before submission."
        )
    strict_boxes = strict_reviewed_annotation_count(annotations)
    if strict_boxes < MIN_APPLSCI_BOXES:
        warnings.append(
            "Applied Sciences strength warning: "
            f"{strict_boxes} strict reviewed boxes are available; target at least {MIN_APPLSCI_BOXES}."
        )
    if len(classes) < MIN_APPLSCI_CLASSES:
        warnings.append(
            "Applied Sciences strength warning: "
            f"{len(classes)} detection classes are represented; target at least {MIN_APPLSCI_CLASSES}."
        )
    if publishable_rows < DATA_JOURNAL_MIN_IMAGES:
        warnings.append(
            "Data journal fallback warning: "
            f"{publishable_rows} publishable images are available; data-journal route needs about "
            f"{DATA_JOURNAL_MIN_IMAGES} redistributable license-clean images plus a repository DOI."
        )
    if kz_eval_rows and all(is_zero_metric(row) for row in kz_eval_rows):
        warnings.append(
            "Kazakhstan evaluation warning: all paper-eligible Kazakhstan evaluation metrics are zero; "
            "submit only with a sample-size-limited domain-shift interpretation or stronger adaptation results."
        )
    elif not kz_eval_rows:
        warnings.append("Kazakhstan evaluation warning: no paper-eligible Kazakhstan evaluation rows are recorded.")
    return warnings


def publication_strategy_summary(
    *,
    publishable_rows: int,
    damaged_rows: int,
    annotations: list[dict[str, str]],
    kz_eval_rows: list[dict[str, str]],
) -> dict:
    """Summarize journal-route readiness for machine-readable status reports."""

    classes = represented_detection_classes(annotations)
    strict_boxes = strict_reviewed_annotation_count(annotations)
    provisional_boxes = len(annotations) - strict_boxes
    return {
        "primary_target": "MDPI Applied Sciences Article",
        "recommended_positioning": "Kazakhstan road-damage benchmark with Ghost-CA-YOLO adaptation and external validation",
        "avoid_positioning": "large standalone Kazakhstan training dataset",
        "applied_sciences_minimum": {
            "damaged_images": MIN_APPLSCI_DAMAGED_IMAGES,
            "boxes": MIN_APPLSCI_BOXES,
            "classes": MIN_APPLSCI_CLASSES,
            "damaged_images_high": HIGH_APPLSCI_DAMAGED_IMAGES,
        },
        "applied_sciences_preferred": {
            "damaged_images": PREFERRED_APPLSCI_DAMAGED_IMAGES,
        },
        "data_journal_minimum": {
            "redistributable_images": DATA_JOURNAL_MIN_IMAGES,
            "requires_repository_doi": True,
        },
        "current": {
            "publishable_images": publishable_rows,
            "damaged_images": damaged_rows,
            "annotation_rows": len(annotations),
            "gold_boxes": strict_boxes,
            "provisional_boxes": provisional_boxes,
            "represented_detection_classes": sorted(classes),
            "kazakhstan_eval_rows": len(kz_eval_rows),
            "kazakhstan_eval_all_zero": bool(kz_eval_rows) and all(is_zero_metric(row) for row in kz_eval_rows),
        },
        "ready_for_applied_sciences_full_article": (
            damaged_rows >= MIN_APPLSCI_DAMAGED_IMAGES
            and strict_boxes >= MIN_APPLSCI_BOXES
            and len(classes) >= MIN_APPLSCI_CLASSES
            and bool(kz_eval_rows)
            and not all(is_zero_metric(row) for row in kz_eval_rows)
        ),
        "ready_for_data_journal": publishable_rows >= DATA_JOURNAL_MIN_IMAGES,
    }


def represented_detection_classes(annotations: list[dict[str, str]]) -> set[str]:
    return {
        row.get("class_name", "").strip()
        for row in annotations
        if row.get("class_name", "").strip() in DETECTION_CLASSES
    }


def strict_reviewed_annotation_count(annotations: list[dict[str, str]]) -> int:
    return sum(1 for row in annotations if row.get("review_status", "").strip().lower() == "gold")


def is_zero_metric(row: dict[str, str]) -> bool:
    values = []
    for field in ["precision", "recall", "map50", "map50_95"]:
        try:
            values.append(float(row.get(field, "") or 0))
        except ValueError:
            values.append(0.0)
    return all(value == 0.0 for value in values)


def write_table_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    from .schema import write_csv

    write_csv(path, rows, fields)


def copy_sample_annotation_figure(source_dir: Path, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = sorted(source_dir.glob("*.jpg")) + sorted(source_dir.glob("*.png"))
    if not candidates:
        return ""
    target = output_dir / "sample_annotation.jpg"
    shutil.copy2(candidates[0], target)
    return str(target)


def is_publishable_manifest_row(row: dict[str, str]) -> bool:
    return (
        normalize_bool(row.get("license_ok", ""))
        and normalize_bool(row.get("privacy_checked", ""))
        and not audit_image_row(row)
        and row.get("damage_labels", "") not in {"", "unknown"}
    )


def label_counter(rows: list[dict[str, str]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for row in rows:
        labels = [label.strip() for label in row.get("damage_labels", "").split(";") if label.strip()]
        counter.update(labels or ["unknown"])
    return counter


def markdown_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "_None recorded._"
    lines = ["| Item | Count |", "| --- | ---: |"]
    for key, value in sorted(counts.items()):
        lines.append(f"| `{key}` | {value} |")
    return "\n".join(lines)
