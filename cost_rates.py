"""
Centralised rate table for all billable API calls.
====================================================
All cost-per-unit rates live here. No other module should hardcode rates.
When a model price changes, update ONE file.

Rates are in USD.
"""

# --- LLM (OpenAI) ---
# GPT-3.5-turbo (used for tour text generation, directions, descriptions, fact extraction)
GPT35_TURBO_COST_PER_1K_TOKENS = 0.002

# GPT-4o-mini (used in some newer paths — same rate applies for metering purposes)
GPT4O_MINI_COST_PER_1K_TOKENS = 0.002

# --- Search (Serper) ---
SERPER_COST_PER_QUERY = 0.001  # ~$1 per 1,000 queries

# --- TTS ---
# Amazon Polly
POLLY_COST_PER_1M_CHARS = 4.00
POLLY_COST_PER_CHAR = POLLY_COST_PER_1M_CHARS / 1_000_000  # $0.000004

# AWS Translate (the translation service uses boto3 translate_text, not Google)
# [LOCAL-135] Corrected: service uses AWS Translate at $15/1M, not Google at $20/1M.
AWS_TRANSLATE_COST_PER_1M_CHARS = 15.00
AWS_TRANSLATE_COST_PER_CHAR = AWS_TRANSLATE_COST_PER_1M_CHARS / 1_000_000  # $0.000015

# Legacy alias — kept for any code importing the old name
GOOGLE_TRANSLATE_COST_PER_1M_CHARS = AWS_TRANSLATE_COST_PER_1M_CHARS
GOOGLE_TRANSLATE_COST_PER_CHAR = AWS_TRANSLATE_COST_PER_CHAR

# --- Cache ---
CACHE_HIT_COST_USD = 0.00  # A cache hit costs us nothing

# --- Helper ---
def llm_cost(total_tokens: int, model: str = "gpt-3.5-turbo") -> float:
    """Calculate LLM cost from token count."""
    if "gpt-4o" in model:
        return total_tokens / 1000 * GPT4O_MINI_COST_PER_1K_TOKENS
    return total_tokens / 1000 * GPT35_TURBO_COST_PER_1K_TOKENS


def search_cost(num_queries: int) -> float:
    """Calculate search (Serper) cost from query count."""
    return num_queries * SERPER_COST_PER_QUERY


def tts_cost(char_count: int) -> float:
    """Calculate TTS (Polly) cost from character count."""
    return char_count * POLLY_COST_PER_CHAR



# [LOCAL-143] Deployed translation mode.
# The running container determines how many translate_text calls happen per stop.
# - TWO_PASS (2): old behaviour — each stop translated twice (full + nav-stripped).
#   Deployed container built 2026-07-28; LOCAL-142 merged 2026-08-02 but NOT deployed.
# - SINGLE_PASS (1): LOCAL-142 behaviour — each stop translated once, nav fields
#   stripped positionally from the raw output. Fallback fires on line mismatch
#   (logged as "[LOCAL-142] Positional strip fallback"), adding 1 extra call per
#   affected stop. In the best case the multiplier is 1.0; worst case = 2.0.
#
# HOW DETERMINED: `docker exec audioura-translation-service-1 grep -c "LOCAL-142"
# /app/translation_service.py` returns 0 → the container has no single-pass code.
# See tests/test_local143_cost_model_matches_deploy.py for automated enforcement.
DEPLOYED_TRANSLATION_PASSES = 2


def translation_cost(char_count: int, passes: int = None) -> float:
    """Calculate full translation cost from source character count.

    [LOCAL-135] Corrected to reflect actual service behavior.
    [LOCAL-143] Parameterized by pass count so the cost model follows the
    code that actually ran, not a hardcoded assumption.

    Args:
        char_count: Source text character count (English).
        passes: Number of translate_text calls per stop.
            2 = two-pass (full + nav-stripped). Default before LOCAL-142 deployed.
            1 = single-pass (full only; nav stripped positionally from output).
            None = use DEPLOYED_TRANSLATION_PASSES constant (matches running container).

    Returns:
        Total cost in USD (AWS Translate + Polly TTS).
    """
    if passes is None:
        passes = DEPLOYED_TRANSLATION_PASSES

    if passes == 2:
        # Two-pass: source text sent twice (full + nav-stripped ≈ 95% of full)
        translate_chars = char_count * 1.95
    elif passes == 1:
        # Single-pass: source text sent once (full only)
        translate_chars = char_count * 1.0
    else:
        raise ValueError(f"passes must be 1 or 2, got {passes}")

    translate_usd = translate_chars * AWS_TRANSLATE_COST_PER_CHAR

    # Polly: always runs on translated TTS text (nav-stripped source × 1.06 expansion)
    # Polly cost is the same regardless of pass count — audio is always generated.
    polly_chars = char_count * 0.95 * 1.06  # 95% nav-stripped, 6% translation expansion
    polly_usd = polly_chars * POLLY_COST_PER_CHAR

    return translate_usd + polly_usd
