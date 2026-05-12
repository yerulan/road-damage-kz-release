"""Helpers for draft object annotations."""

from __future__ import annotations

from pathlib import Path

from .schema import ANNOTATION_FIELDS, read_csv, write_csv

DETECTION_CLASSES = {"longitudinal_crack", "transverse_crack", "alligator_crack", "pothole"}


def draft_annotations(
    queue_path: Path,
    output_path: Path,
    *,
    preview_dir: Path | None = None,
    overwrite: bool = False,
    max_boxes_per_image: int = 4,
) -> dict[str, int]:
    try:
        import cv2
        import numpy as np
    except ModuleNotFoundError as error:  # pragma: no cover - depends on optional install
        raise RuntimeError("draft-annotations requires OpenCV and NumPy. Install with: pip install -e '.[privacy]'") from error

    existing_rows = [] if overwrite or not output_path.exists() else read_csv(output_path)
    existing_ids = {row.get("image_id", "") for row in existing_rows}
    rows = list(existing_rows)
    preview_written = 0
    queued = 0
    boxes_written = 0
    skipped_existing = 0
    skipped_missing = 0
    fallback_boxes = 0

    if preview_dir:
        preview_dir.mkdir(parents=True, exist_ok=True)

    for queue_row in read_csv(queue_path):
        image_id = queue_row.get("image_id", "")
        if not image_id:
            continue
        if image_id in existing_ids:
            skipped_existing += 1
            continue
        local_path = Path(queue_row.get("local_path", ""))
        if not local_path.exists():
            skipped_missing += 1
            continue

        image = cv2.imread(str(local_path))
        if image is None:
            skipped_missing += 1
            continue

        queued += 1
        labels = [
            label.strip()
            for label in queue_row.get("damage_labels", "").split(";")
            if label.strip() in DETECTION_CLASSES
        ]
        if not labels:
            continue

        boxes = _propose_boxes(cv2, np, image, max_boxes_per_image=max_boxes_per_image)
        used_fallback = False
        if not boxes:
            boxes = [_fallback_box(image)]
            used_fallback = True
            fallback_boxes += 1

        for box in boxes:
            class_name = _choose_class(labels, box)
            rows.append(
                {
                    "image_id": image_id,
                    "class_name": class_name,
                    "x_min": str(box[0]),
                    "y_min": str(box[1]),
                    "x_max": str(box[2]),
                    "y_max": str(box[3]),
                    "annotator": "roadkz_draft_annotations_v1",
                    "review_status": "draft_auto",
                    "notes": "Auto-proposed weak box; verify before using as gold annotation."
                    if not used_fallback
                    else "Fallback weak box; no crack-like connected component found.",
                }
            )
            boxes_written += 1

        if preview_dir:
            preview = image.copy()
            for box in boxes:
                color = (0, 255, 255) if not used_fallback else (0, 128, 255)
                cv2.rectangle(preview, (box[0], box[1]), (box[2], box[3]), color, 2)
            cv2.imwrite(str(preview_dir / f"{image_id}.jpg"), preview)
            preview_written += 1

    write_csv(output_path, rows, ANNOTATION_FIELDS)
    return {
        "queued": queued,
        "boxes_written": boxes_written,
        "skipped_existing": skipped_existing,
        "skipped_missing": skipped_missing,
        "fallback_boxes": fallback_boxes,
        "preview_written": preview_written,
    }


def _propose_boxes(cv2, np, image, *, max_boxes_per_image: int) -> list[tuple[int, int, int, int]]:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    roi_top = int(height * 0.25)
    roi = gray[roi_top:height, :]
    if roi.size == 0:
        return []

    blackhat_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    blackhat = cv2.morphologyEx(roi, cv2.MORPH_BLACKHAT, blackhat_kernel)
    blackhat = cv2.GaussianBlur(blackhat, (5, 5), 0)
    _, mask = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close_kernel, iterations=2)
    dilate_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.dilate(mask, dilate_kernel, iterations=2)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = width * height
    boxes = []
    for contour in contours:
        x, y, box_width, box_height = cv2.boundingRect(contour)
        y += roi_top
        area = box_width * box_height
        if area < max(80, image_area * 0.00025):
            continue
        if area > image_area * 0.20:
            continue
        if box_width < 8 or box_height < 8:
            continue
        boxes.append((x, y, x + box_width, y + box_height, area))

    boxes.sort(key=lambda item: item[4], reverse=True)
    return [(x1, y1, x2, y2) for x1, y1, x2, y2, _ in boxes[:max_boxes_per_image]]


def _fallback_box(image) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    return (
        int(width * 0.20),
        int(height * 0.55),
        int(width * 0.80),
        int(height * 0.90),
    )


def _choose_class(labels: list[str], box: tuple[int, int, int, int]) -> str:
    if len(labels) == 1:
        return labels[0]
    x_min, y_min, x_max, y_max = box
    box_width = x_max - x_min
    box_height = y_max - y_min
    if "transverse_crack" in labels and box_width > box_height * 1.35:
        return "transverse_crack"
    if "longitudinal_crack" in labels:
        return "longitudinal_crack"
    return labels[0]
