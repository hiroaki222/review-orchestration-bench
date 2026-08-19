#!/usr/bin/env python3
"""Render 16:9 presentation variants of the Pareto and budget figures.

The paper figures are portrait-ish greyscale tuned for print; on a projector
their annotations are unreadable. These variants trade print-safety for
legibility: vendor colour coding, fewer annotations, larger type.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
EXP_DIR = ROOT / "data" / "experiments" / "v0"

CONFIG_ORDER = ["single", "parallel", "adversarial", "multi"]
CONFIG_MARKER = {"single": "o", "parallel": "s", "adversarial": "^", "multi": "D"}
CONFIG_LABEL = {"single": "Single", "parallel": "Parallel",
                "adversarial": "Adversarial", "multi": "Multi-run"}

# Bar annotations sit in a narrow column, so the long Gemini names wrap.
BAR_MODEL_LABEL = {
    "gemini-3.5-flash-lite": "Gemini 3.5\nflash-lite",
    "gemini-3.6-flash": "Gemini 3.6\nflash",
    "gemini-3.1-pro-preview": "Gemini 3.1\npro-preview",
}

VENDOR_COLOR = {"anthropic": "#D9730D", "openai": "#0F9D58", "google": "#1A73E8"}
VENDOR_LABEL = {"anthropic": "Anthropic", "openai": "OpenAI", "google": "Google"}

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

BUDGETS = [0.002, 0.01, 0.02, 0.05, 0.2]

# Match the beamer deck, which sets Harano Aji Gothic via luatexja-preset.
JP_FONT_DIR = Path("/usr/share/texlive/texmf-dist/fonts/opentype/public/haranoaji")
JP_FONT = JP_FONT_DIR / "HaranoAjiGothic-Regular.otf"


def style() -> None:
    family = "DejaVu Sans"
    if JP_FONT.exists():
        for face in sorted(JP_FONT_DIR.glob("HaranoAjiGothic-*.otf")):
            font_manager.fontManager.addfont(str(face))
        family = font_manager.FontProperties(fname=str(JP_FONT)).get_name()
    plt.rcParams.update({
        "font.family": family,
        "mathtext.fontset": "dejavusans",
        "pdf.fonttype": 42,
        "font.size": 14,
        "axes.labelsize": 15,
        "axes.titlesize": 16,
        "xtick.labelsize": 13,
        "ytick.labelsize": 13,
        "legend.fontsize": 12,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "0.3",
        "lines.linewidth": 2.2,
    })


def vendor_of(model_id: str) -> str:
    if model_id.startswith("claude"):
        return "anthropic"
    if model_id.startswith("gpt") or model_id == "o3":
        return "openai"
    return "google"


def prf2(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    return 5 * p * r / (4 * p + r) if (4 * p + r) else 0.0


def load_points(run: str) -> list[dict]:
    entries = [json.loads(line) for line in
               (EXP_DIR / f"{run}.results.jsonl").open() if line.strip()]
    by_mc = defaultdict(list)
    for e in entries:
        by_mc[(e["model"], e["config"])].append(e)
    points = []
    for (m, c), es in by_mc.items():
        tp = sum(e["tp"] for e in es)
        fp = sum(e["fp"] for e in es)
        fn = sum(e["fn"] for e in es)
        points.append({"model": m, "config": c,
                       "cost": sum(e["cost_usd"] for e in es) / len(es),
                       "f2": prf2(tp, fp, fn)})
    return points


def split_front(points: list[dict]) -> tuple[list[dict], list[dict]]:
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
    return front, [p for i, p in enumerate(points) if i in dominated]


# Hand-tuned so the six front labels never collide with the step line.
FRONT_LABEL_OFFSET = {
    ("gemini-3.5-flash-lite", "single"): (6, -22),
    ("gemini-3.5-flash-lite", "parallel"): (-4, 10),
    ("claude-haiku-4-5", "single"): (8, -6),
    ("claude-haiku-4-5", "multi"): (-22, -42),
    ("gpt-5-mini", "adversarial"): (14, 9),
    ("gpt-5-mini", "multi"): (-30, 12),
}


def plot_pareto(points: list[dict], out: Path) -> None:
    front, dom = split_front(points)
    fig, ax = plt.subplots(figsize=(9.2, 4.9), constrained_layout=True)
    ax.set_xscale("log")

    for c in CONFIG_ORDER:
        subset = [p for p in dom if p["config"] == c]
        if not subset:
            continue
        ax.scatter([p["cost"] for p in subset], [p["f2"] for p in subset],
                   marker=CONFIG_MARKER[c], s=55, facecolor="0.86",
                   edgecolor="0.6", linewidth=0.8, zorder=2)

    fx = [p["cost"] for p in front]
    fy = [p["f2"] for p in front]
    ymin = min(p["f2"] for p in points) - 0.05
    ax.fill_between(fx, fy, y2=ymin, step="post", color="#F5F0E8", zorder=1)
    ax.plot(fx, fy, drawstyle="steps-post", color="0.25", lw=2.4, zorder=3)
    ax.set_ylim(ymin, max(p["f2"] for p in points) + 0.10)

    for p in front:
        v = vendor_of(p["model"])
        ax.scatter(p["cost"], p["f2"], marker=CONFIG_MARKER[p["config"]], s=200,
                   facecolor=VENDOR_COLOR[v], edgecolor="black",
                   linewidth=1.4, zorder=4)
        dx, dy = FRONT_LABEL_OFFSET.get((p["model"], p["config"]), (8, 8))
        ax.annotate(f"{MODEL_LABEL[p['model']]}\n{CONFIG_LABEL[p['config']]}",
                    (p["cost"], p["f2"]), xytext=(dx, dy),
                    textcoords="offset points", fontsize=11.5,
                    color=VENDOR_COLOR[v], fontweight="bold", zorder=5)

    cfg_handles = [Line2D([], [], marker=CONFIG_MARKER[c], ls="", mfc="0.5",
                          mec="black", markersize=10, label=CONFIG_LABEL[c])
                   for c in CONFIG_ORDER]
    vendor_handles = [Line2D([], [], marker="o", ls="", mfc=VENDOR_COLOR[v],
                             mec="black", markersize=10, label=VENDOR_LABEL[v])
                      for v in ("anthropic", "openai", "google")]
    leg1 = ax.legend(handles=cfg_handles, loc="lower right", ncol=2,
                     frameon=True, framealpha=0.95, title="Configuration")
    ax.add_artist(leg1)
    ax.legend(handles=vendor_handles, loc="upper left", frameon=True,
              framealpha=0.95, title="Vendor (front only)")

    ax.set_xlabel("項目あたりコスト (USD, 対数軸)")
    ax.set_ylabel("$F_2$")
    ax.grid(True, alpha=0.25)
    fig.savefig(out)
    print(f"saved {out}")


def best_in_budget(points, budget, orchestrated: bool):
    pool = [p for p in points if p["cost"] <= budget
            and ((p["config"] != "single") if orchestrated else (p["config"] == "single"))]
    return max(pool, key=lambda p: p["f2"]) if pool else None


def plot_budget(points: list[dict], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 4.9), constrained_layout=True)
    x = np.arange(len(BUDGETS))
    w = 0.44

    for i, orch in enumerate([False, True]):
        rows = [best_in_budget(points, b, orch) for b in BUDGETS]
        vals = [r["f2"] if r else 0.0 for r in rows]
        ax.bar(x + (i - 0.5) * w, vals, w,
               facecolor="#C9CBCF" if not orch else "#D9730D",
               edgecolor="black", linewidth=0.9,
               label="Single のみ" if not orch else "オーケストレーション構成",
               zorder=3)
        for xi, r in zip(x + (i - 0.5) * w, rows):
            if not r:
                continue
            name = BAR_MODEL_LABEL.get(r["model"], MODEL_LABEL[r["model"]])
            # Labels sit inside the bars; above them, adjacent pairs collide.
            ax.annotate(f"{name}\n{CONFIG_LABEL[r['config']]}",
                        (xi, r["f2"]), xytext=(0, -7),
                        textcoords="offset points", ha="center", va="top",
                        fontsize=9, color="white" if orch else "black",
                        zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels([f"\\${b:g}" for b in BUDGETS])
    ax.set_xlabel("項目あたり予算上限 (USD)")
    ax.set_ylabel("予算内で達成可能な最高 $F_2$")
    ax.set_ylim(0, 1.02)
    ax.legend(loc="upper left", frameon=True, framealpha=0.95)
    ax.grid(axis="y", color="0.9", lw=0.8, zorder=0)
    fig.savefig(out)
    print(f"saved {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--outdir", default=str(ROOT / "docs" / "slides" / "sigagi" / "fig"))
    args = ap.parse_args()

    style()
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    points = load_points(args.run)
    plot_pareto(points, outdir / "pareto_slide.pdf")
    plot_budget(points, outdir / "budget_slide.pdf")


if __name__ == "__main__":
    main()
