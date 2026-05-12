# Applied Sciences Publication Plan

## Current Decision

Keep Applied Sciences as the primary target and frame the work as a Kazakhstan road-damage benchmark with Ghost-CA-YOLO adaptation and external validation. Do not describe the current repository as a large Kazakhstan road-damage dataset.

Current evidence:

- 3613 Kazakhstan image leads;
- 75 publishable rows after license and privacy review;
- 50 publishable damaged images;
- 104 bounding boxes, including 34 strict gold boxes and 70 provisional fast-growth boxes;
- RDD2022 imported as an external training source;
- previous RDD baseline runs recorded;
- YOLO11s and Ghost-CA-YOLO GPU experiments are the active final paper cohort.

## Evidence Targets

Minimum Applied Sciences target before full submission:

- 30-50 damaged Kazakhstan images;
- 100 or more strict reviewed boxes;
- at least 3 represented detection classes;
- RDD-only YOLO11s and Ghost-CA-YOLO results on RDD validation and Kazakhstan test;
- Kazakhstan-adapted YOLO11s and Ghost-CA-YOLO results on the unchanged Kazakhstan test split;
- efficiency indicators for Ghost-CA-YOLO relative to YOLO11s.

The project now reaches the damaged-image and total-box thresholds, but not yet the strict-reviewed annotation threshold. The fast-growth Shymkent sequence should be treated as provisional until a strict second pass confirms boxes and prevents sequence leakage across train/validation/test splits.

Preferred Applied Sciences target:

- 100 or more damaged Kazakhstan images;
- normal hard negatives across weather, road type, city, and rural contexts;
- RDD-only and RDD+Kazakhstan-adapted experiment rows.

Data-journal fallback target:

- 800 or more license-clean redistributable Kazakhstan images;
- complete source, author, license, privacy, and annotation metadata;
- repository DOI and dataset citation.

## Next Data Route

Commons and broad keyword search are close to saturated for Kazakhstan pavement distress. Prioritize:

- Mapillary existing Kazakhstan street-level imagery collected through the API;
- Kazakhstan road authority or municipal road-repair imagery with written reuse terms;
- university or field-collected photos with author permission and privacy review;
- partner dashcam or inspection imagery with documented blur/reuse permission;
- source-specific open datasets where the original license can be verified from the source page.

Every new image must keep the manifest rule: source URL, author/owner, license label or permission text, `license_ok=true`, and `privacy_checked=true` before it can be publishable.

## Manuscript Work

Maintain [paper/main.tex](/Users/belesprit/Documents/New%20project/paper/main.tex) as an Applied Sciences Article. The Results and Discussion should foreground:

- discovery-to-publishable attrition;
- privacy and licensing as methodological constraints;
- RDD validation performance;
- Ghost-CA-YOLO architecture and efficiency;
- Kazakhstan false negatives and domain-shift failure modes;
- limits imposed by the current Kazakhstan sample size.

The Data Availability statement should release code, manifests, annotations, and reports, while excluding raw third-party images unless explicit redistribution permission is recorded.
