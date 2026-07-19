#!/usr/bin/env python3
"""Measure per-run cost: N benchmark items x single-reviewer config x one model.

Usage: uv run scripts/measure_cost.py --model claude-sonnet-4-5 --items 3
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
    parser.add_argument("--model", required=True)
    parser.add_argument("--items", type=int, default=3)
    parser.add_argument("--budget-usd", type=float, default=2.0)
    args = parser.parse_args()

    run_id = f"measure-{args.model}-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = ROOT / "runs" / run_id
    ledger = Ledger(run_dir, PriceTable())
    client = Client(ledger, run_id, budget_usd=args.budget_usd)

    packages = sorted((ROOT / "data" / "benchmark" / "v0" / "prs").glob("*.json"))[: args.items]
    results = []
    for path in packages:
        pkg = json.loads(path.read_text())
        r = client.chat(model=args.model, system=SYSTEM, user=pr_prompt(pkg),
                        context={"item": pkg["id"], "config": "single"})
        results.append({"item": pkg["id"], "usage": r.usage, "cost_usd": r.cost_usd})
        print(f"{pkg['id']:24s} in={r.usage['input_tokens']:6d} out={r.usage['output_tokens']:6d} "
              f"${r.cost_usd:.4f}")
        (run_dir / f"{pkg['id']}.review.txt").write_text(r.text)

    total = sum(x["cost_usd"] for x in results)
    mean = total / len(results)
    print(f"\ntotal ${total:.4f}, mean ${mean:.4f}/run")
    print(f"projection: 85 items x 4 configs x 4 models x 2 budgets ~ ${mean * 85 * 4 * 4 * 2:,.0f} "
          f"(single-config extrapolation; parallel/multi-run cost more)")
    (run_dir / "summary.json").write_text(json.dumps(
        {"run_id": run_id, "model": args.model, "results": results,
         "total_usd": total, "mean_usd": mean}, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
