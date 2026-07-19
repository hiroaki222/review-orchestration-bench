#!/usr/bin/env python3
"""Select the benchmark sample from classified candidates into data/benchmark/v0/selection.json.

Deterministic: post-cutoff candidates are taken first, remaining slots are
filled by category round-robin (rarest category first; within a category
test-accompanied commits first, then newer commits).
"""

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = {"fastapi": 25, "valibot": 20, "chi": 15, "pgrust": 25}


def stratified_pick(candidates: list, n: int) -> list:
    if len(candidates) <= n:
        return candidates
    by_cat = defaultdict(list)
    for c in candidates:
        by_cat[c["category"]].append(c)
    for cat in by_cat:
        by_cat[cat].sort(key=lambda c: (not c["has_test"], c["date"]), reverse=False)
        by_cat[cat].sort(key=lambda c: c["date"], reverse=True)
        by_cat[cat].sort(key=lambda c: not c["has_test"])
    order = sorted(by_cat, key=lambda cat: (len(by_cat[cat]), cat))
    picked = []
    while len(picked) < n:
        progressed = False
        for cat in order:
            if by_cat[cat] and len(picked) < n:
                picked.append(by_cat[cat].pop(0))
                progressed = True
        if not progressed:
            break
    return picked


def main() -> None:
    items = json.loads((ROOT / "data" / "mining" / "classified.json").read_text())["items"]
    injectable = [m for m in items if m["genuine"] and m["injectable"]]

    selection = []
    for repo, target in TARGETS.items():
        pool = [m for m in injectable if m["repo"] == repo]
        post = [m for m in pool if m["post_cutoff"]]
        pre = [m for m in pool if not m["post_cutoff"]]

        picked = stratified_pick(post, target)
        if len(picked) < target:
            picked += stratified_pick(pre, target - len(picked))
        selection += picked

        cats = Counter(m["category"] for m in picked)
        post_n = sum(1 for m in picked if m["post_cutoff"])
        print(f"{repo:10s} {len(picked):3d}/{target} post={post_n:3d} pre={len(picked)-post_n:3d} "
              f"with_test={sum(1 for m in picked if m['has_test']):3d} {dict(cats)}")

    out_dir = ROOT / "data" / "benchmark" / "v0"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "selection.json"
    out.write_text(json.dumps({
        "targets": TARGETS,
        "policy": "post-cutoff first, then pre-cutoff by category round-robin (rarest first, has_test first, newest first)",
        "items": selection,
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"\ntotal {len(selection)} -> {out}")


if __name__ == "__main__":
    main()
