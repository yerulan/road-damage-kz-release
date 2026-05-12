# Applied Sciences Submission Checklist

Target journal: MDPI Applied Sciences, Article type.

## Technical Package

- [ ] `paper/Definitions/` contains the current official MDPI LaTeX template files.
- [ ] `paper/main.tex` compiles to PDF without errors.
- [ ] All figures referenced in the manuscript exist and are rights-safe.
- [ ] Figure files are at least 1000 px width/height or 300 dpi where applicable.
- [ ] The LaTeX source folder can be zipped with all required figures and `Definitions/`.
- [ ] Supplementary files exclude raw third-party images unless redistribution rights are explicit.

## Data And Reproducibility

- [ ] `reports/project_status.json` has no blockers except administrative fields.
- [ ] `reports/project_status.json` publication-strategy warnings have been explicitly addressed in the manuscript limitations or resolved by new data.
- [ ] `reports/dataset_card.md` describes source policy, labels, splits, privacy, and limitations.
- [ ] `reports/paper_summary.json` and `reports/experiment_table.csv` are regenerated from scripts.
- [ ] `data/manifests/experiments.csv` contains paper-eligible YOLO11s and Ghost-CA-YOLO rows.
- [ ] Experiment rows include RDD2022 validation, Kazakhstan RDD-only evaluation, and Kazakhstan-adapted evaluation for both models.
- [ ] Ghost-CA-YOLO parameter count, GFLOPs, and inference-speed values are recorded or exported from the training logs.
- [ ] Manuscript counts match regenerated reports; no stale manifest, publishable-row, annotation, or experiment counts remain.
- [ ] Current Applied Sciences evidence is at least 30-50 damaged Kazakhstan images, 100 gold boxes, and 3 represented detection classes, or the manuscript is explicitly framed as a small pilot/domain-shift case study.
- [ ] Kazakhstan evaluation contains either nonzero adaptation/domain-shift evidence or a carefully argued sample-size-limited zero-result interpretation.
- [ ] RDD raw images are not included in the public release.
- [ ] Kazakhstan raw third-party images are not redistributed by default.
- [ ] Data Availability statement explains code/manifests release and source reconstruction.

## Manuscript

- [ ] Title, author names, affiliations, emails, and ORCID identifiers are final.
- [ ] Abstract reports only verified dataset sizes and model metrics.
- [ ] Methods describe source discovery, license audit, privacy handling, annotation taxonomy, RDD import, Ghost-CA-YOLO architecture, training settings, and evaluation metrics.
- [ ] Results tables match `reports/experiment_table.csv`.
- [ ] Ghost-CA-YOLO efficiency table and figures match measured server outputs, not draft estimates.
- [ ] Limitations explicitly state the small Kazakhstan damaged subset and licensing constraints.
- [ ] Funding, Acknowledgments, Author Contributions, Conflicts of Interest, and Data Availability are complete.
- [ ] References include RDD, RoadDamageDetector/RDD2022, YOLO/Ultralytics, road-damage surveys, and Kazakhstan context.

## SUSY Submission

- [ ] Submit via MDPI SUSY for Applied Sciences.
- [ ] Upload manuscript PDF and LaTeX source ZIP.
- [ ] Upload supplementary ZIP with code/manifests/report tables, excluding raw third-party images.
- [ ] Paste cover letter text from `paper/cover-letter.md`.
- [ ] Provide suggested reviewers with institutional emails and no conflicts.
- [ ] Confirm all authors approved the manuscript.
- [ ] Confirm publication ethics, copyright, figure permissions, and conflicts statements.
- [ ] Confirm APC expectation before final submission; Applied Sciences APC was CHF 2400 when checked in May 2026.

## Final Local Commands

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
.venv/bin/roadkz figures --paper
.venv/bin/roadkz project-status --fail-on-blockers
```

`pytest` is optional; use the `unittest` command above when the active virtual environment does not include the `dev` extra.
