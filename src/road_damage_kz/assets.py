"""Local asset caching for visual review and reproducibility."""

from __future__ import annotations

from html import escape
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import hashlib

from .schema import LOCAL_FILE_FIELDS, normalize_bool, read_csv, write_csv


USER_AGENT = "road-damage-kz/0.1 (+research image candidate caching)"


def download_candidates(
    triage_path: Path,
    output_dir: Path,
    cache_manifest: Path,
    *,
    limit: int | None = None,
    photo_candidates_only: bool = True,
    overwrite: bool = False,
    thumbnail_width: int = 960,
    original: bool = False,
    max_bytes: int = 20 * 1024 * 1024,
    verbose: bool = False,
    request_delay: float = 2.0,
    unreviewed_only: bool = False,
    retry_failed: bool = False,
    image_id_prefix: str = "",
) -> dict[str, int]:
    rows = read_csv(triage_path)
    existing_cache = read_csv(cache_manifest) if cache_manifest.exists() else []
    cache_by_id = {row.get("image_id", ""): row for row in existing_cache}
    candidates = []
    skipped_failed_cache = 0
    for row in rows:
        if image_id_prefix and not row.get("image_id", "").startswith(image_id_prefix):
            continue
        if not normalize_bool(row.get("license_ok", "")):
            continue
        if photo_candidates_only and not normalize_bool(row.get("is_photo_candidate", "")):
            continue
        if not row.get("download_url", ""):
            continue
        if unreviewed_only and row.get("recommended_action", "").strip():
            continue
        cached = cache_by_id.get(row.get("image_id", ""))
        if cached and cached.get("status") == "failed" and not retry_failed:
            skipped_failed_cache += 1
            continue
        candidates.append(row)
    if limit is not None:
        candidates = candidates[:limit]

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, str]] = []
    downloaded = 0
    skipped_existing = 0
    failed = 0

    for index, row in enumerate(candidates, start=1):
        image_id = row["image_id"]
        asset_url = row["download_url"] if original else commons_thumbnail_url(row["download_url"], thumbnail_width)
        extension = extension_from_url(row["download_url"])
        local_path = output_dir / f"{image_id}{extension}"
        cached = cache_by_id.get(image_id)
        if cached and Path(cached.get("local_path", "")).exists() and not overwrite:
            results.append(cached)
            skipped_existing += 1
            if verbose:
                print(f"[{index}/{len(candidates)}] existing {image_id}", flush=True)
            continue

        try:
            if verbose:
                print(f"[{index}/{len(candidates)}] downloading {image_id}", flush=True)
            payload = fetch_bytes(asset_url, max_bytes=max_bytes, request_delay=request_delay)
            local_path.write_bytes(payload)
            digest = sha256_bytes(payload)
            results.append(
                {
                    "image_id": image_id,
                    "source_url": row.get("source_url", ""),
                    "download_url": asset_url,
                    "local_path": str(local_path),
                    "sha256": digest,
                    "bytes": str(len(payload)),
                    "status": "downloaded",
                    "error": "",
                }
            )
            downloaded += 1
            if verbose:
                print(f"[{index}/{len(candidates)}] downloaded {image_id} ({len(payload)} bytes)", flush=True)
        except (RuntimeError, OSError) as exc:
            results.append(
                {
                    "image_id": image_id,
                    "source_url": row.get("source_url", ""),
                    "download_url": asset_url,
                    "local_path": str(local_path),
                    "sha256": "",
                    "bytes": "0",
                    "status": "failed",
                    "error": str(exc),
                }
            )
            failed += 1
            if verbose:
                print(f"[{index}/{len(candidates)}] failed {image_id}: {exc}", flush=True)

    untouched = [row for row in existing_cache if row.get("image_id", "") not in {r["image_id"] for r in results}]
    write_csv(cache_manifest, untouched + results, LOCAL_FILE_FIELDS)
    return {
        "candidates": len(candidates),
        "downloaded": downloaded,
        "skipped_existing": skipped_existing,
        "skipped_failed_cache": skipped_failed_cache,
        "failed": failed,
    }


def generate_local_gallery(
    cache_manifest: Path,
    output_html: Path,
    *,
    limit: int | None = None,
    image_id_prefix: str = "",
) -> dict[str, int]:
    rows = [row for row in read_csv(cache_manifest) if row.get("status") in {"downloaded", "cached"}]
    if image_id_prefix:
        rows = [row for row in rows if row.get("image_id", "").startswith(image_id_prefix)]
    if limit is not None:
        rows = rows[:limit]
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(render_local_gallery(rows, output_html.parent), encoding="utf-8")
    return {"rows": len(rows)}


def render_local_gallery(rows: list[dict[str, str]], html_dir: Path) -> str:
    cards = "\n".join(render_local_card(row, html_dir) for row in rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Road Damage KZ Local Candidate Gallery</title>
  <style>
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: #17202a;
      background: #f7f8fa;
    }}
    header {{
      padding: 16px 20px;
      background: #fff;
      border-bottom: 1px solid #d8dee5;
      position: sticky;
      top: 0;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 20px;
    }}
    p {{
      margin: 0;
      color: #5e6b78;
      font-size: 14px;
    }}
    main {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 12px;
      padding: 12px;
    }}
    article {{
      border: 1px solid #d8dee5;
      border-radius: 8px;
      background: #fff;
      overflow: hidden;
    }}
    img {{
      display: block;
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      background: #e8edf2;
    }}
    .body {{
      padding: 10px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    strong {{
      display: block;
      font-size: 13px;
      margin-bottom: 6px;
    }}
    a {{
      color: #0f766e;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Road Damage KZ Local Candidate Gallery</h1>
    <p>Offline review gallery generated from downloaded candidate files.</p>
  </header>
  <main>
    {cards}
  </main>
</body>
</html>
"""


def render_local_card(row: dict[str, str], html_dir: Path) -> str:
    local_path = Path(row.get("local_path", ""))
    try:
        image_src = local_path.relative_to(html_dir)
    except ValueError:
        image_src = Path("../") / local_path
    source_url = escape(row.get("source_url", ""))
    image_id = escape(row.get("image_id", ""))
    digest = escape(row.get("sha256", "")[:16])
    return f"""<article id="{image_id}">
  <a href="{source_url}" target="_blank" rel="noopener"><img loading="lazy" src="{escape(str(image_src))}" alt="{image_id}"></a>
  <div class="body">
    <strong>{image_id}</strong>
    <div>sha256: {digest}</div>
    <div><a href="{source_url}" target="_blank" rel="noopener">Commons source</a></div>
  </div>
</article>"""


def fetch_bytes(url: str, *, max_bytes: int, request_delay: float) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(4):
        try:
            sleep(request_delay)
            with urlopen(request, timeout=30) as response:
                chunks = []
                total = 0
                while True:
                    chunk = response.read(1024 * 256)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total += len(chunk)
                    if total > max_bytes:
                        raise RuntimeError(f"download exceeds {max_bytes} bytes")
                return b"".join(chunks)
        except HTTPError as exc:
            if exc.code != 429:
                raise RuntimeError(f"HTTP {exc.code}") from exc
            if attempt == 3:
                raise RuntimeError(f"HTTP {exc.code}") from exc
            retry_after = exc.headers.get("Retry-After")
            delay = int(retry_after) if retry_after and retry_after.isdigit() else (attempt + 1) * 8
            sleep(delay)
        except URLError as exc:
            if attempt == 3:
                raise RuntimeError(str(exc)) from exc
            sleep((attempt + 1) * 3)
    raise RuntimeError("download failed")


def extension_from_url(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def commons_thumbnail_url(url: str, width: int = 960) -> str:
    parsed = urlparse(url)
    parts = parsed.path.split("/")
    try:
        commons_index = parts.index("commons")
    except ValueError:
        return url
    tail = parts[commons_index + 1 :]
    if len(tail) < 3 or tail[0] == "thumb":
        return url
    filename = tail[-1]
    prefix = "/".join(parts[: commons_index + 1])
    directories = "/".join(tail[:-1])
    return f"{parsed.scheme}://{parsed.netloc}{prefix}/thumb/{directories}/{filename}/{width}px-{filename}"


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
