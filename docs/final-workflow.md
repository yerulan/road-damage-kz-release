# Final Workflow

This workflow produces the Applied Sciences submission package without redistributing raw third-party images.

## 0. Publication Strength Gate

Use Applied Sciences as the primary target, but do not position the paper as a large standalone Kazakhstan dataset. The current defensible framing is a Kazakhstan road-damage benchmark with Ghost-CA-YOLO adaptation and external validation.

Before final submission, either meet these minimum evidence targets or explicitly frame the article as a small pilot study:

- 30-50 damaged Kazakhstan images;
- 100 or more gold bounding boxes;
- at least 3 represented detection classes;
- paper-eligible RDD-only and Kazakhstan-evaluation rows;
- either nonzero adaptation/domain-shift evidence or a careful sample-size-limited interpretation of zero Kazakhstan metrics.

Preferred evidence is 100+ damaged Kazakhstan images plus normal hard negatives. MDPI Data and Data in Brief remain fallbacks only if the project reaches about 800 redistributable license-clean images and can create a repository DOI.

## 1. Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev,ml,privacy]"
```

## 2. Kazakhstan Benchmark Checks

```bash
roadkz audit-licenses \
  --manifest data/manifests/images.csv \
  --report reports/license_audit.json

roadkz validate-annotations \
  --annotations data/manifests/annotations.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv

roadkz dedupe \
  --manifest data/manifests/images.csv \
  --report reports/dedupe_report.json

roadkz prepare \
  --format yolo \
  --manifest data/manifests/images.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv \
  --annotations data/manifests/annotations.csv \
  --config configs/dataset.yaml \
  --output-dir data/processed/yolo
```

## 3. RDD2022 Practical Subset

Download RDD2022 manually from the official RoadDamageDetector/RDD2022 source, review the terms, and extract a practical subset under:

```text
data/external/RDD2022/
```

Default subset for the paper run: India, Czech, United States, and Japan. Keep Norway optional because of archive size.

Generate a reviewable download script:

```bash
roadkz rdd-download-plan \
  --script reports/rdd_download_plan.sh
```

The generated script uses the official country-specific RDD2022 archive URLs from RoadDamageDetector and then runs `roadkz check-rdd`. Review terms, disk space, and network limits before executing it:

```bash
bash reports/rdd_download_plan.sh
```

Then run:

```bash
roadkz check-rdd \
  --rdd-root data/external/RDD2022 \
  --report reports/rdd_readiness.json \
  --fail-on-not-ready

roadkz import-rdd-voc \
  --rdd-root data/external/RDD2022 \
  --output-dir data/processed/rdd_yolo \
  --copy-mode symlink
```

## 4. Paper Experiments

Run the YOLO11s baseline and Ghost-CA-YOLO experiment on the GPU server:

```bash
python scripts/run_remote_experiments.py \
  --model-kind yolo11s \
  --rdd-epochs 50 \
  --kz-epochs 30 \
  --imgsz 640 \
  --batch 16 \
  --device 0 \
  --workers 8
```

```bash
python scripts/run_remote_experiments.py \
  --model-kind ghost-ca \
  --rdd-epochs 50 \
  --kz-epochs 30 \
  --imgsz 640 \
  --batch 16 \
  --device 0 \
  --workers 8
```

The commands record paper-eligible train/evaluation rows in `data/manifests/experiments.csv`, including RDD2022 validation, RDD-only Kazakhstan external validation, and Kazakhstan-adapted evaluation.

## 5. Paper Artifacts

```bash
roadkz figures \
  --paper \
  --output reports/paper_summary.json \
  --experiment-table reports/experiment_table.csv \
  --dataset-card reports/dataset_card.md \
  --figures-dir reports/figures

roadkz project-status \
  --output reports/project_status.json
```

Expected generated artifacts:

- `reports/paper_summary.json`
- `reports/experiment_table.csv`
- `reports/dataset_card.md`
- `reports/figures/*.csv`
- `reports/figures/sample_annotation.jpg`
- `reports/project_status.json`

## 6. Public Release

Follow `docs/release-instructions.md`. The public release should include code, manifests, annotations, configs, docs, paper source, and report tables. It should exclude raw third-party images, RDD archives, extracted RDD images, model run folders, and local processed data unless a source-specific redistribution right is explicitly recorded.

## 7. Manuscript And Submission

Use the official MDPI LaTeX template in `paper/Definitions/`. Compile from `paper/main.tex` after the YOLO11s/Ghost-CA-YOLO rows are recorded and manuscript result placeholders are replaced.

```bash
cd paper
pdflatex main.tex
pdflatex main.tex
```

Before submission, run:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
roadkz project-status --fail-on-blockers
```

`project-status` may report publication-strength warnings even when blockers are clear. Treat those warnings as manuscript acceptance gates: resolve them with more data/experiments or discuss them directly as limitations.

Known blockers before final submission:

- RDD2022 practical subset must be downloaded/imported.
- Paper-eligible YOLO11s and Ghost-CA-YOLO experiment rows must exist.
- Manuscript dataset and metric counts must match regenerated reports.
- Author names, affiliations, ORCID, funding, acknowledgments, and suggested reviewers must be finalized.
