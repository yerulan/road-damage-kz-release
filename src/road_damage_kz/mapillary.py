"""Mapillary metadata discovery for Kazakhstan street-level imagery."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .schema import is_open_license


API_ENDPOINT = "https://graph.mapillary.com/images"
USER_AGENT = "road-damage-kz/0.1 (+research metadata discovery)"
REQUEST_DELAY_SECONDS = 1.0
MAPILLARY_LICENSE = "CC-BY-SA-4.0"

IMAGE_FIELDS = [
    "id",
    "captured_at",
    "computed_geometry",
    "geometry",
    "is_pano",
    "creator",
    "thumb_256_url",
    "thumb_1024_url",
    "thumb_2048_url",
    "thumb_original_url",
]

CITY_BBOXES = {
    "almaty": (76.74, 43.15, 77.08, 43.36),
    "astana": (71.30, 51.03, 71.62, 51.26),
    "shymkent": (69.43, 42.22, 69.78, 42.44),
    "karaganda": (73.00, 49.70, 73.30, 49.94),
    "aktobe": (57.02, 50.18, 57.36, 50.38),
    "pavlodar": (76.82, 52.20, 77.12, 52.38),
    "atyrau": (51.78, 47.02, 52.04, 47.20),
    "taraz": (71.26, 42.82, 71.48, 43.00),
    "kyzylorda": (65.35, 44.73, 65.65, 44.92),
    "semey": (80.10, 50.34, 80.42, 50.52),
    "oskemen": (82.48, 49.86, 82.78, 50.08),
}


def collect_mapillary_bbox(
    bbox: tuple[float, float, float, float],
    *,
    access_token: str,
    limit: int,
    city: str = "",
    region: str = "",
    thumbnail_size: str = "1024",
    min_captured_at: str = "",
    max_captured_at: str = "",
    request_delay: float = REQUEST_DELAY_SECONDS,
    grid_size: int = 1,
) -> list[dict[str, str]]:
    """Collect Mapillary image metadata inside a bounding box."""

    if not access_token:
        raise RuntimeError("Mapillary access token is required. Set MAPILLARY_ACCESS_TOKEN or pass --access-token.")
    validate_bbox(bbox)
    images: list[dict] = []
    seen_ids: set[str] = set()
    failures: list[str] = []
    for tile in split_bbox(bbox, grid_size=max(1, grid_size)):
        if len(images) >= limit:
            break
        try:
            tile_images = _fetch_images(
                tile,
                access_token=access_token,
                limit=limit - len(images),
                min_captured_at=min_captured_at,
                max_captured_at=max_captured_at,
                request_delay=request_delay,
            )
        except RuntimeError as error:
            failures.append(f"{format_bbox(tile)}: {error}")
            continue
        for image in tile_images:
            image_id = str(image.get("id") or "")
            if image_id and image_id not in seen_ids:
                images.append(image)
                seen_ids.add(image_id)
            if len(images) >= limit:
                break
    if not images and failures:
        raise RuntimeError("Mapillary API request failed for all bbox tiles: " + "; ".join(failures[:3]))

    rows: list[dict[str, str]] = []
    for image in images:
        row = manifest_row_from_mapillary_image(
            image,
            bbox=bbox,
            city=city,
            region=region,
            thumbnail_size=thumbnail_size,
        )
        if row:
            rows.append(row)
    return rows[:limit]


def split_bbox(
    bbox: tuple[float, float, float, float],
    *,
    grid_size: int,
) -> list[tuple[float, float, float, float]]:
    """Split a bbox into smaller tiles to avoid Mapillary timeout errors."""

    bbox = validate_bbox(bbox)
    grid_size = max(1, grid_size)
    west, south, east, north = bbox
    lon_step = (east - west) / grid_size
    lat_step = (north - south) / grid_size
    tiles: list[tuple[float, float, float, float]] = []
    for y in range(grid_size):
        tile_south = south + y * lat_step
        tile_north = north if y == grid_size - 1 else south + (y + 1) * lat_step
        for x in range(grid_size):
            tile_west = west + x * lon_step
            tile_east = east if x == grid_size - 1 else west + (x + 1) * lon_step
            tiles.append((tile_west, tile_south, tile_east, tile_north))
    return tiles


def manifest_row_from_mapillary_image(
    image: dict,
    *,
    bbox: tuple[float, float, float, float],
    city: str = "",
    region: str = "",
    thumbnail_size: str = "1024",
) -> dict[str, str] | None:
    """Convert one Mapillary API image object into a manifest row."""

    image_id = str(image.get("id") or "").strip()
    if not image_id:
        return None

    author = creator_name(image.get("creator"))
    download_url = thumbnail_url(image, thumbnail_size)
    source_url = mapillary_image_url(image_id)
    captured_at = format_captured_at(image.get("captured_at"))
    coordinates = image_coordinates(image)
    license_ok = bool(download_url and author and is_open_license(MAPILLARY_LICENSE))
    context_parts = ["mapillary"]
    if city:
        context_parts.append(f"city:{city}")
    if captured_at:
        context_parts.append(f"captured_at:{captured_at}")
    if image.get("is_pano") is not None:
        context_parts.append(f"is_pano:{str(bool(image.get('is_pano'))).lower()}")
    context_parts.append(f"bbox:{format_bbox(bbox)}")
    if coordinates:
        context_parts.append(f"lonlat:{coordinates[0]:.6f},{coordinates[1]:.6f}")

    notes = [
        "Collected from Mapillary API.",
        "Mapillary states imagery is shared under CC-BY-SA; attribution and share-alike obligations apply.",
        "Privacy review still required before publication or export.",
    ]
    if not author:
        notes.append("Creator metadata missing; keep license_ok=false until attribution is resolved.")
    if not download_url:
        notes.append("No thumbnail URL returned by API; candidate cannot be locally reviewed yet.")

    return {
        "image_id": f"mapillary_{image_id}",
        "source_url": source_url,
        "download_url": download_url,
        "license": MAPILLARY_LICENSE,
        "author": author,
        "country": "Kazakhstan",
        "region": region,
        "city": city,
        "capture_context": ";".join(context_parts),
        "damage_labels": "unknown",
        "split": "",
        "license_ok": str(license_ok).lower(),
        "privacy_checked": "false",
        "notes": " ".join(notes),
    }


def creator_name(value: object) -> str:
    """Return a stable attribution string from Mapillary creator metadata."""

    if isinstance(value, dict):
        username = str(value.get("username") or value.get("name") or "").strip()
        creator_id = str(value.get("id") or "").strip()
        if username and creator_id:
            return f"{username} (Mapillary user {creator_id})"
        return username or (f"Mapillary user {creator_id}" if creator_id else "")
    if value is None:
        return ""
    return str(value).strip()


def thumbnail_url(image: dict, thumbnail_size: str) -> str:
    key_by_size = {
        "256": "thumb_256_url",
        "1024": "thumb_1024_url",
        "2048": "thumb_2048_url",
        "original": "thumb_original_url",
    }
    preferred = key_by_size.get(thumbnail_size, "thumb_1024_url")
    for key in [preferred, "thumb_1024_url", "thumb_2048_url", "thumb_256_url", "thumb_original_url"]:
        value = str(image.get(key) or "").strip()
        if value:
            return value
    return ""


def image_coordinates(image: dict) -> tuple[float, float] | None:
    geometry = image.get("computed_geometry") or image.get("geometry") or {}
    if not isinstance(geometry, dict):
        return None
    coordinates = geometry.get("coordinates") or []
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    try:
        return float(coordinates[0]), float(coordinates[1])
    except (TypeError, ValueError):
        return None


def format_captured_at(value: object) -> str:
    if value in {None, ""}:
        return ""
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return str(value)
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).date().isoformat()


def mapillary_image_url(image_id: str) -> str:
    return f"https://www.mapillary.com/app/?pKey={image_id}"


def format_bbox(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(f"{value:.6f}" for value in bbox)


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must contain four comma-separated values: west,south,east,north")
    try:
        bbox = tuple(float(part) for part in parts)
    except ValueError as error:
        raise ValueError("bbox values must be numeric: west,south,east,north") from error
    return validate_bbox(bbox)  # type: ignore[arg-type]


def validate_bbox(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = bbox
    if west >= east:
        raise ValueError("bbox west must be smaller than east")
    if south >= north:
        raise ValueError("bbox south must be smaller than north")
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise ValueError("bbox longitude values must be between -180 and 180")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise ValueError("bbox latitude values must be between -90 and 90")
    return bbox


def _fetch_images(
    bbox: tuple[float, float, float, float],
    *,
    access_token: str,
    limit: int,
    min_captured_at: str,
    max_captured_at: str,
    request_delay: float,
) -> list[dict]:
    images: list[dict] = []
    after = ""
    while len(images) < limit:
        page_size = min(100, limit - len(images))
        params: dict[str, str] = {
            "access_token": access_token,
            "fields": ",".join(IMAGE_FIELDS),
            "bbox": format_bbox(bbox),
            "limit": str(page_size),
        }
        if min_captured_at:
            params["start_captured_at"] = min_captured_at
        if max_captured_at:
            params["end_captured_at"] = max_captured_at
        if after:
            params["after"] = after
        payload = _api_get(params, request_delay=request_delay)
        batch = payload.get("data", [])
        if not batch:
            return images
        images.extend(batch)
        after = str(payload.get("paging", {}).get("cursors", {}).get("after") or "")
        if not after:
            return images
    return images


def _api_get(params: dict[str, str], *, request_delay: float = REQUEST_DELAY_SECONDS) -> dict:
    safe_params = dict(params)
    query = urlencode(safe_params)
    request = Request(f"{API_ENDPOINT}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            sleep(request_delay)
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504} or attempt == 4:
                raise RuntimeError(f"Mapillary API request failed with HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else (attempt + 1) * 10
            sleep(delay)
        except URLError as exc:
            if attempt == 4:
                raise RuntimeError(f"Mapillary API request failed: {exc}") from exc
            sleep((attempt + 1) * 5)
    raise RuntimeError("Mapillary API request failed after retries")
