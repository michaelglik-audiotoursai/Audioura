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

# Google Translate
GOOGLE_TRANSLATE_COST_PER_1M_CHARS = 20.00
GOOGLE_TRANSLATE_COST_PER_CHAR = GOOGLE_TRANSLATE_COST_PER_1M_CHARS / 1_000_000  # $0.00002

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
    """Calculate translation (Google Translate) cost from character count."""
    return char_count * GOOGLE_TRANSLATE_COST_PER_CHAR
