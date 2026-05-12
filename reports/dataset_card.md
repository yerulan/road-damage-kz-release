# Kazakhstan Road Damage Benchmark Dataset Card

## Dataset Purpose

This benchmark supports external validation for road-damage detection models on license-audited Kazakhstan road imagery. It is not currently framed as a large standalone Kazakhstan training dataset.

## Current Contents

- Manifest rows: 3613
- Publishable rows: 75
- Publishable damaged rows: 50
- Publishable normal rows: 25
- Bounding boxes: 104
- Annotation review status:

| Item | Count |
| --- | ---: |
| `gold` | 34 |
| `provisional_fast_growth` | 70 |

## Class Distribution

| Item | Count |
| --- | ---: |
| `alligator_crack` | 35 |
| `longitudinal_crack` | 48 |
| `pothole` | 11 |
| `transverse_crack` | 10 |

## Split Distribution

| Item | Count |
| --- | ---: |
| `kz-test` | 10 |
| `train` | 53 |
| `val` | 12 |

## Source And License Policy

Images enter the publishable benchmark only when `license_ok=true`, source URL, author/owner attribution, reusable license metadata, and `privacy_checked=true` are recorded in `data/manifests/images.csv`. Web search and Openverse rows are discovery leads until source-page licensing is verified.

## Privacy Handling

Faces, readable license plates, and other personal identifiers must be blurred or the image is excluded. Publishable exports should use `data/manifests/privacy_safe_files.csv`.

## Redistribution Rule

The public release contains code, manifests, annotations, and reports. Raw third-party images are not redistributed by default. Reusers should reconstruct local image caches from recorded source URLs and respect each source license.

## Known Limitations

The Kazakhstan damaged subset is small and class-imbalanced. It is suitable for external validation and domain-shift analysis, not for claims of broad Kazakhstan road-damage coverage without further data collection.

## Publication Readiness

Applied Sciences remains the primary target, but the current benchmark is below the preferred strength for submission as a full domain-shift study.

- Minimum Applied Sciences target before submission: 30--50 damaged Kazakhstan images, 100 strict reviewed boxes, and 3 represented damage classes.
- Preferred Applied Sciences target: 100 or more damaged Kazakhstan images plus normal hard negatives.
- Data-journal fallback target: 800 or more redistributable license-clean Kazakhstan images with repository DOI.

Current status: 50 damaged images, 104 bounding boxes, and 4 represented detection classes. Boxes marked as provisional require strict second-pass review before final manuscript claims.
