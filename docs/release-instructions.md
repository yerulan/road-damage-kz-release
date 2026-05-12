# Public Release Instructions

The public release should make the work reproducible without redistributing raw third-party images.

## Include

- `src/road_damage_kz/`
- `tests/`
- `configs/`
- `scripts/run_remote_experiments.py`
- `data/manifests/images.csv`
- `data/manifests/annotations.csv`
- `data/manifests/experiments.csv`
- `data/manifests/external_datasets.csv`
- `docs/`
- `paper/`
- generated report tables and dataset card
- Ghost-CA-YOLO architecture config and Coordinate Attention implementation

## Exclude

- `data/raw/`
- `data/external/`
- `data/processed/`
- `runs/`
- unblurred third-party images
- RDD archives or extracted RDD images
- private author/admin files

## Reproducibility Notes

Users should reconstruct local image caches from the manifest source URLs and must respect the license recorded for each source. RDD data must be downloaded separately from the official RoadDamageDetector/RDD2022 source according to its terms.

The release should describe the Kazakhstan imagery as a source-reconstructable benchmark unless every raw image has explicit redistribution permission. Do not attach raw third-party images to the repository, supplementary ZIP, or data deposit by default.

Model weights may be released only if they do not bundle restricted data and all dependency licenses are acceptable for the target repository. If weights are not released, provide the exact training commands from `docs/ghost-ca-remote-training.md` and the recorded experiment table.

## Data-Journal Gate

Do not submit the release as an MDPI Data or Data in Brief data article unless all of the following are true:

- at least 800 Kazakhstan images are license-clean and redistributable;
- source URL, author/owner, license text or SPDX-like label, and privacy review are recorded for every image;
- annotations and metadata pass quality checks;
- a trusted repository DOI can be created and cited;
- the Data Availability statement can point to deposited data rather than only source-reconstruction instructions.

## Suggested Release Command

Recommended route: publish a GitHub release and archive that release through Zenodo to obtain a DOI. Use the DOI in the manuscript Data Availability Statement and cite the software/data package where appropriate.

After final checks pass, create a repository tag and attach:

- manuscript PDF;
- LaTeX source ZIP;
- supplementary ZIP with code, manifests, annotations, configs, docs, and report tables;
- no raw third-party images by default.

## Final Checks

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
roadkz figures --paper
roadkz project-status --fail-on-blockers
```
