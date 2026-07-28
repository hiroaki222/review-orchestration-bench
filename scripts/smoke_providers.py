#!/usr/bin/env python3
"""Smoke-test all 3 providers with a trivial prompt. Costs a few cents total.

Verifies: API auth works, usage fields parse, ledger records, cost > 0.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from harness.ledger import Ledger, PriceTable
from harness.llm import Client

ROOT = Path(__file__).resolve().parent.parent
MODELS = ["claude-haiku-4-5", "claude-sonnet-5", "gpt-5-mini", "gpt-5"]


def main() -> None:
    run_id = f"smoke-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir = ROOT / "runs" / run_id
    ledger = Ledger(run_dir, PriceTable())
    client = Client(ledger, run_id, budget_usd=1.0)

    for model in MODELS:
        try:
            r = client.chat(
                model=model,
                system="You are a terse assistant. Answer with exactly one short sentence.",
                user="Say the single word: pong",
                max_tokens=1024,
                context={"item": "smoke", "config": "smoke"},
            )
            print(f"OK   {model:24s} in={r.usage['input_tokens']:4d} out={r.usage['output_tokens']:4d} "
                  f"${r.cost_usd:.6f}  stop={r.stop_reason}  text={r.text!r}")
        except Exception as e:
            print(f"FAIL {model:24s} {type(e).__name__}: {e}")

    print(f"\ntotal spent: ${ledger.spent_usd(run_id):.6f}")
    print(f"ledger:      {run_dir / 'ledger.jsonl'}")


if __name__ == "__main__":
    main()
