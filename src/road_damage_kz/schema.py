"""Manifest schemas and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import csv


IMAGE_MANIFEST_FIELDS = [
    "image_id",
    "source_url",
    "download_url",
    "license",
    "author",
    "country",
    "region",
    "city",
    "capture_context",
    "damage_labels",
    "split",
    "license_ok",
    "privacy_checked",
    "notes",
]

SOURCE_MANIFEST_FIELDS = [
    "source_id",
    "source_name",
    "source_url",
    "source_type",
    "license_policy",
    "notes",
]

COMMONS_CATEGORY_FIELDS = [
    "category",
    "limit",
    "include_subcategories",
    "max_depth",
    "notes",
]

TRIAGE_FIELDS = [
    "image_id",
    "source_url",
    "download_url",
    "license",
    "author",
    "capture_context",
    "damage_labels",
    "license_ok",
    "privacy_checked",
    "is_photo_candidate",
    "road_surface_visible",
    "target_damage_visible",
    "privacy_ok",
    "recommended_action",
    "reviewer",
    "notes",
]

LOCAL_FILE_FIELDS = [
    "image_id",
    "source_url",
    "download_url",
    "local_path",
    "sha256",
    "bytes",
    "status",
    "error",
]

SCORE_FIELDS = [
    "image_id",
    "local_path",
    "source_url",
    "road_surface_score",
    "damage_score",
    "normal_road_score",
    "non_road_score",
    "privacy_context_score",
    "review_priority",
    "suggested_action",
    "model",
    "notes",
]

REVIEW_QUEUE_FIELDS = [
    "rank",
    "image_id",
    "review_priority",
    "suggested_action",
    "road_surface_score",
    "damage_score",
    "normal_road_score",
    "non_road_score",
    "privacy_context_score",
    "triage_action",
    "triage_labels",
    "local_path",
    "source_url",
    "notes",
]

CLASSIFICATION_EXPORT_FIELDS = [
    "image_id",
    "export_path",
    "labels",
    "source_url",
    "license",
    "author",
    "split",
]

ANNOTATION_QUEUE_FIELDS = [
    "image_id",
    "local_path",
    "source_url",
    "damage_labels",
    "annotation_needed",
    "notes",
]

ANNOTATION_FIELDS = [
    "image_id",
    "class_name",
    "x_min",
    "y_min",
    "x_max",
    "y_max",
    "annotator",
    "review_status",
    "notes",
]

PRIVACY_REPORT_FIELDS = [
    "image_id",
    "local_path",
    "source_url",
    "status",
    "face_count",
    "plate_candidate_count",
    "total_regions",
    "blur_required",
    "detections_json",
    "notes",
]

EXPERIMENT_FIELDS = [
    "experiment_id",
    "phase",
    "training_dataset",
    "evaluation_dataset",
    "model",
    "dataset_config",
    "eval_split",
    "weights",
    "epochs",
    "imgsz",
    "precision",
    "recall",
    "map50",
    "map50_95",
    "paper_eligible",
    "source_run_dir",
    "notes",
]

EXPERIMENT_TABLE_FIELDS = [
    "model",
    "training_dataset",
    "evaluation_dataset",
    "eval_split",
    "precision",
    "recall",
    "map50",
    "map50_95",
    "experiment_id",
]

OPEN_LICENSES = {
    "CC0",
    "CC0-1.0",
    "CC-BY",
    "CC-BY-2.0",
    "CC-BY-3.0",
    "CC-BY-4.0",
    "CC-BY-SA",
    "CC-BY-SA-2.0",
    "CC-BY-SA-2.5",
    "CC-BY-SA-3.0",
    "CC-BY-SA-4.0",
    "PDM",
    "PUBLIC DOMAIN",
    "MIT",
    "EXPLICIT PERMISSION",
}


@dataclass(frozen=True)
class AuditFinding:
    image_id: str
    field: str
    message: str
    severity: str = "error"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [{key: value or "" for key, value in row.items()} for row in reader]


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def normalize_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def normalize_license(value: str) -> str:
    return value.strip().upper().replace(" ", "-")


def is_open_license(value: str) -> bool:
    normalized = normalize_license(value)
    return normalized in {normalize_license(item) for item in OPEN_LICENSES}


def validate_manifest_columns(path: Path, required_fields: list[str]) -> list[str]:
    if not path.exists():
        return [f"Missing manifest: {path}"]
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
    missing = [field for field in required_fields if field not in fieldnames]
    return [f"Missing required column: {field}" for field in missing]


def audit_image_row(row: dict[str, str]) -> list[AuditFinding]:
    image_id = row.get("image_id", "<missing>")
    findings: list[AuditFinding] = []

    required = ["image_id", "source_url", "license", "author", "country"]
    for field in required:
        if not row.get(field, "").strip():
            findings.append(AuditFinding(image_id, field, "Required field is empty."))

    if row.get("license", "").strip() and not is_open_license(row["license"]):
        findings.append(
            AuditFinding(
                image_id,
                "license",
                f"License is not in the approved open-license list: {row['license']}",
            )
        )

    if not normalize_bool(row.get("license_ok", "")):
        findings.append(
            AuditFinding(image_id, "license_ok", "Image is not marked license_ok=true.")
        )

    if not normalize_bool(row.get("privacy_checked", "")):
        findings.append(
            AuditFinding(
                image_id,
                "privacy_checked",
                "Image is not marked privacy_checked=true.",
            )
        )

    return findings
