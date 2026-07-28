"""Score predicted findings against ground-truth hunks.

A prediction is a TP iff its file matches a ground-truth hunk and its
[line_start, line_end] range overlaps (or is within a tolerance of) the hunk.
Each hunk can be matched by at most one prediction (first-match wins by
prediction order).
"""

from dataclasses import dataclass, field

from .review import Finding

LINE_TOLERANCE = 2


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int, tol: int = LINE_TOLERANCE) -> bool:
    return a_end + tol >= b_start and b_end + tol >= a_start


@dataclass
class ItemScore:
    item_id: str
    tp: int = 0
    fp: int = 0
    fn: int = 0
    matched_findings: list[int] = field(default_factory=list)


def score_item(findings: list[Finding], ground_truth: list[dict]) -> ItemScore:
    remaining = list(range(len(ground_truth)))
    tp = 0
    matched = []
    for i, f in enumerate(findings):
        hit = None
        for gi in remaining:
            g = ground_truth[gi]
            if f.file != g["file"]:
                continue
            if _overlaps(f.line_start, f.line_end, g["start"], g["end"]):
                hit = gi
                break
        if hit is not None:
            tp += 1
            matched.append(i)
            remaining.remove(hit)
    fp = len(findings) - tp
    fn = len(remaining)
    return ItemScore(item_id="", tp=tp, fp=fp, fn=fn, matched_findings=matched)


def aggregate(scores: list[ItemScore]) -> dict:
    tp = sum(s.tp for s in scores)
    fp = sum(s.fp for s in scores)
    fn = sum(s.fn for s in scores)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": prec, "recall": rec, "f1": f1,
            "items": len(scores)}
