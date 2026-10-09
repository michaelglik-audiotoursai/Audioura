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
    # [LEAD 2026-10-08] gpt-4.1 is the main narration model. It was missing, so every gpt-4.1 call was
    # priced at the "most expensive" gpt-4o rate: the ledger overstated OpenAI (LOCAL-626 harness $1.72
    # vs network meter $0.85). List price; matches PRICE_CARD.md tag 2026-10-08-r3.
    "gpt-4.1-mini": {
        "input_per_1m": 0.40,
        "output_per_1m": 1.60,
    },
    "gpt-4.1": {
        "input_per_1m": 2.00,
        "output_per_1m": 8.00,
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

# --- Grounding (Gemini + Grounding with Google Search) ---
# [LOCAL-533 / LOCAL-594]
# Source: https://ai.google.dev/gemini-api/docs/pricing
# Read: 2026-10-06
#
# The pricing page lists Grounding with Google Search as "5,000 free search
# requests per month (shared across all Gemini 3.x models), then $14 per 1,000
# requests". But what Google actually INVOICES is measured in SEARCH QUERIES, not
# requests: Michael's bill SKU is "Generate content search query gemini 3 paid",
# and on 2026-10-05 it read 1,653 queries for $23.14 — $14.00 per 1,000 queries.
# A single grounded REQUEST can issue several search queries, reported back in
# `groundingMetadata.webSearchQueries`. So the honest dollar figure follows the
# QUERIES (that is the invoice line); the request count is kept only to enforce
# the LOCAL-594 "<= 1 grounded request per stop" cap.
#
# This supersedes the LOCAL-533 flat $0.035/request estimate, which did not match
# the bill. $0.035 was never on any pricing page; it over- or under-counted
# depending on how many queries a request fanned out into. We now price the unit
# Google prices.
GROUNDING_COST_PER_QUERY = 0.014  # $14 / 1,000 search queries
# [LEAD 2026-10-09, price card r4] Google bills each SEARCH-ENABLED request ($35 / 1,000), reconciled
# against Michael's bills within 2% (PRICE_CARD.md). The ledger priced per reported query and showed
# the Walters tour at $0.37 instead of ~$0.56. Ledger/plan caps now use the request price.
GROUNDED_REQUEST_COST = 0.035

# Legacy LOCAL-533 constant — DEPRECATED. The per-request rate never matched the
# invoice. Kept only so older callers/tests import without breaking; new code
# prices per query via grounding_query_cost(). Value re-pointed to the per-query
# rate so any stray use is at least on the right order of magnitude.
GROUNDING_COST_PER_REQUEST = GROUNDING_COST_PER_QUERY


def grounding_query_cost(num_queries: int) -> float:
    """[LOCAL-594] Cost in USD of `num_queries` Google search queries issued by
    grounded Gemini requests. This is the unit Google invoices
    ("Generate content search query gemini 3 paid"), counted via
    story_leads.get_grounding_queries(). A generation that issues zero grounded
    queries (e.g. a cache hit, or a grounded request that did not search) costs
    $0.00 on this channel."""
    return max(0, int(num_queries)) * GROUNDING_COST_PER_QUERY


def grounding_cost(num_requests: int) -> float:
    """DEPRECATED [LOCAL-594]: use grounding_query_cost(num_queries) for the
    dollar figure. Kept for LOCAL-533 callers. Prices requests at the per-query
    rate (one query per request assumption), which under-counts when a request
    fans out into several queries — so it is no longer the figure Michael sees."""
    return max(0, int(num_requests)) * GROUNDING_COST_PER_QUERY

# --- Gemini Flash tokens (the token channel, separate from grounding) ---
# [LOCAL-609]
# Source: https://ai.google.dev/gemini-api/docs/pricing  (Read: 2026-10-06)
# plus corroborating trade trackers read the same day:
#   https://www.morphllm.com/gemini-api-pricing  (Read: 2026-10-06)
#   https://rapidevelopers.com/ai-api-limits-performance-matrix/gemini-2-5-flash
#     (Read: 2026-10-06)
#
# The deployed model is `gemini-flash-latest` (story_leads.GEMINI_MODEL default),
# which resolves to the Gemini 2.5 Flash family. Its paid token rate as invoiced
# today (raised 2026-07-02) is $0.30 / 1M input tokens and $2.50 / 1M output
# tokens. These are the TOKEN prices only — the Grounding-with-Google-Search
# charge is a SEPARATE line (GROUNDING_COST_PER_QUERY above), billed per search
# query, and must not be conflated with the token cost. A grounded Gemini call
# therefore has TWO costs: its input/output tokens (this channel) and the search
# queries it issued (the grounding channel).
#
# Why this exists: before LOCAL-609 the Gemini Flash token spend was metered
# NOWHERE. The ledger carried grounding (per-query) but never the tokens the same
# calls burned, so Michael's per-tour figure silently omitted the Flash token
# line entirely. We price the unit Google invoices.
GEMINI_FLASH_INPUT_PER_1M = 0.30
GEMINI_FLASH_OUTPUT_PER_1M = 2.50
GEMINI_FLASH_INPUT_PER_TOKEN = GEMINI_FLASH_INPUT_PER_1M / 1_000_000
GEMINI_FLASH_OUTPUT_PER_TOKEN = GEMINI_FLASH_OUTPUT_PER_1M / 1_000_000


def gemini_tokens_cost(input_tokens: int = 0, output_tokens: int = 0) -> float:
    """[LOCAL-609] Cost in USD of Gemini Flash token usage.

    This is the TOKEN channel only (promptTokenCount + candidatesTokenCount from
    the response's usageMetadata). The grounding search-query charge is priced
    separately via grounding_query_cost(). Returns $0.00 for zero tokens — an
    ungrounded cache hit that made no Gemini call costs nothing here.
    """
    input_tokens = max(0, int(input_tokens or 0))
    output_tokens = max(0, int(output_tokens or 0))
    return (input_tokens * GEMINI_FLASH_INPUT_PER_TOKEN
            + output_tokens * GEMINI_FLASH_OUTPUT_PER_TOKEN)


# --- Preflight (LOCAL-603 venue preflight) ---
# [LOCAL-609]
# The LOCAL-603 preflight is a single grounded Gemini call made BEFORE the main
# generation to read a venue's hours/admission. It is not a distinct provider —
# its dollars are Gemini grounding search queries plus Gemini Flash tokens — but
# Michael asked for it as its OWN ledger line because it is "its own call, not
# visible per job" (the ticket's words). So the preflight channel is reported
# separately in the breakdown; its dollar figure is computed with the SAME rates
# as the grounding + token channels (no new rate), via preflight_cost(). On a
# cache hit the preflight does not run, so this channel is $0.00 and we say so.
def preflight_cost(num_queries: int = 0, input_tokens: int = 0,
                   output_tokens: int = 0) -> float:
    """[LOCAL-609] Cost in USD of one venue preflight: its grounding search
    queries priced at GROUNDING_COST_PER_QUERY plus its Gemini Flash tokens priced
    at the Flash token rates. Uses no new rate — the preflight is a grounded
    Gemini call, reported on its own line for visibility (ticket LOCAL-609)."""
    return (max(grounding_query_cost(num_queries), GROUNDED_REQUEST_COST)  # one grounded request
            + gemini_tokens_cost(input_tokens, output_tokens))


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
