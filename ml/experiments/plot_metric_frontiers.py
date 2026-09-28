"""Render aggregate PR frontiers without saving candidate-level scores."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
)

from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths

DESTINATION = Path("experiments/metric-frontiers-followup-2026-09-24.png")


def main():
    """Plot the unchanged model families on 2025 and diagnostic 2026H1."""
    plt.switch_backend("Agg")
    fig, axes = plt.subplots(1, 2, figsize=(11.8, 4.8), sharex=True, sharey=True)
    for axis, sensor, title, window in (
        (axes[0], "pump", "Насос: смесь 50/50, окно 3 года", 3),
        (axes[1], "fan", "Вентилятор: смесь 50/50, вся история", 0),
    ):
        cache, _, _ = cache_paths(sensor, False)
        frame = pd.read_parquet(cache)
        for year, color, label in (
            (2025, "#2255aa", "2025"),
            (2026, "#d17a10", "2026H1"),
        ):
            valid, (linear, tree), _ = fit_scores(frame, year, window)
            labels = valid["target"].to_numpy()
            score = (linear + tree) / 2
            precision, recall, _ = precision_recall_curve(labels, score)
            ap = average_precision_score(labels, score)
            axis.plot(recall, precision, color=color, linewidth=1.5, label=f"{label}: AP {ap:.3f}")
        axis.axhline(0.70, color="#9d2431", linestyle="--", linewidth=0.9)
        axis.axvline(0.50, color="#9d2431", linestyle="--", linewidth=0.9)
        axis.fill_between([0.50, 1.0], 0.70, 1.0, color="#9d2431", alpha=0.07)
        axis.set_title(title, fontsize=11)
        axis.set_xlim(0, 1)
        axis.set_ylim(0, 1)
        axis.set_xlabel("Recall на кандидатах")
        axis.grid(alpha=0.2)
        axis.legend(loc="upper right", fontsize=9)
    axes[0].set_ylabel("Precision на кандидатах")
    fig.suptitle("PR-кривые после временного разделения; цель — область справа сверху", fontsize=12)
    fig.text(0.5, 0.015, "2026H1 уже использовался для диагностики; кривые показывают оракульный выбор порога.",
             ha="center", fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.045, 1, 0.94))
    fig.savefig(DESTINATION, dpi=180, facecolor="white")
    plt.close(fig)
    print(f"Wrote {DESTINATION}")


if __name__ == "__main__":
    main()
