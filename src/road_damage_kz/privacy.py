"""Privacy scanning and blurring helpers for local candidate images."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json

from .schema import (
    LOCAL_FILE_FIELDS,
    PRIVACY_REPORT_FIELDS,
    TRIAGE_FIELDS,
    normalize_bool,
    read_csv,
    write_csv,
)


@dataclass(frozen=True)
class Detection:
    kind: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "confidence": self.confidence,
        }


def scan_privacy(
    cache_manifest: Path,
    output: Path,
    *,
    detector: object | None = None,
    detect_plates: bool = False,
    limit: int | None = None,
    include_failed: bool = False,
) -> dict[str, int]:
    rows = [
        row
        for row in read_csv(cache_manifest)
        if include_failed or row.get("status") in {"downloaded", "cached", "blurred"}
    ]
    if limit is not None:
        rows = rows[:limit]
    detector = detector or OpenCvPrivacyDetector(detect_plates=detect_plates)

    report_rows = []
    summary = {"scanned": 0, "clear": 0, "needs_blur": 0, "failed": 0, "missing": 0}
    for row in rows:
        local_path = Path(row.get("local_path", ""))
        base = {
            "image_id": row.get("image_id", ""),
            "local_path": row.get("local_path", ""),
            "source_url": row.get("source_url", ""),
            "face_count": "0",
            "plate_candidate_count": "0",
            "total_regions": "0",
            "blur_required": "false",
            "detections_json": "[]",
            "notes": "",
        }
        if not local_path.exists():
            summary["missing"] += 1
            report_rows.append(
                base
                | {
                    "status": "missing_file",
                    "notes": "Privacy scan skipped because local file is missing.",
                }
            )
            continue

        try:
            detections = detector.detect(local_path)
            face_count = sum(1 for detection in detections if detection.kind == "face")
            plate_count = sum(
                1 for detection in detections if detection.kind == "plate_candidate"
            )
            status = "needs_blur" if detections else "clear"
            summary["scanned"] += 1
            summary["needs_blur" if detections else "clear"] += 1
            report_rows.append(
                base
                | {
                    "status": status,
                    "face_count": str(face_count),
                    "plate_candidate_count": str(plate_count),
                    "total_regions": str(len(detections)),
                    "blur_required": str(bool(detections)).lower(),
                    "detections_json": json.dumps(
                        [detection.as_dict() for detection in detections],
                        separators=(",", ":"),
                    ),
                    "notes": (
                        "Automated privacy scan found regions requiring blur."
                        if detections
                        else "Automated privacy scan found no face or plate-candidate regions."
                    ),
                }
            )
        except RuntimeError as exc:
            raise
        except Exception as exc:  # pragma: no cover - defensive around image codecs
            summary["failed"] += 1
            report_rows.append(
                base
                | {
                    "status": "scan_failed",
                    "notes": f"Privacy scan failed: {exc}",
                }
            )

    write_csv(output, report_rows, PRIVACY_REPORT_FIELDS)
    return summary


def blur_privacy_regions(
    privacy_report: Path,
    output_dir: Path,
    output_manifest: Path,
) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    detector = OpenCvPrivacyDetector()
    rows = read_csv(privacy_report)
    blurred_rows = []
    summary = {"blurred": 0, "skipped": 0, "failed": 0}

    for row in rows:
        if not normalize_bool(row.get("blur_required", "")):
            summary["skipped"] += 1
            continue
        local_path = Path(row.get("local_path", ""))
        detections = detections_from_json(row.get("detections_json", "[]"))
        if not local_path.exists() or not detections:
            summary["failed"] += 1
            continue
        output_path = output_dir / local_path.name
        try:
            detector.blur_file(local_path, output_path, detections)
        except Exception:  # pragma: no cover - defensive around image codecs
            summary["failed"] += 1
            continue
        payload = output_path.read_bytes()
        blurred_rows.append(
            {
                "image_id": row.get("image_id", ""),
                "source_url": row.get("source_url", ""),
                "download_url": "",
                "local_path": str(output_path),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": str(len(payload)),
                "status": "blurred",
                "error": "",
            }
        )
        summary["blurred"] += 1

    write_csv(output_manifest, blurred_rows, LOCAL_FILE_FIELDS)
    return summary


def export_privacy_safe_cache(
    cache_manifest: Path,
    blurred_manifest: Path,
    output_manifest: Path,
    *,
    extra_cache_manifests: list[Path] | None = None,
) -> dict[str, int]:
    rows = []
    seen: set[str] = set()
    for manifest in [cache_manifest, *(extra_cache_manifests or [])]:
        for row in read_csv(manifest):
            image_id = row.get("image_id", "")
            if image_id in seen:
                continue
            seen.add(image_id)
            rows.append(row)
    blurred_by_id = {
        row.get("image_id", ""): row
        for row in read_csv(blurred_manifest)
        if row.get("status") == "blurred"
    }
    output_rows = []
    replaced = 0
    kept = 0
    for row in rows:
        image_id = row.get("image_id", "")
        blurred = blurred_by_id.get(image_id)
        if blurred:
            merged = dict(row)
            merged.update(
                {
                    "download_url": row.get("download_url", ""),
                    "local_path": blurred.get("local_path", ""),
                    "sha256": blurred.get("sha256", ""),
                    "bytes": blurred.get("bytes", ""),
                    "status": "blurred",
                    "error": "",
                }
            )
            output_rows.append(merged)
            replaced += 1
        else:
            output_rows.append(row)
            kept += 1
    write_csv(output_manifest, output_rows, LOCAL_FILE_FIELDS)
    return {"rows": len(output_rows), "replaced": replaced, "kept": kept}


def apply_privacy_report_to_triage(
    triage_path: Path,
    privacy_report: Path,
    output_path: Path,
    *,
    blurred_manifest: Path | None = None,
    trust_clear: bool = False,
    reviewer: str = "privacy_scan_v1",
) -> dict[str, int]:
    triage_rows = read_csv(triage_path)
    report_by_id = {row.get("image_id", ""): row for row in read_csv(privacy_report)}
    blurred_ids = set()
    if blurred_manifest and blurred_manifest.exists():
        blurred_ids = {
            row.get("image_id", "")
            for row in read_csv(blurred_manifest)
            if row.get("status") == "blurred"
        }

    summary = {
        "updated": 0,
        "clear_marked": 0,
        "blurred_marked": 0,
        "needs_review_marked": 0,
        "unchanged": 0,
    }
    for row in triage_rows:
        image_id = row.get("image_id", "")
        report = report_by_id.get(image_id)
        if not report:
            summary["unchanged"] += 1
            continue

        status = report.get("status", "")
        if status == "clear" and trust_clear:
            row["privacy_ok"] = "true"
            row["privacy_checked"] = "true"
            row["reviewer"] = reviewer
            row["notes"] = append_note(
                row.get("notes", ""),
                "Privacy scan clear: no face or plate-candidate regions detected.",
            )
            summary["updated"] += 1
            summary["clear_marked"] += 1
        elif image_id in blurred_ids:
            row["privacy_ok"] = "true"
            row["privacy_checked"] = "true"
            row["reviewer"] = reviewer
            row["notes"] = append_note(
                row.get("notes", ""),
                "Privacy identifiers blurred in derivative local file; use blurred derivative for export.",
            )
            summary["updated"] += 1
            summary["blurred_marked"] += 1
        elif status == "needs_blur":
            if not row.get("recommended_action", "").strip():
                row["recommended_action"] = "needs_review"
            row["privacy_ok"] = "false"
            row["reviewer"] = reviewer
            row["notes"] = append_note(
                row.get("notes", ""),
                "Privacy scan detected face or plate-candidate regions; blur or exclude before publication.",
            )
            summary["updated"] += 1
            summary["needs_review_marked"] += 1
        else:
            summary["unchanged"] += 1

    write_csv(output_path, triage_rows, TRIAGE_FIELDS)
    return summary


def detections_from_json(payload: str) -> list[Detection]:
    try:
        rows = json.loads(payload or "[]")
    except json.JSONDecodeError:
        return []
    detections = []
    for row in rows:
        try:
            detections.append(
                Detection(
                    kind=str(row["kind"]),
                    x=int(row["x"]),
                    y=int(row["y"]),
                    width=int(row["width"]),
                    height=int(row["height"]),
                    confidence=float(row.get("confidence", 1.0)),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return detections


def append_note(existing: str, note: str) -> str:
    existing = existing.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing} {note}"


class OpenCvPrivacyDetector:
    def __init__(self, *, detect_plates: bool = False) -> None:
        try:
            import cv2
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Privacy scanning requires OpenCV. Install with: "
                'python -m pip install -e ".[privacy]"'
            ) from exc
        self.cv2 = cv2
        self.detect_plates = detect_plates
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self.face_cascade = cv2.CascadeClassifier(cascade_path)
        if self.face_cascade.empty():
            raise RuntimeError("OpenCV face cascade could not be loaded.")

    def detect(self, image_path: Path) -> list[Detection]:
        image = self.cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f"OpenCV could not read image: {image_path}")
        gray = self.cv2.cvtColor(image, self.cv2.COLOR_BGR2GRAY)
        faces = self.face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(24, 24),
        )
        detections = [
            Detection("face", int(x), int(y), int(w), int(h), 1.0)
            for (x, y, w, h) in faces
        ]
        if self.detect_plates:
            detections.extend(self.detect_plate_candidates(gray))
        return detections

    def detect_plate_candidates(self, gray) -> list[Detection]:
        edges = self.cv2.Canny(gray, 80, 180)
        contours, _ = self.cv2.findContours(
            edges, self.cv2.RETR_EXTERNAL, self.cv2.CHAIN_APPROX_SIMPLE
        )
        detections = []
        height, width = gray.shape[:2]
        image_area = width * height
        for contour in contours:
            x, y, w, h = self.cv2.boundingRect(contour)
            if h == 0:
                continue
            aspect = w / h
            area = w * h
            if 2.0 <= aspect <= 6.5 and 200 <= area <= image_area * 0.02:
                if w >= 28 and h >= 8:
                    detections.append(
                        Detection("plate_candidate", int(x), int(y), int(w), int(h), 0.35)
                    )
        return detections[:20]

    def blur_file(
        self,
        input_path: Path,
        output_path: Path,
        detections: list[Detection],
    ) -> None:
        image = self.cv2.imread(str(input_path))
        if image is None:
            raise ValueError(f"OpenCV could not read image: {input_path}")
        height, width = image.shape[:2]
        for detection in detections:
            pad_x = max(4, int(detection.width * 0.15))
            pad_y = max(4, int(detection.height * 0.20))
            x1 = max(0, detection.x - pad_x)
            y1 = max(0, detection.y - pad_y)
            x2 = min(width, detection.x + detection.width + pad_x)
            y2 = min(height, detection.y + detection.height + pad_y)
            region = image[y1:y2, x1:x2]
            if region.size == 0:
                continue
            kernel_w = max(15, ((x2 - x1) // 2) * 2 + 1)
            kernel_h = max(15, ((y2 - y1) // 2) * 2 + 1)
            image[y1:y2, x1:x2] = self.cv2.GaussianBlur(region, (kernel_w, kernel_h), 0)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.cv2.imwrite(str(output_path), image):
            raise ValueError(f"OpenCV could not write image: {output_path}")
