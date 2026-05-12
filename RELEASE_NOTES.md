# Release Notes

## v0.1.1

Submission-ready GitHub-only release. This update removes the requirement for
a Zenodo DOI, points the manuscript Data Availability Statement to the public
GitHub release repository, adds the MDPI AI-assisted preparation disclosure,
and rebuilds the manuscript and submission package.

## v0.1.0

Initial public release for the Applied Sciences submission package.

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

The public repository for citation and data availability is:

```text
https://github.com/yerulan/road-damage-kz-release
```

Zenodo archiving can be added later if available; this release is designed to
support journal submission through the public GitHub repository.
