# Release Notes

## v0.1.0-draft

Preparation release for the Applied Sciences submission package.

Includes:

- Kazakhstan road-image provenance and annotation manifests.
- Ghost-CA-YOLO architecture support through `configs/ghost_ca_yolo11s.yaml`.
- Coordinate Attention implementation in `src/road_damage_kz/ghost_ca.py`.
- Remote GPU experiment runner in `scripts/run_remote_experiments.py`.
- MDPI manuscript source and generated draft PDF.
- Dataset card, project-status report, and paper-supporting figures.
- Submission and release workflow documentation.

Excludes:

- raw third-party images;
- RDD2022 archives or extracted images;
- local processed datasets;
- model run folders and weights.

Before creating the final Zenodo release:

- sync real YOLO11s and Ghost-CA-YOLO metrics back from the GPU server;
- update manuscript tables, figures, abstract, discussion, and conclusion;
- regenerate `reports/experiment_table.csv`, `reports/paper_summary.json`, and `reports/project_status.json`;
- rebuild `submission_package/`;
- replace placeholder GitHub URLs in `CITATION.cff` and `.zenodo.json`;
- tag the final GitHub release as `v1.0.0`.
