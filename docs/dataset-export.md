# Dataset Export

The project now has two dataset tracks:

- **Image-level classification export**, available now for publishable rows.
- **Object-detection export**, blocked until bounding boxes are annotated.

## Image-Level Dataset

After triage decisions are applied and the license audit passes for some rows:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli export-classification-dataset \
  --manifest data/manifests/images.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv \
  --output-dir data/processed/classification
```

Output:

- `data/processed/classification/images/`
- `data/processed/classification/labels.csv`

This export includes only rows with `license_ok=true`, `privacy_checked=true`, and non-`unknown` labels.

## Annotation Queue

For object detection, damaged images need bounding boxes:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli annotation-queue \
  --manifest data/manifests/images.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv \
  --output data/manifests/annotation_queue.csv
```

Use this queue in CVAT, Label Studio, or LabelImg. Export annotations into `data/manifests/annotations.csv` using the columns already defined there.

If hand annotation is not feasible, generate weak draft boxes:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli draft-annotations \
  --queue data/manifests/annotation_queue.csv \
  --output data/manifests/annotations.csv \
  --preview-dir reports/annotation_previews \
  --overwrite
```

## Object Detection Dataset

Once `annotations.csv` contains bounding boxes:

```bash
PYTHONPATH=src python3 -m road_damage_kz.cli validate-annotations \
  --annotations data/manifests/annotations.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv

PYTHONPATH=src python3 -m road_damage_kz.cli prepare \
  --format yolo \
  --manifest data/manifests/images.csv \
  --cache-manifest data/manifests/privacy_safe_files.csv \
  --annotations data/manifests/annotations.csv \
  --config configs/dataset.yaml \
  --output-dir data/processed/yolo
```

`prepare` copies only publishable rows. Damaged rows are skipped until at least one bounding box exists in `annotations.csv`; normal rows are copied with empty YOLO label files so they can act as negative examples.

Annotation boxes use pixel coordinates:

```csv
image_id,class_name,x_min,y_min,x_max,y_max,annotator,review_status,notes
commons_123,longitudinal_crack,120,420,260,470,belesprit,draft,
```
