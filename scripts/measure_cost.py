#!/usr/bin/env python3
"""Measure per-run cost: N benchmark items x single-reviewer config x one model.

Usage: uv run scripts/measure_cost.py --model claude-sonnet-5 --items 3
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from harness.ledger import Ledger, PriceTable
from harness.llm import Client

ROOT = Path(__file__).resolve().parent.parent

SYSTEM = """You are a senior software engineer reviewing a pull request.
Identify any defects the change would introduce. For each finding, give:
- file and line range
- severity (high/medium/low)
- a one-paragraph explanation
If you find no defects, say so explicitly. Be precise; do not pad."""


def pr_prompt(pkg: dict) -> str:
    return (f"# Pull request: {pkg['pr_title']}\n\n{pkg['pr_description']}\n\n"
            f"# Diff\n```diff\n{pkg['pr_diff']}\n```")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--items", type=int, default=3)
    parser.add_argument("--budget-usd", type=float, default=2.0)
    args = parser.parse_args()

    run_id = f"measure-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = ROOT / "runs" / run_id
    ledger = Ledger(run_dir, PriceTable())

    packages = sorted((ROOT / "data" / "benchmark" / "v0" / "prs").glob("*.json"))[: args.items]
    per_model = {}
    for model in args.models:
        client = Client(ledger, f"{run_id}:{model}", budget_usd=args.budget_usd)
        results = []
        for path in packages:
            pkg = json.loads(path.read_text())
            r = client.chat(model=model, system=SYSTEM, user=pr_prompt(pkg),
                            context={"item": pkg["id"], "config": "single", "model": model})
            results.append({"item": pkg["id"], "usage": r.usage, "cost_usd": r.cost_usd,
                            "latency_ms": None})
            print(f"{model:22s} {pkg['id']:22s} in={r.usage['input_tokens']:6d} "
                  f"out={r.usage['output_tokens']:6d} ${r.cost_usd:.4f}")
            (run_dir / f"{model}--{pkg['id']}.review.txt").write_text(r.text)
        per_model[model] = {
            "total_usd": sum(x["cost_usd"] for x in results),
            "mean_usd": sum(x["cost_usd"] for x in results) / len(results),
            "mean_in": sum(x["usage"]["input_tokens"] for x in results) / len(results),
            "mean_out": sum(x["usage"]["output_tokens"] for x in results) / len(results),
            "results": results,
        }

    print(f"\n{'model':22s} {'mean/item':>12s} {'mean in':>10s} {'mean out':>10s}")
    for m, s in per_model.items():
        print(f"{m:22s} ${s['mean_usd']:11.4f} {s['mean_in']:10.0f} {s['mean_out']:10.0f}")
    print(f"\ntotal spent: ${ledger.spent_usd():.4f}")

    (run_dir / "summary.json").write_text(json.dumps(
        {"run_id": run_id, "items": args.items, "per_model": per_model}, ensure_ascii=False, indent=2) + "\n")


def project(mean_per_item: float, items: int, configs_multiplier: float,
            models: int, budgets: int) -> float:
    return mean_per_item * items * configs_multiplier * models * budgets


if __name__ == "__main__":
    main()
