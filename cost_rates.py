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


def translation_cost(char_count: int) -> float:
    """Calculate full translation cost from source character count.

    [LOCAL-135] Corrected to reflect actual service behavior:
    The translation service translates each stop TWICE per language
    (full text for .txt + nav-stripped text for Polly input), then
    synthesizes audio via Polly on the translated TTS text.

    Effective rate: ~$32.58 per 1M source characters (measured over 5 tours).
    Breakdown: 2x AWS Translate ($15/1M each pass) + Polly ($4/1M on ~95% of source).
    """
    # Translate API: source text is sent twice (full + nav-stripped ≈ 95% of full)
    translate_chars = char_count * 1.95  # full + ~95% for TTS-stripped
    translate_usd = translate_chars * AWS_TRANSLATE_COST_PER_CHAR

    # Polly: runs on translated TTS text (nav-stripped source * ~1.06 expansion ratio)
    polly_chars = char_count * 0.95 * 1.06  # 95% nav-stripped, 6% translation expansion
    polly_usd = polly_chars * POLLY_COST_PER_CHAR

    return translate_usd + polly_usd
