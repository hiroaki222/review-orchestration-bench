"""Provider-agnostic chat call with mandatory ledger recording.

Budget is enforced before each call: if the run's recorded spend has reached
the cap, BudgetExhausted is raised instead of calling the API.
"""

import os
import time
from dataclasses import dataclass

from dotenv import load_dotenv

from .ledger import Ledger
from .usage import _normalize_anthropic, _normalize_gemini, _normalize_openai

load_dotenv()


class BudgetExhausted(Exception):
    pass


@dataclass
class ChatResult:
    text: str
    usage: dict
    cost_usd: float
    stop_reason: str


class Client:
    def __init__(self, ledger: Ledger, run_id: str, budget_usd: float | None = None):
        self.ledger = ledger
        self.run_id = run_id
        self.budget_usd = budget_usd
        self._anthropic = None
        self._openai = None
        self._google = None

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
        elif provider == "google":
            if self._google is None:
                from google import genai
                self._google = genai.Client(api_key=os.environ["GOOGLE_API_KEY_EXPERIMENT"])
            from google.genai import types as gt
            resp = self._google.models.generate_content(
                model=model,
                contents=user,
                config=gt.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                ),
            )
            text = resp.text or ""
            usage_raw = resp.usage_metadata.model_dump()
            usage = _normalize_gemini(resp.usage_metadata)
            stop = resp.candidates[0].finish_reason.name if resp.candidates else "unknown"
        else:
            raise ValueError(f"unknown provider: {provider}")

        latency_ms = int((time.monotonic() - start) * 1000)
        entry = self.ledger.record(
            run_id=self.run_id, provider=provider, model=model,
            usage_raw=usage_raw, usage_normalized=usage,
            latency_ms=latency_ms, context=context)
        return ChatResult(text=text, usage=usage,
                          cost_usd=entry["cost_usd"]["total"], stop_reason=stop)
