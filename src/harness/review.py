"""Review-configuration implementations (single / parallel / adversarial / multi-run).

Each config exposes `run(pkg, client, model, budget_usd) -> ReviewResult`. The
budget is per-item; when the ledger records enough spend to hit it, remaining
passes are skipped and the partial result is returned.
"""

from dataclasses import dataclass, field
from typing import Callable

from .llm import BudgetExhausted, Client
from .parsing import Finding, parse_findings, parse_verdict
from .prompts import ASPECTS, BASE_SYSTEM, VERIFY_SYSTEM


@dataclass
class ReviewResult:
    config: str
    findings: list[Finding]
    cost_usd: float
    passes: int
    truncated: bool
    parse_failures: int = 0
    per_pass_meta: list[dict] = field(default_factory=list)


def pr_prompt(pkg: dict) -> str:
    return (f"# Pull request: {pkg['pr_title']}\n\n{pkg['pr_description']}\n\n"
            f"# Diff\n```diff\n{pkg['pr_diff']}\n```")


def _call(client: Client, model: str, system: str, user: str,
          item_id: str, config: str, pass_name: str,
          max_tokens: int = 8192) -> tuple[str, float, dict]:
    r = client.chat(
        model=model, system=system, user=user, max_tokens=max_tokens,
        context={"item": item_id, "config": config, "pass": pass_name, "model": model},
    )
    return r.text, r.cost_usd, r.usage


def run_single(pkg: dict, client: Client, model: str) -> ReviewResult:
    text, cost, _ = _call(client, model, BASE_SYSTEM, pr_prompt(pkg),
                          pkg["id"], "single", "reviewer")
    parsed = parse_findings(text)
    return ReviewResult("single", parsed or [], cost, 1, False,
                        parse_failures=0 if parsed is not None else 1)


def run_parallel(pkg: dict, client: Client, model: str) -> ReviewResult:
    findings: list[Finding] = []
    seen: set = set()
    cost_total = 0.0
    passes = 0
    parse_fail = 0
    truncated = False
    meta = []
    for name, hint in ASPECTS.items():
        try:
            text, cost, _ = _call(client, model, hint + "\n\n" + BASE_SYSTEM,
                                  pr_prompt(pkg), pkg["id"], "parallel", f"aspect:{name}")
        except BudgetExhausted:
            truncated = True
            break
        passes += 1
        cost_total += cost
        parsed = parse_findings(text)
        if parsed is None:
            parse_fail += 1
            meta.append({"pass": name, "parse_ok": False})
            continue
        added = 0
        for f in parsed:
            if f.key() not in seen:
                seen.add(f.key())
                findings.append(f)
                added += 1
        meta.append({"pass": name, "parse_ok": True, "raw": len(parsed), "added": added})
    return ReviewResult("parallel", findings, cost_total, passes, truncated,
                        parse_failures=parse_fail, per_pass_meta=meta)


def run_adversarial(pkg: dict, client: Client, model: str,
                    verify_rounds: int = 2) -> ReviewResult:
    cost_total = 0.0
    passes = 0
    parse_fail = 0
    meta = []
    truncated = False

    try:
        text, cost, _ = _call(client, model, BASE_SYSTEM, pr_prompt(pkg),
                              pkg["id"], "adversarial", "propose")
    except BudgetExhausted:
        return ReviewResult("adversarial", [], 0.0, 0, True, 0, [])
    passes += 1
    cost_total += cost
    proposed = parse_findings(text)
    if proposed is None:
        parse_fail += 1
        proposed = []
    meta.append({"pass": "propose", "parse_ok": proposed is not None,
                 "raw": len(proposed)})

    survivors: list[Finding] = []
    for f in proposed:
        confirms = 0
        for r_idx in range(verify_rounds):
            user = (f"# Diff\n```diff\n{pkg['pr_diff']}\n```\n\n"
                    f"# Claimed defect\nfile: {f.file}\nlines: {f.line_start}-{f.line_end}\n"
                    f"category: {f.category}\nseverity: {f.severity}\n"
                    f"summary: {f.summary}\n\nIs this a real defect?")
            try:
                vtext, vcost, _ = _call(client, model, VERIFY_SYSTEM, user,
                                        pkg["id"], "adversarial",
                                        f"verify:{f.file}:{f.line_start}:{r_idx}",
                                        max_tokens=2048)
            except BudgetExhausted:
                truncated = True
                break
            passes += 1
            cost_total += vcost
            v = parse_verdict(vtext)
            if v is True:
                confirms += 1
            elif v is None:
                parse_fail += 1
        if truncated:
            break
        if confirms >= (verify_rounds + 1) // 2:
            survivors.append(f)
        meta.append({"pass": f"verify:{f.file}:{f.line_start}",
                     "confirms": confirms, "rounds": verify_rounds})

    return ReviewResult("adversarial", survivors, cost_total, passes, truncated,
                        parse_failures=parse_fail, per_pass_meta=meta)


def run_multi(pkg: dict, client: Client, model: str, k: int = 5,
              vote_threshold: int = 2) -> ReviewResult:
    cost_total = 0.0
    passes = 0
    parse_fail = 0
    truncated = False
    votes: dict[tuple, tuple[Finding, int]] = {}
    meta = []
    for i in range(k):
        try:
            text, cost, _ = _call(client, model, BASE_SYSTEM, pr_prompt(pkg),
                                  pkg["id"], "multi", f"run:{i}")
        except BudgetExhausted:
            truncated = True
            break
        passes += 1
        cost_total += cost
        parsed = parse_findings(text)
        if parsed is None:
            parse_fail += 1
            meta.append({"pass": f"run:{i}", "parse_ok": False})
            continue
        for f in parsed:
            k_ = (f.file, f.line_start // 4)
            if k_ in votes:
                votes[k_] = (votes[k_][0], votes[k_][1] + 1)
            else:
                votes[k_] = (f, 1)
        meta.append({"pass": f"run:{i}", "parse_ok": True, "raw": len(parsed)})
    findings = [f for f, v in votes.values() if v >= vote_threshold]
    return ReviewResult("multi", findings, cost_total, passes, truncated,
                        parse_failures=parse_fail, per_pass_meta=meta)


CONFIGS: dict[str, Callable[..., ReviewResult]] = {
    "single": run_single,
    "parallel": run_parallel,
    "adversarial": run_adversarial,
    "multi": run_multi,
}
