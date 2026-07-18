#!/usr/bin/env python3
"""Mine bug-fix commit candidates from cloned target repos into data/mining/<repo>.json."""

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOS_DIR = ROOT / "repos"
OUT_DIR = ROOT / "data" / "mining"

MAX_SOURCE_LINES = 100
MAX_SOURCE_FILES = 5

FIX = r"fix(?:es|ed|ing)?"
BUG = r"bug(?:s|gy|fix(?:es)?)?"

CONFIGS = {
    "fastapi": {
        "subject_include": rf"(?i)^🐛|\b(?:{FIX}|{BUG})\b",
        "subject_exclude": r"(?i)\b(typo|revert|bump|translation|changelog)\b",
        "source": r"^fastapi/.*\.py$",
        "test": r"^tests/.*\.py$",
    },
    "valibot": {
        "subject_include": rf"(?i)\b(?:{FIX}|{BUG})\b",
        "subject_exclude": r"(?i)\b(typo|revert|bump|changelog|format)\b",
        "source": r"^(library|packages/[^/]+)/src/.*(?<!\.test)(?<!\.test-d)\.ts$",
        "test": r"^(library|packages/[^/]+)/src/.*\.test(-d)?\.ts$",
    },
    "chi": {
        "subject_include": rf"(?i)\b(?:{FIX}|{BUG}|panic(?:s|ked)?|rac(?:e|es|y)|nil|leak(?:s|ed|y)?|incorrect(?:ly)?|wrong(?:ly)?)\b",
        "subject_exclude": r"(?i)\b(typo|revert|bump)\b",
        "source": r"^(?!.*_test\.go$).*\.go$",
        "test": r".*_test\.go$",
    },
    "pgrust": {
        "subject_include": rf"(?i)\b(?:{FIX}|{BUG}|incorrect(?:ly)?|wrong(?:ly)?|panic(?:s|ked)?|overflow(?:s|ed)?|crash(?:es|ed|ing)?)\b",
        "subject_exclude": r"(?i)\b(typo|revert|ported?|porting|vendored?|vendor|import)\b",
        "source": r"^crates/(?!.*/tests?/).*\.rs$",
        "test": r"^crates/.*/tests?/.*\.rs$",
    },
}

WINDOWS = {"since_2026_01": "2026-01-01", "since_2026_04": "2026-04-01", "since_2026_06": "2026-06-01"}

RENAME_RE = re.compile(r"\{([^{}]*) => ([^{}]*)\}")


def normalize_path(path: str) -> str:
    if " => " in path and not RENAME_RE.search(path):
        return path.split(" => ")[-1]
    return RENAME_RE.sub(lambda m: m.group(2), path).replace("//", "/")


def mine(repo: str, cfg: dict) -> dict:
    inc = re.compile(cfg["subject_include"])
    exc = re.compile(cfg["subject_exclude"])
    src = re.compile(cfg["source"])
    tst = re.compile(cfg["test"])

    repo_head = subprocess.run(
        ["git", "-C", str(REPOS_DIR / repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    out = subprocess.run(
        ["git", "-C", str(REPOS_DIR / repo), "log", "--no-merges", "--numstat",
         "--pretty=format:\x1e%H\x1f%aI\x1f%s"],
        capture_output=True, text=True, check=True,
    ).stdout

    candidates = []
    stats = {"total_commits": 0, "subject_matched": 0}
    for record in out.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        stats["total_commits"] += 1
        header, *file_lines = record.split("\n")
        sha, date, subject = header.split("\x1f")
        if not inc.search(subject) or exc.search(subject):
            continue
        stats["subject_matched"] += 1

        files = []
        for line in file_lines:
            if not line.strip():
                continue
            add, delete, path = line.split("\t", 2)
            path = normalize_path(path)
            kind = "test" if tst.match(path) else "source" if src.match(path) else "other"
            lines = (0 if add == "-" else int(add)) + (0 if delete == "-" else int(delete))
            files.append({"path": path, "lines": lines, "kind": kind})

        source_files = [f for f in files if f["kind"] == "source"]
        source_lines = sum(f["lines"] for f in source_files)
        passes = (
            len(source_files) >= 1
            and len(source_files) <= MAX_SOURCE_FILES
            and source_lines <= MAX_SOURCE_LINES
        )
        candidates.append({
            "sha": sha,
            "date": date,
            "subject": subject,
            "source_files": len(source_files),
            "source_lines": source_lines,
            "has_test": any(f["kind"] == "test" for f in files),
            "files": files,
            "passes_filter": passes,
        })

    passed = [c for c in candidates if c["passes_filter"]]
    summary = {
        **stats,
        "candidates": len(candidates),
        "passed": len(passed),
        "passed_with_test": sum(1 for c in passed if c["has_test"]),
        **{w: sum(1 for c in passed if c["date"] >= d) for w, d in WINDOWS.items()},
    }
    return {"repo": repo, "repo_head": repo_head,
            "filters": {"max_source_lines": MAX_SOURCE_LINES, "max_source_files": MAX_SOURCE_FILES},
            "config": cfg, "summary": summary, "candidates": candidates}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for repo, cfg in CONFIGS.items():
        result = mine(repo, cfg)
        out_path = OUT_DIR / f"{repo}.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        s = result["summary"]
        print(f"{repo:10s} matched={s['subject_matched']:5d} passed={s['passed']:4d} "
              f"with_test={s['passed_with_test']:4d} "
              f"2026-01+={s['since_2026_01']:4d} 04+={s['since_2026_04']:4d} 06+={s['since_2026_06']:4d}")


if __name__ == "__main__":
    main()
