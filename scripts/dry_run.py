#!/usr/bin/env python3
"""Dry-run the 4 configs on 2 items with the cheapest model to validate the harness.

Verifies: config runners return findings, ledger tracks cost, JSON parse works,
scorer runs. Cheap: ~$0.02 total.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from harness.eval import aggregate, score_item
from harness.ledger import Ledger, PriceTable
from harness.llm import Client
from harness.review import CONFIGS

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    model = "claude-haiku-4-5"
    run_id = f"dryrun-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = ROOT / "runs" / run_id
    ledger = Ledger(run_dir, PriceTable())

    items = []
    for p in sorted((ROOT / "data" / "benchmark" / "v0" / "prs").glob("*.json"))[:2]:
        items.append(json.loads(p.read_text()))

    print(f"model={model}  items={len(items)}  configs={list(CONFIGS)}")
    print(f"{'config':12s} {'item':22s} {'passes':>6s} {'cost':>8s} {'tp':>3s} {'fp':>3s} {'fn':>3s} {'trunc':>5s}")
    all_scores = {c: [] for c in CONFIGS}
    for cfg_name, runner in CONFIGS.items():
        client = Client(ledger, f"{run_id}:{cfg_name}", budget_usd=5.0)
        for pkg in items:
            result = runner(pkg, client, model)
            score = score_item(result.findings, pkg["ground_truth"])
            score.item_id = pkg["id"]
            all_scores[cfg_name].append(score)
            print(f"{cfg_name:12s} {pkg['id']:22s} {result.passes:6d} ${result.cost_usd:7.4f} "
                  f"{score.tp:3d} {score.fp:3d} {score.fn:3d} {str(result.truncated):>5s}")

    print(f"\n{'config':12s} {'TP':>4s} {'FP':>4s} {'FN':>4s} {'prec':>6s} {'rec':>6s} {'F1':>6s}")
    for cfg_name, scores in all_scores.items():
        agg = aggregate(scores)
        print(f"{cfg_name:12s} {agg['tp']:4d} {agg['fp']:4d} {agg['fn']:4d} "
              f"{agg['precision']:6.2f} {agg['recall']:6.2f} {agg['f1']:6.2f}")

    print(f"\ntotal spent: ${ledger.spent_usd():.4f}")


if __name__ == "__main__":
    main()
