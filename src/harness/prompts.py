"""LLM prompt definitions used by review configurations.

Kept separate from `review.py` so prompt edits are diff-visible and don't
mix with orchestration flow. All strings imported by `review.py`.
"""

FINDING_SCHEMA = """Output ONLY a JSON array. Each element is a finding:
{
  "file": "<repo-relative path exactly as in the diff>",
  "line_start": <int, line number in the NEW file>,
  "line_end": <int, inclusive>,
  "severity": "high" | "medium" | "low",
  "category": "logic" | "concurrency" | "api-misuse" | "error-handling" | "type-safety" | "security" | "resource-leak" | "other",
  "summary": "<one sentence>"
}
If the change is clean, output []. No prose, no code fences — just JSON."""

BASE_SYSTEM = (
    "You are a senior software engineer reviewing a pull request for defects the "
    "change would introduce (not stylistic nitpicks). Be precise; do not pad. "
    + FINDING_SCHEMA
)

ASPECTS = {
    "correctness": "Focus strictly on correctness defects: wrong logic, off-by-one, missing return, wrong branch, dead code that hides bugs.",
    "concurrency": "Focus strictly on concurrency and lifecycle defects: races, deadlocks, missing synchronization, resource leaks, use-after-free.",
    "api-misuse": "Focus strictly on API and contract misuse: wrong argument, missed nil/None/error, deprecated call, spec violation, type-safety issues.",
    "security": "Focus strictly on security defects: injection, auth bypass, unchecked input, memory safety, sensitive data leakage.",
}

VERIFY_SYSTEM = (
    "You verify a claimed defect against the diff. Default to REFUTED unless the "
    "diff clearly demonstrates the bug. Output ONLY a JSON object: "
    '{"verdict": "confirmed" | "refuted", "reason": "<one sentence>"}. '
    "No prose, no code fences."
)
