"""Review queue assembly from model scores, triage rows, and local files."""

from __future__ import annotations

from pathlib import Path

from .schema import REVIEW_QUEUE_FIELDS, read_csv, write_csv


def export_review_queue(
    scores_path: Path,
    triage_path: Path,
    output_path: Path,
    *,
    unreviewed_only: bool = True,
    include_triage_actions: set[str] | None = None,
    exclude_suggested: set[str] | None = None,
    limit: int | None = None,
    image_id_prefix: str = "",
) -> dict[str, int]:
    scores = read_csv(scores_path)
    triage_by_id = {row.get("image_id", ""): row for row in read_csv(triage_path)}
    include_triage_actions = include_triage_actions or set()
    exclude_suggested = exclude_suggested or set()

    rows = []
    for score in scores:
        image_id = score.get("image_id", "")
        if image_id_prefix and not image_id.startswith(image_id_prefix):
            continue
        triage = triage_by_id.get(image_id, {})
        triage_action = triage.get("recommended_action", "").strip()
        suggested = score.get("suggested_action", "").strip()
        if unreviewed_only and triage_action and triage_action not in include_triage_actions:
            continue
        if suggested in exclude_suggested:
            continue
        rows.append(
            {
                "rank": "",
                "image_id": image_id,
                "review_priority": score.get("review_priority", ""),
                "suggested_action": suggested,
                "road_surface_score": score.get("road_surface_score", ""),
                "damage_score": score.get("damage_score", ""),
                "normal_road_score": score.get("normal_road_score", ""),
                "non_road_score": score.get("non_road_score", ""),
                "privacy_context_score": score.get("privacy_context_score", ""),
                "triage_action": triage_action,
                "triage_labels": triage.get("damage_labels", ""),
                "local_path": score.get("local_path", ""),
                "source_url": score.get("source_url", ""),
                "notes": score.get("notes", ""),
            }
        )

    rows.sort(key=lambda row: float(row["review_priority"] or 0.0), reverse=True)
    if limit is not None:
        rows = rows[:limit]
    for index, row in enumerate(rows, start=1):
        row["rank"] = str(index)

    write_csv(output_path, rows, REVIEW_QUEUE_FIELDS)
    return {"queued": len(rows)}
