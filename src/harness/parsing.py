"""Finding dataclass and JSON parsers for LLM response text.

Split from `review.py` so parsing utilities and the review-flow orchestration
are readable independently. `Finding` lives here because `parse_findings`
returns it and re-exporting via a third module would add noise.
"""

import json
import re
from dataclasses import dataclass


@dataclass
class Finding:
    file: str
    line_start: int
    line_end: int
    severity: str
    category: str
    summary: str

    def key(self) -> tuple:
        return (self.file, self.line_start, self.line_end, self.summary[:60])


_FENCED = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_findings(text: str) -> list[Finding] | None:
    if not text or not text.strip():
        return []
    candidate = text.strip()
    m = _FENCED.search(candidate)
    if m:
        candidate = m.group(1).strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("[")
        end = candidate.rfind("]")
        if start >= 0 and end > start:
            try:
                data = json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None
    if not isinstance(data, list):
        return None
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            out.append(Finding(
                file=str(item.get("file", "")),
                line_start=int(item.get("line_start", 0)),
                line_end=int(item.get("line_end", item.get("line_start", 0))),
                severity=str(item.get("severity", "medium")),
                category=str(item.get("category", "other")),
                summary=str(item.get("summary", "")),
            ))
        except (ValueError, TypeError):
            continue
    return out


def parse_verdict(text: str) -> bool | None:
    if not text or not text.strip():
        return None
    candidate = text.strip()
    m = _FENCED.search(candidate)
    if m:
        candidate = m.group(1).strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            return None
    v = data.get("verdict") if isinstance(data, dict) else None
    if v == "confirmed":
        return True
    if v == "refuted":
        return False
    return None
