#!/usr/bin/env python3
"""Aggregate experiment results into per-(model, config) tables and cost-quality Pareto data.

Reads data/experiments/v0/<run_name>.results.jsonl and writes summary tables +
per-(model, config) roll-ups + item-level detail to
data/experiments/v0/<run_name>.summary/.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

ROOT = Path(__file__).resolve().parent.parent
EXP_DIR = ROOT / "data" / "experiments" / "v0"

CONFIG_ORDER = ["single", "parallel", "adversarial", "multi"]
MODEL_ORDER = [
    "claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5",
    "gpt-5-mini", "gpt-5", "gpt-5.6-luna", "gpt-5.6-terra", "o3",
    "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-pro-preview",
]


def load_results(run_name: str) -> list[dict]:
    path = EXP_DIR / f"{run_name}.results.jsonl"
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def prf(tp: int, fp: int, fn: int, beta: float = 1.0) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    b2 = beta * beta
    f = (1 + b2) * p * r / (b2 * p + r) if (b2 * p + r) else 0.0
    return p, r, f


def summarize_group(entries: list[dict]) -> dict:
    if not entries:
        return {}
    tp = sum(e["tp"] for e in entries)
    fp = sum(e["fp"] for e in entries)
    fn = sum(e["fn"] for e in entries)
    p, r, f1 = prf(tp, fp, fn, beta=1.0)
    _, _, f2 = prf(tp, fp, fn, beta=2.0)
    costs = [e["cost_usd"] for e in entries]
    passes = [e["passes"] for e in entries]
    return {
        "n_items": len(entries),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(p, 4),
        "recall": round(r, 4),
        "f1": round(f1, 4),
        "f2": round(f2, 4),
        "cost_total": round(sum(costs), 6),
        "cost_mean": round(mean(costs), 6),
        "cost_median": round(median(costs), 6),
        "cost_stdev": round(stdev(costs), 6) if len(costs) > 1 else 0.0,
        "passes_mean": round(mean(passes), 2),
        "passes_max": max(passes),
        "truncated": sum(1 for e in entries if e["truncated"]),
        "parse_failures": sum(e["parse_failures"] for e in entries),
        "n_findings_mean": round(mean(e["n_findings"] for e in entries), 2),
        "cost_per_tp": round(sum(costs) / tp, 6) if tp else None,
    }


def print_table(headers: list[str], rows: list[list], widths: list[int]) -> None:
    line = " ".join(f"{h:<{w}}" for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for row in rows:
        print(" ".join(f"{str(c):<{w}}" for c, w in zip(row, widths)))


def render_by_model_config(all_by_mc: dict) -> None:
    print("\n=== per (model, config) ===")
    print_table(
        ["model", "config", "n", "TP", "FP", "FN", "prec", "rec", "F2", "$mean", "$/TP", "passes"],
        [[m, c,
          s.get("n_items", 0), s.get("tp", 0), s.get("fp", 0), s.get("fn", 0),
          f"{s.get('precision', 0):.3f}", f"{s.get('recall', 0):.3f}", f"{s.get('f2', 0):.3f}",
          f"${s.get('cost_mean', 0):.4f}",
          f"${s.get('cost_per_tp', 0):.4f}" if s.get("cost_per_tp") else "-",
          f"{s.get('passes_mean', 0):.1f}"]
         for (m, c), s in sorted(all_by_mc.items(),
                                 key=lambda x: (MODEL_ORDER.index(x[0][0]),
                                                CONFIG_ORDER.index(x[0][1])))],
        [22, 12, 4, 4, 4, 4, 6, 6, 6, 8, 8, 7],
    )


def render_pareto(all_by_mc: dict) -> None:
    print("\n=== cost-F2 Pareto (dominated combos marked *) ===")
    points = [(m, c, s["cost_mean"], s["f2"]) for (m, c), s in all_by_mc.items()]
    dominated = set()
    for i, (m1, c1, cost1, f2_1) in enumerate(points):
        for j, (m2, c2, cost2, f2_2) in enumerate(points):
            if i == j:
                continue
            if cost2 <= cost1 and f2_2 >= f2_1 and (cost2 < cost1 or f2_2 > f2_1):
                dominated.add(i)
                break
    print_table(
        ["model", "config", "$mean", "F2", "on-front?"],
        [[m, c, f"${cost:.4f}", f"{f2:.3f}", "" if i in dominated else "*"]
         for i, (m, c, cost, f2) in
         sorted(enumerate(points), key=lambda x: x[1][2])],
        [22, 12, 8, 6, 10],
    )


def render_by_repo(entries: list[dict]) -> None:
    by_repo = defaultdict(list)
    for e in entries:
        by_repo[e["repo"]].append(e)
    print("\n=== per repo (all model/config combined) ===")
    print_table(
        ["repo", "n_entries", "TP", "FP", "FN", "prec", "rec", "F2", "$total"],
        [[repo, len(es),
          sum(e["tp"] for e in es), sum(e["fp"] for e in es), sum(e["fn"] for e in es),
          f"{prf(sum(e['tp'] for e in es), sum(e['fp'] for e in es), sum(e['fn'] for e in es), beta=2.0)[0]:.3f}",
          f"{prf(sum(e['tp'] for e in es), sum(e['fp'] for e in es), sum(e['fn'] for e in es), beta=2.0)[1]:.3f}",
          f"{prf(sum(e['tp'] for e in es), sum(e['fp'] for e in es), sum(e['fn'] for e in es), beta=2.0)[2]:.3f}",
          f"${sum(e['cost_usd'] for e in es):.3f}"]
         for repo, es in sorted(by_repo.items())],
        [10, 10, 4, 4, 4, 6, 6, 6, 8],
    )


def render_by_cutoff(entries: list[dict]) -> None:
    print("\n=== pre-cutoff vs post-cutoff (all combined; leakage sanity) ===")
    for flag in [True, False]:
        es = [e for e in entries if e["post_cutoff"] == flag]
        if not es:
            continue
        p, r, f = prf(sum(e["tp"] for e in es), sum(e["fp"] for e in es), sum(e["fn"] for e in es), beta=2.0)
        label = "post-cutoff" if flag else "pre-cutoff"
        print(f"  {label:12s} n={len(es):4d}  prec={p:.3f}  rec={r:.3f}  F2={f:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Run name (matches <run>.results.jsonl)")
    ap.add_argument("--save", action="store_true", help="Write summary JSON to disk")
    ap.add_argument("--paper-dir", default=None,
                    help="If set, also write LaTeX tables to <paper-dir>/tables/")
    args = ap.parse_args()

    entries = load_results(args.run)
    print(f"run={args.run}  total_entries={len(entries)}")

    by_mc = defaultdict(list)
    for e in entries:
        by_mc[(e["model"], e["config"])].append(e)
    all_by_mc = {k: summarize_group(v) for k, v in by_mc.items()}

    render_by_model_config(all_by_mc)
    render_pareto(all_by_mc)
    render_by_repo(entries)
    render_by_cutoff(entries)

    total_cost = sum(e["cost_usd"] for e in entries)
    print(f"\ntotal spend across all runs: ${total_cost:.4f}")

    if args.save:
        out_dir = EXP_DIR / f"{args.run}.summary"
        out_dir.mkdir(exist_ok=True)
        (out_dir / "by_model_config.json").write_text(json.dumps(
            {f"{m}::{c}": s for (m, c), s in all_by_mc.items()},
            ensure_ascii=False, indent=2) + "\n")
        (out_dir / "table_main.tex").write_text(latex_main_table(all_by_mc))
        (out_dir / "table_pareto.tex").write_text(latex_pareto_table(all_by_mc))
        print(f"\nsaved to {out_dir}/")

    if args.paper_dir:
        paper_tables = Path(args.paper_dir) / "tables"
        paper_tables.mkdir(parents=True, exist_ok=True)
        (paper_tables / "table_main.tex").write_text(latex_main_table(all_by_mc))
        (paper_tables / "table_pareto.tex").write_text(latex_pareto_table(all_by_mc))
        (paper_tables / "table_repo_best.tex").write_text(
            latex_repo_best_table(repo_breakdown(entries))
        )
        (paper_tables / "table_category_best.tex").write_text(
            latex_category_best_table(categorical_breakdown(entries))
        )
        (paper_tables / "table_beta.tex").write_text(
            latex_beta_table(f_beta_by_config(entries))
        )
        (paper_tables / "macros.tex").write_text(
            latex_macros(all_by_mc, entries,
                         categorical_breakdown(entries),
                         repo_breakdown(entries),
                         bootstrap_f2_ci(entries))
        )
        print(f"paper tables -> {paper_tables}/")


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
CATEGORY_LABEL = {
    "logic": "logic", "concurrency": "concurrency",
    "type-safety": "type-safety", "error-handling": "error-handling",
    "api-misuse": "api-misuse", "security": "security",
    "resource-leak": "resource-leak", "other": "other",
}
CONFIG_LABEL = {
    "single": "Single", "parallel": "Parallel",
    "adversarial": "Adversarial", "multi": "Multi-run",
}


CONFIG_SHORT = {"single": "Sin", "parallel": "Par",
                "adversarial": "Adv", "multi": "MR"}
VENDOR_OF_MODEL = {
    "claude-haiku-4-5": "Anthropic", "claude-sonnet-5": "Anthropic",
    "claude-opus-5": "Anthropic", "claude-fable-5": "Anthropic",
    "gpt-5-mini": "OpenAI", "gpt-5": "OpenAI",
    "gpt-5.6-luna": "OpenAI", "gpt-5.6-terra": "OpenAI", "o3": "OpenAI",
    "gemini-3.5-flash-lite": "Google", "gemini-3.6-flash": "Google",
    "gemini-3.1-pro-preview": "Google",
}


def latex_main_table(all_by_mc: dict) -> str:
    points = [(m, c, s["cost_mean"], s["f2"])
              for (m, c), s in all_by_mc.items()]
    dominated = set()
    for i, (_, _, cost1, f2_1) in enumerate(points):
        for j, (_, _, cost2, f2_2) in enumerate(points):
            if i == j:
                continue
            if (cost2 <= cost1 and f2_2 >= f2_1
                    and (cost2 < cost1 or f2_2 > f2_1)):
                dominated.add(i)
                break
    pareto_mc = {(points[i][0], points[i][1]) for i in range(len(points))
                 if i not in dominated}

    global_best_mc = max(all_by_mc.items(), key=lambda x: x[1]["f2"])[0]
    per_model_best_config = {}
    for m in MODEL_ORDER:
        cfgs = {c: all_by_mc[(m, c)]["f2"] for c in CONFIG_ORDER
                if (m, c) in all_by_mc}
        if cfgs:
            per_model_best_config[m] = max(cfgs, key=lambda c: cfgs[c])

    lines = [r"\begin{tabular}{@{}llrrrr@{}}", r"\toprule",
             r"Model & Cfg & Prec & Rec & $F_2$ & \$/item \\", r"\midrule"]
    prev_vendor = None
    for m_idx, m in enumerate(MODEL_ORDER):
        cfgs_present = [c for c in CONFIG_ORDER if (m, c) in all_by_mc
                        or any(k[0] == m for k in all_by_mc)]
        model_rows = [(m, c) for c in CONFIG_ORDER]
        vendor = VENDOR_OF_MODEL.get(m, "")
        if vendor != prev_vendor:
            if prev_vendor is not None:
                lines.append(r"\midrule")
            lines.append(
                r"\multicolumn{6}{@{}l}{\textit{" + vendor + r"}} \\[1pt]")
            prev_vendor = vendor
        elif m_idx > 0:
            lines.append(r"\addlinespace[2pt]")

        label_m = MODEL_LABEL.get(m, m)
        for idx, (mm, c) in enumerate(model_rows):
            first = r"\multirow[t]{4}{*}{" + label_m + "}" if idx == 0 else ""
            label_c = CONFIG_SHORT.get(c, c)
            s = all_by_mc.get((mm, c))
            if not s:
                lines.append(
                    f"{first} & {label_c} & "
                    r"\multicolumn{4}{c@{}}{--$^{\dagger}$} \\"
                )
                continue
            f2_str = f"{s['f2']:.3f}"
            if (mm, c) == global_best_mc:
                f2_str = r"\underline{\textbf{" + f2_str + "}}"
            elif per_model_best_config.get(mm) == c:
                f2_str = r"\textbf{" + f2_str + "}"
            if (mm, c) in pareto_mc:
                f2_str = f2_str + r"$^{P}$"
            lines.append(
                f"{first} & {label_c} & {s['precision']:.2f} & {s['recall']:.2f} & "
                f"{f2_str} & {s['cost_mean']:.4f} \\\\"
            )

    by_config: dict = defaultdict(list)
    for (_, c), s in all_by_mc.items():
        by_config[c].append(s["f2"])
    means = {c: mean(vs) for c, vs in by_config.items()}
    best_mean_c = max(means, key=lambda c: means[c])
    mean_frags = []
    for c in CONFIG_ORDER:
        if c not in means:
            continue
        v = f"{means[c]:.3f}"
        if c == best_mean_c:
            v = r"\textbf{" + v + "}"
        mean_frags.append(f"{CONFIG_SHORT[c]}\\,{v}")
    lines.append(r"\midrule")
    lines.append(
        r"\multicolumn{6}{@{}l}{\textit{Mean $F_2$ over models}: "
        + " / ".join(mean_frags) + r"} \\"
    )

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


CATEGORY_ORDER_TABLE = [
    "logic", "type-safety", "error-handling", "concurrency",
    "api-misuse", "security", "resource-leak", "other",
]


def latex_category_best_table(cat_bd: dict) -> str:
    lines = [r"\begin{tabular}{@{}lllr@{}}", r"\toprule",
             r"バグ種別 & 最良 (モデル / 構成) & $F_2$ & N \\", r"\midrule"]
    for cat in CATEGORY_ORDER_TABLE:
        v = cat_bd.get(cat)
        if not v:
            continue
        label = (f"{MODEL_LABEL.get(v['best_model'], v['best_model'])} / "
                 f"{CONFIG_LABEL.get(v['best_config'], v['best_config'])}")
        n = v['n_items']
        n_str = f"{n}$^{{\\dagger}}$" if n <= 2 else f"{n}"
        lines.append(
            f"{CATEGORY_LABEL.get(cat, cat)} & {label} & "
            f"{v['best_f2']:.3f} & {n_str} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def latex_beta_table(f_by_beta: dict) -> str:
    betas = sorted(f_by_beta.keys())
    lines = [r"\begin{tabular}{@{}l" + "r" * len(betas) + r"@{}}",
             r"\toprule"]
    header = "Config"
    for b in betas:
        header += f" & $F_{{{b:g}}}$"
    lines.append(header + r" \\")
    lines.append(r"\midrule")
    for c in CONFIG_ORDER:
        row = CONFIG_LABEL.get(c, c)
        vals_at_c = [f_by_beta[b].get(c, 0.0) for b in betas]
        for b, v in zip(betas, vals_at_c):
            best_in_col = max(f_by_beta[b].values())
            cell = f"{v:.3f}"
            if abs(v - best_in_col) < 1e-6:
                cell = r"\textbf{" + cell + "}"
            row += f" & {cell}"
        lines.append(row + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def latex_repo_best_table(repo_bd: dict) -> str:
    repos = ["fastapi", "valibot", "chi", "pgrust"]
    lines = [r"\begin{tabular}{@{}lll@{}}", r"\toprule",
             r"リポジトリ (言語) & 最良 (モデル / 構成) & $F_2$ \\", r"\midrule"]
    for repo in repos:
        v = repo_bd.get(repo)
        if not v:
            continue
        label = (f"{MODEL_LABEL.get(v['best_model'], v['best_model'])} / "
                 f"{CONFIG_LABEL.get(v['best_config'], v['best_config'])}")
        lines.append(
            f"{REPO_LABEL.get(repo, repo)} & {label} & {v['best_f2']:.3f} \\\\"
        )
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def latex_pareto_table(all_by_mc: dict) -> str:
    points = [(m, c, s["cost_mean"], s["f2"]) for (m, c), s in all_by_mc.items()]
    dominated = set()
    for i, (_, _, cost1, f2_1) in enumerate(points):
        for j, (_, _, cost2, f2_2) in enumerate(points):
            if i == j:
                continue
            if cost2 <= cost1 and f2_2 >= f2_1 and (cost2 < cost1 or f2_2 > f2_1):
                dominated.add(i)
                break
    on_front = [(m, c, cost, f2) for i, (m, c, cost, f2) in enumerate(points)
                if i not in dominated]
    on_front.sort(key=lambda x: x[2])
    lines = [r"\begin{tabular}{llrr}", r"\toprule",
             r"Model & Config & \$/item & $F_2$ \\", r"\midrule"]
    for m, c, cost, f2 in on_front:
        lines.append(f"{MODEL_LABEL[m]} & {CONFIG_LABEL[c]} & "
                     f"\\${cost:.4f} & {f2:.3f} \\\\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    return "\n".join(lines) + "\n"


def latex_discussion(all_by_mc: dict, entries: list[dict]) -> str:
    if not all_by_mc:
        return "% no data\n"
    best_f1 = max(all_by_mc.items(), key=lambda x: x[1]["f1"])
    cheapest = min(all_by_mc.items(), key=lambda x: x[1]["cost_mean"])
    priciest = max(all_by_mc.items(), key=lambda x: x[1]["cost_mean"])
    spread = priciest[1]["cost_mean"] / cheapest[1]["cost_mean"] if cheapest[1]["cost_mean"] else 0
    total_cost = sum(e["cost_usd"] for e in entries)

    by_config = defaultdict(list)
    for (m, c), s in all_by_mc.items():
        by_config[c].append(s)
    config_means = {c: {"f1": mean(s["f1"] for s in ss),
                         "cost": mean(s["cost_mean"] for s in ss)}
                     for c, ss in by_config.items()}

    lines = [
        r"最良の $F_1$ は " + f"\\textbf{{{MODEL_LABEL[best_f1[0][0]]} / {CONFIG_LABEL[best_f1[0][1]]}}}"
        f" ($F_1 = {best_f1[1]['f1']:.3f}$, \\${best_f1[1]['cost_mean']:.4f}/件) で得られた．",
        f"項目あたりコストは最安 \\${cheapest[1]['cost_mean']:.4f} から最高 \\${priciest[1]['cost_mean']:.4f} まで {spread:.0f} 倍の広がりを持つが，"
        r"$F_1$ は必ずしもコストに単調ではない．",
    ]
    if "single" in config_means and "parallel" in config_means:
        lines.append(
            f"構成の観点では，Single の平均 $F_1={config_means['single']['f1']:.3f}$ に対して "
            f"Parallel は {config_means['parallel']['f1']:.3f} と低く，"
            r"観点別の並列化は反証機構なしでは偽陽性を増やし精度を下げる傾向が示唆された．"
        )
    if "adversarial" in config_means:
        lines.append(
            f"Adversarial は平均 $F_1={config_means['adversarial']['f1']:.3f}$ で "
            f"平均 \\${config_means['adversarial']['cost']:.4f}/件を要し，"
            r"提案の反証段が精度を押し上げる一方，パス数の増加でコストが単一構成の数倍に達する．"
        )
    by_model = defaultdict(list)
    for (m, c), s in all_by_mc.items():
        by_model[m].append((c, s))
    dominated_models = []
    for m, cfg_list in by_model.items():
        model_dominated = True
        for c, s in cfg_list:
            others_beat = False
            for (m2, c2), s2 in all_by_mc.items():
                if m2 == m: continue
                if s2["cost_mean"] <= s["cost_mean"] and s2["f1"] >= s["f1"] and \
                   (s2["cost_mean"] < s["cost_mean"] or s2["f1"] > s["f1"]):
                    others_beat = True; break
            if not others_beat:
                model_dominated = False; break
        if model_dominated:
            dominated_models.append(m)
    if dominated_models:
        labels = "，".join(MODEL_LABEL[m] for m in dominated_models)
        lines.append(
            f"注目すべきは，{labels} が全構成において他モデルの何らかの構成に (コスト, $F_1$) の両面で劣位となり Pareto 前線から外れた点である．"
            r"同一の欠陥検出タスク・同一予算下では，価格帯上位のモデルを単純に選ぶよりも，価格帯下位のモデルに反証段や多数決集約を組み合わせる方が支配的な戦略となる可能性を示唆する．"
        )
    lines.append(
        f"本実験の総 API 支出は \\${total_cost:.2f}であり，追試に必要な計算量が実務範囲に収まることを示す．"
    )
    return "\n".join(lines) + "\n"


def bootstrap_f2_ci(entries: list[dict], n_boot: int = 2000,
                    seed: int = 42) -> dict:
    import random
    rng = random.Random(seed)
    by_mc_items: dict = defaultdict(list)
    for e in entries:
        by_mc_items[(e["model"], e["config"])].append(e)
    result = {}
    for mc, items in by_mc_items.items():
        n = len(items)
        if n < 2:
            continue
        f2s = []
        for _ in range(n_boot):
            sample = [rng.choice(items) for _ in range(n)]
            tp = sum(x["tp"] for x in sample)
            fp = sum(x["fp"] for x in sample)
            fn = sum(x["fn"] for x in sample)
            _, _, f2 = prf(tp, fp, fn, beta=2.0)
            f2s.append(f2)
        f2s.sort()
        lo = f2s[int(n_boot * 0.025)]
        hi = f2s[int(n_boot * 0.975)]
        result[mc] = {"ci_lo": round(lo, 4), "ci_hi": round(hi, 4)}
    return result


def f_beta_by_config(entries: list[dict],
                      betas: list[float] | None = None) -> dict:
    if betas is None:
        betas = [1.0, 1.5, 2.0, 3.0]
    by_mc: dict = defaultdict(list)
    for e in entries:
        by_mc[(e["model"], e["config"])].append(e)
    per_mc_f: dict = {b: {} for b in betas}
    for (m, c), items in by_mc.items():
        tp = sum(x["tp"] for x in items)
        fp = sum(x["fp"] for x in items)
        fn = sum(x["fn"] for x in items)
        for b in betas:
            _, _, f = prf(tp, fp, fn, beta=b)
            per_mc_f[b][(m, c)] = f
    result: dict = {}
    for b in betas:
        by_config: dict = defaultdict(list)
        for (m, c), f in per_mc_f[b].items():
            by_config[c].append(f)
        result[b] = {c: round(mean(fs), 4) for c, fs in by_config.items()}
    return result


def repo_breakdown(entries: list[dict]) -> dict:
    by_repo_mc: dict = defaultdict(lambda: defaultdict(list))
    for e in entries:
        by_repo_mc[e["repo"]][(e["model"], e["config"])].append(e)
    result = {}
    for repo, mc_dict in by_repo_mc.items():
        summaries = {mc: summarize_group(es) for mc, es in mc_dict.items()}
        best_mc, best_s = max(summaries.items(), key=lambda x: x[1]["f2"])
        result[repo] = {
            "best_model": best_mc[0], "best_config": best_mc[1],
            "best_f2": best_s["f2"],
        }
    return result


def _vendor_of(mid: str) -> str:
    if mid.startswith("claude"):
        return "Anthropic"
    if mid.startswith("gpt") or mid == "o3":
        return "OpenAI"
    if mid.startswith("gemini"):
        return "Google"
    return "unknown"


def repo_vendor_breakdown(entries: list[dict]) -> dict:
    by_rv_mc: dict = defaultdict(lambda: defaultdict(list))
    for e in entries:
        by_rv_mc[(e["repo"], _vendor_of(e["model"]))][(e["model"], e["config"])].append(e)
    result = {}
    for (repo, vendor), mc_dict in by_rv_mc.items():
        summaries = {mc: summarize_group(es) for mc, es in mc_dict.items()}
        if not summaries:
            continue
        best_mc, best_s = max(summaries.items(), key=lambda x: x[1]["f2"])
        result[(repo, vendor)] = {
            "best_model": best_mc[0], "best_config": best_mc[1],
            "best_f2": best_s["f2"],
        }
    return result


def categorical_breakdown(entries: list[dict]) -> dict:
    by_cat_mc: dict = defaultdict(lambda: defaultdict(list))
    for e in entries:
        by_cat_mc[e["category"]][(e["model"], e["config"])].append(e)
    result = {}
    for cat, mc_dict in by_cat_mc.items():
        summaries = {mc: summarize_group(es) for mc, es in mc_dict.items()}
        best_mc, best_s = max(summaries.items(), key=lambda x: x[1]["f2"])
        n_items = len({e["item"] for e in entries if e["category"] == cat})
        result[cat] = {
            "best_model": best_mc[0], "best_config": best_mc[1],
            "best_f2": best_s["f2"], "n_items": n_items,
        }
    return result


def latex_categorical(cat_breakdown: dict) -> str:
    from collections import Counter
    if not cat_breakdown:
        return "% no data\n"
    winners = Counter(v["best_model"] for v in cat_breakdown.values())
    n_cats = len(cat_breakdown)
    perfect_cats = [c for c, v in cat_breakdown.items() if v["best_f1"] >= 0.9995]
    hardest = min(cat_breakdown.items(), key=lambda x: x[1]["best_f1"])
    n_min = min(v["n_items"] for v in cat_breakdown.values())
    n_max = max(v["n_items"] for v in cat_breakdown.values())
    winner_str = "，".join(
        f"{MODEL_LABEL.get(m, m)} ({n} 種別)" for m, n in winners.most_common()
    )
    lines = [
        f"バグ種別ごとの $F_1$ 首位を集計すると，全 {n_cats} 種別で勝者となるのは "
        f"{winner_str} であり，"
        r"種別に応じて最適な (モデル, 構成) が入れ替わることを示す．",
    ]
    if perfect_cats:
        cats_str = "・".join(CATEGORY_LABEL.get(c, c) for c in perfect_cats)
        lines.append(
            f"種別別 best $F_1$ は {cats_str} の {len(perfect_cats)} 種で 1.000 に達する一方，"
            f"{CATEGORY_LABEL.get(hardest[0], hardest[0])} は best でも "
            f"{hardest[1]['best_f1']:.3f} と全モデル共通の弱点として残った．"
        )
    else:
        best_cat = max(cat_breakdown.items(), key=lambda x: x[1]["best_f1"])
        lines.append(
            f"最も高い best $F_1$ は {CATEGORY_LABEL.get(best_cat[0], best_cat[0])} の "
            f"{best_cat[1]['best_f1']:.3f}，最も低いのは "
            f"{CATEGORY_LABEL.get(hardest[0], hardest[0])} の "
            f"{hardest[1]['best_f1']:.3f} である．"
        )
    lines.append(
        f"種別あたりの標本数は {n_min}〜{n_max} 件と小さく個別順位は暫定的だが，"
        r"RQ3 に対する予備知見として, 種別に応じた構成の最適性がベンダに直交して現れる傾向が示唆される．"
    )
    return "\n".join(lines) + "\n"


REPO_LABEL = {
    "fastapi": "Python (fastapi)",
    "valibot": "TypeScript (valibot)",
    "chi": "Go (chi)",
    "pgrust": "Rust (pgrust)",
}


def latex_macros(all_by_mc: dict, entries: list[dict], cat_breakdown: dict,
                 repo_bd: dict | None = None,
                 boot_ci: dict | None = None) -> str:
    from collections import Counter

    def cmd(name: str, value) -> str:
        return f"\\newcommand{{\\{name}}}{{{value}}}"

    def dollars(v: float) -> str:
        return f"\\${v:.4f}"

    lines = [
        "% Auto-generated by scripts/analyze.py. DO NOT EDIT.",
        "% Reference macros with trailing {} in body text to preserve spacing:",
        "%   e.g. \\bestModel{} で ... , \\nModels{} 種のモデル",
        "",
    ]

    def vendor_of(mid: str) -> str:
        if mid.startswith("claude"):
            return "anthropic"
        if mid.startswith("gpt") or mid == "o3":
            return "openai"
        if mid.startswith("gemini"):
            return "google"
        return "unknown"

    n_models = len({e["model"] for e in entries})
    n_configs = len({e["config"] for e in entries})
    n_items = len({e["item"] for e in entries})
    n_combos = len(entries)
    n_vendors = len({vendor_of(e["model"]) for e in entries})
    total_spend = sum(e["cost_usd"] for e in entries)

    lines += [
        "% ==== Experiment scale ====",
        cmd("nModels", n_models),
        cmd("nConfigs", n_configs),
        cmd("nItems", n_items),
        cmd("nCombos", n_combos),
        cmd("nVendors", n_vendors),
        cmd("totalSpend", f"\\${total_spend:.2f}"),
        "",
    ]

    if all_by_mc:
        best_mc, best_s = max(all_by_mc.items(), key=lambda x: x[1]["f2"])
        if boot_ci and best_mc in boot_ci:
            lines += [
                "% ==== Bootstrap 95% CI for best combo ====",
                cmd("bestCIlo", f"{boot_ci[best_mc]['ci_lo']:.3f}"),
                cmd("bestCIhi", f"{boot_ci[best_mc]['ci_hi']:.3f}"),
                "",
            ]
            best_single_mc = None
            best_single_f2 = -1.0
            for (m, c), s in all_by_mc.items():
                if c == "single" and s["f2"] > best_single_f2:
                    best_single_mc, best_single_f2 = (m, c), s["f2"]
            if best_single_mc and best_single_mc in boot_ci:
                lines += [
                    "% ==== Bootstrap 95% CI for best Single combo ====",
                    cmd("bestSingleModel",
                        MODEL_LABEL.get(best_single_mc[0], best_single_mc[0])),
                    cmd("bestSingleFtwo", f"{all_by_mc[best_single_mc]['f2']:.3f}"),
                    cmd("bestSingleCIlo",
                        f"{boot_ci[best_single_mc]['ci_lo']:.3f}"),
                    cmd("bestSingleCIhi",
                        f"{boot_ci[best_single_mc]['ci_hi']:.3f}"),
                    "",
                ]
        cheapest = min(all_by_mc.items(), key=lambda x: x[1]["cost_mean"])
        priciest = max(all_by_mc.items(), key=lambda x: x[1]["cost_mean"])
        spread = (priciest[1]["cost_mean"] / cheapest[1]["cost_mean"]
                  if cheapest[1]["cost_mean"] else 0)
        lines += [
            "% ==== Best F2 combo ====",
            cmd("bestModel", MODEL_LABEL.get(best_mc[0], best_mc[0])),
            cmd("bestConfig", CONFIG_LABEL.get(best_mc[1], best_mc[1])),
            cmd("bestFtwo", f"{best_s['f2']:.3f}"),
            cmd("bestCost", dollars(best_s["cost_mean"])),
            "",
            "% ==== Cost spread ====",
            cmd("cheapestCost", dollars(cheapest[1]["cost_mean"])),
            cmd("priciestCost", dollars(priciest[1]["cost_mean"])),
            cmd("costSpread", f"{spread:.0f}"),
            "",
        ]

        per_model_best_cfg = {}
        for m in MODEL_ORDER:
            cfgs = {c: all_by_mc[(m, c)]["f2"] for c in CONFIG_ORDER
                    if (m, c) in all_by_mc}
            if cfgs:
                per_model_best_cfg[m] = max(cfgs, key=lambda c: cfgs[c])
        lines += [
            "% ==== Per-model best-config wins ====",
            cmd("modelMultiWins",
                sum(1 for c in per_model_best_cfg.values() if c == "multi")),
            cmd("modelAdvWins",
                sum(1 for c in per_model_best_cfg.values() if c == "adversarial")),
            cmd("modelSingleWins",
                sum(1 for c in per_model_best_cfg.values() if c == "single")),
            cmd("modelParWins",
                sum(1 for c in per_model_best_cfg.values() if c == "parallel")),
            "",
        ]

        by_config: dict = defaultdict(list)
        for (_, c), s in all_by_mc.items():
            by_config[c].append(s)
        lines.append("% ==== Per-config mean F2 / cost ====")
        for c in CONFIG_ORDER:
            if c not in by_config:
                continue
            mf = mean(s["f2"] for s in by_config[c])
            mc = mean(s["cost_mean"] for s in by_config[c])
            lines.append(cmd(f"{c}MeanF", f"{mf:.3f}"))
            lines.append(cmd(f"{c}MeanCost", dollars(mc)))
        lines.append("")

        by_model: dict = defaultdict(list)
        for (m, c), s in all_by_mc.items():
            by_model[m].append((c, s))
        dominated_models = []
        for m, cfg_list in by_model.items():
            all_dominated = True
            for _, s in cfg_list:
                beaten = False
                for (m2, _), s2 in all_by_mc.items():
                    if m2 == m:
                        continue
                    if (s2["cost_mean"] <= s["cost_mean"] and s2["f2"] >= s["f2"]
                            and (s2["cost_mean"] < s["cost_mean"] or s2["f2"] > s["f2"])):
                        beaten = True
                        break
                if not beaten:
                    all_dominated = False
                    break
            if all_dominated:
                dominated_models.append(m)
        dominated_labels = "，".join(MODEL_LABEL.get(m, m) for m in dominated_models)
        lines += [
            "% ==== Pareto-dominated models ====",
            cmd("dominatedModels", dominated_labels if dominated_labels else "（該当なし）"),
            cmd("dominatedCount", len(dominated_models)),
            "",
        ]

    if repo_bd:
        lines.append("% ==== Per-repo (language) best (model / config) ====")
        for repo in ["fastapi", "valibot", "chi", "pgrust"]:
            if repo not in repo_bd:
                continue
            v = repo_bd[repo]
            label = (f"{MODEL_LABEL.get(v['best_model'], v['best_model'])} / "
                     f"{CONFIG_LABEL.get(v['best_config'], v['best_config'])}")
            lines.append(cmd(f"bestBy{repo.capitalize()}", label))
            lines.append(cmd(f"bestBy{repo.capitalize()}F", f"{v['best_f2']:.3f}"))
        lines.append("")

    if cat_breakdown:
        winners = Counter(v["best_model"] for v in cat_breakdown.values())
        n_cats = len(cat_breakdown)
        perfect_cats = [c for c, v in cat_breakdown.items() if v["best_f2"] >= 0.9995]
        hardest = min(cat_breakdown.items(), key=lambda x: x[1]["best_f2"])
        n_min = min(v["n_items"] for v in cat_breakdown.values())
        n_max = max(v["n_items"] for v in cat_breakdown.values())
        winner_str = "，".join(
            f"{MODEL_LABEL.get(m, m)} ({n} 種別)" for m, n in winners.most_common()
        )
        lines += [
            "% ==== Category breakdown ====",
            cmd("nCategories", n_cats),
            cmd("catWinners", winner_str),
            cmd("perfectCats",
                "・".join(CATEGORY_LABEL.get(c, c) for c in perfect_cats)
                if perfect_cats else "（該当なし）"),
            cmd("perfectCount", len(perfect_cats)),
            cmd("hardestCat", CATEGORY_LABEL.get(hardest[0], hardest[0])),
            cmd("hardestBestFtwo", f"{hardest[1]['best_f2']:.3f}"),
            cmd("catNmin", n_min),
            cmd("catNmax", n_max),
            "",
        ]

    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
