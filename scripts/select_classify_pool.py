#!/usr/bin/env python3
"""Select candidates for LLM classification from data/mining/*.json into data/mining/classify_pool.json."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MINING_DIR = ROOT / "data" / "mining"

POST_CUTOFF = "2026-01-01"

PLANS = {
    "fastapi": {"post": "all", "pre_recent": 30, "spread": 0},
    "valibot": {"post": "all", "pre_recent": 10, "spread": 0},
    "chi": {"post": "all", "pre_recent": 30, "spread": 0},
    "pgrust": {"post": "none", "pre_recent": 0, "spread": 60},
}


def evenly_spaced(items: list, n: int) -> list:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def main() -> None:
    pool = []
    for repo, plan in PLANS.items():
        data = json.loads((MINING_DIR / f"{repo}.json").read_text())
        passed = sorted(
            (c for c in data["candidates"] if c["passes_filter"]),
            key=lambda c: c["date"], reverse=True,
        )
        post = [c for c in passed if c["date"] >= POST_CUTOFF]
        pre = [c for c in passed if c["date"] < POST_CUTOFF]

        selected = []
        if plan["post"] == "all":
            selected += post
        selected += pre[: plan["pre_recent"]]
        if plan["spread"]:
            selected += evenly_spaced(passed, plan["spread"])

        seen = set()
        for c in selected:
            if c["sha"] in seen:
                continue
            seen.add(c["sha"])
            pool.append({
                "repo": repo,
                "sha": c["sha"],
                "date": c["date"],
                "subject": c["subject"],
                "source_lines": c["source_lines"],
                "source_files": c["source_files"],
                "has_test": c["has_test"],
                "post_cutoff": c["date"] >= POST_CUTOFF,
            })

    out = MINING_DIR / "classify_pool.json"
    out.write_text(json.dumps({"post_cutoff_boundary": POST_CUTOFF, "pool": pool},
                              ensure_ascii=False, indent=2) + "\n")
    by_repo = {}
    for item in pool:
        by_repo.setdefault(item["repo"], [0, 0])
        by_repo[item["repo"]][0] += 1
        by_repo[item["repo"]][1] += item["post_cutoff"]
    for repo, (total, post_n) in by_repo.items():
        print(f"{repo:10s} pool={total:3d} (post={post_n}, pre={total - post_n})")
    print(f"{'TOTAL':10s} pool={len(pool)}")


if __name__ == "__main__":
    main()
