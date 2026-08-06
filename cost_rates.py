"""
Centralised rate table for all billable API calls.
All cost-per-unit rates live here. No other module should hardcode rates.
When a model price changes, update ONE file.
Rates are in USD.

LOCAL-197: Per-model input/output rates, split-token llm_cost() signature.
Sources and read-dates inline below.
"""

import logging

_log = logging.getLogger(__name__)

# ─── LLM (OpenAI) — per 1M tokens ────────────────────────────────────────────
# Source: https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/
# Read: 2026-08-04
# gpt-4o-mini: $0.15/1M input, $0.60/1M output (published 2024-07-18)
#
# Source: https://cloudprice.net/models/openai-gpt-3-5-turbo
# Read: 2026-08-04
# gpt-3.5-turbo: $0.50/1M input, $1.50/1M output (last published rate)
#
# Note: gpt-3.5-turbo was delisted from OpenAI's active pricing page ~July 2026,
# but remains available via API at the last published rate.

LLM_RATES = {
    # model-family -> {input_per_1m, output_per_1m}
    "gpt-4o": {
        "input_per_1m": 2.50,
        "output_per_1m": 10.00,
    },
    "gpt-4o-mini": {
        "input_per_1m": 0.15,
        "output_per_1m": 0.60,
    },
    "gpt-3.5-turbo": {
        "input_per_1m": 0.50,
        "output_per_1m": 1.50,
    },
}

# Legacy constants — DEPRECATED. Kept for any code that reads them directly.
# These are the REAL blended rates (approx 30% output ratio), not the old 0.002.
GPT35_TURBO_COST_PER_1K_TOKENS = 0.0008  # ~($0.50*0.7 + $1.50*0.3) / 1000
GPT4O_MINI_COST_PER_1K_TOKENS = 0.000285  # ~($0.15*0.7 + $0.60*0.3) / 1000

# --- Search (Serper) ---
SERPER_COST_PER_QUERY = 0.001

# --- TTS (AWS Polly) ---
# Source: https://aws.amazon.com/polly/pricing/
# Read: 2026-08-06
# Standard voices: $4.00 per 1M characters
# Neural voices: $16.00 per 1M characters
# Neural voices used: Joanna, Matthew, Amy, Brian (see polly_tts_service.py:124,136)
POLLY_STANDARD_COST_PER_1M_CHARS = 4.00
POLLY_NEURAL_COST_PER_1M_CHARS = 16.00
POLLY_STANDARD_COST_PER_CHAR = POLLY_STANDARD_COST_PER_1M_CHARS / 1_000_000  # $0.000004
POLLY_NEURAL_COST_PER_CHAR = POLLY_NEURAL_COST_PER_1M_CHARS / 1_000_000  # $0.000016

# Legacy single-rate constant — kept for existing callers (uses standard rate)
POLLY_COST_PER_1M_CHARS = 4.00
POLLY_COST_PER_CHAR = POLLY_COST_PER_1M_CHARS / 1_000_000  # $0.000004

# AWS Translate
AWS_TRANSLATE_COST_PER_1M_CHARS = 15.00
AWS_TRANSLATE_COST_PER_CHAR = AWS_TRANSLATE_COST_PER_1M_CHARS / 1_000_000  # $0.000015

# Legacy alias
GOOGLE_TRANSLATE_COST_PER_1M_CHARS = AWS_TRANSLATE_COST_PER_1M_CHARS
GOOGLE_TRANSLATE_COST_PER_CHAR = AWS_TRANSLATE_COST_PER_CHAR

CACHE_HIT_COST_USD = 0.00


def _resolve_model_rates(model: str) -> dict:
    """Resolve a model string to its rate dict. Unknown model = warn + most expensive."""
    # Try exact match first
    if model in LLM_RATES:
        return LLM_RATES[model]

    # Try substring match (e.g. "gpt-4o-mini-2024-07-18" contains "gpt-4o-mini")
    # Use longest match to avoid "gpt-4o" matching "gpt-4o-mini-2024-07-18"
    _matches = [(key, LLM_RATES[key]) for key in LLM_RATES if key in model]
    if _matches:
        # Return the longest matching key (most specific)
        _matches.sort(key=lambda x: len(x[0]), reverse=True)
        return _matches[0][1]

    # Unknown model: warn and use the MOST EXPENSIVE known rate to avoid overcharging users
    _most_expensive = max(
        LLM_RATES.values(),
        key=lambda r: r["input_per_1m"] + r["output_per_1m"]
    )
    _log.warning(
        f"[LOCAL-197] Unknown model '{model}' — pricing at most expensive known rate "
        f"(input=${_most_expensive['input_per_1m']}/1M, output=${_most_expensive['output_per_1m']}/1M). "
        f"Error direction: we absorb the difference, never overcharge."
    )
    return _most_expensive


def llm_cost(
    input_tokens: int = 0,
    output_tokens: int = 0,
    model: str = "gpt-3.5-turbo",
    *,
    total_tokens: int = None,
) -> float:
    """Compute LLM cost from token counts.

    Preferred call: llm_cost(input_tokens=N, output_tokens=M, model="gpt-4o-mini")

    Deprecated single-argument path (for callers that only have total_tokens):
        llm_cost(total_tokens=N, model="gpt-4o-mini")
    When total_tokens is used, we assume a 70/30 input/output split and log a
    deprecation warning on first use.

    Returns cost in USD.
    """
    rates = _resolve_model_rates(model)
    input_rate = rates["input_per_1m"] / 1_000_000
    output_rate = rates["output_per_1m"] / 1_000_000

    if total_tokens is not None:
        # Deprecated path: caller cannot supply split counts
        # [LOCAL-278] Identify the caller so it can be fixed independently
        import traceback
        _caller_frame = traceback.extract_stack(limit=3)
        _caller_info = f"{_caller_frame[0].filename}:{_caller_frame[0].lineno}" if _caller_frame else "unknown"
        if not hasattr(llm_cost, "_deprecated_warned"):
            llm_cost._deprecated_warned = set()
        if _caller_info not in llm_cost._deprecated_warned:
            llm_cost._deprecated_warned.add(_caller_info)
            _log.warning(
                f"[LOCAL-197] llm_cost() called with total_tokens (deprecated) "
                f"by {_caller_info}. "
                "Caller should supply input_tokens and output_tokens separately."
            )
        # Assume 70% input, 30% output (conservative — output is more expensive)
        input_tokens = int(total_tokens * 0.7)
        output_tokens = total_tokens - input_tokens

    return (input_tokens * input_rate) + (output_tokens * output_rate)


def search_cost(num_queries: int) -> float:
    return num_queries * SERPER_COST_PER_QUERY


def tts_cost(char_count: int, engine: str = "standard") -> float:
    """Compute TTS cost from character count and engine type.

    Args:
        char_count: Number of characters submitted to Polly.
        engine: 'neural' or 'standard'. Defaults to 'standard'.

    Returns:
        Cost in USD.
    """
    if engine == "neural":
        return char_count * POLLY_NEURAL_COST_PER_CHAR
    return char_count * POLLY_STANDARD_COST_PER_CHAR


DEPLOYED_TRANSLATION_PASSES = 1


def translation_cost(char_count: int, passes: int = None) -> float:
    if passes is None:
        passes = DEPLOYED_TRANSLATION_PASSES
    if passes == 2:
        translate_chars = char_count * 1.95
    elif passes == 1:
        translate_chars = char_count * 1.0
    else:
        raise ValueError(f"passes must be 1 or 2, got {passes}")
    translate_usd = translate_chars * AWS_TRANSLATE_COST_PER_CHAR
    polly_chars = char_count * 0.95 * 1.06
    polly_usd = polly_chars * POLLY_COST_PER_CHAR
    return translate_usd + polly_usd
