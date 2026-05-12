# Ghost-CA-YOLO Remote Training Pipeline

This pipeline produces the measured results required by the paper. It compares
YOLO11s with Ghost-CA-YOLO, evaluates transfer from RDD2022 to Kazakhstan, then
fine-tunes on the Kazakhstan split and records paper-ready metrics.

## 1. What Must Be Trained

Run the following four paper rows:

| Row | Model | Training data | Evaluation data |
| --- | --- | --- | --- |
| A | YOLO11s | RDD2022 | RDD2022 validation |
| B | YOLO11s | RDD2022 | Kazakhstan test |
| C | YOLO11s | RDD2022 + Kazakhstan fine-tuning | Kazakhstan test |
| D | Ghost-CA-YOLO | RDD2022 | RDD2022 validation |
| E | Ghost-CA-YOLO | RDD2022 | Kazakhstan test |
| F | Ghost-CA-YOLO | RDD2022 + Kazakhstan fine-tuning | Kazakhstan test |

The script `scripts/run_remote_experiments.py` records these rows into
`data/manifests/experiments.csv`.

## 2. Server Requirements

- NVIDIA GPU with CUDA.
- Python 3.10-3.12 recommended.
- 30 GB free disk minimum; 60 GB preferred.
- Network access for package install and `yolo11s.pt` download, unless weights
  are copied manually.

## 3. Environment Setup

```bash
cd /path/to/New\ project
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,ml,privacy]"
```

Check CUDA:

```bash
python - <<'PY'
import torch
print("cuda:", torch.cuda.is_available())
print("device:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu")
PY
```

## 4. Data Preparation

```bash
roadkz check-rdd \
  --rdd-root data/external/RDD2022 \
  --report reports/rdd_readiness.json \
  --fail-on-not-ready

roadkz import-rdd-voc \
  --rdd-root data/external/RDD2022 \
  --output-dir data/processed/rdd_yolo \
  --copy-mode symlink

roadkz prepare \
  --format yolo \
  --manifest data/manifests/images.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv \
  --annotations data/manifests/annotations.csv \
  --config configs/dataset.yaml \
  --output-dir data/processed/yolo
```

## 5. Training Commands

Start with conservative batch size 16. If VRAM allows, increase to 24 or 32.

```bash
python scripts/run_remote_experiments.py \
  --model-kind yolo11s \
  --rdd-epochs 50 \
  --kz-epochs 30 \
  --imgsz 640 \
  --batch 16 \
  --device 0 \
  --workers 8

python scripts/run_remote_experiments.py \
  --model-kind ghost-ca \
  --rdd-epochs 50 \
  --kz-epochs 30 \
  --imgsz 640 \
  --batch 16 \
  --device 0 \
  --workers 8
```

If a run is interrupted after RDD training finishes, resume only the evaluation
and Kazakhstan adaptation part:

```bash
python scripts/run_remote_experiments.py \
  --model-kind ghost-ca \
  --skip-rdd-train \
  --rdd-epochs 50 \
  --kz-epochs 30 \
  --imgsz 640 \
  --batch 16 \
  --device 0 \
  --workers 8
```

## 6. After Training

```bash
roadkz figures \
  --paper \
  --experiments data/manifests/experiments.csv \
  --output reports/paper_summary.json \
  --experiment-table reports/experiment_table.csv \
  --dataset-card reports/dataset_card.md \
  --figures-dir reports/figures

roadkz project-status \
  --output reports/project_status.json
```

Copy these back from the server:

- `data/manifests/experiments.csv`
- `reports/experiment_table.csv`
- `reports/paper_summary.json`
- `reports/project_status.json`
- `runs/detect/rdd_yolo11s/results.csv`
- `runs/detect/kz_adapt_yolo11s/results.csv`
- `runs/detect/rdd_ghost_ca_yolo11s/results.csv`
- `runs/detect/kz_adapt_ghost_ca_yolo11s/results.csv`

Do not publish raw images or RDD archives.
