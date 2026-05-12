# Model-Assisted Triage

Manual review remains required for publication, but cached candidates can be ranked before review.

## Install Optional Vision Dependencies

```bash
python -m pip install -e ".[vision]"
```

The default scorer uses `openai/clip-vit-base-patch32` through Hugging Face Transformers. The first run downloads model weights.

## Score Cached Images

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli score-candidates \
  --backend clip \
  --cache-manifest data/manifests/local_files.csv \
  --output data/manifests/model_scores.csv
```

For a no-model smoke test:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli score-candidates \
  --backend keyword \
  --cache-manifest data/manifests/local_files.csv \
  --output data/manifests/model_scores.csv
```

## How To Use Scores

Review `data/manifests/model_scores.csv` in descending `review_priority`.

For a cleaner queue that joins model scores with triage state and omits likely exclusions:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli review-queue \
  --scores data/manifests/model_scores.csv \
  --triage data/manifests/triage.csv \
  --output data/manifests/review_queue.csv
```

## Conservative Auto-Triage

After scoring, use `auto-triage` to reduce manual work before opening the review queue:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli auto-triage \
  --scores data/manifests/model_scores.csv \
  --triage data/manifests/triage.csv \
  --dry-run
```

Then apply it:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli auto-triage \
  --scores data/manifests/model_scores.csv \
  --triage data/manifests/triage.csv
```

The command only changes unreviewed rows by default. It can auto-exclude likely non-road or unusable images, and it can mark likely normal/damaged/privacy-sensitive road images as `needs_review`.

It intentionally does not auto-publish images. `privacy_checked=true` and final damage labels still require manual confirmation or a future dedicated privacy/blur pipeline.

Suggested actions:

- `review_damage_first`: likely useful damaged-road candidates.
- `review_normal_candidate`: likely normal-road candidates.
- `review_privacy`: potentially useful but likely has people/vehicles/plates.
- `review_exclude`: likely map, landscape, market, or other non-road content.
- `review_later`: uncertain.

CLIP scores do not establish privacy compliance or final labels. They only decide review order.

## Current Calibration Notes

The current CLIP prompt groups are strongest for broad filtering:

- road surface vs. non-road/context;
- normal road candidates vs. obvious exclusions;
- privacy/context warning when people, cars, or street scenes dominate.

They are weaker for fine-grained damage classification. Treat `damage_score` as a signal for review priority, not as an automatic label.
