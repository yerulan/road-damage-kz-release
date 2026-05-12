# Post-Training Finalization Checklist

Use this checklist after the GPU server finishes YOLO11s and Ghost-CA-YOLO runs.

## 1. Copy Back Server Outputs

From the Mac:

```bash
cd "/Users/belesprit/Documents/New project"

rsync -azP \
  slide:~/yerulan/paper/data/manifests/experiments.csv \
  data/manifests/experiments.csv

rsync -azP \
  slide:~/yerulan/paper/reports/experiment_table.csv \
  slide:~/yerulan/paper/reports/paper_summary.json \
  slide:~/yerulan/paper/reports/project_status.json \
  reports/

rsync -azP \
  slide:~/yerulan/paper/runs/detect/ \
  runs/detect/
```

## 2. Check Metrics Are Present

```bash
.venv/bin/python - <<'PY'
import csv
from pathlib import Path

path = Path("data/manifests/experiments.csv")
rows = list(csv.DictReader(path.open()))
for row in rows:
    if row.get("paper_eligible") == "true":
        print(row["model"], row["phase"], row["training_dataset"], row["evaluation_dataset"], row["map50"], row["map50_95"])
PY
```

Expected paper rows:

- YOLO11s trained on RDD2022, evaluated on RDD2022 validation.
- YOLO11s trained on RDD2022, evaluated on Kazakhstan test.
- YOLO11s fine-tuned on Kazakhstan, evaluated on Kazakhstan test.
- Ghost-CA-YOLO trained on RDD2022, evaluated on RDD2022 validation.
- Ghost-CA-YOLO trained on RDD2022, evaluated on Kazakhstan test.
- Ghost-CA-YOLO fine-tuned on Kazakhstan, evaluated on Kazakhstan test.

## 3. Regenerate Reports And Figures

```bash
.venv/bin/roadkz figures \
  --paper \
  --experiments data/manifests/experiments.csv \
  --output reports/paper_summary.json \
  --experiment-table reports/experiment_table.csv \
  --dataset-card reports/dataset_card.md \
  --figures-dir reports/figures

env MPLCONFIGDIR=/private/tmp/roadkz-mpl-cache \
  .venv/bin/python paper/make_figures.py
```

## 4. Update Manuscript

Replace the draft metric values in `paper/main.tex` with measured values from:

- `reports/experiment_table.csv`
- `data/manifests/experiments.csv`
- `runs/detect/*/results.csv`

Update these manuscript locations:

- Abstract model results.
- RDD2022 validation table.
- Kazakhstan external-validation table.
- Class-level table, if class-level metrics are exported.
- Ghost-CA-YOLO efficiency table.
- Discussion and conclusion result statements.

## 5. Final Validation

```bash
cd "/Users/belesprit/Documents/New project"

.venv/bin/python -m unittest discover -s tests
.venv/bin/roadkz project-status --output reports/project_status.json

cd paper
tectonic --keep-logs main.tex
```

Before submission, the project-status report should have no blockers. Warnings
about dataset size are acceptable only if the limitations section discusses
sample size, class imbalance, and sequence grouping directly.
