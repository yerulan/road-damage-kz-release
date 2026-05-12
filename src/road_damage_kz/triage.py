"""Visual triage helpers for candidate image manifests."""

from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlparse

from .schema import IMAGE_MANIFEST_FIELDS, TRIAGE_FIELDS, normalize_bool, read_csv, write_csv


ACTION_INCLUDE = "include"
ACTION_EXCLUDE = "exclude"
ACTION_NEEDS_REVIEW = "needs_review"


def generate_gallery(
    triage_csv: Path,
    output_html: Path,
    *,
    limit: int | None = None,
    photo_candidates_only: bool = False,
) -> dict[str, int]:
    rows = read_csv(triage_csv)
    if photo_candidates_only:
        rows = [row for row in rows if normalize_bool(row.get("is_photo_candidate", ""))]
    if limit is not None:
        rows = rows[:limit]

    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(render_gallery(rows), encoding="utf-8")
    return {"rows": len(rows)}


def render_gallery(rows: list[dict[str, str]]) -> str:
    cards = "\n".join(render_card(row) for row in rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Road Damage KZ Triage Gallery</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17202a;
      --muted: #5e6b78;
      --line: #d8dee5;
      --paper: #f7f8fa;
      --accent: #0f766e;
    }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--paper);
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      padding: 16px 20px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 20px;
      line-height: 1.2;
    }}
    header p {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}
    main {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
      padding: 16px;
    }}
    article {{
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 8px;
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
      padding: 12px;
    }}
    h2 {{
      margin: 0 0 8px;
      font-size: 15px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }}
    dl {{
      display: grid;
      grid-template-columns: 84px 1fr;
      gap: 5px 8px;
      margin: 0;
      font-size: 12px;
      line-height: 1.35;
    }}
    dt {{
      color: var(--muted);
    }}
    dd {{
      margin: 0;
      overflow-wrap: anywhere;
    }}
    a {{
      color: var(--accent);
    }}
    .flags {{
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin: 10px 0;
    }}
    .flag {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 11px;
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <header>
    <h1>Road Damage KZ Triage Gallery</h1>
    <p>Use this visual pass to fill <code>data/manifests/triage.csv</code>, then run <code>roadkz apply-triage</code>.</p>
  </header>
  <main>
    {cards}
  </main>
</body>
</html>
"""


def render_card(row: dict[str, str]) -> str:
    image_id = escape(row.get("image_id", ""))
    source_url = escape(row.get("source_url", ""))
    download_url = escape(row.get("download_url", ""))
    license_name = escape(row.get("license", ""))
    author = escape(row.get("author", ""))
    context = escape(row.get("capture_context", ""))
    notes = escape(row.get("notes", ""))
    filename = escape(Path(urlparse(row.get("source_url", "")).path).name.replace("_", " "))
    photo_flag = "photo candidate" if normalize_bool(row.get("is_photo_candidate", "")) else "needs asset check"
    return f"""<article id="{image_id}">
  <a href="{source_url}" target="_blank" rel="noopener"><img loading="lazy" src="{download_url}" alt="{filename}"></a>
  <div class="body">
    <h2>{image_id}</h2>
    <div class="flags">
      <span class="flag">{escape(photo_flag)}</span>
      <span class="flag">{license_name}</span>
    </div>
    <dl>
      <dt>File</dt><dd>{filename}</dd>
      <dt>Author</dt><dd>{author}</dd>
      <dt>Context</dt><dd>{context}</dd>
      <dt>Source</dt><dd><a href="{source_url}" target="_blank" rel="noopener">Commons page</a></dd>
      <dt>Notes</dt><dd>{notes}</dd>
    </dl>
  </div>
</article>"""


def apply_triage(manifest_path: Path, triage_path: Path, output_path: Path) -> dict[str, int | list[str]]:
    manifest_rows = read_csv(manifest_path)
    triage_rows = read_csv(triage_path)
    triage_by_id = {row.get("image_id", ""): row for row in triage_rows}

    updated_rows = []
    promoted = 0
    already_promoted = 0
    skipped = 0
    skipped_reasons: list[str] = []

    for row in manifest_rows:
        triage = triage_by_id.get(row.get("image_id", ""))
        if not triage:
            updated_rows.append(row)
            continue

        action = triage.get("recommended_action", "").strip().lower()
        if action != ACTION_INCLUDE:
            updated_rows.append(row)
            continue

        reason = promotion_blocker(row, triage)
        if reason:
            skipped += 1
            skipped_reasons.append(f"{row.get('image_id', '<missing>')}: {reason}")
            updated_rows.append(row)
            continue

        updated = dict(row)
        updated["privacy_checked"] = "true"
        label = triage.get("damage_labels", "").strip()
        if normalize_bool(triage.get("target_damage_visible", "")):
            updated["damage_labels"] = label
        else:
            updated["damage_labels"] = "normal"
        triage_note = triage.get("notes", "").strip()
        reviewer = triage.get("reviewer", "").strip()
        updated["notes"] = append_note(
            updated.get("notes", ""),
            f"Triage include by {reviewer or 'reviewer'}."
            + (f" Triage notes: {triage_note}" if triage_note else ""),
        )
        if updated == row:
            already_promoted += 1
        else:
            promoted += 1
        updated_rows.append(updated)

    write_csv(output_path, updated_rows, IMAGE_MANIFEST_FIELDS)
    return {
        "promoted": promoted,
        "already_promoted": already_promoted,
        "skipped": skipped,
        "skipped_reasons": skipped_reasons,
    }


def promotion_blocker(manifest_row: dict[str, str], triage_row: dict[str, str]) -> str:
    if not normalize_bool(manifest_row.get("license_ok", "")):
        return "license_ok is not true"
    if not normalize_bool(triage_row.get("is_photo_candidate", "")):
        return "not marked as a photo candidate"
    if not normalize_bool(triage_row.get("road_surface_visible", "")):
        return "road surface is not marked visible"
    if not normalize_bool(triage_row.get("privacy_ok", "")):
        return "privacy_ok is not true"
    if normalize_bool(triage_row.get("target_damage_visible", "")):
        label = triage_row.get("damage_labels", "").strip()
        if not label or label == "unknown":
            return "target damage is visible but damage_labels is empty/unknown"
    return ""


def append_note(existing: str, note: str) -> str:
    existing = existing.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing} {note}"


def validate_triage_columns(path: Path) -> list[str]:
    if not path.exists():
        return [f"Missing triage file: {path}"]
    rows = read_csv(path)
    if not rows:
        return []
    missing = [field for field in TRIAGE_FIELDS if field not in rows[0]]
    return [f"Missing required triage column: {field}" for field in missing]
