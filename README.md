# Kazakhstan Road Damage Classification

This project supports a journal paper on **road damage detection and classification for Kazakhstan road imagery**. The repository is organized so the paper, dataset ledger, annotation policy, Ghost-CA-YOLO model, and evaluation pipeline evolve together.

## Current Target

- Primary journal: **Applied Sciences** research article.
- Main contribution: a Kazakhstan-focused road-damage benchmark plus an adapted Ghost-CA-YOLO detector compared with YOLO11s.
- Fallbacks: **MDPI Data** or **Data in Brief** only if the dataset can be legally deposited, reused, and assigned a repository DOI.

## Publication Strategy

The project is not currently strong enough to claim a large standalone Kazakhstan road-damage dataset. The Applied Sciences-first route should emphasize reproducible source auditing, privacy-safe benchmarking, Ghost-CA-YOLO adaptation, YOLO11s comparison, Kazakhstan-only external validation, and domain-shift/error analysis.

Submission-strength targets:

- minimum Applied Sciences target: 30-50 damaged Kazakhstan images, at least 100 gold boxes, and at least 3 represented damage classes;
- preferred Applied Sciences target: 100+ damaged Kazakhstan images plus normal hard negatives;
- data-journal fallback target: 800+ redistributable license-clean Kazakhstan images with repository DOI.

## Repository Layout

```text
configs/                 Class taxonomy and dataset config
data/manifests/          Source, image, and annotation ledgers
docs/                    Research, journal, data, and annotation documentation
paper/                   MDPI-style LaTeX paper scaffold
reports/                 Generated audit/evaluation reports
src/road_damage_kz/      Reproducible pipeline and CLI
tests/                   Validation tests
```

Raw images, processed data, model runs, and generated outputs are intentionally ignored by git.

## Citation And Release

The public release repository for the Applied Sciences submission is:

```text
https://github.com/yerulan/road-damage-kz-release
```

Zenodo archiving can be added later if the service becomes available, but the
current submission package uses the public GitHub repository as the data and
code availability location.

Code is released under the MIT License. Project-created manifests,
annotations, and reports are released under CC BY 4.0. Raw third-party images
and RDD2022 data are not redistributed by default; see `DATA-LICENSE.md`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Optional model training dependencies:

```bash
python -m pip install -e ".[ml]"
```

Optional privacy scanning dependencies:

```bash
python -m pip install -e ".[privacy]"
```

## Reproducible Commands

```bash
roadkz collect --sources data/manifests/sources.csv --output data/manifests/images.csv
roadkz collect-commons --category "Category:Roads in Kazakhstan" --include-subcategories --limit 250
roadkz collect-openverse-search --query "Kazakhstan pothole road" --query "Kazakhstan cracked asphalt" --limit 50
MAPILLARY_ACCESS_TOKEN=... roadkz collect-mapillary --city almaty --limit 200 --grid-size 6
roadkz audit-licenses --manifest data/manifests/images.csv
roadkz triage-sheet --license-ready-only --manifest data/manifests/images.csv --output data/manifests/triage.csv
roadkz triage-gallery --triage data/manifests/triage.csv --output reports/triage_gallery.html
roadkz download-candidates --triage data/manifests/triage.csv --limit 25 --thumbnail-width 960 --request-delay 4 --unreviewed-only
roadkz local-gallery --cache-manifest data/manifests/local_files.csv --output reports/local_gallery.html
roadkz score-candidates --backend clip --cache-manifest data/manifests/local_files.csv --output data/manifests/model_scores.csv
roadkz auto-triage --scores data/manifests/model_scores.csv --triage data/manifests/triage.csv --dry-run
roadkz auto-triage --scores data/manifests/model_scores.csv --triage data/manifests/triage.csv
roadkz privacy-scan --cache-manifest data/manifests/local_files.csv --output data/manifests/privacy_report.csv
roadkz blur-privacy --privacy-report data/manifests/privacy_report.csv --output-dir data/processed/privacy_blurred
roadkz apply-privacy --triage data/manifests/triage.csv --privacy-report data/manifests/privacy_report.csv
roadkz privacy-cache --cache-manifest data/manifests/local_files.csv --blur-manifest data/manifests/privacy_blurred_files.csv --output data/manifests/privacy_safe_files.csv
roadkz review-queue --scores data/manifests/model_scores.csv --triage data/manifests/triage.csv --output data/manifests/review_queue.csv
roadkz apply-triage --manifest data/manifests/images.csv --triage data/manifests/triage.csv
roadkz export-classification-dataset --manifest data/manifests/images.csv --cache-manifest data/manifests/local_files.csv --output-dir data/processed/classification
roadkz annotation-queue --manifest data/manifests/images.csv --cache-manifest data/manifests/local_files.csv --output data/manifests/annotation_queue.csv
roadkz dedupe --manifest data/manifests/images.csv
roadkz rdd-download-plan --script reports/rdd_download_plan.sh
roadkz check-rdd --rdd-root data/external/RDD2022 --report reports/rdd_readiness.json
roadkz import-rdd-voc --rdd-root data/external/RDD2022 --output-dir data/processed/rdd_yolo
python scripts/run_remote_experiments.py --model-kind yolo11s --rdd-epochs 50 --kz-epochs 30 --imgsz 640 --batch 16 --device 0 --workers 8
python scripts/run_remote_experiments.py --model-kind ghost-ca --rdd-epochs 50 --kz-epochs 30 --imgsz 640 --batch 16 --device 0 --workers 8
roadkz prepare --format yolo --config configs/dataset.yaml
roadkz evaluate --split kz-test --config configs/dataset.yaml
roadkz record-experiment --run-dir runs/detect/val --phase eval --eval-split kz-test
roadkz figures --paper --output reports/paper_summary.json --experiment-table reports/experiment_table.csv
roadkz project-status --output reports/project_status.json
```

## Tests

Use the standard-library test runner, which works even when `pytest` is not installed in the active virtual environment:

```bash
.venv/bin/python -m unittest discover -s tests
```

`pytest` remains optional through the `dev` extra.

For the regular scaled intake loop, prefer the batch wrapper:

```bash
roadkz batch-intake --limit 100 --request-delay 6 --dry-run
roadkz batch-intake --limit 100 --request-delay 6
```

`batch-intake` downloads unreviewed candidates, scores them, applies conservative auto-triage, runs privacy scan/blur/cache generation, and writes a review queue. It stops before applying triage to the publishable manifest.
Download progress is shown by default; use `--quiet-download` to suppress per-file lines. CLIP weights are cached under `data/external/hf-cache` by default and loaded locally on later runs. If the selected model is missing from the cache, run once with `--allow-model-download`.

`collect-openverse-search` is for broader discovery after Commons search slows down. It keeps rows as unverified leads by default (`license_ok=false`), so verify the source-page license before downloading or publishing them.

`collect-mapillary` is the preferred no-fieldwork street-level source after Commons saturation. It requires a Mapillary access token (`MAPILLARY_ACCESS_TOKEN` or `--access-token`), stores Mapillary image pages and thumbnail URLs as license-ready but privacy-unchecked leads, and relies on the existing triage/privacy workflow before any row becomes publishable. City queries are tiled by default; increase `--grid-size` if Mapillary returns HTTP 500/timeouts for a large area.

For Mapillary-only intake after collection, use `--image-id-prefix mapillary_` on download, scoring, and review-queue commands.

## Dataset Principle

An image is not part of the publishable dataset until its source, author, license, privacy review, and annotation status are recorded in `data/manifests/images.csv`. Internet-only collection is allowed for discovery, but unlicensed images must not be redistributed.

## First Milestones

1. Build a license-clean Kazakhstan image ledger.
2. Annotate damage boxes using the taxonomy in `docs/annotation-guide.md`.
3. Train YOLO11s and Ghost-CA-YOLO on public RDD-style data where available.
4. Evaluate domain shift and Kazakhstan fine-tuning against Kazakhstan-only test images.
5. Expand the Kazakhstan damaged set through permissioned/source-specific collection before treating the manuscript as submission-ready.
6. Draft and maintain the Applied Sciences article in `paper/main.tex`.

## Scaling Candidate Review

Use `docs/scaling-workflow.md` for the CLIP-assisted batch loop: download candidates, score them, run conservative auto-triage, export a ranked review queue for the remaining rows, apply triage, then export classification and annotation datasets.

## Finish-Line Workflow

Use `docs/final-workflow.md` for the Applied Sciences submission path, `docs/submission-checklist.md` for SUSY/package checks, and `docs/release-instructions.md` for the public repository release policy.
