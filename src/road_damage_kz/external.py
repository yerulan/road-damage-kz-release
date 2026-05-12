"""Import helpers for external road-damage datasets."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from pathlib import Path
import json
import random
import shutil
import xml.etree.ElementTree as ET


RDD_TO_PROJECT_CLASS = {
    "D00": 0,  # longitudinal crack
    "D10": 1,  # transverse crack
    "D20": 2,  # alligator crack
    "D40": 3,  # pothole
}

YOLO_NAMES = {
    0: "longitudinal_crack",
    1: "transverse_crack",
    2: "alligator_crack",
    3: "pothole",
}

RDD2022_COUNTRY_DOWNLOADS = {
    "japan": {
        "filename": "RDD2022_Japan.zip",
        "url": "https://bigdatacup.s3.ap-northeast-1.amazonaws.com/2022/CRDDC2022/RDD2022/Country_Specific_Data_CRDDC2022/RDD2022_Japan.zip",
        "size": "1022.9 MB",
    },
    "india": {
        "filename": "RDD2022_India.zip",
        "url": "https://bigdatacup.s3.ap-northeast-1.amazonaws.com/2022/CRDDC2022/RDD2022/Country_Specific_Data_CRDDC2022/RDD2022_India.zip",
        "size": "502.3 MB",
    },
    "czech": {
        "filename": "RDD2022_Czech.zip",
        "url": "https://bigdatacup.s3.ap-northeast-1.amazonaws.com/2022/CRDDC2022/RDD2022/Country_Specific_Data_CRDDC2022/RDD2022_Czech.zip",
        "size": "245.2 MB",
    },
    "united_states": {
        "filename": "RDD2022_United_States.zip",
        "url": "https://bigdatacup.s3.ap-northeast-1.amazonaws.com/2022/CRDDC2022/RDD2022/Country_Specific_Data_CRDDC2022/RDD2022_United_States.zip",
        "size": "423.8 MB",
    },
    "norway": {
        "filename": "RDD2022_Norway.zip",
        "url": "https://bigdatacup.s3.ap-northeast-1.amazonaws.com/2022/CRDDC2022/RDD2022/Country_Specific_Data_CRDDC2022/RDD2022_Norway.zip",
        "size": "9.9 GB",
    },
    "china_motorbike": {
        "filename": "RDD2022_China_MotorBike.zip",
        "url": "https://bigdatacup.s3.ap-northeast-1.amazonaws.com/2022/CRDDC2022/RDD2022/Country_Specific_Data_CRDDC2022/RDD2022_China_MotorBike.zip",
        "size": "183.1 MB",
    },
    "china_drone": {
        "filename": "RDD2022_China_Drone.zip",
        "url": "https://bigdatacup.s3.ap-northeast-1.amazonaws.com/2022/CRDDC2022/RDD2022/Country_Specific_Data_CRDDC2022/RDD2022_China_Drone.zip",
        "size": "152.8 MB",
    },
}

PRACTICAL_RDD2022_COUNTRIES = ["india", "czech", "united_states", "japan"]


@dataclass(frozen=True)
class RddSample:
    xml_path: Path
    image_path: Path
    labels: list[str]


def import_rdd_voc_dataset(
    rdd_root: Path,
    output_dir: Path,
    *,
    seed: int = 20260509,
    val_ratio: float = 0.15,
    copy_mode: str = "symlink",
    limit: int | None = None,
) -> dict[str, int]:
    """Convert RDD-style Pascal VOC annotations to YOLO format."""

    samples = discover_rdd_samples(rdd_root)
    if limit is not None:
        samples = samples[:limit]

    random.Random(seed).shuffle(samples)
    val_count = round(len(samples) * val_ratio)
    if len(samples) > 1:
        val_count = max(1, val_count)
    split_by_xml = {
        sample.xml_path: ("val" if index < val_count else "train")
        for index, sample in enumerate(samples)
    }

    for split in ["train", "val"]:
        (output_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    imported = 0
    boxes = 0
    skipped_empty = 0
    imported_by_split: Counter[str] = Counter()
    for sample in samples:
        if not sample.labels:
            skipped_empty += 1
            continue
        split = split_by_xml[sample.xml_path]
        target_image = output_dir / "images" / split / sample.image_path.name
        if copy_mode == "copy":
            shutil.copy2(sample.image_path, target_image)
        else:
            _replace_symlink(sample.image_path, target_image)

        label_path = output_dir / "labels" / split / f"{sample.image_path.stem}.txt"
        label_path.write_text("\n".join(sample.labels) + "\n", encoding="utf-8")
        imported += 1
        boxes += len(sample.labels)
        imported_by_split[split] += 1

    write_dataset_yaml(output_dir / "dataset.yaml", output_dir)
    class_distribution = class_distribution_from_samples([sample for sample in samples if sample.labels])
    summary = {
        "discovered": len(samples),
        "imported": imported,
        "boxes": boxes,
        "skipped_empty": skipped_empty,
        "train": imported_by_split["train"],
        "val": imported_by_split["val"],
        "class_distribution": dict(class_distribution),
    }
    write_json(output_dir / "import_summary.json", summary)
    return summary


def check_rdd_readiness(rdd_root: Path) -> dict:
    """Summarize whether an RDD-style Pascal VOC root is usable."""

    if not rdd_root.exists():
        return {
            "status": "missing_root",
            "rdd_root": str(rdd_root),
            "xml_files": 0,
            "matched_images": 0,
            "usable_images": 0,
            "boxes": 0,
            "class_distribution": {},
            "messages": [f"Missing RDD root: {rdd_root}"],
        }

    xml_files = sorted(rdd_root.rglob("*.xml"))
    if not xml_files:
        return {
            "status": "no_xml",
            "rdd_root": str(rdd_root),
            "xml_files": 0,
            "matched_images": 0,
            "usable_images": 0,
            "boxes": 0,
            "class_distribution": {},
            "messages": [f"No Pascal VOC XML files found under {rdd_root}"],
        }

    image_index = _build_image_index(rdd_root)
    matched = 0
    usable = 0
    boxes = 0
    distribution: Counter[str] = Counter()
    for xml_path in xml_files:
        if find_image_for_xml(xml_path, image_index) is None:
            continue
        matched += 1
        labels = labels_from_voc_xml(xml_path)
        if labels:
            usable += 1
            boxes += len(labels)
            distribution.update(class_name_from_label(label) for label in labels)

    status = "ready" if usable > 0 else "no_usable_annotations"
    messages = []
    if matched == 0:
        messages.append("XML files were found, but no matching image files were found.")
    if usable == 0:
        messages.append("No matched XML files contained supported RDD classes D00/D10/D20/D40.")
    return {
        "status": status,
        "rdd_root": str(rdd_root),
        "xml_files": len(xml_files),
        "matched_images": matched,
        "usable_images": usable,
        "boxes": boxes,
        "class_distribution": dict(distribution),
        "messages": messages,
    }


def rdd_download_script(countries: list[str], output_dir: Path) -> str:
    """Build a shell script for manually downloading selected RDD2022 archives."""

    normalized = [country.strip().lower().replace("-", "_").replace(" ", "_") for country in countries]
    unknown = [country for country in normalized if country not in RDD2022_COUNTRY_DOWNLOADS]
    if unknown:
        valid = ", ".join(sorted(RDD2022_COUNTRY_DOWNLOADS))
        raise ValueError(f"Unknown RDD2022 country key(s): {', '.join(unknown)}. Valid keys: {valid}")

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Review RDD2022 terms and citation requirements before running.",
        f"mkdir -p {output_dir}",
    ]
    for country in normalized:
        item = RDD2022_COUNTRY_DOWNLOADS[country]
        archive = output_dir / item["filename"]
        lines.extend(
            [
                "",
                f"# {country}: {item['size']}",
                f"curl -fL {shell_quote(item['url'])} -o {shell_quote(str(archive))}",
                f"unzip -t {shell_quote(str(archive))} >/dev/null",
                f"unzip -n {shell_quote(str(archive))} -d {shell_quote(str(output_dir))}",
            ]
        )
    lines.extend(
        [
            "",
            "roadkz check-rdd --rdd-root data/external/RDD2022 --report reports/rdd_readiness.json",
        ]
    )
    return "\n".join(lines) + "\n"


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def discover_rdd_samples(rdd_root: Path) -> list[RddSample]:
    """Find Pascal VOC XML files and matching images under an RDD root."""

    image_index = _build_image_index(rdd_root)
    samples: list[RddSample] = []
    for xml_path in sorted(rdd_root.rglob("*.xml")):
        image_path = find_image_for_xml(xml_path, image_index)
        if image_path is None:
            continue
        labels = labels_from_voc_xml(xml_path)
        samples.append(RddSample(xml_path=xml_path, image_path=image_path, labels=labels))
    return samples


def labels_from_voc_xml(xml_path: Path) -> list[str]:
    """Read RDD Pascal VOC boxes and convert known classes to YOLO lines."""

    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    if size is None:
        return []
    try:
        width = float(size.findtext("width", ""))
        height = float(size.findtext("height", ""))
    except ValueError:
        return []
    if width <= 0 or height <= 0:
        return []

    labels: list[str] = []
    for obj in root.findall("object"):
        class_name = (obj.findtext("name") or "").strip()
        class_id = RDD_TO_PROJECT_CLASS.get(class_name)
        box = obj.find("bndbox")
        if class_id is None or box is None:
            continue
        try:
            x_min = float(box.findtext("xmin", ""))
            y_min = float(box.findtext("ymin", ""))
            x_max = float(box.findtext("xmax", ""))
            y_max = float(box.findtext("ymax", ""))
        except ValueError:
            continue
        if x_max <= x_min or y_max <= y_min:
            continue
        x_min = max(0.0, min(x_min, width))
        x_max = max(0.0, min(x_max, width))
        y_min = max(0.0, min(y_min, height))
        y_max = max(0.0, min(y_max, height))
        x_center = ((x_min + x_max) / 2) / width
        y_center = ((y_min + y_max) / 2) / height
        box_width = (x_max - x_min) / width
        box_height = (y_max - y_min) / height
        labels.append(f"{class_id} {x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}")
    return labels


def class_distribution_from_samples(samples: list[RddSample]) -> Counter[str]:
    distribution: Counter[str] = Counter()
    for sample in samples:
        distribution.update(class_name_from_label(label) for label in sample.labels)
    return distribution


def class_name_from_label(label: str) -> str:
    class_id = int(label.split()[0])
    return YOLO_NAMES.get(class_id, f"class_{class_id}")


def find_image_for_xml(xml_path: Path, image_index: dict[str, Path]) -> Path | None:
    stem = xml_path.stem
    sibling_candidates = []
    for image_dir_name in ["images", "JPEGImages", "jpg", "img"]:
        sibling_candidates.extend(
            [
                xml_path.parent / image_dir_name / f"{stem}{suffix}"
                for suffix in [".jpg", ".jpeg", ".png"]
            ]
        )
        sibling_candidates.extend(
            [
                xml_path.parent.parent / image_dir_name / f"{stem}{suffix}"
                for suffix in [".jpg", ".jpeg", ".png"]
            ]
        )
    sibling_candidates.extend(xml_path.with_suffix(suffix) for suffix in [".jpg", ".jpeg", ".png"])
    for candidate in sibling_candidates:
        if candidate.exists():
            return candidate
    return image_index.get(stem)


def write_dataset_yaml(path: Path, output_dir: Path) -> None:
    lines = [
        f"path: {output_dir}",
        "train: images/train",
        "val: images/val",
        "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in YOLO_NAMES.items())
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_image_index(root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    for suffix in ["*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"]:
        for path in root.rglob(suffix):
            index.setdefault(path.stem, path)
    return index


def _replace_symlink(source: Path, target: Path) -> None:
    if target.exists() or target.is_symlink():
        target.unlink()
    target.symlink_to(source.resolve())
