#!/usr/bin/env python3
"""Build buggy-PR packages from selected fix commits into data/benchmark/v0/prs/.

For each selected fix commit F: base = state with F applied, PR diff = reverse of
F's source-file changes (tests untouched so the existing suite remains a failing
oracle against the buggy state), ground truth = hunk positions of the reverse diff.
"""

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOS_DIR = ROOT / "repos"
OUT_DIR = ROOT / "data" / "benchmark" / "v0" / "prs"

HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def git(repo: str, *args: str) -> str:
    return subprocess.run(["git", "-C", str(REPOS_DIR / repo), *args],
                          capture_output=True, text=True, check=True).stdout


def source_files(item: dict) -> list:
    return [f["path"] for f in item["files"] if f["kind"] == "source"]


def build(item: dict) -> dict:
    repo, sha = item["repo"], item["sha"]
    files = source_files(item)
    reverse_diff = git(repo, "diff", sha, f"{sha}^", "--", *files)

    ground_truth = []
    current = None
    for line in reverse_diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif m := HUNK_RE.match(line):
            start, length = int(m.group(1)), int(m.group(2) or "1")
            ground_truth.append({"file": current, "start": start, "end": start + max(length - 1, 0)})

    return {
        "id": f"{repo}-{sha[:10]}",
        "repo": repo,
        "fix_sha": sha,
        "base_sha": sha,
        "language": {"fastapi": "python", "valibot": "typescript", "chi": "go", "pgrust": "rust"}[repo],
        "category": item["category"],
        "severity": item["severity"],
        "post_cutoff": item["post_cutoff"],
        "bug_summary": item["summary"],
        "pr_diff": reverse_diff,
        "ground_truth": ground_truth,
        "pr_title": None,
        "pr_description": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--ids", nargs="*", default=None)
    args = parser.parse_args()

    selection = json.loads((ROOT / "data" / "benchmark" / "v0" / "selection.json").read_text())["items"]
    mined = {}
    for repo_file in (ROOT / "data" / "mining").glob("*.json"):
        data = json.loads(repo_file.read_text())
        if "candidates" not in data:
            continue
        for c in data["candidates"]:
            mined[c["sha"]] = c

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    built = 0
    for item in selection:
        merged = {**mined[item["sha"]], **item}
        pkg = build(merged)
        if args.ids and pkg["id"] not in args.ids:
            continue
        out_path = OUT_DIR / f"{pkg['id']}.json"
        if out_path.exists():
            prev = json.loads(out_path.read_text())
            pkg["pr_title"] = prev.get("pr_title")
            pkg["pr_description"] = prev.get("pr_description")
        out_path.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n")
        print(f"{pkg['id']:22s} files={len(source_files(merged))} hunks={len(pkg['ground_truth'])} "
              f"diff={len(pkg['pr_diff'].splitlines())}L")
        built += 1
        if args.limit and built >= args.limit:
            break
    print(f"built {built} packages -> {OUT_DIR}")


if __name__ == "__main__":
    main()
