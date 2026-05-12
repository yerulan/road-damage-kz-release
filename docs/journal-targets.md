# Journal Targets

## Recommendation

Optimize the first manuscript for **Applied Sciences** as an original research article. The current repo supports a Kazakhstan road-damage benchmark with Ghost-CA-YOLO adaptation and external validation, not a large standalone dataset claim. Internet-only image sourcing makes a data-only journal risky unless every image can be legally redistributed from a repository.

## Fit Matrix

| Journal | Best Article Type | Fit | Main Risk | Required Project Evidence |
| --- | --- | --- | --- | --- |
| Applied Sciences | Article | Strongest | Needs a clear technical contribution beyond data collection | Ghost-CA-YOLO, YOLO11s comparison, domain-shift analysis, reproducible methods, clear limitations |
| MDPI Data | Data Descriptor | Not yet | Dataset must be openly reusable and scientifically useful | Repository DOI, complete metadata, license-clean images, annotation protocol |
| Data in Brief | Data Article | Not yet | Requires deposited data linked from the article | Repository deposit, dataset citation, complete template, data value statement |

## Applied Sciences Positioning

The manuscript should emphasize:

- road-damage detection under Kazakhstan-specific visual conditions;
- provenance-aware data construction as a reproducibility and publication constraint, not as a large-dataset claim;
- comparison between global RDD training data and Kazakhstan-focused validation;
- Ghost-CA-YOLO performance, YOLO11s comparison, false negatives, errors, and deployment implications.

## Current Decision Gate

The repository is mechanically close to submission-ready, but the scientific evidence is still thin:

- current manifest: 3613 Kazakhstan image leads;
- current publishable benchmark: 75 rows;
- current damaged subset: 50 publishable images and 104 boxes, including 70 provisional fast-growth boxes mostly from a Shymkent Mapillary sequence;
- active final experiment cohort: YOLO11s and Ghost-CA-YOLO on RDD2022 validation, Kazakhstan RDD-only evaluation, and Kazakhstan-adapted evaluation.

Before treating the Applied Sciences article as a full submission, target at least 30-50 damaged Kazakhstan images, 100 strict reviewed boxes, and 3 represented detection classes. Prefer 100+ damaged Kazakhstan images plus normal hard negatives. The project has reached the damaged-image and total-box thresholds, but the newest Shymkent additions are sequence-correlated and provisional, so the next gate is strict review plus more independent damaged locations.

The next data-growth route should prioritize permissioned or source-specific imagery:

- Mapillary street-level Kazakhstan imagery collected through the API with attribution;
- Kazakhstan road authority or municipal repair imagery with explicit reuse terms;
- university or field-collected images with author permission and privacy review;
- partner-provided dashcam or inspection imagery with documented blur and reuse permission.

Do not spend major effort rerunning broad Commons searches unless a new, specific category/source appears.

## Data Journal Fallback Criteria

Switch to MDPI Data or Data in Brief only if all are true:

- at least 800 Kazakhstan road images are license-clean;
- every image can be redistributed or deposited;
- annotations pass quality checks;
- metadata includes source, author, license, location level, capture context, and privacy review;
- a repository DOI can be created before submission.

Data in Brief should be treated especially cautiously because it expects repository-linked research data. MDPI Data also expects dataset title/DOI/license metadata for a Data Descriptor.

## Reference Use

- `10.3390/app131910918` is useful as an Applied Sciences formatting/style example, but it is not a road-damage or computer-vision dataset anchor.
- `10.55648/1998-6920-2025-19-4-17-26` is not a direct road-damage computer-vision reference; use it only if there is a specific writing-method reason.

## Required Statements

The paper must include:

- Author Contributions;
- Funding;
- Data Availability;
- Conflicts of Interest;
- Ethics/privacy statement for public imagery;
- Generative AI disclosure if AI tools support writing, coding, data curation, or figure generation.
