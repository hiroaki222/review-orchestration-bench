"""Per-provider usage normalization.

Each vendor SDK exposes token counts under different attribute names and
groupings. These helpers flatten them into the common shape
`{input_tokens, output_tokens, cache_read_tokens, cache_write_tokens}`
consumed by `Ledger.record` for pricing.
"""


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


def _normalize_gemini(usage) -> dict:
    total_prompt = getattr(usage, "prompt_token_count", 0) or 0
    cached = getattr(usage, "cached_content_token_count", 0) or 0
    visible = getattr(usage, "candidates_token_count", 0) or 0
    thoughts = getattr(usage, "thoughts_token_count", 0) or 0
    return {
        "input_tokens": total_prompt - cached,
        "output_tokens": visible + thoughts,
        "cache_read_tokens": cached,
        "cache_write_tokens": 0,
    }
