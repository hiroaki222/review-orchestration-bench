#!/usr/bin/env python3
"""Budget-tier bar chart: naive Single-model choice vs orchestrated combos.

For each budget ceiling B, take max F2 achievable within `cost_mean <= B`
separately from (a) Single-config combos and (b) Parallel/Adversarial/Multi-run
combos. The bars visualize the paper's core claim ("under matched budget,
cheap model + orchestration beats premium model / single call").
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["pdf.fonttype"] = 42

ROOT = Path(__file__).resolve().parent.parent
EXP_DIR = ROOT / "data" / "experiments" / "v0"

BUDGETS = [0.002, 0.01, 0.02, 0.05, 0.2]

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


def best_in_budget(points, budget, orchestrated: bool):
    if orchestrated:
        pool = [p for p in points if p["cost"] <= budget and p["config"] != "single"]
    else:
        pool = [p for p in points if p["cost"] <= budget and p["config"] == "single"]
    if not pool:
        return None
    return max(pool, key=lambda p: p["f2"])


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

    fig, ax = plt.subplots(figsize=(6.5, 3.6), constrained_layout=True)
    x = np.arange(len(BUDGETS))
    w = 0.38

    for i, orch in enumerate([False, True]):
        rows = [best_in_budget(points, b, orch) for b in BUDGETS]
        vals = [r["f2"] if r else 0.0 for r in rows]
        ax.bar(x + (i - 0.5) * w, vals, w,
               facecolor="white" if not orch else "0.75",
               edgecolor="black",
               hatch=None if not orch else "///",
               label="Single (best affordable model)" if not orch
                     else "Orchestrated (best model+config)",
               zorder=3)
        for xi, r in zip(x + (i - 0.5) * w, rows):
            if not r:
                continue
            ax.annotate(f"{MODEL_LABEL[r['model']]}\n{CONFIG_LABEL[r['config']]}",
                        (xi, r["f2"]), xytext=(0, 2),
                        textcoords="offset points",
                        ha="center", va="bottom", fontsize=6)

    ax.set_xticks(x)
    ax.set_xticklabels([f"${b:g}" for b in BUDGETS])
    ax.set_xlabel("Cost budget per item (USD)")
    ax.set_ylabel("Best achievable F2 within budget")
    ax.set_ylim(0, 0.95)
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(axis="y", color="0.9", lw=0.6, zorder=0)

    out = args.out or str(EXP_DIR / f"{args.run}.summary" / "budget.pdf")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
