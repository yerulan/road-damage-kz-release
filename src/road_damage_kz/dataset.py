"""Dataset export helpers."""

from __future__ import annotations

from pathlib import Path
import random
import shutil
import struct

from .schema import (
    ANNOTATION_FIELDS,
    ANNOTATION_QUEUE_FIELDS,
    CLASSIFICATION_EXPORT_FIELDS,
    IMAGE_MANIFEST_FIELDS,
    audit_image_row,
    normalize_bool,
    read_csv,
    write_csv,
)

DETECTION_CLASS_IDS = {
    "longitudinal_crack": 0,
    "transverse_crack": 1,
    "alligator_crack": 2,
    "pothole": 3,
}

VALID_SPLITS = {"train", "val", "test", "kz-test"}


def export_classification_dataset(
    manifest_path: Path,
    cache_manifest_path: Path,
    output_dir: Path,
    *,
    copy_images: bool = True,
) -> dict[str, int]:
    manifest_rows = read_csv(manifest_path)
    cache_by_id = {row.get("image_id", ""): row for row in read_csv(cache_manifest_path)}
    image_dir = output_dir / "images"
    rows = []
    exported = 0
    missing_local = 0

    if copy_images:
        image_dir.mkdir(parents=True, exist_ok=True)

    for row in manifest_rows:
        if not is_publishable(row):
            continue
        cache = cache_by_id.get(row.get("image_id", ""))
        source_path = Path(cache.get("local_path", ""))
        if not source_path.exists():
            missing_local += 1
            continue
        suffix = source_path.suffix or ".jpg"
        export_path = image_dir / f"{row['image_id']}{suffix}"
        if copy_images:
            shutil.copy2(source_path, export_path)
        rows.append(
            {
                "image_id": row.get("image_id", ""),
                "export_path": str(export_path),
                "labels": row.get("damage_labels", ""),
                "source_url": row.get("source_url", ""),
                "license": row.get("license", ""),
                "author": row.get("author", ""),
                "split": row.get("split", ""),
            }
        )
        exported += 1

    write_csv(output_dir / "labels.csv", rows, CLASSIFICATION_EXPORT_FIELDS)
    return {"exported": exported, "missing_local": missing_local}


def export_annotation_queue(
    manifest_path: Path,
    cache_manifest_path: Path,
    output_path: Path,
) -> dict[str, int]:
    manifest_rows = read_csv(manifest_path)
    cache_by_id = {row.get("image_id", ""): row for row in read_csv(cache_manifest_path)}
    rows = []
    for row in manifest_rows:
        if not is_publishable(row):
            continue
        labels = row.get("damage_labels", "")
        if labels == "normal" or labels == "unknown":
            continue
        cache = cache_by_id.get(row.get("image_id", ""))
        rows.append(
            {
                "image_id": row.get("image_id", ""),
                "local_path": cache.get("local_path", ""),
                "source_url": row.get("source_url", ""),
                "damage_labels": labels,
                "annotation_needed": "true",
                "notes": "Create bounding boxes for each visible damage instance.",
            }
        )
    write_csv(output_path, rows, ANNOTATION_QUEUE_FIELDS)
    return {"queued": len(rows)}


def is_publishable(row: dict[str, str]) -> bool:
    return (
        normalize_bool(row.get("license_ok", ""))
        and normalize_bool(row.get("privacy_checked", ""))
        and not audit_image_row(row)
        and row.get("damage_labels", "") not in {"", "unknown"}
    )


def assign_dataset_splits(
    manifest_path: Path,
    output_path: Path,
    *,
    seed: int = 20260503,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_split: str = "kz-test",
) -> dict[str, int]:
    rows = read_csv(manifest_path)
    damaged = [row for row in rows if is_publishable(row) and row.get("damage_labels", "") != "normal"]
    normal = [row for row in rows if is_publishable(row) and row.get("damage_labels", "") == "normal"]

    assignments = {}
    for group, group_seed in [(damaged, seed), (normal, seed + 1)]:
        sorted_group = sorted(group, key=lambda row: row.get("image_id", ""))
        random.Random(group_seed).shuffle(sorted_group)
        for row, split in zip(sorted_group, _split_sequence(len(sorted_group), train_ratio, val_ratio, test_split)):
            assignments[row.get("image_id", "")] = split

    split_counts = {"train": 0, "val": 0, "test": 0, "kz-test": 0}
    assigned = 0
    for row in rows:
        image_id = row.get("image_id", "")
        if image_id in assignments:
            row["split"] = assignments[image_id]
            split_counts[row["split"]] += 1
            assigned += 1
        elif row.get("split", "") not in VALID_SPLITS:
            row["split"] = ""

    write_csv(output_path, rows, IMAGE_MANIFEST_FIELDS)
    return {
        "assigned": assigned,
        "damaged": len(damaged),
        "normal": len(normal),
        "train": split_counts["train"],
        "val": split_counts["val"],
        "test": split_counts["test"],
        "kz-test": split_counts["kz-test"],
    }


def _split_sequence(total: int, train_ratio: float, val_ratio: float, test_split: str) -> list[str]:
    if total <= 0:
        return []
    if total == 1:
        return [test_split]
    if total == 2:
        return ["train", test_split]

    train_count = max(1, round(total * train_ratio))
    val_count = max(1, round(total * val_ratio))
    test_count = total - train_count - val_count
    if test_count < 1:
        test_count = 1
        if train_count >= val_count and train_count > 1:
            train_count -= 1
        elif val_count > 1:
            val_count -= 1
    while train_count + val_count + test_count > total:
        if train_count > 1:
            train_count -= 1
        elif val_count > 1:
            val_count -= 1
        else:
            test_count -= 1

    return ["train"] * train_count + ["val"] * val_count + [test_split] * test_count


def prepare_yolo_dataset(
    manifest_path: Path,
    cache_manifest_path: Path,
    annotations_path: Path,
    output_dir: Path,
) -> dict[str, int]:
    """Materialize publishable rows and box annotations in YOLO format."""

    manifest_rows = read_csv(manifest_path)
    cache_by_id = {row.get("image_id", ""): row for row in read_csv(cache_manifest_path)}
    annotations = read_csv(annotations_path)
    annotations_by_id: dict[str, list[dict[str, str]]] = {}
    for row in annotations:
        image_id = row.get("image_id", "").strip()
        if not image_id:
            continue
        annotations_by_id.setdefault(image_id, []).append(row)

    for subdir in ["images", "labels"]:
        target = output_dir / subdir
        if target.exists():
            shutil.rmtree(target)
    for split in ["train", "val", "test", "kz-test"]:
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    copied_images = 0
    written_labels = 0
    skipped_missing_local = 0
    skipped_missing_annotations = 0
    invalid_annotations = 0

    for row in manifest_rows:
        if not is_publishable(row):
            continue

        image_id = row.get("image_id", "")
        labels = row.get("damage_labels", "")
        image_annotations = annotations_by_id.get(image_id, [])
        if labels != "normal" and not image_annotations:
            skipped_missing_annotations += 1
            continue

        cache = cache_by_id.get(image_id, {})
        source_path = Path(cache.get("local_path", ""))
        if not source_path.exists():
            skipped_missing_local += 1
            continue

        split = row.get("split", "").strip() or "kz-test"
        if split not in {"train", "val", "test", "kz-test"}:
            split = "kz-test"

        suffix = source_path.suffix or ".jpg"
        target_image = output_dir / "images" / split / f"{image_id}{suffix}"
        shutil.copy2(source_path, target_image)
        copied_images += 1

        label_lines: list[str] = []
        if labels != "normal":
            width, height = image_size(source_path)
            for annotation in image_annotations:
                line = yolo_label_line(annotation, width, height)
                if line is None:
                    invalid_annotations += 1
                    continue
                label_lines.append(line)

        label_path = output_dir / "labels" / split / f"{image_id}.txt"
        label_path.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")
        written_labels += 1

    return {
        "copied_images": copied_images,
        "written_label_files": written_labels,
        "skipped_missing_local": skipped_missing_local,
        "skipped_missing_annotations": skipped_missing_annotations,
        "invalid_annotations": invalid_annotations,
    }


def validate_box_annotations(
    annotations_path: Path,
    cache_manifest_path: Path,
) -> dict[str, int | list[str]]:
    cache_by_id = {row.get("image_id", ""): row for row in read_csv(cache_manifest_path)}
    errors: list[str] = []
    checked = 0

    for line_number, row in enumerate(read_csv(annotations_path), start=2):
        checked += 1
        image_id = row.get("image_id", "").strip()
        if not image_id:
            errors.append(f"line {line_number}: image_id is required")
            continue
        cache = cache_by_id.get(image_id)
        if not cache:
            errors.append(f"{image_id} line {line_number}: missing local cache row")
            continue
        local_path = Path(cache.get("local_path", ""))
        if not local_path.exists():
            errors.append(f"{image_id} line {line_number}: missing local file {local_path}")
            continue
        try:
            width, height = image_size(local_path)
        except ValueError as error:
            errors.append(f"{image_id} line {line_number}: {error}")
            continue
        if yolo_label_line(row, width, height) is None:
            errors.append(
                f"{image_id} line {line_number}: invalid class or box coordinates "
                f"for {width}x{height} image"
            )

    return {"checked": checked, "errors": len(errors), "messages": errors}


def yolo_label_line(annotation: dict[str, str], image_width: int, image_height: int) -> str | None:
    class_name = annotation.get("class_name", "").strip()
    class_id = DETECTION_CLASS_IDS.get(class_name)
    if class_id is None:
        return None
    try:
        x_min = float(annotation.get("x_min", ""))
        y_min = float(annotation.get("y_min", ""))
        x_max = float(annotation.get("x_max", ""))
        y_max = float(annotation.get("y_max", ""))
    except ValueError:
        return None

    if x_max <= x_min or y_max <= y_min:
        return None
    if x_min < 0 or y_min < 0 or x_max > image_width or y_max > image_height:
        return None

    x_center = ((x_min + x_max) / 2) / image_width
    y_center = ((y_min + y_max) / 2) / image_height
    width = (x_max - x_min) / image_width
    height = (y_max - y_min) / image_height
    return f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}"


def image_size(path: Path) -> tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as image:
            return image.size
    except ModuleNotFoundError:
        return _image_size_without_pillow(path)


def _image_size_without_pillow(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index < len(data):
            while index < len(data) and data[index] == 0xFF:
                index += 1
            if index >= len(data):
                break
            marker = data[index]
            index += 1
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(data):
                break
            segment_length = struct.unpack(">H", data[index : index + 2])[0]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if index + 7 > len(data):
                    break
                height = struct.unpack(">H", data[index + 3 : index + 5])[0]
                width = struct.unpack(">H", data[index + 5 : index + 7])[0]
                return width, height
            index += segment_length
    raise ValueError(f"Unsupported image format or unreadable image size: {path}")


def empty_annotations_file(path: Path) -> None:
    write_csv(path, [], ANNOTATION_FIELDS)
