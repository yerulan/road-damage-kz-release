"""Openverse metadata discovery for license-audited image leads."""

from __future__ import annotations

from hashlib import sha1
import json
import re
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .schema import is_open_license


API_ENDPOINT = "https://api.openverse.org/v1/images/"
USER_AGENT = "road-damage-kz/0.1 (+research metadata discovery)"
REQUEST_DELAY_SECONDS = 1.0


def collect_openverse_search(
    query: str,
    *,
    limit: int,
    trust_openverse_license: bool = False,
) -> list[dict[str, str]]:
    """Collect Openverse image search results as manifest-compatible leads."""

    results = _search_images(query, limit=limit)
    rows: list[dict[str, str]] = []
    for result in results:
        row = manifest_row_from_openverse_result(
            result,
            query=query,
            trust_openverse_license=trust_openverse_license,
        )
        if row:
            rows.append(row)
    return rows[:limit]


def manifest_row_from_openverse_result(
    result: dict,
    *,
    query: str,
    trust_openverse_license: bool = False,
) -> dict[str, str] | None:
    """Convert one Openverse API result into an image manifest row."""

    download_url = str(result.get("url") or "").strip()
    source_url = str(result.get("foreign_landing_url") or download_url).strip()
    if not source_url:
        return None

    license_label = canonical_openverse_license(
        str(result.get("license") or ""),
        str(result.get("license_version") or ""),
    )
    author = str(result.get("creator") or result.get("provider") or result.get("source") or "").strip()
    source = str(result.get("source") or result.get("provider") or "unknown").strip()
    title = str(result.get("title") or "").strip()
    open_license = bool(download_url and author and is_open_license(license_label))
    license_ok = trust_openverse_license and open_license

    notes = [
        f"Collected from Openverse search: {query}",
        f"Openverse source: {source}",
        "Openverse license metadata must be verified on the source page before publication.",
    ]
    if title:
        notes.append(f"Title: {title}")
    if not trust_openverse_license:
        notes.append("Stored as discovery lead with license_ok=false by default.")
    elif not open_license:
        notes.append("License metadata was incomplete or not in the approved open-license list.")

    return {
        "image_id": f"openverse_{stable_openverse_suffix(result, source_url)}",
        "source_url": source_url,
        "download_url": download_url,
        "license": license_label,
        "author": author,
        "country": "Kazakhstan",
        "region": "",
        "city": "",
        "capture_context": f"openverse-search:{query};source:{source}",
        "damage_labels": "unknown",
        "split": "",
        "license_ok": str(license_ok).lower(),
        "privacy_checked": "false",
        "notes": " ".join(notes),
    }


def canonical_openverse_license(license_name: str, license_version: str) -> str:
    """Normalize Openverse license fields to the project license labels."""

    name = re.sub(r"\s+", "-", license_name.strip().upper())
    version = license_version.strip()
    if not name:
        return ""
    if name in {"PDM", "PUBLIC-DOMAIN", "PUBLICDOMAIN"}:
        return "PDM"
    if name == "CC0":
        return f"CC0-{version}" if version else "CC0"
    if name.startswith("CC-"):
        if version and not name.endswith(f"-{version}"):
            return f"{name}-{version}"
        return name
    if name.startswith("BY"):
        prefix = f"CC-{name}"
        if version and not prefix.endswith(f"-{version}"):
            return f"{prefix}-{version}"
        return prefix
    return name


def stable_openverse_suffix(result: dict, source_url: str) -> str:
    identifier = str(result.get("id") or result.get("identifier") or source_url)
    digest = sha1(identifier.encode("utf-8")).hexdigest()[:12]
    return digest


def _search_images(query: str, *, limit: int) -> list[dict]:
    results: list[dict] = []
    page = 1
    while len(results) < limit:
        page_size = min(50, limit - len(results))
        params = {
            "format": "json",
            "q": query,
            "page_size": str(page_size),
            "page": str(page),
        }
        payload = _api_get(params)
        batch = payload.get("results", [])
        if not batch:
            return results
        results.extend(batch)
        if not payload.get("next"):
            return results
        page += 1
    return results


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
                raise RuntimeError(f"Openverse API request failed with HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else (attempt + 1) * 10
            sleep(delay)
        except URLError as exc:
            if attempt == 4:
                raise RuntimeError(f"Openverse API request failed: {exc}") from exc
            sleep((attempt + 1) * 5)
    raise RuntimeError("Openverse API request failed after retries")
