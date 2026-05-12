"""Wikimedia Commons metadata collection."""

from __future__ import annotations

from html import unescape
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json
import re

from .schema import IMAGE_MANIFEST_FIELDS, is_open_license, write_csv


API_ENDPOINT = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "road-damage-kz/0.1 (+research metadata collection)"
REQUEST_DELAY_SECONDS = 0.5


def collect_commons_category(
    category: str,
    *,
    limit: int,
    include_subcategories: bool = False,
    max_depth: int = 1,
) -> list[dict[str, str]]:
    """Collect Commons file metadata for a category."""

    category = normalize_category_title(category)
    titles = _collect_file_titles(
        category,
        limit=limit,
        include_subcategories=include_subcategories,
        max_depth=max_depth,
    )
    rows: list[dict[str, str]] = []
    for batch in _chunks(titles, 20):
        pages = _fetch_imageinfo(batch)
        for page in pages:
            row = manifest_row_from_page(page, category)
            if row:
                rows.append(row)
    return rows[:limit]


def collect_commons_search(query: str, *, limit: int) -> list[dict[str, str]]:
    """Collect Commons file metadata from a file-title/full-text search."""

    titles = _search_file_titles(query, limit=limit)
    rows: list[dict[str, str]] = []
    for batch in _chunks(titles, 20):
        pages = _fetch_imageinfo(batch)
        for page in pages:
            row = manifest_row_from_page(page, f"Search:{query}")
            if row:
                rows.append(row)
    return rows[:limit]


def append_rows(
    output: Path, existing: list[dict[str, str]], new_rows: list[dict[str, str]]
) -> tuple[int, int]:
    """Append or refresh candidate rows, preserving manual review decisions."""

    rows = list(existing)
    by_image_id = {row.get("image_id", ""): index for index, row in enumerate(rows) if row.get("image_id")}
    by_source_url = {
        row.get("source_url", ""): index for index, row in enumerate(rows) if row.get("source_url")
    }
    added = 0
    updated = 0
    for row in new_rows:
        image_id = row.get("image_id", "")
        source_url = row.get("source_url", "")
        if image_id in by_image_id:
            index = by_image_id[image_id]
        elif source_url in by_source_url:
            index = by_source_url[source_url]
        else:
            index = None
        if index is not None:
            merged = merge_candidate_row(rows[index], row)
            if merged != rows[index]:
                rows[index] = merged
                updated += 1
            continue
        rows.append(row)
        by_image_id[row.get("image_id", "")] = len(rows) - 1
        by_source_url[row.get("source_url", "")] = len(rows) - 1
        added += 1
    write_csv(output, rows, IMAGE_MANIFEST_FIELDS)
    return added, updated


def merge_candidate_row(existing: dict[str, str], incoming: dict[str, str]) -> dict[str, str]:
    """Refresh machine-collected metadata without overwriting human decisions."""

    merged = dict(incoming)
    for field in ["damage_labels", "split", "privacy_checked"]:
        old_value = existing.get(field, "")
        if field == "damage_labels" and old_value and old_value != "unknown":
            merged[field] = old_value
        elif field == "split" and old_value:
            merged[field] = old_value
        elif field == "privacy_checked" and old_value.lower() == "true":
            merged[field] = old_value
    return merged


def manifest_row_from_page(page: dict, category: str) -> dict[str, str] | None:
    """Convert one MediaWiki page object into an image manifest row."""

    imageinfo = page.get("imageinfo") or []
    if not imageinfo:
        return None
    info = imageinfo[0]
    mime = info.get("mime", "")
    if mime and not mime.startswith("image/"):
        return None

    metadata = info.get("extmetadata") or {}
    license_label = canonical_license(_metadata_value(metadata, "LicenseShortName"))
    author = strip_html(_metadata_value(metadata, "Artist") or _metadata_value(metadata, "Credit"))
    title = page.get("title", "")
    pageid = str(page.get("pageid", stable_suffix(title)))
    source_url = commons_file_url(title)
    download_url = clean_download_url(info.get("url", ""))
    license_ok = bool(download_url and author and is_open_license(license_label))

    notes = [
        f"Collected from {category}",
        f"Commons title: {title}",
        f"MIME: {mime or 'unknown'}",
        "Privacy review still required before publication.",
    ]
    if is_likely_non_photo(title, mime):
        notes.append("Triage warning: likely non-photo or map/diagram asset.")

    return {
        "image_id": f"commons_{pageid}",
        "source_url": source_url,
        "download_url": download_url,
        "license": license_label,
        "author": author,
        "country": "Kazakhstan",
        "region": "",
        "city": "",
        "capture_context": f"wikimedia-commons:{category.removeprefix('Category:')}",
        "damage_labels": "unknown",
        "split": "",
        "license_ok": str(license_ok).lower(),
        "privacy_checked": "false",
        "notes": " ".join(notes),
    }


def normalize_category_title(value: str) -> str:
    value = value.strip()
    if value.startswith("https://commons.wikimedia.org/wiki/"):
        value = value.rsplit("/", 1)[-1]
    value = value.replace("_", " ")
    if not value.startswith("Category:"):
        value = f"Category:{value}"
    return value


def commons_file_url(title: str) -> str:
    return "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_"), safe=":_()'.,-")


def clean_download_url(url: str) -> str:
    return url.split("?", 1)[0]


def canonical_license(value: str) -> str:
    cleaned = strip_html(value).strip()
    normalized = cleaned.upper().replace("CREATIVE COMMONS", "CC")
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("ATTRIBUTION-SHARE ALIKE", "BY-SA")
    normalized = normalized.replace("ATTRIBUTION SHAREALIKE", "BY-SA")
    normalized = normalized.replace("ATTRIBUTION", "BY")
    normalized = normalized.replace("SHARE ALIKE", "SA")
    normalized = normalized.replace("PUBLIC DOMAIN", "PDM")
    normalized = normalized.replace("CC ", "CC-")
    normalized = normalized.replace("BY SA", "BY-SA")
    normalized = normalized.replace(" ", "-")
    normalized = normalized.replace("--", "-")
    if normalized in {"PD", "PDM", "PUBLIC-DOMAIN"}:
        return "PDM"
    return normalized


def strip_html(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def stable_suffix(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return safe[:80] or "unknown"


def is_likely_non_photo(title: str, mime: str) -> bool:
    lowered = title.lower()
    if mime in {"image/svg+xml"}:
        return True
    if lowered.endswith((".svg", ".png", ".gif", ".webp")):
        return True
    non_photo_terms = ["map", "diagram", "route", "sign", "logo", "icon"]
    return any(term in lowered for term in non_photo_terms)


def _collect_file_titles(
    category: str,
    *,
    limit: int,
    include_subcategories: bool,
    max_depth: int,
) -> list[str]:
    titles: list[str] = []
    visited = set()
    queue: list[tuple[str, int]] = [(category, 0)]

    while queue and len(titles) < limit:
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        members = _category_members(current)
        for member in members:
            title = member.get("title", "")
            namespace = member.get("ns")
            if namespace == 6 and len(titles) < limit:
                titles.append(title)
            elif include_subcategories and namespace == 14 and depth < max_depth:
                queue.append((title, depth + 1))
            if len(titles) >= limit:
                break

    return titles


def _category_members(category: str) -> list[dict]:
    members: list[dict] = []
    cmcontinue = None
    while True:
        params = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": "file|subcat",
            "cmlimit": "100",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        payload = _api_get(params)
        members.extend(payload.get("query", {}).get("categorymembers", []))
        cmcontinue = payload.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            return members


def _search_file_titles(query: str, *, limit: int) -> list[str]:
    titles: list[str] = []
    sroffset = 0
    while len(titles) < limit:
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srnamespace": "6",
            "srsearch": query,
            "srlimit": str(min(50, limit - len(titles))),
            "sroffset": str(sroffset),
        }
        payload = _api_get(params)
        search_rows = payload.get("query", {}).get("search", [])
        if not search_rows:
            return titles
        titles.extend(row.get("title", "") for row in search_rows if row.get("title"))
        next_offset = payload.get("continue", {}).get("sroffset")
        if next_offset is None:
            return titles
        sroffset = int(next_offset)
    return titles


def _fetch_imageinfo(titles: list[str]) -> list[dict]:
    if not titles:
        return []
    params = {
        "action": "query",
        "format": "json",
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "titles": "|".join(titles),
    }
    payload = _api_get(params)
    pages = payload.get("query", {}).get("pages", {})
    return list(pages.values())


def _api_get(params: dict[str, str]) -> dict:
    query = urlencode(params)
    request = Request(f"{API_ENDPOINT}?{query}", headers={"User-Agent": USER_AGENT})
    for attempt in range(5):
        try:
            sleep(REQUEST_DELAY_SECONDS)
            with urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise RuntimeError(f"Commons API request failed with HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else (attempt + 1) * 10
            sleep(delay)
        except URLError as exc:
            if attempt == 4:
                raise RuntimeError(f"Commons API request failed: {exc}") from exc
            sleep((attempt + 1) * 5)
    raise RuntimeError("Commons API request failed after retries")


def _metadata_value(metadata: dict, key: str) -> str:
    value = metadata.get(key, {})
    if isinstance(value, dict):
        return str(value.get("value", ""))
    return str(value or "")


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]
