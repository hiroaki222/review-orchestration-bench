#!/usr/bin/env python3
"""Run the SIG-AGI pilot: (models) x (configs) x (items) grid.

Deterministic across resumes: results already in --out are skipped so partial
runs can pick up where they left off. Progress lines flush immediately so
`zellij action dump-screen` shows live status.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from harness.eval import score_item
from harness.ledger import Ledger, PriceTable
from harness.llm import Client
from harness.review import CONFIGS

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_MODELS = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-5", "claude-fable-5",
                  "gpt-5-mini", "gpt-5", "gpt-5.6-luna", "gpt-5.6-terra", "o3",
                  "gemini-3.5-flash-lite", "gemini-3.6-flash", "gemini-3.1-pro-preview"]
DEFAULT_CONFIGS = ["single", "parallel", "adversarial", "multi"]
DEFAULT_QUOTA = {"fastapi": 9, "valibot": 7, "chi": 5, "pgrust": 9}


def load_items(quota: dict) -> list[dict]:
    sel = json.loads((ROOT / "data" / "benchmark" / "v0" / "selection.json").read_text())["items"]
    by_repo: dict[str, list] = {r: [] for r in quota}
    for m in sel:
        if m["repo"] in by_repo and len(by_repo[m["repo"]]) < quota[m["repo"]]:
            by_repo[m["repo"]].append(m)
    picked = []
    for r in quota:
        for m in by_repo[r]:
            path = ROOT / "data" / "benchmark" / "v0" / "prs" / f"{r}-{m['sha'][:10]}.json"
            picked.append(json.loads(path.read_text()))
    return picked


def load_done(out_path: Path) -> set[tuple]:
    if not out_path.exists():
        return set()
    done = set()
    with out_path.open() as f:
        for line in f:
            e = json.loads(line)
            done.add((e["model"], e["config"], e["item"]))
    return done


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    p.add_argument("--configs", nargs="+", default=DEFAULT_CONFIGS)
    p.add_argument("--budget-per-item", type=float, default=0.30,
                   help="Per-item cost cap; a config truncates when it hits this.")
    p.add_argument("--run-name", default=None)
    args = p.parse_args()

    run_name = args.run_name or f"pilot-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = ROOT / "runs" / run_name
    out_dir = ROOT / "data" / "experiments" / "v0"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{run_name}.results.jsonl"

    ledger = Ledger(run_dir, PriceTable())
    items = load_items(DEFAULT_QUOTA)
    done = load_done(out_path)

    total_combos = len(args.models) * len(args.configs) * len(items)
    remaining = total_combos - len(done)
    print(f"run={run_name}  models={len(args.models)}  configs={len(args.configs)}  "
          f"items={len(items)}  combos={total_combos}  already_done={len(done)}  remaining={remaining}",
          flush=True)

    grand_start = time.monotonic()
    n_done = 0
    with out_path.open("a") as out_f:
        for model in args.models:
            for cfg_name in args.configs:
                runner = CONFIGS[cfg_name]
                run_id = f"{run_name}:{model}:{cfg_name}"
                client = Client(ledger, run_id, budget_usd=None)
                for pkg in items:
                    key = (model, cfg_name, pkg["id"])
                    if key in done:
                        continue
                    per_item_client = Client(ledger, f"{run_id}:{pkg['id']}",
                                             budget_usd=args.budget_per_item)
                    start = time.monotonic()
                    try:
                        result = runner(pkg, per_item_client, model)
                    except Exception as e:
                        print(f"ERR {model:20s} {cfg_name:12s} {pkg['id']:22s} "
                              f"{type(e).__name__}: {e}", flush=True)
                        continue
                    elapsed = time.monotonic() - start
                    score = score_item(result.findings, pkg["ground_truth"])
                    entry = {
                        "run": run_name, "model": model, "config": cfg_name,
                        "item": pkg["id"], "repo": pkg["repo"],
                        "category": pkg["category"], "post_cutoff": pkg["post_cutoff"],
                        "passes": result.passes, "truncated": result.truncated,
                        "parse_failures": result.parse_failures,
                        "n_findings": len(result.findings),
                        "n_ground_truth": len(pkg["ground_truth"]),
                        "tp": score.tp, "fp": score.fp, "fn": score.fn,
                        "cost_usd": result.cost_usd,
                        "elapsed_s": round(elapsed, 2),
                        "findings": [
                            {"file": f.file, "line_start": f.line_start,
                             "line_end": f.line_end, "severity": f.severity,
                             "category": f.category, "summary": f.summary}
                            for f in result.findings
                        ],
                    }
                    out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    out_f.flush()
                    n_done += 1
                    total_spent = ledger.spent_usd()
                    print(f"[{n_done:4d}/{remaining}] {model:20s} {cfg_name:12s} "
                          f"{pkg['id']:22s} passes={result.passes:2d} "
                          f"tp={score.tp} fp={score.fp} fn={score.fn} "
                          f"${result.cost_usd:.4f} ({elapsed:5.1f}s) "
                          f"cum=${total_spent:.3f}",
                          flush=True)

    elapsed_total = time.monotonic() - grand_start
    print(f"\ndone in {elapsed_total/60:.1f} min. total ledger spend: ${ledger.spent_usd():.4f}")
    print(f"results: {out_path}")


if __name__ == "__main__":
    main()
