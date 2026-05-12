"""Command line interface for the Kazakhstan road damage project."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
from time import perf_counter

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised in minimal environments
    yaml = None

from .schema import (
    COMMONS_CATEGORY_FIELDS,
    EXPERIMENT_TABLE_FIELDS,
    IMAGE_MANIFEST_FIELDS,
    SOURCE_MANIFEST_FIELDS,
    TRIAGE_FIELDS,
    audit_image_row,
    normalize_bool,
    read_csv,
    validate_manifest_columns,
    write_csv,
)
from .baselines import baseline_commands
from .commons import append_rows, collect_commons_category, collect_commons_search
from .openverse import collect_openverse_search
from .mapillary import CITY_BBOXES, collect_mapillary_bbox, parse_bbox
from .assets import download_candidates, generate_local_gallery
from .auto_triage import AutoTriageThresholds, auto_triage_scores
from .annotations import draft_annotations
from .dataset import (
    assign_dataset_splits,
    export_annotation_queue,
    export_classification_dataset,
    prepare_yolo_dataset,
    validate_box_annotations,
)
from .external import PRACTICAL_RDD2022_COUNTRIES, check_rdd_readiness, import_rdd_voc_dataset, rdd_download_script
from .experiments import record_experiment
from .evaluation import evaluate_and_record
from .finishline import (
    copy_sample_annotation_figure,
    dataset_summary,
    project_status,
    write_dataset_card,
)
from .privacy import (
    apply_privacy_report_to_triage,
    blur_privacy_regions,
    export_privacy_safe_cache,
    scan_privacy,
)
from .review import export_review_queue
from .scoring import score_candidates
from .triage import apply_triage, generate_gallery, validate_triage_columns


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roadkz")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Normalize source leads into the image manifest.")
    collect.add_argument("--sources", default="data/manifests/sources.csv")
    collect.add_argument("--output", default="data/manifests/images.csv")
    collect.set_defaults(func=cmd_collect)

    commons = subparsers.add_parser("collect-commons", help="Collect Wikimedia Commons file metadata.")
    commons.add_argument("--category", default="Category:Roads in Kazakhstan")
    commons.add_argument("--output", default="data/manifests/images.csv")
    commons.add_argument("--limit", type=int, default=100)
    commons.add_argument("--include-subcategories", action="store_true")
    commons.add_argument("--max-depth", type=int, default=1)
    commons.set_defaults(func=cmd_collect_commons)

    commons_batch = subparsers.add_parser(
        "collect-commons-batch",
        help="Collect Wikimedia Commons metadata from a CSV list of categories.",
    )
    commons_batch.add_argument("--categories", default="data/manifests/commons_categories.csv")
    commons_batch.add_argument("--output", default="data/manifests/images.csv")
    commons_batch.add_argument("--report", default="reports/commons_batch_report.json")
    commons_batch.add_argument("--limit", type=int, help="Override per-category limits.")
    commons_batch.add_argument("--offset", type=int, default=0, help="Skip this many category rows before collecting.")
    commons_batch.add_argument("--max-categories", type=int, help="Collect at most this many category rows.")
    commons_batch.set_defaults(func=cmd_collect_commons_batch)

    commons_search = subparsers.add_parser(
        "collect-commons-search",
        help="Collect Wikimedia Commons file metadata from search terms.",
    )
    commons_search.add_argument("--query", action="append", required=True)
    commons_search.add_argument("--output", default="data/manifests/images.csv")
    commons_search.add_argument("--report", default="reports/commons_search_report.json")
    commons_search.add_argument("--limit", type=int, default=50)
    commons_search.set_defaults(func=cmd_collect_commons_search)

    openverse_search = subparsers.add_parser(
        "collect-openverse-search",
        help="Collect Openverse image metadata from search terms as license-verification leads.",
    )
    openverse_search.add_argument("--query", action="append", required=True)
    openverse_search.add_argument("--output", default="data/manifests/images.csv")
    openverse_search.add_argument("--report", default="reports/openverse_search_report.json")
    openverse_search.add_argument("--limit", type=int, default=50)
    openverse_search.add_argument(
        "--trust-openverse-license",
        action="store_true",
        help=(
            "Mark rows license_ok=true when Openverse metadata has an approved license. "
            "Default keeps rows as unverified discovery leads."
        ),
    )
    openverse_search.set_defaults(func=cmd_collect_openverse_search)

    mapillary = subparsers.add_parser(
        "collect-mapillary",
        help="Collect Mapillary street-level image metadata inside Kazakhstan city/bbox areas.",
    )
    mapillary_area = mapillary.add_mutually_exclusive_group(required=True)
    mapillary_area.add_argument(
        "--city",
        choices=sorted(CITY_BBOXES),
        help="Use a built-in Kazakhstan city bounding box.",
    )
    mapillary_area.add_argument(
        "--bbox",
        help="Bounding box as west,south,east,north.",
    )
    mapillary.add_argument("--region", default="")
    mapillary.add_argument("--output", default="data/manifests/images.csv")
    mapillary.add_argument("--report", default="reports/mapillary_report.json")
    mapillary.add_argument("--limit", type=int, default=100)
    mapillary.add_argument(
        "--thumbnail-size",
        choices=["256", "1024", "2048", "original"],
        default="1024",
        help="Thumbnail URL size to store as download_url.",
    )
    mapillary.add_argument(
        "--access-token",
        default="",
        help="Mapillary access token. Defaults to MAPILLARY_ACCESS_TOKEN.",
    )
    mapillary.add_argument("--min-captured-at", default="", help="Optional Mapillary start_captured_at filter.")
    mapillary.add_argument("--max-captured-at", default="", help="Optional Mapillary end_captured_at filter.")
    mapillary.add_argument("--request-delay", type=float, default=1.0)
    mapillary.add_argument(
        "--grid-size",
        type=int,
        default=4,
        help="Split the bbox into an NxN grid to avoid large Mapillary API query timeouts.",
    )
    mapillary.set_defaults(func=cmd_collect_mapillary)

    audit = subparsers.add_parser("audit-licenses", help="Audit manifest rows for publication readiness.")
    audit.add_argument("--manifest", default="data/manifests/images.csv")
    audit.add_argument("--report", default="reports/license_audit.json")
    audit.set_defaults(func=cmd_audit_licenses)

    dedupe = subparsers.add_parser("dedupe", help="Detect duplicate local files referenced by the manifest.")
    dedupe.add_argument("--manifest", default="data/manifests/images.csv")
    dedupe.add_argument("--report", default="reports/dedupe_report.json")
    dedupe.set_defaults(func=cmd_dedupe)

    split_dataset = subparsers.add_parser(
        "split-dataset",
        help="Assign deterministic train/val/test splits to publishable manifest rows.",
    )
    split_dataset.add_argument("--manifest", default="data/manifests/images.csv")
    split_dataset.add_argument("--output", default="data/manifests/images.csv")
    split_dataset.add_argument("--seed", type=int, default=20260503)
    split_dataset.add_argument("--train-ratio", type=float, default=0.70)
    split_dataset.add_argument("--val-ratio", type=float, default=0.15)
    split_dataset.add_argument("--test-split", choices=["test", "kz-test"], default="kz-test")
    split_dataset.set_defaults(func=cmd_split_dataset)

    prepare = subparsers.add_parser("prepare", help="Prepare a training dataset from audited manifest rows.")
    prepare.add_argument("--format", choices=["yolo"], default="yolo")
    prepare.add_argument("--manifest", default="data/manifests/images.csv")
    prepare.add_argument("--cache-manifest", default="data/manifests/privacy_safe_files.csv")
    prepare.add_argument("--annotations", default="data/manifests/annotations.csv")
    prepare.add_argument("--config", default="configs/dataset.yaml")
    prepare.add_argument("--output-dir", default="data/processed/yolo")
    prepare.set_defaults(func=cmd_prepare)

    check_rdd = subparsers.add_parser(
        "check-rdd",
        help="Check whether an RDD Pascal VOC root is ready for YOLO import.",
    )
    check_rdd.add_argument("--rdd-root", default="data/external/RDD2022")
    check_rdd.add_argument("--report", default="reports/rdd_readiness.json")
    check_rdd.add_argument("--fail-on-not-ready", action="store_true")
    check_rdd.set_defaults(func=cmd_check_rdd)

    rdd_plan = subparsers.add_parser(
        "rdd-download-plan",
        help="Write a reviewable shell script for downloading selected official RDD2022 archives.",
    )
    rdd_plan.add_argument("--country", action="append", default=[])
    rdd_plan.add_argument("--output-dir", default="data/external/RDD2022")
    rdd_plan.add_argument("--script", default="reports/rdd_download_plan.sh")
    rdd_plan.set_defaults(func=cmd_rdd_download_plan)

    import_rdd = subparsers.add_parser(
        "import-rdd-voc",
        help="Convert an externally downloaded RDD Pascal VOC dataset into YOLO format.",
    )
    import_rdd.add_argument("--rdd-root", default="data/external/RDD2022")
    import_rdd.add_argument("--output-dir", default="data/processed/rdd_yolo")
    import_rdd.add_argument("--seed", type=int, default=20260509)
    import_rdd.add_argument("--val-ratio", type=float, default=0.15)
    import_rdd.add_argument("--limit", type=int)
    import_rdd.add_argument("--copy-mode", choices=["symlink", "copy"], default="symlink")
    import_rdd.set_defaults(func=cmd_import_rdd_voc)

    train = subparsers.add_parser("train", help="Train a baseline detector.")
    train.add_argument("--config", default="configs/dataset.yaml")
    train.add_argument("--model", default="yolov8n.pt")
    train.add_argument("--epochs", type=int, default=50)
    train.add_argument("--imgsz", type=int, default=640)
    train.add_argument("--dry-run", action="store_true")
    train.set_defaults(func=cmd_train)

    evaluate = subparsers.add_parser("evaluate", help="Evaluate a trained detector.")
    evaluate.add_argument("--split", default="kz-test")
    evaluate.add_argument("--config", default="configs/dataset.yaml")
    evaluate.add_argument("--model", default="runs/detect/train/weights/best.pt")
    evaluate.add_argument("--dry-run", action="store_true")
    evaluate.set_defaults(func=cmd_evaluate)

    baseline = subparsers.add_parser(
        "run-baseline",
        help="Run or print the RDD training plus Kazakhstan evaluation baseline workflow.",
    )
    baseline.add_argument("--rdd-root", default="data/external/RDD2022")
    baseline.add_argument("--rdd-output-dir", default="data/processed/rdd_yolo")
    baseline.add_argument("--kz-config", default="configs/dataset.yaml")
    baseline.add_argument("--experiments", default="data/manifests/experiments.csv")
    baseline.add_argument("--epochs", type=int, default=50)
    baseline.add_argument("--imgsz", type=int, default=640)
    baseline.add_argument("--batch", type=int)
    baseline.add_argument("--device", default="")
    baseline.add_argument("--workers", type=int)
    baseline.add_argument("--fraction", type=float)
    baseline.add_argument("--model", action="append", default=[])
    baseline.add_argument("--dry-run", action="store_true")
    baseline.set_defaults(func=cmd_run_baseline)

    record = subparsers.add_parser(
        "record-experiment",
        help="Append Ultralytics run metrics to the experiment ledger.",
    )
    record.add_argument("--run-dir", required=True)
    record.add_argument("--output", default="data/manifests/experiments.csv")
    record.add_argument("--phase", choices=["train", "eval", "smoke"], default="eval")
    record.add_argument("--eval-split", default="")
    record.add_argument("--training-dataset", default="")
    record.add_argument("--evaluation-dataset", default="")
    record.add_argument("--paper-eligible", action="store_true")
    record.add_argument("--notes", default="")
    record.set_defaults(func=cmd_record_experiment)

    eval_recorded = subparsers.add_parser(
        "evaluate-recorded",
        help="Evaluate a detector and append machine-readable metrics to the experiment ledger.",
    )
    eval_recorded.add_argument("--split", default="kz-test")
    eval_recorded.add_argument("--config", default="configs/dataset.yaml")
    eval_recorded.add_argument("--model", required=True)
    eval_recorded.add_argument("--model-label", default="")
    eval_recorded.add_argument("--name", default="")
    eval_recorded.add_argument(
        "--project",
        default=".",
        help="Ultralytics project root. The default writes under runs/detect/<name>.",
    )
    eval_recorded.add_argument("--experiments", default="data/manifests/experiments.csv")
    eval_recorded.add_argument("--imgsz", type=int, default=640)
    eval_recorded.add_argument("--batch", type=int)
    eval_recorded.add_argument("--workers", type=int)
    eval_recorded.add_argument("--device", default="")
    eval_recorded.add_argument("--training-dataset", default="")
    eval_recorded.add_argument("--evaluation-dataset", default="")
    eval_recorded.add_argument("--paper-eligible", action="store_true")
    eval_recorded.add_argument("--notes", default="")
    eval_recorded.set_defaults(func=cmd_evaluate_recorded)

    figures = subparsers.add_parser("figures", help="Generate paper-ready summary tables/figure data.")
    figures.add_argument("--paper", action="store_true")
    figures.add_argument("--manifest", default="data/manifests/images.csv")
    figures.add_argument("--annotations", default="data/manifests/annotations.csv")
    figures.add_argument("--experiments", default="data/manifests/experiments.csv")
    figures.add_argument("--rdd-summary", default="data/processed/rdd_yolo/import_summary.json")
    figures.add_argument("--output", default="reports/paper_summary.json")
    figures.add_argument("--experiment-table", default="reports/experiment_table.csv")
    figures.add_argument("--dataset-card", default="reports/dataset_card.md")
    figures.add_argument("--figures-dir", default="reports/figures")
    figures.set_defaults(func=cmd_figures)

    status = subparsers.add_parser(
        "project-status",
        help="Summarize finish-line readiness for the Applied Sciences submission package.",
    )
    status.add_argument("--manifest", default="data/manifests/images.csv")
    status.add_argument("--annotations", default="data/manifests/annotations.csv")
    status.add_argument("--cache-manifest", default="data/manifests/privacy_safe_files.csv")
    status.add_argument("--experiments", default="data/manifests/experiments.csv")
    status.add_argument("--rdd-root", default="data/external/RDD2022")
    status.add_argument("--paper-dir", default="paper")
    status.add_argument("--reports-dir", default="reports")
    status.add_argument("--yolo-dir", default="data/processed/yolo")
    status.add_argument("--output", default="reports/project_status.json")
    status.add_argument("--fail-on-blockers", action="store_true")
    status.set_defaults(func=cmd_project_status)

    triage = subparsers.add_parser("triage-sheet", help="Create a visual triage sheet from candidate rows.")
    triage.add_argument("--manifest", default="data/manifests/images.csv")
    triage.add_argument("--output", default="data/manifests/triage.csv")
    triage.add_argument("--license-ready-only", action="store_true")
    triage.add_argument(
        "--merge-existing",
        action="store_true",
        help="Preserve existing triage decisions for matching image_id rows in the output file.",
    )
    triage.set_defaults(func=cmd_triage_sheet)

    gallery = subparsers.add_parser("triage-gallery", help="Render an HTML gallery from triage rows.")
    gallery.add_argument("--triage", default="data/manifests/triage.csv")
    gallery.add_argument("--output", default="reports/triage_gallery.html")
    gallery.add_argument("--limit", type=int)
    gallery.add_argument("--photo-candidates-only", action="store_true")
    gallery.set_defaults(func=cmd_triage_gallery)

    apply = subparsers.add_parser("apply-triage", help="Promote reviewed triage rows back into the image manifest.")
    apply.add_argument("--manifest", default="data/manifests/images.csv")
    apply.add_argument("--triage", default="data/manifests/triage.csv")
    apply.add_argument("--output", default="data/manifests/images.csv")
    apply.add_argument("--report", default="reports/apply_triage_report.json")
    apply.set_defaults(func=cmd_apply_triage)

    download = subparsers.add_parser("download-candidates", help="Download triage candidates into the ignored local data cache.")
    download.add_argument("--triage", default="data/manifests/triage.csv")
    download.add_argument("--output-dir", default="data/raw/candidates")
    download.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    download.add_argument("--limit", type=int)
    download.add_argument("--include-non-photo", action="store_true")
    download.add_argument("--overwrite", action="store_true")
    download.add_argument("--thumbnail-width", type=int, default=960)
    download.add_argument("--original", action="store_true")
    download.add_argument("--max-mb", type=int, default=20)
    download.add_argument("--verbose", action="store_true")
    download.add_argument("--request-delay", type=float, default=2.0)
    download.add_argument("--unreviewed-only", action="store_true")
    download.add_argument("--retry-failed", action="store_true")
    download.add_argument("--image-id-prefix", default="", help="Only download rows whose image_id starts with this prefix.")
    download.set_defaults(func=cmd_download_candidates)

    local_gallery = subparsers.add_parser("local-gallery", help="Render an offline gallery from downloaded local files.")
    local_gallery.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    local_gallery.add_argument("--output", default="reports/local_gallery.html")
    local_gallery.add_argument("--limit", type=int)
    local_gallery.add_argument("--image-id-prefix", default="", help="Only include rows whose image_id starts with this prefix.")
    local_gallery.set_defaults(func=cmd_local_gallery)

    score = subparsers.add_parser("score-candidates", help="Score cached candidates to prioritize visual triage.")
    score.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    score.add_argument("--output", default="data/manifests/model_scores.csv")
    score.add_argument("--backend", choices=["clip", "keyword"], default="clip")
    score.add_argument("--model", default="openai/clip-vit-base-patch32")
    score.add_argument("--model-cache-dir", default="data/external/hf-cache")
    score.add_argument(
        "--allow-model-download",
        action="store_true",
        help="Allow downloading CLIP model files if they are missing from the local cache.",
    )
    score.add_argument("--limit", type=int)
    score.add_argument("--include-failed", action="store_true")
    score.add_argument("--image-id-prefix", default="", help="Only score rows whose image_id starts with this prefix.")
    score.set_defaults(func=cmd_score_candidates)

    review_queue = subparsers.add_parser("review-queue", help="Join CLIP scores and triage rows into a ranked review queue.")
    review_queue.add_argument("--scores", default="data/manifests/model_scores.csv")
    review_queue.add_argument("--triage", default="data/manifests/triage.csv")
    review_queue.add_argument("--output", default="data/manifests/review_queue.csv")
    review_queue.add_argument("--include-reviewed", action="store_true")
    review_queue.add_argument(
        "--include-triage-action",
        action="append",
        default=[],
        help="Include rows with this triage recommended_action even when reviewed rows are skipped.",
    )
    review_queue.add_argument(
        "--exclude-suggested",
        action="append",
        default=["review_exclude"],
        help="Suggested action to omit; repeat to omit multiple actions.",
    )
    review_queue.add_argument("--limit", type=int)
    review_queue.add_argument("--image-id-prefix", default="", help="Only queue rows whose image_id starts with this prefix.")
    review_queue.set_defaults(func=cmd_review_queue)

    auto_triage = subparsers.add_parser(
        "auto-triage",
        help="Apply conservative model-assisted triage decisions to unreviewed rows.",
    )
    auto_triage.add_argument("--scores", default="data/manifests/model_scores.csv")
    auto_triage.add_argument("--triage", default="data/manifests/triage.csv")
    auto_triage.add_argument("--output", default="data/manifests/triage.csv")
    auto_triage.add_argument("--include-reviewed", action="store_true")
    auto_triage.add_argument("--dry-run", action="store_true")
    auto_triage.add_argument("--road-min", type=float, default=0.12)
    auto_triage.add_argument("--non-road-exclude", type=float, default=0.45)
    auto_triage.add_argument("--privacy-review", type=float, default=0.35)
    auto_triage.add_argument("--damage-review", type=float, default=0.25)
    auto_triage.add_argument("--normal-review", type=float, default=0.50)
    auto_triage.set_defaults(func=cmd_auto_triage)

    export_classification = subparsers.add_parser(
        "export-classification-dataset",
        help="Export publishable image-level rows into a classification dataset folder.",
    )
    export_classification.add_argument("--manifest", default="data/manifests/images.csv")
    export_classification.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    export_classification.add_argument("--output-dir", default="data/processed/classification")
    export_classification.add_argument("--no-copy", action="store_true")
    export_classification.set_defaults(func=cmd_export_classification_dataset)

    annotation_queue = subparsers.add_parser(
        "annotation-queue",
        help="Export publishable damaged rows that need bounding-box annotation.",
    )
    annotation_queue.add_argument("--manifest", default="data/manifests/images.csv")
    annotation_queue.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    annotation_queue.add_argument("--output", default="data/manifests/annotation_queue.csv")
    annotation_queue.set_defaults(func=cmd_annotation_queue)

    validate_annotations = subparsers.add_parser(
        "validate-annotations",
        help="Validate bounding-box annotations before YOLO export.",
    )
    validate_annotations.add_argument("--annotations", default="data/manifests/annotations.csv")
    validate_annotations.add_argument("--cache-manifest", default="data/manifests/privacy_safe_files.csv")
    validate_annotations.set_defaults(func=cmd_validate_annotations)

    draft_annotation_parser = subparsers.add_parser(
        "draft-annotations",
        help="Create weak draft bounding boxes for damaged annotation-queue rows.",
    )
    draft_annotation_parser.add_argument("--queue", default="data/manifests/annotation_queue.csv")
    draft_annotation_parser.add_argument("--output", default="data/manifests/annotations.csv")
    draft_annotation_parser.add_argument("--preview-dir", default="reports/annotation_previews")
    draft_annotation_parser.add_argument("--overwrite", action="store_true")
    draft_annotation_parser.add_argument("--max-boxes-per-image", type=int, default=4)
    draft_annotation_parser.set_defaults(func=cmd_draft_annotations)

    privacy_scan = subparsers.add_parser(
        "privacy-scan",
        help="Scan cached local images for faces and optional license-plate-like regions.",
    )
    privacy_scan.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    privacy_scan.add_argument("--output", default="data/manifests/privacy_report.csv")
    privacy_scan.add_argument("--limit", type=int)
    privacy_scan.add_argument("--include-failed", action="store_true")
    privacy_scan.add_argument(
        "--detect-plates",
        action="store_true",
        help="Enable experimental license-plate-like region detection. Expect false positives.",
    )
    privacy_scan.set_defaults(func=cmd_privacy_scan)

    blur_privacy = subparsers.add_parser(
        "blur-privacy",
        help="Create blurred local derivatives for rows flagged by privacy-scan.",
    )
    blur_privacy.add_argument("--privacy-report", default="data/manifests/privacy_report.csv")
    blur_privacy.add_argument("--output-dir", default="data/processed/privacy_blurred")
    blur_privacy.add_argument("--output-manifest", default="data/manifests/privacy_blurred_files.csv")
    blur_privacy.set_defaults(func=cmd_blur_privacy)

    apply_privacy = subparsers.add_parser(
        "apply-privacy",
        help="Apply privacy-scan/blur outcomes back to triage rows.",
    )
    apply_privacy.add_argument("--triage", default="data/manifests/triage.csv")
    apply_privacy.add_argument("--privacy-report", default="data/manifests/privacy_report.csv")
    apply_privacy.add_argument("--blur-manifest", default="data/manifests/privacy_blurred_files.csv")
    apply_privacy.add_argument("--output", default="data/manifests/triage.csv")
    apply_privacy.add_argument(
        "--trust-clear",
        action="store_true",
        help="Mark no-detection rows privacy_ok=true. Use only after spot-check calibration.",
    )
    apply_privacy.set_defaults(func=cmd_apply_privacy)

    privacy_cache = subparsers.add_parser(
        "privacy-cache",
        help="Merge raw cache rows with blurred derivatives for privacy-safe exports.",
    )
    privacy_cache.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    privacy_cache.add_argument(
        "--extra-cache-manifest",
        action="append",
        default=[],
        help="Additional local cache manifest to merge into the privacy-safe cache; repeat for multiple sources.",
    )
    privacy_cache.add_argument("--blur-manifest", default="data/manifests/privacy_blurred_files.csv")
    privacy_cache.add_argument("--output", default="data/manifests/privacy_safe_files.csv")
    privacy_cache.set_defaults(func=cmd_privacy_cache)

    batch = subparsers.add_parser(
        "batch-intake",
        help="Run the scalable intake loop: download, score, auto-triage, privacy processing, and review queue.",
    )
    batch.add_argument("--triage", default="data/manifests/triage.csv")
    batch.add_argument("--download-dir", default="data/raw/candidates")
    batch.add_argument("--cache-manifest", default="data/manifests/local_files.csv")
    batch.add_argument("--limit", type=int, default=100)
    batch.add_argument("--thumbnail-width", type=int, default=960)
    batch.add_argument("--request-delay", type=float, default=6.0)
    batch.add_argument("--max-mb", type=int, default=20)
    batch.add_argument("--include-non-photo", action="store_true")
    batch.add_argument("--retry-failed", action="store_true")
    batch.add_argument("--overwrite", action="store_true")
    batch.add_argument("--scores", default="data/manifests/model_scores.csv")
    batch.add_argument("--backend", choices=["clip", "keyword"], default="clip")
    batch.add_argument("--model", default="openai/clip-vit-base-patch32")
    batch.add_argument("--model-cache-dir", default="data/external/hf-cache")
    batch.add_argument("--allow-model-download", action="store_true")
    batch.add_argument("--privacy-report", default="data/manifests/privacy_report.csv")
    batch.add_argument("--blur-dir", default="data/processed/privacy_blurred")
    batch.add_argument("--blur-manifest", default="data/manifests/privacy_blurred_files.csv")
    batch.add_argument("--privacy-safe-cache", default="data/manifests/privacy_safe_files.csv")
    batch.add_argument("--review-queue", default="data/manifests/review_queue.csv")
    batch.add_argument("--queue-limit", type=int, default=100)
    batch.add_argument("--skip-download", action="store_true")
    batch.add_argument("--skip-scoring", action="store_true")
    batch.add_argument("--skip-privacy", action="store_true")
    batch.add_argument("--trust-clear", action="store_true")
    batch.add_argument("--detect-plates", action="store_true")
    batch.add_argument("--dry-run", action="store_true")
    batch.add_argument("--quiet-download", action="store_true")
    batch.set_defaults(func=cmd_batch_intake)

    return parser


def cmd_collect(args: argparse.Namespace) -> int:
    source_path = Path(args.sources)
    output_path = Path(args.output)
    errors = validate_manifest_columns(source_path, SOURCE_MANIFEST_FIELDS)
    if errors:
        return _fail(errors)

    sources = read_csv(source_path)
    existing = read_csv(output_path) if output_path.exists() else []
    existing_ids = {row.get("image_id", "") for row in existing}
    rows = list(existing)

    for source in sources:
        image_id = f"lead_{source['source_id']}"
        if image_id in existing_ids:
            continue
        rows.append(
            {
                "image_id": image_id,
                "source_url": source["source_url"],
                "download_url": "",
                "license": "",
                "author": "",
                "country": "Kazakhstan",
                "region": "",
                "city": "",
                "capture_context": source["source_type"],
                "damage_labels": "unknown",
                "split": "",
                "license_ok": "false",
                "privacy_checked": "false",
                "notes": f"Discovery lead from {source['source_name']}; verify per-image license before use.",
            }
        )

    write_csv(output_path, rows, IMAGE_MANIFEST_FIELDS)
    print(f"Wrote {len(rows)} manifest rows to {output_path}")
    return 0


def cmd_collect_commons(args: argparse.Namespace) -> int:
    output = Path(args.output)
    existing = read_csv(output) if output.exists() else []
    rows = collect_commons_category(
        args.category,
        limit=args.limit,
        include_subcategories=args.include_subcategories,
        max_depth=args.max_depth,
    )
    added, updated = append_rows(output, existing, rows)
    license_ready = sum(1 for row in rows if normalize_bool(row.get("license_ok", "")))
    print(
        f"Collected {len(rows)} Commons candidates from {args.category}; "
        f"added {added}; updated {updated}; "
        f"{license_ready} have license metadata ready for privacy review."
    )
    return 0


def cmd_collect_commons_batch(args: argparse.Namespace) -> int:
    categories_path = Path(args.categories)
    output = Path(args.output)
    errors = validate_manifest_columns(categories_path, COMMONS_CATEGORY_FIELDS)
    if errors:
        return _fail(errors)

    category_rows = read_csv(categories_path)
    report_rows = []
    total_collected = 0
    total_added = 0
    total_updated = 0
    failed = 0

    active_rows = [
        row
        for row in category_rows
        if row.get("category", "").strip() and not row.get("category", "").strip().startswith("#")
    ]
    if args.offset:
        active_rows = active_rows[args.offset :]
    if args.max_categories is not None:
        active_rows = active_rows[: args.max_categories]

    for index, row in enumerate(active_rows, start=1):
        category = row.get("category", "").strip()
        limit = args.limit if args.limit is not None else _parse_int(row.get("limit", ""), 100)
        include_subcategories = normalize_bool(row.get("include_subcategories", ""))
        max_depth = _parse_int(row.get("max_depth", ""), 0)
        print(
            f"[{index}/{len(active_rows)}] collecting {category} "
            f"(limit={limit}, subcategories={include_subcategories}, max_depth={max_depth})",
            flush=True,
        )
        try:
            rows = collect_commons_category(
                category,
                limit=limit,
                include_subcategories=include_subcategories,
                max_depth=max_depth,
            )
            existing = read_csv(output) if output.exists() else []
            added, updated = append_rows(output, existing, rows)
            license_ready = sum(1 for item in rows if normalize_bool(item.get("license_ok", "")))
            total_collected += len(rows)
            total_added += added
            total_updated += updated
            report_rows.append(
                {
                    "category": category,
                    "limit": limit,
                    "include_subcategories": include_subcategories,
                    "max_depth": max_depth,
                    "collected": len(rows),
                    "added": added,
                    "updated": updated,
                    "license_ready": license_ready,
                    "status": "ok",
                    "error": "",
                }
            )
            print(
                f"{category}: collected {len(rows)}, added {added}, "
                f"updated {updated}, license-ready {license_ready}.",
                flush=True,
            )
        except RuntimeError as exc:
            failed += 1
            report_rows.append(
                {
                    "category": category,
                    "limit": limit,
                    "include_subcategories": include_subcategories,
                    "max_depth": max_depth,
                    "collected": 0,
                    "added": 0,
                    "updated": 0,
                    "license_ready": 0,
                    "status": "failed",
                    "error": str(exc),
                }
            )
            print(f"{category}: failed: {exc}", file=sys.stderr)

    report = {
        "categories": report_rows,
        "total_collected": total_collected,
        "total_added": total_added,
        "total_updated": total_updated,
        "failed": failed,
        "output": str(output),
    }
    _write_json(Path(args.report), report)
    print(
        f"Commons batch complete: collected {total_collected}, added {total_added}, "
        f"updated {total_updated}, failed {failed}. Report: {args.report}"
    )
    return 0 if failed == 0 else 2


def cmd_collect_commons_search(args: argparse.Namespace) -> int:
    output = Path(args.output)
    report_rows = []
    total_collected = 0
    total_added = 0
    total_updated = 0
    failed = 0

    for index, query in enumerate(args.query, start=1):
        print(f"[{index}/{len(args.query)}] searching Commons for {query!r} (limit={args.limit})", flush=True)
        try:
            rows = collect_commons_search(query, limit=args.limit)
            existing = read_csv(output) if output.exists() else []
            added, updated = append_rows(output, existing, rows)
            license_ready = sum(1 for item in rows if normalize_bool(item.get("license_ok", "")))
            total_collected += len(rows)
            total_added += added
            total_updated += updated
            report_rows.append(
                {
                    "query": query,
                    "limit": args.limit,
                    "collected": len(rows),
                    "added": added,
                    "updated": updated,
                    "license_ready": license_ready,
                    "status": "ok",
                    "error": "",
                }
            )
            print(
                f"{query}: collected {len(rows)}, added {added}, "
                f"updated {updated}, license-ready {license_ready}.",
                flush=True,
            )
        except RuntimeError as error:
            failed += 1
            report_rows.append(
                {
                    "query": query,
                    "limit": args.limit,
                    "collected": 0,
                    "added": 0,
                    "updated": 0,
                    "license_ready": 0,
                    "status": "failed",
                    "error": str(error),
                }
            )
            print(f"{query}: failed: {error}", flush=True)

    report = {
        "queries": report_rows,
        "total_collected": total_collected,
        "total_added": total_added,
        "total_updated": total_updated,
        "failed": failed,
    }
    _write_json(Path(args.report), report)
    print(
        f"Commons search complete: collected {total_collected}, added {total_added}, "
        f"updated {total_updated}, failed {failed}. Report: {args.report}"
    )
    return 0 if failed == 0 else 2


def cmd_collect_openverse_search(args: argparse.Namespace) -> int:
    output = Path(args.output)
    report_rows = []
    total_collected = 0
    total_added = 0
    total_updated = 0
    total_license_ready = 0
    failed = 0

    for index, query in enumerate(args.query, start=1):
        print(f"[{index}/{len(args.query)}] searching Openverse for {query!r} (limit={args.limit})", flush=True)
        try:
            rows = collect_openverse_search(
                query,
                limit=args.limit,
                trust_openverse_license=args.trust_openverse_license,
            )
            existing = read_csv(output) if output.exists() else []
            added, updated = append_rows(output, existing, rows)
            license_ready = sum(1 for item in rows if normalize_bool(item.get("license_ok", "")))
            total_collected += len(rows)
            total_added += added
            total_updated += updated
            total_license_ready += license_ready
            report_rows.append(
                {
                    "query": query,
                    "limit": args.limit,
                    "collected": len(rows),
                    "added": added,
                    "updated": updated,
                    "license_ready": license_ready,
                    "trust_openverse_license": args.trust_openverse_license,
                    "status": "ok",
                    "error": "",
                }
            )
            print(
                f"{query}: collected {len(rows)}, added {added}, "
                f"updated {updated}, license-ready {license_ready}.",
                flush=True,
            )
        except RuntimeError as error:
            failed += 1
            report_rows.append(
                {
                    "query": query,
                    "limit": args.limit,
                    "collected": 0,
                    "added": 0,
                    "updated": 0,
                    "license_ready": 0,
                    "trust_openverse_license": args.trust_openverse_license,
                    "status": "failed",
                    "error": str(error),
                }
            )
            print(f"{query}: failed: {error}", flush=True)

    report = {
        "queries": report_rows,
        "total_collected": total_collected,
        "total_added": total_added,
        "total_updated": total_updated,
        "total_license_ready": total_license_ready,
        "trust_openverse_license": args.trust_openverse_license,
        "failed": failed,
        "default_policy": "Rows are discovery leads unless --trust-openverse-license is used.",
    }
    _write_json(Path(args.report), report)
    print(
        f"Openverse search complete: collected {total_collected}, added {total_added}, "
        f"updated {total_updated}, license-ready {total_license_ready}, failed {failed}. "
        f"Report: {args.report}"
    )
    return 0 if failed == 0 else 2


def cmd_collect_mapillary(args: argparse.Namespace) -> int:
    output = Path(args.output)
    token = args.access_token or os.environ.get("MAPILLARY_ACCESS_TOKEN", "")
    try:
        bbox = CITY_BBOXES[args.city] if args.city else parse_bbox(args.bbox)
    except ValueError as error:
        return _fail([str(error)])

    label = args.city or args.bbox
    print(f"Collecting Mapillary imagery for {label!r} (limit={args.limit})", flush=True)
    try:
        rows = collect_mapillary_bbox(
            bbox,
            access_token=token,
            limit=args.limit,
            city=args.city or "",
            region=args.region,
            thumbnail_size=args.thumbnail_size,
            min_captured_at=args.min_captured_at,
            max_captured_at=args.max_captured_at,
            request_delay=args.request_delay,
            grid_size=args.grid_size,
        )
    except RuntimeError as error:
        report = {
            "area": label,
            "bbox": ",".join(str(value) for value in bbox),
            "limit": args.limit,
            "collected": 0,
            "added": 0,
            "updated": 0,
            "license_ready": 0,
            "grid_size": args.grid_size,
            "status": "failed",
            "error": str(error),
            "policy": "Mapillary rows are license-ready leads, but privacy_checked remains false until review.",
        }
        _write_json(Path(args.report), report)
        print(f"Mapillary collection failed: {error}", flush=True)
        return 2

    existing = read_csv(output) if output.exists() else []
    added, updated = append_rows(output, existing, rows)
    license_ready = sum(1 for item in rows if normalize_bool(item.get("license_ok", "")))
    report = {
        "area": label,
        "bbox": ",".join(str(value) for value in bbox),
        "limit": args.limit,
        "collected": len(rows),
        "added": added,
        "updated": updated,
        "license_ready": license_ready,
            "thumbnail_size": args.thumbnail_size,
            "grid_size": args.grid_size,
            "status": "ok",
        "error": "",
        "policy": "Mapillary rows are license-ready leads, but privacy_checked remains false until review.",
    }
    _write_json(Path(args.report), report)
    print(
        f"Mapillary collection complete: collected {len(rows)}, added {added}, "
        f"updated {updated}, license-ready {license_ready}. Report: {args.report}",
        flush=True,
    )
    return 0


def cmd_audit_licenses(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if errors:
        return _fail(errors)

    rows = read_csv(manifest)
    findings = [finding for row in rows for finding in audit_image_row(row)]
    publishable = [
        row
        for row in rows
        if normalize_bool(row.get("license_ok", ""))
        and normalize_bool(row.get("privacy_checked", ""))
        and not audit_image_row(row)
    ]

    report = {
        "manifest": str(manifest),
        "total_rows": len(rows),
        "publishable_rows": len(publishable),
        "finding_count": len(findings),
        "findings": [finding.__dict__ for finding in findings],
    }
    _write_json(Path(args.report), report)
    print(f"Audit complete: {len(publishable)}/{len(rows)} publishable rows. Report: {args.report}")
    return 0 if not findings else 2


def cmd_dedupe(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if errors:
        return _fail(errors)

    rows = read_csv(manifest)
    by_hash: dict[str, list[str]] = defaultdict(list)
    missing_local_files = 0

    for row in rows:
        local_path = row.get("local_path") or row.get("file_path") or ""
        if not local_path:
            missing_local_files += 1
            continue
        path = Path(local_path)
        if not path.exists():
            missing_local_files += 1
            continue
        by_hash[_sha256(path)].append(row.get("image_id", str(path)))

    duplicates = {digest: ids for digest, ids in by_hash.items() if len(ids) > 1}
    report = {
        "manifest": str(manifest),
        "hashed_files": sum(len(ids) for ids in by_hash.values()),
        "missing_local_files": missing_local_files,
        "duplicate_groups": duplicates,
    }
    _write_json(Path(args.report), report)
    print(f"Dedupe complete: {len(duplicates)} duplicate groups. Report: {args.report}")
    return 0


def cmd_split_dataset(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if errors:
        return _fail(errors)
    summary = assign_dataset_splits(
        manifest,
        Path(args.output),
        seed=args.seed,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_split=args.test_split,
    )
    print(
        f"Assigned {summary['assigned']} publishable rows "
        f"({summary['damaged']} damaged, {summary['normal']} normal): "
        f"train={summary['train']}, val={summary['val']}, "
        f"test={summary['test']}, kz-test={summary['kz-test']}."
    )
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    cache_manifest = Path(args.cache_manifest)
    annotations = Path(args.annotations)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if errors:
        return _fail(errors)
    if not cache_manifest.exists():
        return _fail([f"Missing cache manifest: {cache_manifest}"])
    if not annotations.exists():
        return _fail([f"Missing annotations file: {annotations}"])

    output_dir = Path(args.output_dir)
    try:
        summary = prepare_yolo_dataset(manifest, cache_manifest, annotations, output_dir)
    except ValueError as error:
        return _fail([str(error)])

    config_path = Path(args.config)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if yaml is None and config_path.exists():
        _replace_yaml_scalar(config_path, "path", str(output_dir))
    else:
        config = _load_yaml_config(config_path) if config_path.exists() else {}
        config["path"] = str(output_dir)
        config_path.write_text(_dump_yaml_config(config), encoding="utf-8")

    print(
        "Prepared YOLO dataset. "
        f"Copied {summary['copied_images']} images; "
        f"wrote {summary['written_label_files']} label files; "
        f"skipped {summary['skipped_missing_annotations']} damaged rows without annotations; "
        f"{summary['invalid_annotations']} invalid annotation rows."
    )
    return 0


def cmd_check_rdd(args: argparse.Namespace) -> int:
    summary = check_rdd_readiness(Path(args.rdd_root))
    _write_json(Path(args.report), summary)
    print(
        f"RDD readiness: {summary['status']}; "
        f"xml={summary['xml_files']}, matched={summary['matched_images']}, "
        f"usable={summary['usable_images']}, boxes={summary['boxes']}. "
        f"Report: {args.report}"
    )
    if args.fail_on_not_ready and summary["status"] != "ready":
        return 2
    return 0


def cmd_rdd_download_plan(args: argparse.Namespace) -> int:
    countries = args.country or PRACTICAL_RDD2022_COUNTRIES
    try:
        script = rdd_download_script(countries, Path(args.output_dir))
    except ValueError as error:
        return _fail([str(error)])
    script_path = Path(args.script)
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script, encoding="utf-8")
    print(
        f"Wrote RDD2022 download plan for {', '.join(countries)} to {script_path}. "
        "Review terms and file sizes before running it."
    )
    return 0


def cmd_import_rdd_voc(args: argparse.Namespace) -> int:
    summary = import_rdd_voc_dataset(
        Path(args.rdd_root),
        Path(args.output_dir),
        seed=args.seed,
        val_ratio=args.val_ratio,
        copy_mode=args.copy_mode,
        limit=args.limit,
    )
    print(
        f"RDD import complete: discovered {summary['discovered']}, "
        f"imported {summary['imported']} images, wrote {summary['boxes']} boxes, "
        f"skipped {summary['skipped_empty']} empty/unsupported annotation files. "
        f"Dataset config: {Path(args.output_dir) / 'dataset.yaml'}"
    )
    return 0 if summary["imported"] > 0 else 2


def cmd_train(args: argparse.Namespace) -> int:
    yolo = _resolve_executable("yolo")
    command = [
        yolo,
        "detect",
        "train",
        f"data={args.config}",
        f"model={args.model}",
        f"epochs={args.epochs}",
        f"imgsz={args.imgsz}",
    ]
    if args.dry_run:
        print(" ".join(command))
        return 0
    if yolo == "yolo" and shutil.which("yolo") is None:
        return _fail(["Ultralytics CLI not found. Install with: python -m pip install -e \".[ml]\""])
    start = perf_counter()
    result = subprocess.run(command, check=False, env=_subprocess_env())
    print(f"Training finished in {perf_counter() - start:.1f}s")
    return result.returncode


def cmd_evaluate(args: argparse.Namespace) -> int:
    yolo = _resolve_executable("yolo")
    split = "test" if args.split == "kz-test" else args.split
    command = [
        yolo,
        "detect",
        "val",
        f"data={args.config}",
        f"model={args.model}",
        f"split={split}",
    ]
    if args.dry_run:
        print(" ".join(command))
        return 0
    if yolo == "yolo" and shutil.which("yolo") is None:
        return _fail(["Ultralytics CLI not found. Install with: python -m pip install -e \".[ml]\""])
    result = subprocess.run(command, check=False, env=_subprocess_env())
    return result.returncode


def cmd_run_baseline(args: argparse.Namespace) -> int:
    commands = baseline_commands(
        rdd_root=args.rdd_root,
        rdd_output_dir=args.rdd_output_dir,
        kz_config=args.kz_config,
        experiments=args.experiments,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        fraction=args.fraction,
        models=args.model or None,
    )
    if args.dry_run:
        print("Baseline dry run:")
        for command in commands:
            print(" ".join(command))
        return 0

    for command in commands:
        if command[0] == "yolo" and shutil.which("yolo") is None:
            resolved = _resolve_executable("yolo")
            command = [resolved] + command[1:]
            if resolved == "yolo" and shutil.which("yolo") is None:
                return _fail(["Ultralytics CLI not found. Install with: python -m pip install -e \".[ml]\""])
        print("Running: " + " ".join(command), flush=True)
        result = subprocess.run(command, check=False, env=_subprocess_env())
        if result.returncode != 0:
            return result.returncode
    return 0


def cmd_record_experiment(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    if not run_dir.exists():
        return _fail([f"Missing run directory: {run_dir}"])
    try:
        record = record_experiment(
            run_dir,
            Path(args.output),
            phase=args.phase,
            eval_split=args.eval_split,
            training_dataset=args.training_dataset,
            evaluation_dataset=args.evaluation_dataset,
            paper_eligible=args.paper_eligible,
            notes=args.notes,
        )
    except ValueError as error:
        return _fail([str(error)])
    print(
        f"Recorded experiment {record['experiment_id']} "
        f"({record['phase']}, split={record['eval_split'] or 'unspecified'}) "
        f"to {args.output}."
    )
    return 0


def cmd_evaluate_recorded(args: argparse.Namespace) -> int:
    model_path = Path(args.model)
    if not model_path.exists():
        return _fail([f"Missing model weights: {model_path}"])
    config_path = Path(args.config)
    if not config_path.exists():
        return _fail([f"Missing dataset config: {config_path}"])
    name = args.name or f"{model_path.stem}_eval"
    try:
        record = evaluate_and_record(
            model_path=model_path,
            config_path=config_path,
            split=args.split,
            name=name,
            project=Path(args.project),
            experiments_path=Path(args.experiments),
            imgsz=args.imgsz,
            batch=args.batch,
            workers=args.workers,
            device=args.device,
            model_label=args.model_label,
            training_dataset=args.training_dataset,
            evaluation_dataset=args.evaluation_dataset,
            paper_eligible=args.paper_eligible,
            notes=args.notes,
        )
    except (RuntimeError, ValueError) as error:
        return _fail([str(error)])
    print(
        f"Recorded evaluation {record['experiment_id']} "
        f"({record['model']}, split={record['eval_split']}) "
        f"to {args.experiments}."
    )
    return 0


def cmd_figures(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if errors:
        return _fail(errors)
    rows = read_csv(manifest)
    annotations_path = Path(args.annotations)
    annotations = read_csv(annotations_path) if annotations_path.exists() else []

    by_country = Counter(row.get("country", "unknown") or "unknown" for row in rows)
    by_split = Counter(row.get("split", "unsplit") or "unsplit" for row in rows)
    by_license = Counter(row.get("license", "unknown") or "unknown" for row in rows)
    by_label = Counter()
    publishable_rows = [
        row
        for row in rows
        if normalize_bool(row.get("license_ok", ""))
        and normalize_bool(row.get("privacy_checked", ""))
        and not audit_image_row(row)
        and row.get("damage_labels", "") not in {"", "unknown"}
    ]
    for row in rows:
        labels = [label.strip() for label in row.get("damage_labels", "").split(";") if label.strip()]
        by_label.update(labels or ["unknown"])

    experiments = read_csv(Path(args.experiments)) if Path(args.experiments).exists() else []
    paper_experiments = [row for row in experiments if normalize_bool(row.get("paper_eligible", ""))]
    best_experiments = best_experiments_by_model_split(paper_experiments)
    rdd_summary = _read_json(Path(args.rdd_summary)) if Path(args.rdd_summary).exists() else {}
    dataset = dataset_summary(rows, annotations)
    figures_dir = Path(args.figures_dir)
    sample_annotation = ""
    if args.paper:
        sample_annotation = copy_sample_annotation_figure(
            Path("reports/annotation_previews_gold"),
            figures_dir,
        )

    summary = {
        "total_rows": len(rows),
        "publishable_rows": len(publishable_rows),
        "by_country": dict(by_country),
        "by_split": dict(by_split),
        "by_license": dict(by_license),
        "by_damage_label": dict(by_label),
        "rdd_import_summary": rdd_summary,
        "experiment_count": len(experiments),
        "paper_eligible_experiment_count": len(paper_experiments),
        "best_experiments": best_experiments,
        "dataset_summary": dataset,
        "sample_annotation_figure": sample_annotation,
    }
    _write_json(Path(args.output), summary)
    if args.paper:
        write_csv(Path(args.experiment_table), best_experiments, EXPERIMENT_TABLE_FIELDS)
        write_dataset_card(Path(args.dataset_card), dataset)
        write_csv(figures_dir / "dataset_summary_table.csv", summary_table_rows(dataset), ["metric", "value"])
        write_csv(figures_dir / "class_distribution_table.csv", count_rows(dataset["by_annotation_class"]), ["item", "count"])
        write_csv(figures_dir / "split_distribution_table.csv", count_rows(dataset["by_split"]), ["item", "count"])
        write_csv(figures_dir / "rdd_import_summary_table.csv", summary_table_rows(rdd_summary), ["metric", "value"])
    print(f"Paper summary data written to {args.output}")
    return 0


def cmd_project_status(args: argparse.Namespace) -> int:
    status = project_status(
        manifest_path=Path(args.manifest),
        annotations_path=Path(args.annotations),
        cache_manifest_path=Path(args.cache_manifest),
        experiments_path=Path(args.experiments),
        rdd_root=Path(args.rdd_root),
        paper_dir=Path(args.paper_dir),
        reports_dir=Path(args.reports_dir),
        yolo_dir=Path(args.yolo_dir),
    )
    _write_json(Path(args.output), status)
    print(
        f"Project status: {status['status']}; "
        f"{len(status['blockers'])} blockers, {len(status['warnings'])} warnings. "
        f"Report: {args.output}"
    )
    for blocker in status["blockers"]:
        print(f"blocker: {blocker}")
    return 2 if args.fail_on_blockers and status["blockers"] else 0


def cmd_triage_sheet(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if errors:
        return _fail(errors)

    rows = read_csv(manifest)
    output = Path(args.output)
    existing_by_id = {}
    if args.merge_existing and output.exists():
        errors = validate_triage_columns(output)
        if errors:
            return _fail(errors)
        existing_by_id = {row.get("image_id", ""): row for row in read_csv(output)}
    triage_rows = []
    preserved = 0
    added = 0
    for row in rows:
        if args.license_ready_only and not normalize_bool(row.get("license_ok", "")):
            continue
        if row.get("image_id", "").startswith("lead_"):
            continue
        image_id = row.get("image_id", "")
        if image_id in existing_by_id:
            merged = dict(existing_by_id[image_id])
            for field in [
                "source_url",
                "download_url",
                "license",
                "author",
                "capture_context",
                "license_ok",
                "privacy_checked",
            ]:
                merged[field] = row.get(field, merged.get(field, ""))
            if not merged.get("damage_labels", "").strip():
                merged["damage_labels"] = row.get("damage_labels", "")
            triage_rows.append(merged)
            preserved += 1
            continue
        notes = row.get("notes", "")
        triage_rows.append(
            {
                "image_id": image_id,
                "source_url": row.get("source_url", ""),
                "download_url": row.get("download_url", ""),
                "license": row.get("license", ""),
                "author": row.get("author", ""),
                "capture_context": row.get("capture_context", ""),
                "damage_labels": row.get("damage_labels", ""),
                "license_ok": row.get("license_ok", ""),
                "privacy_checked": row.get("privacy_checked", ""),
                "is_photo_candidate": str("Triage warning" not in notes).lower(),
                "road_surface_visible": "",
                "target_damage_visible": "",
                "privacy_ok": "",
                "recommended_action": "",
                "reviewer": "",
                "notes": notes,
            }
        )
        added += 1

    write_csv(output, triage_rows, TRIAGE_FIELDS)
    if args.merge_existing:
        print(f"Wrote {len(triage_rows)} triage rows to {args.output}; preserved {preserved}, added {added}.")
    else:
        print(f"Wrote {len(triage_rows)} triage rows to {args.output}")
    return 0


def cmd_triage_gallery(args: argparse.Namespace) -> int:
    errors = validate_triage_columns(Path(args.triage))
    if errors:
        return _fail(errors)
    summary = generate_gallery(
        Path(args.triage),
        Path(args.output),
        limit=args.limit,
        photo_candidates_only=args.photo_candidates_only,
    )
    print(f"Wrote triage gallery with {summary['rows']} rows to {args.output}")
    return 0


def cmd_apply_triage(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    triage = Path(args.triage)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    errors.extend(validate_triage_columns(triage))
    if errors:
        return _fail(errors)
    report = apply_triage(manifest, triage, Path(args.output))
    _write_json(Path(args.report), report)
    print(
        f"Applied triage: promoted {report['promoted']} rows, "
        f"{report.get('already_promoted', 0)} already promoted, "
        f"skipped {report['skipped']} include requests. Report: {args.report}"
    )
    return 0 if report["skipped"] == 0 else 2


def cmd_download_candidates(args: argparse.Namespace) -> int:
    errors = validate_triage_columns(Path(args.triage))
    if errors:
        return _fail(errors)
    summary = download_candidates(
        Path(args.triage),
        Path(args.output_dir),
        Path(args.cache_manifest),
        limit=args.limit,
        photo_candidates_only=not args.include_non_photo,
        overwrite=args.overwrite,
        thumbnail_width=args.thumbnail_width,
        original=args.original,
        max_bytes=args.max_mb * 1024 * 1024,
        verbose=args.verbose,
        request_delay=args.request_delay,
        unreviewed_only=args.unreviewed_only,
        retry_failed=args.retry_failed,
        image_id_prefix=args.image_id_prefix,
    )
    print(
        "Candidate download complete: "
        f"{summary['downloaded']} downloaded, "
        f"{summary['skipped_existing']} existing, "
        f"{summary['skipped_failed_cache']} skipped failed-cache, "
        f"{summary['failed']} failed "
        f"out of {summary['candidates']} candidates."
    )
    return 0 if summary["failed"] == 0 else 2


def cmd_local_gallery(args: argparse.Namespace) -> int:
    cache_manifest = Path(args.cache_manifest)
    if not cache_manifest.exists():
        return _fail([f"Missing local cache manifest: {cache_manifest}"])
    summary = generate_local_gallery(
        cache_manifest,
        Path(args.output),
        limit=args.limit,
        image_id_prefix=args.image_id_prefix,
    )
    print(f"Wrote local gallery with {summary['rows']} rows to {args.output}")
    return 0


def cmd_score_candidates(args: argparse.Namespace) -> int:
    cache_manifest = Path(args.cache_manifest)
    if not cache_manifest.exists():
        return _fail([f"Missing local cache manifest: {cache_manifest}"])
    try:
        summary = score_candidates(
            cache_manifest,
            Path(args.output),
            backend=args.backend,
            model_name=args.model,
            model_cache_dir=Path(args.model_cache_dir) if args.model_cache_dir else None,
            allow_model_download=args.allow_model_download,
            limit=args.limit,
            include_failed=args.include_failed,
            image_id_prefix=args.image_id_prefix,
        )
    except RuntimeError as exc:
        return _fail([str(exc)])
    print(f"Scored {summary['scored']} cached candidates. Output: {args.output}")
    return 0


def cmd_review_queue(args: argparse.Namespace) -> int:
    scores = Path(args.scores)
    triage = Path(args.triage)
    if not scores.exists():
        return _fail([f"Missing model scores file: {scores}"])
    errors = validate_triage_columns(triage)
    if errors:
        return _fail(errors)
    summary = export_review_queue(
        scores,
        triage,
        Path(args.output),
        unreviewed_only=not args.include_reviewed,
        include_triage_actions=set(args.include_triage_action or []),
        exclude_suggested=set(args.exclude_suggested or []),
        limit=args.limit,
        image_id_prefix=args.image_id_prefix,
    )
    print(f"Wrote {summary['queued']} rows to review queue: {args.output}")
    return 0


def cmd_auto_triage(args: argparse.Namespace) -> int:
    scores = Path(args.scores)
    triage = Path(args.triage)
    if not scores.exists():
        return _fail([f"Missing model scores file: {scores}"])
    errors = validate_triage_columns(triage)
    if errors:
        return _fail(errors)
    thresholds = AutoTriageThresholds(
        road_min=args.road_min,
        non_road_exclude=args.non_road_exclude,
        privacy_review=args.privacy_review,
        damage_review=args.damage_review,
        normal_review=args.normal_review,
    )
    summary = auto_triage_scores(
        scores,
        triage,
        Path(args.output),
        thresholds=thresholds,
        unreviewed_only=not args.include_reviewed,
        dry_run=args.dry_run,
    )
    mode = "Dry run" if args.dry_run else "Auto-triage"
    print(
        f"{mode}: {summary['updated']} updates "
        f"({summary['auto_exclude']} exclude, {summary['needs_review']} needs_review), "
        f"{summary['unchanged']} unchanged, {summary['missing_triage']} missing triage rows."
    )
    return 0


def cmd_export_classification_dataset(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    cache_manifest = Path(args.cache_manifest)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if not cache_manifest.exists():
        errors.append(f"Missing local cache manifest: {cache_manifest}")
    if errors:
        return _fail(errors)
    summary = export_classification_dataset(
        manifest,
        cache_manifest,
        Path(args.output_dir),
        copy_images=not args.no_copy,
    )
    print(
        f"Exported {summary['exported']} classification rows to {args.output_dir}; "
        f"{summary['missing_local']} publishable rows missing local files."
    )
    return 0 if summary["missing_local"] == 0 else 2


def cmd_annotation_queue(args: argparse.Namespace) -> int:
    manifest = Path(args.manifest)
    cache_manifest = Path(args.cache_manifest)
    errors = validate_manifest_columns(manifest, IMAGE_MANIFEST_FIELDS)
    if not cache_manifest.exists():
        errors.append(f"Missing local cache manifest: {cache_manifest}")
    if errors:
        return _fail(errors)
    summary = export_annotation_queue(manifest, cache_manifest, Path(args.output))
    print(f"Wrote {summary['queued']} rows to annotation queue: {args.output}")
    return 0


def cmd_validate_annotations(args: argparse.Namespace) -> int:
    annotations = Path(args.annotations)
    cache_manifest = Path(args.cache_manifest)
    errors = []
    if not annotations.exists():
        errors.append(f"Missing annotations file: {annotations}")
    if not cache_manifest.exists():
        errors.append(f"Missing local cache manifest: {cache_manifest}")
    if errors:
        return _fail(errors)
    summary = validate_box_annotations(annotations, cache_manifest)
    if summary["errors"]:
        return _fail(summary["messages"])
    print(f"Validated {summary['checked']} annotation rows.")
    return 0


def cmd_draft_annotations(args: argparse.Namespace) -> int:
    queue = Path(args.queue)
    if not queue.exists():
        return _fail([f"Missing annotation queue: {queue}"])
    preview_dir = Path(args.preview_dir) if args.preview_dir else None
    try:
        summary = draft_annotations(
            queue,
            Path(args.output),
            preview_dir=preview_dir,
            overwrite=args.overwrite,
            max_boxes_per_image=args.max_boxes_per_image,
        )
    except RuntimeError as error:
        return _fail([str(error)])
    print(
        f"Draft annotations: {summary['boxes_written']} boxes for {summary['queued']} images; "
        f"{summary['fallback_boxes']} fallback boxes; "
        f"{summary['skipped_existing']} skipped existing; "
        f"{summary['skipped_missing']} missing; "
        f"{summary['preview_written']} previews."
    )
    return 0


def cmd_privacy_scan(args: argparse.Namespace) -> int:
    cache_manifest = Path(args.cache_manifest)
    if not cache_manifest.exists():
        return _fail([f"Missing local cache manifest: {cache_manifest}"])
    try:
        summary = scan_privacy(
            cache_manifest,
            Path(args.output),
            limit=args.limit,
            include_failed=args.include_failed,
            detect_plates=args.detect_plates,
        )
    except RuntimeError as exc:
        return _fail([str(exc)])
    print(
        f"Privacy scan: {summary['scanned']} scanned, {summary['clear']} clear, "
        f"{summary['needs_blur']} need blur, {summary['missing']} missing, "
        f"{summary['failed']} failed. Report: {args.output}"
    )
    return 0 if summary["failed"] == 0 and summary["missing"] == 0 else 2


def cmd_blur_privacy(args: argparse.Namespace) -> int:
    privacy_report = Path(args.privacy_report)
    if not privacy_report.exists():
        return _fail([f"Missing privacy report: {privacy_report}"])
    try:
        summary = blur_privacy_regions(
            privacy_report,
            Path(args.output_dir),
            Path(args.output_manifest),
        )
    except RuntimeError as exc:
        return _fail([str(exc)])
    print(
        f"Privacy blur: {summary['blurred']} blurred, {summary['skipped']} skipped, "
        f"{summary['failed']} failed. Manifest: {args.output_manifest}"
    )
    return 0 if summary["failed"] == 0 else 2


def cmd_apply_privacy(args: argparse.Namespace) -> int:
    triage = Path(args.triage)
    privacy_report = Path(args.privacy_report)
    errors = validate_triage_columns(triage)
    if not privacy_report.exists():
        errors.append(f"Missing privacy report: {privacy_report}")
    if errors:
        return _fail(errors)
    blur_manifest = Path(args.blur_manifest)
    summary = apply_privacy_report_to_triage(
        triage,
        privacy_report,
        Path(args.output),
        blurred_manifest=blur_manifest if blur_manifest.exists() else None,
        trust_clear=args.trust_clear,
    )
    print(
        f"Applied privacy report: {summary['updated']} updated "
        f"({summary['clear_marked']} clear, {summary['blurred_marked']} blurred, "
        f"{summary['needs_review_marked']} needs_review), {summary['unchanged']} unchanged."
    )
    return 0


def cmd_privacy_cache(args: argparse.Namespace) -> int:
    cache_manifest = Path(args.cache_manifest)
    extra_cache_manifests = [Path(path) for path in args.extra_cache_manifest]
    blur_manifest = Path(args.blur_manifest)
    errors = []
    if not cache_manifest.exists():
        errors.append(f"Missing local cache manifest: {cache_manifest}")
    for path in extra_cache_manifests:
        if not path.exists():
            errors.append(f"Missing extra local cache manifest: {path}")
    if not blur_manifest.exists():
        errors.append(f"Missing blurred privacy manifest: {blur_manifest}")
    if errors:
        return _fail(errors)
    summary = export_privacy_safe_cache(
        cache_manifest,
        blur_manifest,
        Path(args.output),
        extra_cache_manifests=extra_cache_manifests,
    )
    print(
        f"Privacy-safe cache: {summary['rows']} rows, {summary['replaced']} blurred replacements, "
        f"{summary['kept']} raw/cache rows kept. Output: {args.output}"
    )
    return 0


def cmd_batch_intake(args: argparse.Namespace) -> int:
    triage = Path(args.triage)
    errors = validate_triage_columns(triage)
    if args.skip_download and not Path(args.cache_manifest).exists():
        errors.append(f"Missing local cache manifest: {args.cache_manifest}")
    if args.skip_scoring and not Path(args.scores).exists():
        errors.append(f"Missing model scores file: {args.scores}")
    if errors:
        return _fail(errors)

    if args.dry_run:
        for line in batch_intake_plan(args):
            print(line)
        return 0

    exit_code = 0
    print("Batch intake starting.")

    if args.skip_download:
        print("Step 1/6 download: skipped.")
    else:
        download_summary = download_candidates(
            triage,
            Path(args.download_dir),
            Path(args.cache_manifest),
            limit=args.limit,
            photo_candidates_only=not args.include_non_photo,
            overwrite=args.overwrite,
            thumbnail_width=args.thumbnail_width,
            original=False,
            max_bytes=args.max_mb * 1024 * 1024,
            verbose=not args.quiet_download,
            request_delay=args.request_delay,
            unreviewed_only=True,
            retry_failed=args.retry_failed,
        )
        print(
            "Step 1/6 download: "
            f"{download_summary['downloaded']} downloaded, "
            f"{download_summary['skipped_existing']} existing, "
            f"{download_summary['skipped_failed_cache']} skipped failed-cache, "
            f"{download_summary['failed']} failed "
            f"out of {download_summary['candidates']} candidates."
        )
        if (
            download_summary["downloaded"] == 0
            and download_summary["failed"] == 0
            and download_summary["skipped_existing"] == download_summary["candidates"]
        ):
            print(
                "Step 1/6 download: no uncached eligible rows found. "
                "Collect more manifest rows or use --retry-failed to retry failed cache entries."
            )
        if download_summary["failed"]:
            exit_code = 2

    cache_manifest = Path(args.cache_manifest)
    if not cache_manifest.exists():
        return _fail([f"Missing local cache manifest after download step: {cache_manifest}"])

    if args.skip_scoring:
        print("Step 2/6 scoring: skipped.")
    else:
        try:
            score_summary = score_candidates(
                cache_manifest,
                Path(args.scores),
                backend=args.backend,
                model_name=args.model,
                model_cache_dir=Path(args.model_cache_dir) if args.model_cache_dir else None,
                allow_model_download=args.allow_model_download,
            )
        except RuntimeError as exc:
            return _fail([str(exc)])
        print(f"Step 2/6 scoring: {score_summary['scored']} cached candidates scored.")

    scores = Path(args.scores)
    if not scores.exists():
        return _fail([f"Missing model scores file after scoring step: {scores}"])

    auto_summary = auto_triage_scores(scores, triage, triage)
    print(
        "Step 3/6 auto-triage: "
        f"{auto_summary['updated']} updates "
        f"({auto_summary['auto_exclude']} exclude, {auto_summary['needs_review']} needs_review), "
        f"{auto_summary['unchanged']} unchanged."
    )

    if args.skip_privacy:
        print("Step 4/6 privacy: skipped.")
        safe_cache = cache_manifest
    else:
        try:
            privacy_summary = scan_privacy(
                cache_manifest,
                Path(args.privacy_report),
                detect_plates=args.detect_plates,
            )
            blur_summary = blur_privacy_regions(
                Path(args.privacy_report),
                Path(args.blur_dir),
                Path(args.blur_manifest),
            )
        except RuntimeError as exc:
            return _fail([str(exc)])
        apply_summary = apply_privacy_report_to_triage(
            triage,
            Path(args.privacy_report),
            triage,
            blurred_manifest=Path(args.blur_manifest),
            trust_clear=args.trust_clear,
        )
        cache_summary = export_privacy_safe_cache(
            cache_manifest,
            Path(args.blur_manifest),
            Path(args.privacy_safe_cache),
        )
        safe_cache = Path(args.privacy_safe_cache)
        print(
            "Step 4/6 privacy: "
            f"{privacy_summary['scanned']} scanned, {privacy_summary['clear']} clear, "
            f"{privacy_summary['needs_blur']} need blur; "
            f"{blur_summary['blurred']} blurred; "
            f"{apply_summary['updated']} triage rows updated; "
            f"{cache_summary['replaced']} safe-cache replacements."
        )
        if privacy_summary["failed"] or privacy_summary["missing"] or blur_summary["failed"]:
            exit_code = 2

    review_summary = export_review_queue(
        scores,
        triage,
        Path(args.review_queue),
        include_triage_actions={"needs_review"},
        exclude_suggested={"review_exclude"},
        limit=args.queue_limit,
    )
    print(f"Step 5/6 review queue: {review_summary['queued']} rows written to {args.review_queue}.")

    print(f"Step 6/6 next: review {args.review_queue}; exports should use {safe_cache}.")
    print("Batch intake complete.")
    return exit_code


def batch_intake_plan(args: argparse.Namespace) -> list[str]:
    lines = ["Batch intake dry run. Planned steps:"]
    if args.skip_download:
        lines.append("1. Skip download.")
    else:
        lines.append(
            "1. Download up to "
            f"{args.limit} unreviewed candidates into {args.download_dir} "
            f"with request delay {args.request_delay}s."
        )
    if args.skip_scoring:
        lines.append("2. Skip scoring.")
    else:
        cache_note = (
            f" using model cache {args.model_cache_dir}"
            if args.backend == "clip" and args.model_cache_dir
            else ""
        )
        download_note = " with model download allowed" if args.allow_model_download else ""
        lines.append(
            f"2. Score cached candidates with {args.backend}{cache_note}{download_note} into {args.scores}."
        )
    lines.append(f"3. Auto-triage unreviewed rows in {args.triage}.")
    if args.skip_privacy:
        lines.append("4. Skip privacy scan/blur/cache.")
    else:
        plate_note = " with experimental plate detection" if args.detect_plates else ""
        trust_note = " and trust clear scans" if args.trust_clear else ""
        lines.append(
            "4. Run privacy scan"
            f"{plate_note}, blur detections, apply privacy outcomes{trust_note}, "
            f"and write {args.privacy_safe_cache}."
        )
    lines.append(f"5. Write ranked review queue to {args.review_queue}.")
    lines.append("6. Stop before applying triage to the publishable manifest.")
    return lines


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def best_experiments_by_model_split(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    best: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            row.get("model", ""),
            row.get("evaluation_dataset", ""),
            row.get("eval_split", ""),
        )
        current = best.get(key)
        if current is None or experiment_selection_key(row) > experiment_selection_key(current):
            best[key] = row

    table_rows = []
    for row in sorted(best.values(), key=lambda item: (item.get("model", ""), item.get("eval_split", ""))):
        table_rows.append(
            {
                "model": row.get("model", ""),
                "training_dataset": row.get("training_dataset", ""),
                "evaluation_dataset": row.get("evaluation_dataset", ""),
                "eval_split": row.get("eval_split", ""),
                "precision": row.get("precision", ""),
                "recall": row.get("recall", ""),
                "map50": row.get("map50", ""),
                "map50_95": row.get("map50_95", ""),
                "experiment_id": row.get("experiment_id", ""),
            }
        )
    return table_rows


def experiment_selection_key(row: dict[str, str]) -> tuple[int, int, int, float]:
    """Prefer final-cohort runs before comparing metric quality.

    Local pilot runs can have better metrics on a tiny split by chance. For paper tables we
    first prefer full-size AWS-style runs (`imgsz>=640`, 50-epoch train rows when present),
    then use mAP50-95 to break ties within the same cohort.
    """

    imgsz = _int_metric(row.get("imgsz", ""))
    epochs = _int_metric(row.get("epochs", ""))
    phase = row.get("phase", "")
    final_sized = 1 if imgsz >= 640 else 0
    final_training = 1 if phase != "train" or epochs >= 50 else 0
    return (final_sized, final_training, imgsz, _float_metric(row.get("map50_95", "")))


def _int_metric(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def count_rows(counts: dict[str, int]) -> list[dict[str, str]]:
    return [{"item": key, "count": str(value)} for key, value in sorted(counts.items())]


def summary_table_rows(summary: dict) -> list[dict[str, str]]:
    rows = []
    for key, value in summary.items():
        if isinstance(value, (dict, list)):
            continue
        rows.append({"metric": key, "value": str(value)})
    return rows


def _float_metric(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def _load_yaml_config(path: Path) -> dict:
    if yaml is not None:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    # Minimal fallback for this scaffold's simple dataset config. Install PyYAML
    # before using nested production configs.
    config: dict[str, object] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value:
            config[key.strip()] = value
    return config


def _dump_yaml_config(config: dict) -> str:
    if yaml is not None:
        return yaml.safe_dump(config, sort_keys=False)
    lines = []
    for key, value in config.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            for child_key, child_value in value.items():
                lines.append(f"  {child_key}: {child_value}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _replace_yaml_scalar(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    prefix = f"{key}:"
    replaced = False
    output = []
    for line in lines:
        if line.startswith(prefix):
            output.append(f"{key}: {value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.insert(0, f"{key}: {value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def _fail(messages: list[str]) -> int:
    for message in messages:
        print(f"error: {message}", file=sys.stderr)
    return 1


def _resolve_executable(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    sibling = Path(sys.executable).with_name(name)
    if sibling.exists():
        return str(sibling)
    return name


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    cache_root = Path("/tmp/roadkz")
    env.setdefault("YOLO_CONFIG_DIR", str(cache_root / "ultralytics"))
    env.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    return env


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
