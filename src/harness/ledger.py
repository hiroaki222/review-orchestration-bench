"""Append-only cost ledger.

Every API call is recorded with the provider-reported usage verbatim plus a
deterministic cost computed from the committed price table, so total spend can
be re-derived offline from the ledger alone.
"""

import hashlib
import json
import time
import uuid
from pathlib import Path

PRICES_PATH = Path(__file__).parent / "prices.json"


class PriceTable:
    def __init__(self, path: Path = PRICES_PATH):
        self.path = path
        self.raw = path.read_text()
        data = json.loads(self.raw)
        if data["retrieved_at"] is None:
            raise RuntimeError(
                f"{path}: retrieved_at is null. Fill unit prices from the provider "
                "pricing pages and set retrieved_at (YYYY-MM-DD) before running."
            )
        self.retrieved_at = data["retrieved_at"]
        self.models = data["models"]
        self.sha256 = hashlib.sha256(self.raw.encode()).hexdigest()

    def cost_usd(self, model: str, usage: dict) -> dict:
        p = self.models[model]
        for field in ("input", "output"):
            if p[field] is None:
                raise RuntimeError(f"{self.path}: price '{field}' for {model} is null")
        per = {
            "input": usage.get("input_tokens", 0) * p["input"] / 1e6,
            "output": usage.get("output_tokens", 0) * p["output"] / 1e6,
            "cache_read": usage.get("cache_read_tokens", 0) * (p.get("cache_read") or 0) / 1e6,
            "cache_write": usage.get("cache_write_tokens", 0) * (p.get("cache_write") or 0) / 1e6,
        }
        per["total"] = sum(per.values())
        return per


class Ledger:
    def __init__(self, run_dir: Path, price_table: PriceTable):
        self.path = run_dir / "ledger.jsonl"
        self.prices = price_table
        run_dir.mkdir(parents=True, exist_ok=True)

    def record(self, *, run_id: str, provider: str, model: str,
               usage_raw: dict, usage_normalized: dict, latency_ms: int,
               context: dict | None = None) -> dict:
        entry = {
            "call_id": uuid.uuid4().hex,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "run_id": run_id,
            "provider": provider,
            "model": model,
            "usage_raw": usage_raw,
            "usage": usage_normalized,
            "cost_usd": self.prices.cost_usd(model, usage_normalized),
            "price_table": {"retrieved_at": self.prices.retrieved_at, "sha256": self.prices.sha256},
            "latency_ms": latency_ms,
            "context": context or {},
        }
        with self.path.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def spent_usd(self, run_id: str | None = None) -> float:
        if not self.path.exists():
            return 0.0
        total = 0.0
        with self.path.open() as f:
            for line in f:
                e = json.loads(line)
                if run_id is None or e["run_id"] == run_id:
                    total += e["cost_usd"]["total"]
        return total
