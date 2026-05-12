# Visual Triage Workflow

The candidate manifest contains license-ready Wikimedia Commons rows, but none are publishable until visual triage confirms road relevance and privacy safety.

## Generate Review Files

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli triage-sheet \
  --license-ready-only \
  --manifest data/manifests/images.csv \
  --output data/manifests/triage.csv

PYTHONPATH=src python3 -m road_damage_kz.cli triage-gallery \
  --triage data/manifests/triage.csv \
  --output reports/triage_gallery.html \
  --photo-candidates-only
```

Open `reports/triage_gallery.html` and fill `data/manifests/triage.csv`.

For offline review, download a manageable batch and generate a local gallery:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli download-candidates \
  --triage data/manifests/triage.csv \
  --limit 25 \
  --thumbnail-width 960 \
  --request-delay 4 \
  --unreviewed-only \
  --output-dir data/raw/candidates \
  --cache-manifest data/manifests/local_files.csv

PYTHONPATH=src python3 -m road_damage_kz.cli local-gallery \
  --cache-manifest data/manifests/local_files.csv \
  --output reports/local_gallery.html
```

By default this downloads Commons thumbnails, not originals. Use `--original` only when high-resolution review is necessary. `data/raw/candidates/` and `data/manifests/local_files.csv` are local cache artifacts and are not committed.

Use `--retry-failed` only when you intentionally want to revisit rows that previously hit Wikimedia rate limits or download errors.

To prioritize the cached review queue with CLIP, see `docs/model-assisted-triage.md`.

## Required Triage Columns

Use lowercase boolean values: `true` or `false`.

| Column | Meaning |
| --- | --- |
| `road_surface_visible` | Road/pavement surface is visible enough for the image to be useful |
| `target_damage_visible` | One or more target classes are visibly present |
| `privacy_ok` | Faces, license plates, and other identifiers are absent or safe |
| `damage_labels` | Use `pothole`, `longitudinal_crack`, `transverse_crack`, `alligator_crack`, semicolon-separated combinations, or `normal` |
| `recommended_action` | `include`, `exclude`, or `needs_review` |
| `reviewer` | Reviewer initials or name |
| `notes` | Reason for exclusion or uncertainty |

## Promotion Rules

`roadkz apply-triage` promotes only rows where:

- `recommended_action=include`;
- `license_ok=true`;
- `is_photo_candidate=true`;
- `road_surface_visible=true`;
- `privacy_ok=true`;
- if `target_damage_visible=true`, `damage_labels` is not empty or `unknown`;
- if `target_damage_visible=false`, the manifest label becomes `normal`.

Rows that fail these checks are skipped and listed in `reports/apply_triage_report.json`.

## Apply Reviewed Decisions

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli apply-triage \
  --manifest data/manifests/images.csv \
  --triage data/manifests/triage.csv \
  --output data/manifests/images.csv \
  --report reports/apply_triage_report.json

PYTHONPATH=src python3 -m road_damage_kz.cli audit-licenses \
  --manifest data/manifests/images.csv \
  --report reports/license_audit.json
```
