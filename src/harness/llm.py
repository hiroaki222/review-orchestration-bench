"""Provider-agnostic chat call with mandatory ledger recording.

Budget is enforced before each call: if the run's recorded spend has reached
the cap, BudgetExhausted is raised instead of calling the API.
"""

import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from .ledger import Ledger

load_dotenv()


class BudgetExhausted(Exception):
    pass


@dataclass
class ChatResult:
    text: str
    usage: dict
    cost_usd: float
    stop_reason: str


def _normalize_anthropic(usage) -> dict:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
    }


def _normalize_openai(usage) -> dict:
    cached = 0
    details = getattr(usage, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", 0) or 0
    return {
        "input_tokens": usage.prompt_tokens - cached,
        "output_tokens": usage.completion_tokens,
        "cache_read_tokens": cached,
        "cache_write_tokens": 0,
    }


class Client:
    def __init__(self, ledger: Ledger, run_id: str, budget_usd: float | None = None):
        self.ledger = ledger
        self.run_id = run_id
        self.budget_usd = budget_usd
        self._anthropic = None
        self._openai = None

    def _check_budget(self):
        if self.budget_usd is not None:
            spent = self.ledger.spent_usd(self.run_id)
            if spent >= self.budget_usd:
                raise BudgetExhausted(f"run {self.run_id}: spent ${spent:.4f} >= cap ${self.budget_usd:.4f}")

    def chat(self, *, model: str, system: str, user: str, max_tokens: int = 4096,
             context: dict | None = None) -> ChatResult:
        self._check_budget()
        provider = self.ledger.prices.models[model]["provider"]
        start = time.monotonic()

        if provider == "anthropic":
            if self._anthropic is None:
                import anthropic
                self._anthropic = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY_EXPERIMENT"])
            resp = self._anthropic.messages.create(
                model=model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": user}])
            text = "".join(b.text for b in resp.content if b.type == "text")
            usage_raw = resp.usage.model_dump()
            usage = _normalize_anthropic(resp.usage)
            stop = resp.stop_reason
        elif provider == "openai":
            if self._openai is None:
                import openai
                self._openai = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY_EXPERIMENT"])
            resp = self._openai.chat.completions.create(
                model=model, max_completion_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}])
            text = resp.choices[0].message.content or ""
            usage_raw = resp.usage.model_dump()
            usage = _normalize_openai(resp.usage)
            stop = resp.choices[0].finish_reason
        else:
            raise ValueError(f"unknown provider: {provider}")

        latency_ms = int((time.monotonic() - start) * 1000)
        entry = self.ledger.record(
            run_id=self.run_id, provider=provider, model=model,
            usage_raw=usage_raw, usage_normalized=usage,
            latency_ms=latency_ms, context=context)
        return ChatResult(text=text, usage=usage,
                          cost_usd=entry["cost_usd"]["total"], stop_reason=stop)
