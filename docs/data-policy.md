# Data Policy

## Core Rule

Only license-clean images may enter the publishable dataset. A file being visible online is not permission to copy, annotate, redistribute, or deposit it.

## Allowed Image Sources

- Wikimedia Commons images with explicit reusable licenses.
- Mapillary street-level images collected through the Mapillary API with attribution and CC-BY-SA obligations recorded.
- Government or institutional open-data portals with clear reuse terms.
- Public datasets with open licenses compatible with redistribution.
- Directly permissioned images, if permission text is stored in the manifest or a linked permission file.

## Publication Data-Growth Policy

Broad Commons and search-based discovery is now treated as a low-yield source for Kazakhstan pavement distress. For an Applied Sciences submission, prioritize source-specific or permissioned imagery before repeating broad searches:

- Kazakhstan road authority or municipal road-repair imagery with clear reuse terms;
- university or field-collected images with author permission;
- partner dashcam or inspection imagery with explicit blur/reuse permission;
- source-specific open datasets where licensing can be verified from the original source page.

The current minimum target for a full Applied Sciences domain-shift article is 30-50 damaged Kazakhstan images, 100 or more gold boxes, and at least 3 represented detection classes. A data-journal route requires a much larger redistributable dataset and should remain a fallback.

## Mapillary Workflow

Use Mapillary as the next best no-fieldwork source after Commons saturation. Mapillary Help states that images are shared under CC-BY-SA with attribution, and that uploaded images are processed for face and license-plate blurring. This is useful, but it does not replace project privacy review.

Example:

```bash
MAPILLARY_ACCESS_TOKEN=... roadkz collect-mapillary \
  --city almaty \
  --limit 200 \
  --grid-size 6 \
  --output data/manifests/images.csv \
  --report reports/mapillary_almaty_report.json
```

Custom bounding box:

```bash
MAPILLARY_ACCESS_TOKEN=... roadkz collect-mapillary \
  --bbox 76.74,43.15,77.08,43.36 \
  --region Almaty \
  --grid-size 6 \
  --limit 200
```

Mapillary rows are eligible for triage because the source license is recorded as `CC-BY-SA-4.0` when creator attribution and a thumbnail URL are present. They still keep `privacy_checked=false` until manual or automated privacy review passes.

If a city-level query returns HTTP 500 or a timeout-like error, retry with a larger `--grid-size` so the collector asks Mapillary for smaller tiles.

Attribution rule for manuscript/release material:

```text
Mapillary image <source URL> by <Mapillary username>, licensed under CC-BY-SA-4.0.
```

Do not mix Mapillary rows into a differently licensed dataset without documenting share-alike implications.

## Wikimedia Commons Workflow

Use `roadkz collect-commons` to collect file-level metadata from a Commons category. The collector can set `license_ok=true` when Commons metadata contains an approved license, author, and direct file URL, but it always leaves `privacy_checked=false`. A human or dedicated privacy-review step must inspect faces, license plates, and other identifiers before publication.

Use `roadkz triage-sheet --license-ready-only` after collection to create `data/manifests/triage.csv`. Triage should mark whether the image is a photograph, whether road surface is visible, whether target damage is visible, and whether privacy review passes.

Recommended action values in `data/manifests/triage.csv`:

- `include`: promote the row back into `images.csv` if license, road visibility, damage labels, and privacy checks pass.
- `exclude`: keep the row out of the publishable manifest; the reason should be recorded in triage notes.
- `needs_review`: defer the decision.

Run `roadkz triage-gallery` for a browser-friendly visual review and `roadkz apply-triage` after the sheet is filled.

See `docs/triage-workflow.md` for the exact review and promotion steps.

## Openverse Discovery Workflow

Use `roadkz collect-openverse-search` to find broader open-web image leads from the public Openverse API (`https://api.openverse.org/v1/images/`). By default, this command writes manifest-compatible rows with `license_ok=false` even when Openverse returns a Creative Commons license. This is intentional: Openverse metadata is useful for discovery, but the source page must still be checked before an image can become publishable.

Example:

```bash
roadkz collect-openverse-search \
  --query "Kazakhstan pothole road" \
  --query "Kazakhstan cracked asphalt" \
  --limit 50 \
  --output data/manifests/images.csv \
  --report reports/openverse_search_report.json
```

Only use `--trust-openverse-license` for exploratory local experiments where accepting Openverse metadata as license evidence has been explicitly approved. Even then, `privacy_checked` remains `false`, and source attribution must be reviewed before publication.

## Discovery-Only Sources

These can be used to find leads but not directly redistributed unless a compatible license is confirmed:

- Openverse rows whose source-page license has not yet been verified;
- news articles;
- social media;
- forums;
- map/street-view platforms;
- search engine image results;
- personal blogs without explicit licensing.

## Manifest Requirements

The canonical ledger is `data/manifests/images.csv`. Required fields:

| Field | Meaning |
| --- | --- |
| `image_id` | Stable project identifier |
| `source_url` | Page describing the source and license |
| `download_url` | Direct file URL when available |
| `license` | License label or permission note |
| `author` | Creator or rights holder |
| `country` | Country represented by the image |
| `region` | Region/province if known |
| `city` | City/locality if known |
| `capture_context` | Road, street, highway, snowy road, dashcam, etc. |
| `damage_labels` | Semicolon-separated known labels or `unknown` before annotation |
| `split` | `train`, `val`, `test`, `kz-test`, or blank before split |
| `license_ok` | `true` only after audit |
| `privacy_checked` | `true` only after review/blur |
| `notes` | Free-text caveats |

## License Audit Rules

`license_ok=true` requires:

- source URL present;
- author present or source declares public domain/official release;
- license present and compatible with reuse;
- download URL or local file traceable to source;
- privacy review completed.

Preferred license labels include `CC0-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`, `PDM`, `MIT`, or explicit written permission. Restrictive, unknown, editorial-only, or non-commercial-only sources are excluded from the publishable dataset unless the selected journal explicitly allows the intended use and redistribution.

## Privacy Policy

- Blur faces and license plates before publication.
- Exclude images where privacy cannot be resolved.
- Record `privacy_checked=true` only after manual or automated review.
- Store unblurred raw images only locally, never in git.

Automated privacy workflow:

```bash
roadkz privacy-scan \
  --cache-manifest data/manifests/local_files.csv \
  --output data/manifests/privacy_report.csv

roadkz blur-privacy \
  --privacy-report data/manifests/privacy_report.csv \
  --output-dir data/processed/privacy_blurred \
  --output-manifest data/manifests/privacy_blurred_files.csv

roadkz apply-privacy \
  --triage data/manifests/triage.csv \
  --privacy-report data/manifests/privacy_report.csv \
  --blur-manifest data/manifests/privacy_blurred_files.csv
```

The privacy scanner is an aid, not legal proof. Use `--trust-clear` only after spot-checking false negatives on the current batch. Any image with unresolved detections must remain `needs_review` or be excluded.

By default, `privacy-scan` uses face detection only. The `--detect-plates` option is experimental because simple plate-like geometry creates many false positives on pavement textures, signs, and road markings.

## Citation Policy

Every external dataset and image source used in the manuscript must be cited or attributed. Dataset references should include DOI or repository URL when available.
