# External Training Datasets

## Purpose

Kazakhstan-only license-clean damaged imagery is currently too small for a strong detector-training claim. The safer paper design is:

1. train or pretrain baselines on public road-damage datasets;
2. evaluate separately on the Kazakhstan gold set;
3. frame the Kazakhstan contribution as license-audited external validation/domain-shift evidence unless the Kazakhstan subset grows substantially.

## Dataset Ledger

Track external datasets in `data/manifests/external_datasets.csv`. Do not commit downloaded archives or extracted images. Use `data/external/` locally.

## RDD VOC Import

After downloading an RDD-style dataset with Pascal VOC XML annotations, convert it to YOLO format:

```bash
roadkz rdd-download-plan \
  --script reports/rdd_download_plan.sh

# Review source terms, disk space, and file sizes before running:
bash reports/rdd_download_plan.sh

roadkz check-rdd \
  --rdd-root data/external/RDD2022 \
  --report reports/rdd_readiness.json

roadkz import-rdd-voc \
  --rdd-root data/external/RDD2022 \
  --output-dir data/processed/rdd_yolo \
  --copy-mode symlink
```

The importer maps RDD classes to this project taxonomy:

| RDD code | Project class |
| --- | --- |
| `D00` | `longitudinal_crack` |
| `D10` | `transverse_crack` |
| `D20` | `alligator_crack` |
| `D40` | `pothole` |

Unsupported RDD classes are skipped. The generated YOLO config is written to `data/processed/rdd_yolo/dataset.yaml`.

## Baseline Training Pattern

Preview the full baseline workflow without training:

```bash
roadkz run-baseline \
  --model yolov8n.pt \
  --model yolov8s.pt \
  --epochs 50 \
  --imgsz 640 \
  --dry-run
```

Train on RDD:

```bash
roadkz train \
  --config data/processed/rdd_yolo/dataset.yaml \
  --model yolov8n.pt \
  --epochs 50
```

Then evaluate the trained weights on the Kazakhstan-only export:

```bash
roadkz prepare --format yolo --config configs/dataset.yaml
roadkz evaluate \
  --split kz-test \
  --config configs/dataset.yaml \
  --model runs/detect/train/weights/best.pt
```

Record every train/evaluation run in the experiment ledger:

```bash
roadkz record-experiment \
  --run-dir runs/detect/val \
  --phase eval \
  --eval-split kz-test \
  --notes "RDD-trained detector evaluated on Kazakhstan test set"
```

For paper reporting, keep RDD results and Kazakhstan-only results in separate tables. Do not merge external public images into the Kazakhstan publishable image manifest.

Generate paper summary artifacts:

```bash
roadkz figures \
  --paper \
  --output reports/paper_summary.json \
  --experiment-table reports/experiment_table.csv
```

`reports/experiment_table.csv` includes only runs marked `paper_eligible=true`. Smoke runs stay in the ledger but are excluded from paper metric tables.

## Stronger Experiment Track

If the Kazakhstan damaged subset reaches the minimum Applied Sciences evidence target, add a second adaptation track:

1. Start from the RDD-trained YOLO11s and Ghost-CA-YOLO weights.
2. Fine-tune on the Kazakhstan training split only.
3. Keep the current `kz-test` split unchanged.
4. Record the adaptation run in `data/manifests/experiments.csv` with `training_dataset=RDD2022+Kazakhstan`.
5. Report RDD-only and RDD+Kazakhstan-adapted metrics separately.

Do not add this track while the Kazakhstan damaged set remains at the current pilot scale; it would overfit and weaken the paper.
