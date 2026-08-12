#!/usr/bin/env python3
"""Render cost-F2 scatter with Pareto front for a pilot run.

v2 design: dominated points are pushed to a grey background layer; the Pareto
front is drawn as a step function with the dominated region shaded, and only
the front's points carry model/config annotations. Marker shape encodes
configuration so the plot is legible in black-and-white print.
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

CONFIG_ORDER = ["single", "parallel", "adversarial", "multi"]
CONFIG_MARKER = {"single": "o", "parallel": "s", "adversarial": "^", "multi": "D"}
CONFIG_FACE = {"single": "white", "parallel": "0.75",
               "adversarial": "0.45", "multi": "black"}
CONFIG_LABEL = {"single": "Single", "parallel": "Parallel",
                "adversarial": "Adversarial", "multi": "Multi-run"}

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
    dom_pts = [p for i, p in enumerate(points) if i in dominated]

    fig, ax = plt.subplots(figsize=(6.5, 4.2), constrained_layout=True)
    ax.set_xscale("log")

    for c in CONFIG_ORDER:
        subset = [p for p in dom_pts if p["config"] == c]
        if not subset:
            continue
        ax.scatter([p["cost"] for p in subset], [p["f2"] for p in subset],
                   marker=CONFIG_MARKER[c], s=34, facecolor="0.82",
                   edgecolor="0.55", linewidth=0.6, zorder=2)

    front_x = [p["cost"] for p in front]
    front_y = [p["f2"] for p in front]
    ax.plot(front_x, front_y, drawstyle="steps-post", color="black",
            lw=2.0, zorder=3)
    ymin = min([p["f2"] for p in points]) - 0.05
    ax.set_ylim(ymin, max([p["f2"] for p in points]) + 0.06)
    ax.fill_between(front_x, front_y, y2=ymin, step="post",
                    color="0.94", zorder=1)

    for p in front:
        ax.scatter(p["cost"], p["f2"], marker=CONFIG_MARKER[p["config"]], s=100,
                   facecolor=CONFIG_FACE[p["config"]], edgecolor="black",
                   linewidth=1.2, zorder=4)
        ax.annotate(f"{MODEL_LABEL[p['model']]}\n{CONFIG_LABEL[p['config']]}",
                    (p["cost"], p["f2"]),
                    xytext=(5, 6), textcoords="offset points", fontsize=7,
                    zorder=5)

    handles = [Line2D([], [], marker=CONFIG_MARKER[c], ls="",
                      mfc=CONFIG_FACE[c], mec="black", markersize=8,
                      label=CONFIG_LABEL[c]) for c in CONFIG_ORDER]
    handles += [Line2D([], [], color="black", lw=2, label="Pareto front"),
                Line2D([], [], marker="o", ls="", mfc="0.82", mec="0.55",
                       markersize=6, label="Dominated")]
    ax.legend(handles=handles, loc="lower right", fontsize=7, frameon=True,
              framealpha=0.9)

    ax.set_xlabel("Cost budget per item (USD, log scale)")
    ax.set_ylabel("F2")
    ax.grid(True, alpha=0.3)

    out = args.out or str(EXP_DIR / f"{args.run}.summary" / "pareto.pdf")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
