"""Model-assisted triage decisions with conservative publication gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .schema import TRIAGE_FIELDS, read_csv, write_csv


@dataclass(frozen=True)
class AutoTriageThresholds:
    road_min: float = 0.12
    non_road_exclude: float = 0.45
    privacy_review: float = 0.35
    damage_review: float = 0.25
    normal_review: float = 0.50


def auto_triage_scores(
    scores_path: Path,
    triage_path: Path,
    output_path: Path,
    *,
    thresholds: AutoTriageThresholds | None = None,
    unreviewed_only: bool = True,
    dry_run: bool = False,
    reviewer: str = "auto_triage_v1",
) -> dict[str, int]:
    thresholds = thresholds or AutoTriageThresholds()
    scores = read_csv(scores_path)
    triage_rows = read_csv(triage_path)
    triage_by_id = {row.get("image_id", ""): row for row in triage_rows}

    summary = {
        "scored": 0,
        "updated": 0,
        "auto_exclude": 0,
        "needs_review": 0,
        "unchanged": 0,
        "missing_triage": 0,
    }

    for score in scores:
        image_id = score.get("image_id", "")
        triage = triage_by_id.get(image_id)
        if triage is None:
            summary["missing_triage"] += 1
            continue
        if unreviewed_only and triage.get("recommended_action", "").strip():
            summary["unchanged"] += 1
            continue

        summary["scored"] += 1
        decision = classify_score(score, thresholds)
        if decision is None:
            summary["unchanged"] += 1
            continue

        action, labels, road_visible, target_damage, privacy_ok, note = decision
        summary["updated"] += 1
        if action == "exclude":
            summary["auto_exclude"] += 1
        else:
            summary["needs_review"] += 1

        if dry_run:
            continue

        triage["recommended_action"] = action
        triage["damage_labels"] = labels
        triage["road_surface_visible"] = road_visible
        triage["target_damage_visible"] = target_damage
        triage["privacy_ok"] = privacy_ok
        triage["reviewer"] = reviewer
        triage["notes"] = append_note(triage.get("notes", ""), note)

    if not dry_run:
        write_csv(output_path, triage_rows, TRIAGE_FIELDS)

    return summary


def classify_score(
    score: dict[str, str],
    thresholds: AutoTriageThresholds,
) -> tuple[str, str, str, str, str, str] | None:
    road = as_float(score.get("road_surface_score", ""))
    damage = as_float(score.get("damage_score", ""))
    normal = as_float(score.get("normal_road_score", ""))
    non_road = as_float(score.get("non_road_score", ""))
    privacy = as_float(score.get("privacy_context_score", ""))
    suggested = score.get("suggested_action", "").strip()

    if suggested == "review_exclude" or (
        non_road >= thresholds.non_road_exclude and non_road > road
    ):
        return (
            "exclude",
            "unknown",
            "false",
            "false",
            "false",
            "Auto-triage: excluded because model scores indicate non-road or unusable road-surface content.",
        )

    if road < thresholds.road_min and non_road >= road:
        return (
            "exclude",
            "unknown",
            "false",
            "false",
            "false",
            "Auto-triage: excluded because visible paved road surface score is too low.",
        )

    if suggested == "review_privacy" or privacy >= thresholds.privacy_review:
        return (
            "needs_review",
            "unknown",
            "true" if road >= thresholds.road_min else "",
            "false",
            "false",
            "Auto-triage: privacy-sensitive candidate; requires manual blur/exclusion decision.",
        )

    if road >= thresholds.road_min and damage >= thresholds.damage_review:
        return (
            "needs_review",
            "unknown",
            "true",
            "true",
            "",
            "Auto-triage: possible pavement damage; requires manual class labels and privacy check.",
        )

    if road >= thresholds.road_min and normal >= thresholds.normal_review:
        return (
            "needs_review",
            "normal",
            "true",
            "false",
            "",
            "Auto-triage: likely normal paved-road candidate; requires manual privacy confirmation.",
        )

    return None


def as_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def append_note(existing: str, note: str) -> str:
    existing = existing.strip()
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing} {note}"
