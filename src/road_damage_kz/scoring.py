"""Candidate image scoring for faster visual triage."""

from __future__ import annotations

from pathlib import Path
from math import exp

from .schema import SCORE_FIELDS, read_csv, write_csv


CLIP_PROMPT_GROUPS = {
    "road_surface": [
        "a photo with a visible paved road surface",
        "a road surface photographed from a vehicle or roadside",
        "asphalt pavement visible in the foreground",
    ],
    "damage": [
        "cracked asphalt pavement",
        "a road surface with long pavement cracks",
        "a road surface with transverse pavement cracks",
        "a pothole in asphalt pavement",
        "damaged road pavement",
        "broken pavement distress on a road",
    ],
    "normal_road": [
        "a normal paved road with no visible pavement damage",
        "a smooth undamaged asphalt road",
        "a clean highway surface without cracks or potholes",
    ],
    "non_road": [
        "a map or diagram",
        "a landscape without useful road surface",
        "a roadside market or shop",
        "a building or monument photo",
        "a vehicle or truck as the main subject",
    ],
    "privacy_context": [
        "a street photo with identifiable people",
        "a close photo of vehicle license plates",
        "a roadside scene with people and cars",
    ],
}


def score_candidates(
    cache_manifest: Path,
    output: Path,
    *,
    backend: str = "clip",
    model_name: str = "openai/clip-vit-base-patch32",
    model_cache_dir: Path | None = None,
    allow_model_download: bool = False,
    limit: int | None = None,
    include_failed: bool = False,
    image_id_prefix: str = "",
) -> dict[str, int]:
    rows = [
        row
        for row in read_csv(cache_manifest)
        if include_failed or row.get("status") in {"downloaded", "cached"}
    ]
    if image_id_prefix:
        rows = [row for row in rows if row.get("image_id", "").startswith(image_id_prefix)]
    if limit is not None:
        rows = rows[:limit]

    scorer = build_scorer(
        backend,
        model_name,
        model_cache_dir=model_cache_dir,
        allow_model_download=allow_model_download,
    )
    scored_rows = []
    for row in rows:
        local_path = Path(row.get("local_path", ""))
        if not local_path.exists():
            continue
        scores = scorer.score(local_path, row)
        scored_rows.append(score_row(row, scores, scorer.name))

    scored_rows.sort(key=lambda row: float(row["review_priority"]), reverse=True)
    write_csv(output, scored_rows, SCORE_FIELDS)
    return {"scored": len(scored_rows)}


def build_scorer(
    backend: str,
    model_name: str,
    *,
    model_cache_dir: Path | None = None,
    allow_model_download: bool = False,
):
    if backend == "clip":
        return ClipScorer(
            model_name,
            cache_dir=model_cache_dir,
            allow_download=allow_model_download,
        )
    if backend == "keyword":
        return KeywordScorer()
    raise ValueError(f"Unsupported scoring backend: {backend}")


def score_row(row: dict[str, str], scores: dict[str, float], model_name: str) -> dict[str, str]:
    road = scores.get("road_surface", 0.0)
    damage = scores.get("damage", 0.0)
    normal = scores.get("normal_road", 0.0)
    non_road = scores.get("non_road", 0.0)
    privacy = scores.get("privacy_context", 0.0)
    priority = road + damage - non_road - (privacy * 0.25)
    action = suggested_action(road, damage, normal, non_road, privacy)
    return {
        "image_id": row.get("image_id", ""),
        "local_path": row.get("local_path", ""),
        "source_url": row.get("source_url", ""),
        "road_surface_score": format_score(road),
        "damage_score": format_score(damage),
        "normal_road_score": format_score(normal),
        "non_road_score": format_score(non_road),
        "privacy_context_score": format_score(privacy),
        "review_priority": format_score(priority),
        "suggested_action": action,
        "model": model_name,
        "notes": "Model scores are triage aids only; privacy and labels still require human confirmation.",
    }


def suggested_action(
    road: float,
    damage: float,
    normal: float,
    non_road: float,
    privacy: float,
) -> str:
    if non_road >= 0.45 and non_road > road:
        return "review_exclude"
    if privacy >= 0.35:
        return "review_privacy"
    if road >= 0.30 and damage >= 0.25:
        return "review_damage_first"
    if road >= 0.30 and normal >= 0.25:
        return "review_normal_candidate"
    return "review_later"


def format_score(value: float) -> str:
    return f"{value:.6f}"


class KeywordScorer:
    """Deterministic metadata scorer for tests and fallback ranking."""

    name = "keyword"

    def score(self, local_path: Path, row: dict[str, str]) -> dict[str, float]:
        text = " ".join(
            [
                local_path.name,
                row.get("source_url", ""),
                row.get("download_url", ""),
            ]
        ).lower()
        road = keyword_score(text, ["road", "street", "highway", "r-", "unnamed"])
        damage = keyword_score(text, ["crack", "pothole", "damage"])
        normal = keyword_score(text, ["road", "street", "highway"]) * (1.0 - damage)
        non_road = keyword_score(text, ["map", "market", "people", "lake", "steppe"])
        privacy = keyword_score(text, ["people", "street", "market", "car", "vehicle"])
        return {
            "road_surface": road,
            "damage": damage,
            "normal_road": normal,
            "non_road": non_road,
            "privacy_context": privacy,
        }


class ClipScorer:
    def __init__(
        self,
        model_name: str,
        *,
        cache_dir: Path | None = None,
        allow_download: bool = False,
    ) -> None:
        try:
            from PIL import Image
            import torch
            from transformers import CLIPModel, CLIPProcessor
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "CLIP scoring requires optional dependencies. Install with: "
                'python -m pip install -e ".[vision]"'
            ) from exc

        self.name = model_name
        self._image_cls = Image
        self._torch = torch
        load_kwargs = {"cache_dir": str(cache_dir)} if cache_dir else {}
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._model = CLIPModel.from_pretrained(
                model_name,
                local_files_only=True,
                use_safetensors=False,
                **load_kwargs,
            )
            self._processor = CLIPProcessor.from_pretrained(
                model_name,
                local_files_only=True,
                **load_kwargs,
            )
        except OSError:
            if not allow_download:
                cache_hint = f" in {cache_dir}" if cache_dir else ""
                raise RuntimeError(
                    f"CLIP model '{model_name}' is not fully available locally{cache_hint}. "
                    "Run once with --allow-model-download, or use --backend keyword."
                )
            self._model = CLIPModel.from_pretrained(
                model_name,
                use_safetensors=False,
                **load_kwargs,
            )
            self._processor = CLIPProcessor.from_pretrained(model_name, **load_kwargs)
        self._prompt_to_group = []
        self._prompts = []
        for group, prompts in CLIP_PROMPT_GROUPS.items():
            for prompt in prompts:
                self._prompt_to_group.append(group)
                self._prompts.append(prompt)

    def score(self, local_path: Path, row: dict[str, str]) -> dict[str, float]:
        image = self._image_cls.open(local_path).convert("RGB")
        inputs = self._processor(text=self._prompts, images=image, return_tensors="pt", padding=True)
        with self._torch.no_grad():
            outputs = self._model(**inputs)
            probabilities = outputs.logits_per_image.softmax(dim=1)[0].tolist()
        scores = {group: 0.0 for group in CLIP_PROMPT_GROUPS}
        for group, probability in zip(self._prompt_to_group, probabilities):
            scores[group] += probability
        return scores


def keyword_score(text: str, keywords: list[str]) -> float:
    hits = sum(1 for keyword in keywords if keyword in text)
    if hits == 0:
        return 0.05
    return 1.0 / (1.0 + exp(-hits))
