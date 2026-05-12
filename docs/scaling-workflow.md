# Scaling Workflow

Use this loop to scale candidate intake without hand-opening every image.

## One-Command Intake

Use a dry run first:

```bash
roadkz batch-intake \
  --limit 100 \
  --request-delay 6 \
  --dry-run
```

Then run the batch:

```bash
roadkz batch-intake \
  --limit 100 \
  --request-delay 6
```

The batch command runs download, CLIP scoring, auto-triage, privacy scan, privacy blur, privacy-safe cache generation, and review queue export. It deliberately stops before `apply-triage`, so no image enters the publishable manifest without a reviewer confirming the queued rows.

Download progress is enabled by default for `batch-intake`. Use `--quiet-download` if you need compact logs.

CLIP weights are cached under `data/external/hf-cache` by default. The scorer uses local cached files by default; if the selected model is missing, run once with `--allow-model-download`.

Useful variants:

```bash
roadkz batch-intake --limit 50 --request-delay 8 --retry-failed
roadkz batch-intake --limit 100 --backend keyword --skip-privacy
roadkz batch-intake --limit 100 --trust-clear
roadkz batch-intake --limit 100 --quiet-download
roadkz batch-intake --limit 100 --allow-model-download
```

Use `--trust-clear` only after spot-checking the current privacy detector on this collection.

## 0. Find More Leads

### Mapillary Street-Level Imagery

Mapillary is now the preferred no-fieldwork source because it provides street-level road imagery through an API with creator attribution and CC-BY-SA licensing.

```bash
MAPILLARY_ACCESS_TOKEN=... roadkz collect-mapillary \
  --city almaty \
  --limit 200 \
  --grid-size 6 \
  --output data/manifests/images.csv \
  --report reports/mapillary_almaty_report.json

MAPILLARY_ACCESS_TOKEN=... roadkz collect-mapillary \
  --city astana \
  --limit 200 \
  --grid-size 6 \
  --output data/manifests/images.csv \
  --report reports/mapillary_astana_report.json
```

Built-in city bounding boxes include `almaty`, `astana`, `shymkent`, `karaganda`, `aktobe`, `pavlodar`, `atyrau`, `taraz`, `kyzylorda`, `semey`, and `oskemen`. Use `--bbox west,south,east,north` for a custom road corridor. If Mapillary returns HTTP 500 or timeout-like errors, increase `--grid-size` to split the area into smaller API queries.

After collection, merge the new license-ready rows into triage:

```bash
roadkz triage-sheet \
  --license-ready-only \
  --manifest data/manifests/images.csv \
  --output data/manifests/triage.csv \
  --merge-existing
```

Then continue with `batch-intake`, review queue, privacy review, and `apply-triage`. Mapillary rows remain `privacy_checked=false` until the project privacy workflow clears them.

For a Mapillary-only first review batch:

```bash
roadkz download-candidates \
  --triage data/manifests/triage.csv \
  --cache-manifest data/manifests/local_files.csv \
  --limit 50 \
  --image-id-prefix mapillary_ \
  --unreviewed-only \
  --request-delay 2 \
  --verbose

roadkz score-candidates \
  --cache-manifest data/manifests/local_files.csv \
  --output data/manifests/model_scores.csv \
  --image-id-prefix mapillary_

roadkz review-queue \
  --scores data/manifests/model_scores.csv \
  --triage data/manifests/triage.csv \
  --output data/manifests/review_queue.csv \
  --image-id-prefix mapillary_ \
  --limit 50
```

Commons category and search collection remains useful for reproducible open-license leads, but broad Kazakhstan road searches are now low-yield for pavement distress. Use targeted Commons runs only when a new category or query is plausible; use Openverse for broader discovery if API access is available:

```bash
roadkz collect-openverse-search \
  --query "Kazakhstan pothole road" \
  --query "Kazakhstan cracked asphalt" \
  --query "Kazakhstan damaged road" \
  --limit 50 \
  --output data/manifests/images.csv \
  --report reports/openverse_search_report.json
```

Openverse rows are unverified by default (`license_ok=false`), so they will not enter `triage-sheet --license-ready-only` or the publishable dataset until their source-page license and attribution are checked. Use the report to prioritize which source pages to verify.

If Openverse returns HTTP 401 or 403, pause that source and continue with Commons or already collected leads. The public API can throttle anonymous clients; do not bypass that by scraping images directly into the publishable dataset.

## 1. Download A Batch

Start with 50. Increase only if Wikimedia does not rate-limit.

```bash
source .venv/bin/activate

roadkz download-candidates \
  --triage data/manifests/triage.csv \
  --output-dir data/raw/candidates \
  --cache-manifest data/manifests/local_files.csv \
  --limit 50 \
  --thumbnail-width 960 \
  --request-delay 4 \
  --unreviewed-only \
  --verbose
```

If rate-limited, retry later with:

```bash
roadkz download-candidates \
  --triage data/manifests/triage.csv \
  --output-dir data/raw/candidates \
  --cache-manifest data/manifests/local_files.csv \
  --limit 50 \
  --thumbnail-width 960 \
  --request-delay 8 \
  --unreviewed-only \
  --retry-failed \
  --verbose
```

## 2. Score With CLIP

```bash
roadkz score-candidates \
  --backend clip \
  --cache-manifest data/manifests/local_files.csv \
  --output data/manifests/model_scores.csv
```

## 3. Auto-Triage Obvious Cases

Run a dry run first. This reports how many rows would be auto-excluded or sent to manual review.

```bash
roadkz auto-triage \
  --scores data/manifests/model_scores.csv \
  --triage data/manifests/triage.csv \
  --dry-run
```

If the counts look reasonable, apply the conservative decisions:

```bash
roadkz auto-triage \
  --scores data/manifests/model_scores.csv \
  --triage data/manifests/triage.csv \
  --output data/manifests/triage.csv
```

What this automates:

- `exclude`: likely non-road, too distant, map/diagram, or no usable paved road surface.
- `needs_review`: likely damage, likely normal road, or privacy-sensitive road scene.

What this does not automate:

- It does not set `privacy_checked=true`.
- It does not promote rows into the publishable dataset.
- It does not assign final damage labels beyond `normal` for likely normal-road review candidates.

## 4. Scan And Blur Privacy Risks

Install the optional privacy dependency once:

```bash
python -m pip install -e ".[privacy]"
```

Scan cached files:

```bash
roadkz privacy-scan \
  --cache-manifest data/manifests/local_files.csv \
  --output data/manifests/privacy_report.csv
```

The default scan uses face detection. The plate-like detector is experimental and can be enabled with `--detect-plates` for a separate calibration run.

Create blurred derivatives for detected face or plate-candidate regions:

```bash
roadkz blur-privacy \
  --privacy-report data/manifests/privacy_report.csv \
  --output-dir data/processed/privacy_blurred \
  --output-manifest data/manifests/privacy_blurred_files.csv
```

Apply privacy outcomes back to triage:

```bash
roadkz apply-privacy \
  --triage data/manifests/triage.csv \
  --privacy-report data/manifests/privacy_report.csv \
  --blur-manifest data/manifests/privacy_blurred_files.csv \
  --output data/manifests/triage.csv
```

Create a privacy-safe cache for exports. This keeps regular cached paths for clear rows and replaces detected rows with blurred derivatives:

```bash
roadkz privacy-cache \
  --cache-manifest data/manifests/local_files.csv \
  --blur-manifest data/manifests/privacy_blurred_files.csv \
  --output data/manifests/privacy_safe_files.csv
```

Optional, after spot-checking detector quality on this collection:

```bash
roadkz apply-privacy \
  --triage data/manifests/triage.csv \
  --privacy-report data/manifests/privacy_report.csv \
  --blur-manifest data/manifests/privacy_blurred_files.csv \
  --output data/manifests/triage.csv \
  --trust-clear
```

`--trust-clear` marks no-detection rows as privacy-clean. Use it only after checking false negatives, because missed faces or plates remain possible.

## 5. Build A Review Queue

This joins model scores with triage state and skips likely model exclusions by default.

```bash
roadkz review-queue \
  --scores data/manifests/model_scores.csv \
  --triage data/manifests/triage.csv \
  --output data/manifests/review_queue.csv \
  --limit 100
```

Review `data/manifests/review_queue.csv` from top to bottom and manually confirm the remaining `needs_review` rows in `data/manifests/triage.csv`.

## 6. Apply Triage

```bash
roadkz apply-triage \
  --manifest data/manifests/images.csv \
  --triage data/manifests/triage.csv \
  --output data/manifests/images.csv \
  --report reports/apply_triage_report.json

roadkz audit-licenses \
  --manifest data/manifests/images.csv \
  --report reports/license_audit.json
```

## 7. Export Current Datasets

Image-level classification export:

```bash
roadkz export-classification-dataset \
  --manifest data/manifests/images.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv \
  --output-dir data/processed/classification
```

Bounding-box annotation queue:

```bash
roadkz annotation-queue \
  --manifest data/manifests/images.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv \
  --output data/manifests/annotation_queue.csv
```
