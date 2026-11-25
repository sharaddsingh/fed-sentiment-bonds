"""Charts saved as PNGs in results/ (they show directly in the GitHub README)."""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

LLM = "#257de0"        # blue
DICT = "#f47230"       # orange
HAWK = "#f47230"       # orange = hawkish
DOVE = "#257de0"       # blue = dovish
GREY = "#9c9c9c"
TEXT = "#191919"
MUTED = "#666666"
GRID = "#e6e6e6"

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "font.size": 10,
    "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlecolor": TEXT,
    "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
})


def _save(fig, out_dir, name):
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, name), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_tone_timeline(ev: pd.DataFrame, target: pd.Series, score_col: str,
                       score_label: str, out_dir: str):
    """Top: Fed funds rate. Bottom: statement tone (same time axis, no dual y-axis)."""
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True,
                                   gridspec_kw={"height_ratios": [1, 1.3]})
    t = target.loc[ev["date"].min():]
    ax1.step(t.index, t.values, where="post", color=TEXT, linewidth=1.6)
    ax1.set_title("Fed funds target rate (%)")
    s = ev.set_index("date")[score_col]
    colors = [HAWK if v > 0 else DOVE if v < 0 else GREY for v in s.values]
    ax2.bar(s.index, s.values, width=25, color=colors)
    ax2.axhline(0, color=MUTED, linewidth=0.8)
    ax2.set_title(f"Statement tone: {score_label}  (orange = hawkish, blue = dovish)")
    _save(fig, out_dir, "tone_timeline.png")


def plot_scatter(ev: pd.DataFrame, panels: list[tuple[str, str, str]], out_dir: str):
    """Tone change vs 2Y yield move, one panel per method."""
    fig, axes = plt.subplots(1, len(panels), figsize=(5.2 * len(panels), 4.3), squeeze=False)
    for ax, (col, label, color) in zip(axes[0], panels):
        df = ev[[col, "d2y_bps"]].dropna()
        x, y = df[col].values, df["d2y_bps"].values
        jitter = np.random.default_rng(0).normal(0, 0.06 * (x.std() or 1), len(x))
        ax.scatter(x + jitter, y, s=22, color=color, alpha=0.6, edgecolors="white",
                   linewidths=0.6)
        if len(df) > 2 and x.std() > 0:
            b, a = np.polyfit(x, y, 1)
            xs = np.linspace(x.min(), x.max(), 50)
            ax.plot(xs, a + b * xs, color=TEXT, linewidth=1.6)
            r = np.corrcoef(x, y)[0, 1]
            ax.set_title(f"{label}  (r = {r:.2f})")
        ax.axhline(0, color=MUTED, linewidth=0.8)
        ax.axvline(0, color=MUTED, linewidth=0.8)
        ax.set_xlabel("Change in tone vs previous statement")
        ax.set_ylabel("2Y yield move on the day (bps)")
    _save(fig, out_dir, "tone_vs_2y_yield.png")


def plot_correlations(corr: pd.DataFrame, out_dir: str):
    """Grouped bars: correlation of tone change with each market, per method."""
    fig, ax = plt.subplots(figsize=(10, 4))
    markets = list(corr.columns)
    n = len(corr.index)
    w = 0.8 / n
    palette = [LLM, DICT, "#00b894"]
    for i, method in enumerate(corr.index):
        xs = np.arange(len(markets)) + (i - (n - 1) / 2) * w
        vals = corr.loc[method].values
        ax.bar(xs, vals, width=w - 0.03, color=palette[i % 3], label=method)
        for x, v in zip(xs, vals):
            if pd.notna(v):
                ax.annotate(f"{v:+.2f}", (x, v), xytext=(0, 3 if v >= 0 else -11),
                            textcoords="offset points", ha="center", fontsize=8, color=TEXT)
    ax.set_xticks(range(len(markets)))
    ax.set_xticklabels(markets, fontsize=9)
    ax.axhline(0, color=MUTED, linewidth=0.8)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Correlation with tone change")
    ax.set_title("Which markets react to a change in Fed tone?")
    ax.legend(loc="upper right")
    _save(fig, out_dir, "correlation_by_market.png")


def plot_fomc_vs_normal(fomc_moves: pd.Series, normal_moves: pd.Series, out_dir: str):
    vals = [normal_moves.abs().mean(), fomc_moves.abs().mean()]
    fig, ax = plt.subplots(figsize=(6, 3.6))
    bars = ax.bar(["Normal days", "Fed statement days"], vals, color=[GREY, LLM], width=0.55)
    for b, v in zip(bars, vals):
        ax.annotate(f"{v:.1f} bps", (b.get_x() + b.get_width() / 2, v), xytext=(0, 3),
                    textcoords="offset points", ha="center", fontsize=10, color=TEXT)
    ax.grid(axis="x", visible=False)
    ax.set_ylabel("Average absolute 2Y move (bps)")
    ax.set_title("Average 2Y yield move: Fed days vs other days")
    _save(fig, out_dir, "fomc_vs_normal_days.png")
