from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "figure.dpi": 160,
        "savefig.bbox": "tight",
    }
)

colors = {
    "teal": "#2A9D8F",
    "blue": "#457B9D",
    "red": "#E76F51",
    "gold": "#E9C46A",
    "ink": "#243447",
}


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png")
    plt.close(fig)


def dataset_funnel():
    labels = ["Candidate\nleads", "Publishable\nimages", "Damaged\nimages", "Normal /\nhard negatives"]
    values = [3613, 75, 50, 25]
    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    bars = ax.bar(labels, values, color=[colors["ink"], colors["teal"], colors["red"], colors["blue"]])
    ax.set_ylabel("Images")
    ax.set_title("Kazakhstan image audit funnel")
    ax.set_yscale("log")
    ax.set_ylim(10, 6000)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value * 1.12, f"{value:,}", ha="center", va="bottom")
    save(fig, "dataset_funnel")


def class_distribution():
    labels = ["Longitudinal\ncrack", "Alligator\ncrack", "Pothole", "Transverse\ncrack"]
    values = [48, 35, 11, 10]
    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    bars = ax.bar(labels, values, color=[colors["teal"], colors["blue"], colors["gold"], colors["red"]])
    ax.set_ylabel("Bounding boxes")
    ax.set_title("Kazakhstan damage-class distribution")
    ax.set_ylim(0, 55)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 1.2, str(value), ha="center", va="bottom")
    save(fig, "class_distribution")


def external_results():
    models = ["YOLO11s", "Ghost-CA-\nYOLO"]
    rdd_only = np.array([0.1677, 0.2617])
    adapted = np.array([0.6896, 0.6753])
    x = np.arange(len(models))
    width = 0.34

    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    ax.bar(x - width / 2, rdd_only, width, label="RDD-only", color=colors["red"])
    ax.bar(x + width / 2, adapted, width, label="RDD + Kazakhstan", color=colors["teal"])
    ax.set_xticks(x)
    ax.set_xticklabels(models)
    ax.set_ylabel("mAP50")
    ax.set_title("Kazakhstan external-validation performance")
    ax.set_ylim(0, 0.78)
    ax.legend(frameon=False, loc="upper left")
    for xpos, value in zip(x - width / 2, rdd_only):
        ax.text(xpos, value + 0.015, f"{value:.3f}", ha="center")
    for xpos, value in zip(x + width / 2, adapted):
        ax.text(xpos, value + 0.015, f"{value:.3f}", ha="center")
    save(fig, "kz_external_map50")


def adaptation_gain():
    labels = ["YOLO11s\nmAP50", "YOLO11s\nmAP50-95", "Ghost-CA-YOLO\nmAP50", "Ghost-CA-YOLO\nmAP50-95"]
    gains = np.array(
        [
            0.6896 - 0.1677,
            0.3243 - 0.0309,
            0.6753 - 0.2617,
            0.2612 - 0.0320,
        ]
    )
    x = np.arange(len(labels))

    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    bars = ax.bar(x, gains, color=[colors["teal"], colors["blue"], colors["teal"], colors["blue"]])
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Absolute metric gain")
    ax.set_title("Kazakhstan fine-tuning gain over RDD-only transfer")
    ax.set_ylim(0, 0.58)
    for bar, value in zip(bars, gains):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.014, f"+{value:.3f}", ha="center")
    save(fig, "adaptation_gain")


def ghost_ca_efficiency():
    metrics = ["RDD\nmAP50", "RDD\nmAP50-95", "Params\n(M)", "GFLOPs", "Inference\n(ms/img)"]
    baseline = np.array([0.610, 0.298, 9.41, 21.3, 2.7])
    ghost = np.array([0.576, 0.282, 8.54, 23.1, 1.9])
    x = np.arange(len(metrics))
    width = 0.34

    fig, ax = plt.subplots(figsize=(5.8, 3.0))
    ax.bar(x - width / 2, baseline, width, label="YOLO11s", color=colors["blue"])
    ax.bar(x + width / 2, ghost, width, label="Ghost-CA-YOLO", color=colors["teal"])
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("Measured value")
    ax.set_title("RDD2022 accuracy and model-efficiency indicators")
    ax.set_ylim(0, 25.5)
    ax.legend(frameon=False, loc="upper left")
    for xpos, value in zip(x - width / 2, baseline):
        ax.text(xpos, value + 0.45, f"{value:.3g}", ha="center")
    for xpos, value in zip(x + width / 2, ghost):
        ax.text(xpos, value + 0.45, f"{value:.3g}", ha="center")
    save(fig, "ghost_ca_efficiency")


if __name__ == "__main__":
    dataset_funnel()
    class_distribution()
    external_results()
    adaptation_gain()
    ghost_ca_efficiency()
