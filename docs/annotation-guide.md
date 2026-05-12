# Annotation Guide

## Task

The primary task is object detection. Each visible road damage instance receives a bounding box and one class label. Image-level classification can be derived later from the boxes.

## Classes

| ID | Name | Definition |
| --- | --- | --- |
| 0 | `longitudinal_crack` | Crack running mostly parallel to the road direction |
| 1 | `transverse_crack` | Crack running mostly across the road direction |
| 2 | `alligator_crack` | Interconnected crack pattern resembling a network/block surface |
| 3 | `pothole` | Bowl-shaped pavement loss, depression, or open hole |
| 4 | `normal` | Image has no visible target damage; use only for image-level tasks, not box labels |

## Bounding Box Rules

- Draw tight boxes around the visible damaged surface.
- Include the full visible damaged region, not surrounding intact asphalt.
- For connected alligator cracks, one box may cover the connected pattern.
- For clearly separate defects, create separate boxes.
- Do not label shadows, stains, lane markings, gravel, manholes, or road seams unless they are visibly damaged.
- If the image is too ambiguous, mark it in the manifest notes and exclude it from model evaluation.

## Annotation CSV

Use `data/manifests/annotations.csv` as the canonical box ledger:

```csv
image_id,class_name,x_min,y_min,x_max,y_max,annotator,review_status,notes
```

Coordinates are pixel coordinates in the privacy-safe local image named by `data/manifests/annotation_queue.csv`. `x_min,y_min` is the top-left corner; `x_max,y_max` is the bottom-right corner. Keep `class_name` to one of the four detection classes; `normal` is image-level only and must not appear in box rows.

## Difficult Cases

- **Wet potholes:** label as `pothole` if the road depression boundary is visible.
- **Patched areas:** exclude unless there is active cracking or pothole damage.
- **Snow/ice cover:** label only visible pavement damage; otherwise mark as context-only.
- **Dirt roads:** keep only if the road surface damage is comparable to the paved-road taxonomy; otherwise exclude from the benchmark.

## Quality Control

- At least 10% of annotations should be reviewed by a second pass.
- Resolve class disagreements before training.
- Track annotation tool, annotator, and review status in annotation exports.
- Ensure no duplicate or near-duplicate image appears across train/validation/test splits.

## Automatic Draft Boxes

If manual annotation is not feasible, create weak draft boxes from the annotation queue:

```bash
roadkz draft-annotations \
  --queue data/manifests/annotation_queue.csv \
  --output data/manifests/annotations.csv \
  --preview-dir reports/annotation_previews \
  --overwrite
```

This uses image-processing heuristics to propose crack-like boxes and writes `review_status=draft_auto`. Treat these as weak labels for pilot experiments, not journal-grade gold annotations. The preview images in `reports/annotation_previews/` make later spot checks much faster.
