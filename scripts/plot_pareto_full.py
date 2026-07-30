#!/usr/bin/env python3
"""Full-annotation cost-F2 scatter for README / archive use.

Unlike the paper figure (dominated points reduced to grey background), every
one of the 48 (model, config) points here gets a label. Larger canvas, colour
coding, and a two-column legend accept the visual noise in exchange for
completeness.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

plt.rcParams["pdf.fonttype"] = 42

ROOT = Path(__file__).resolve().parent.parent
EXP_DIR = ROOT / "data" / "experiments" / "v0"

MODEL_ORDER = [
    "claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5",
    "gpt-5-mini", "gpt-5", "gpt-5.6-luna", "gpt-5.6-terra", "o3",
    "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-pro-preview",
]
CONFIG_ORDER = ["single", "parallel", "adversarial", "multi"]
CONFIG_MARKER = {"single": "o", "parallel": "s", "adversarial": "^", "multi": "D"}
MODEL_COLOR = {
    # Anthropic — orange/brown family (brand: peach)
    "claude-haiku-4-5": "#FFB380",
    "claude-sonnet-5": "#FF8040",
    "claude-opus-5": "#CC5500",
    "claude-fable-5": "#7A2E00",
    # OpenAI — green family (brand: teal-green)
    "gpt-5-mini": "#A5D6A7",
    "gpt-5": "#66BB6A",
    "gpt-5.6-luna": "#2E7D32",
    "gpt-5.6-terra": "#00695C",
    "o3": "#1B5E20",
    # Google — blue/purple family (brand: Gemini blue)
    "gemini-3.5-flash-lite": "#90CAF9",
    "gemini-3.6-flash": "#1976D2",
    "gemini-3.1-pro-preview": "#0D47A1",
}
MODEL_LABEL = {
    "claude-haiku-4-5": "Haiku 4.5", "claude-sonnet-5": "Sonnet 5",
    "claude-opus-5": "Opus 5", "claude-fable-5": "Fable 5",
    "gpt-5-mini": "GPT-5 mini", "gpt-5": "GPT-5",
    "gpt-5.6-luna": "GPT-5.6 luna", "gpt-5.6-terra": "GPT-5.6 terra",
    "o3": "o3",
    "gemini-3.5-flash-lite": "Gemini 3.5 flash-lite",
    "gemini-3.6-flash": "Gemini 3.6 flash",
    "gemini-3.1-pro-preview": "Gemini 3.1 pro-preview",
}
CONFIG_LABEL = {"single": "Single", "parallel": "Parallel",
                "adversarial": "Adversarial", "multi": "Multi-run"}


def prf2(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return 5 * p * r / (4 * p + r) if (4 * p + r) else 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    entries = [json.loads(line) for line in
               (EXP_DIR / f"{args.run}.results.jsonl").open() if line.strip()]

    by_mc = defaultdict(list)
    for e in entries:
        by_mc[(e["model"], e["config"])].append(e)

    points = []
    for (m, c), es in by_mc.items():
        tp = sum(e["tp"] for e in es); fp = sum(e["fp"] for e in es); fn = sum(e["fn"] for e in es)
        cost_mean = sum(e["cost_usd"] for e in es) / len(es)
        points.append({"model": m, "config": c, "cost": cost_mean, "f2": prf2(tp, fp, fn)})

    dominated = set()
    for i, p1 in enumerate(points):
        for j, p2 in enumerate(points):
            if i == j:
                continue
            if (p2["cost"] <= p1["cost"] and p2["f2"] >= p1["f2"]
                    and (p2["cost"] < p1["cost"] or p2["f2"] > p1["f2"])):
                dominated.add(i)
                break
    front = sorted([p for i, p in enumerate(points) if i not in dominated],
                   key=lambda p: p["cost"])

    fig, ax = plt.subplots(figsize=(16, 10))
    ax.set_xscale("log")

    for p in points:
        ax.scatter(p["cost"], p["f2"], marker=CONFIG_MARKER[p["config"]],
                   color=MODEL_COLOR[p["model"]], s=180, edgecolor="black",
                   linewidth=0.8, zorder=3)

    if front:
        ax.plot([p["cost"] for p in front], [p["f2"] for p in front],
                drawstyle="steps-post", color="black", lw=1.6, alpha=0.6,
                zorder=1, label="Pareto front")

    ax.set_xlabel("Cost per item (USD, log scale)", fontsize=12)
    ax.set_ylabel("F2", fontsize=12)
    ax.grid(True, alpha=0.3)
    ax.set_title(f"All {len(points)} (model, config) combos — Pareto front bold",
                 fontsize=13)

    model_handles = [Line2D([], [], marker="s", ls="", mfc=MODEL_COLOR[m],
                            mec="black", markersize=10, label=MODEL_LABEL[m])
                     for m in MODEL_ORDER if m in {p["model"] for p in points}]
    config_handles = [Line2D([], [], marker=CONFIG_MARKER[c], ls="",
                             mfc="white", mec="black", markersize=10,
                             label=CONFIG_LABEL[c])
                      for c in CONFIG_ORDER]
    front_handle = [Line2D([], [], color="black", lw=1.6, alpha=0.6,
                           label="Pareto front")]

    leg1 = ax.legend(handles=model_handles, loc="lower right",
                     title="Model (color)", fontsize=9, ncol=2,
                     framealpha=0.9)
    ax.add_artist(leg1)
    ax.legend(handles=config_handles + front_handle, loc="upper left",
              title="Config (marker)", fontsize=9, framealpha=0.9)

    out = args.out or str(EXP_DIR / f"{args.run}.summary" / "pareto_full.png")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
