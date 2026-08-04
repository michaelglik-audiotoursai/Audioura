"""
Article Truncation — Character-limit gating for news articles.
================================================================

Truncates article text at the tier-appropriate character limit before
delivery to the user. This is a DISPLAY truncation — it does not affect
TTS audio (which has its own 5,000-char cap in clean_text_for_polly()).

Limits are runtime-configurable via environment variables (same mechanism
as PRICING_MULTIPLIER in SUBSCRIBED_DESIGN.md §Configuration):

    NEWS_FREE_CHAR_LIMIT       = 5000   (characters, free tier)
    NEWS_SUBSCRIBED_CHAR_LIMIT = 15000  (characters, ppu or unlimited)

Michael can change these without a code change.

Truncation rules:
  1. Cut at the last sentence boundary (. ! ?) at or before the limit.
  2. If sentence-boundary cut would discard >15% of the allowance,
     fall back to last word boundary.
  3. The appended notice does NOT push text over the limit (it replaces
     content, not adds to it).

User-facing copy (D58: no cost, no dollar figure, no token count):
  - Free tier, truncated: names the limit and what lifts it. Invitation.
  - Subscribed tier, truncated: names the limit only. No upsell.
  - Not truncated: no notice at all.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Runtime configuration — env vars, no code change to adjust.
# ---------------------------------------------------------------------------

def get_free_char_limit() -> int:
    """Free tier article character limit (reads env each call)."""
    return int(os.environ.get("NEWS_FREE_CHAR_LIMIT", "5000"))


def get_subscribed_char_limit() -> int:
    """Subscribed tier article character limit (reads env each call)."""
    return int(os.environ.get("NEWS_SUBSCRIBED_CHAR_LIMIT", "15000"))


# ---------------------------------------------------------------------------
# Tier-appropriate limit selection
# ---------------------------------------------------------------------------

def get_char_limit_for_tier(tier: str) -> int:
    """Return the character limit for the given subscription tier.

    Args:
        tier: 'free', 'ppu', or 'unlimited'

    Returns:
        Character limit as integer.
    """
    if tier in ('ppu', 'unlimited'):
        return get_subscribed_char_limit()
    return get_free_char_limit()


# ---------------------------------------------------------------------------
# Notice text (D58: no cost, no dollar figure, no "to save cost")
# ---------------------------------------------------------------------------

# --- FREE TIER ---
# Candidate A (shipping): direct, names what lifts it
# D58, Michael's words: "the last line should also encourage people to
# subscribe then this limit will be increased to xxx number of characters."
# He asked for the NUMBER, not a vague "longer" — so the notice names both.
_FREE_NOTICE_A = (
    "\n\nThis article has been shortened to {limit} characters. "
    "Subscribe to read articles up to {sub_limit} characters."
)
# Candidate B (alternate): slightly softer
# NOTE: an earlier draft of B said "Subscribers can access the full text."
# That is false — subscribers get a higher limit, not an unlimited one. Fixed.
_FREE_NOTICE_B = (
    "\n\nYou're reading a shortened version of this article ({limit} characters). "
    "Subscribers can read up to {sub_limit} characters."
)

# --- SUBSCRIBED TIER ---
# Candidate A (shipping): names the limit only
_SUBSCRIBED_NOTICE_A = (
    "\n\nThis article has been shortened to {limit} characters."
)
# Candidate B (alternate): slightly different phrasing
_SUBSCRIBED_NOTICE_B = (
    "\n\nThis article exceeds the {limit}-character limit and has been shortened."
)


def _get_notice(tier: str, limit: int) -> str:
    """Return the truncation notice for the given tier.

    Ships Candidate A for both tiers. LEAD picks; Michael overturns.
    """
    if tier in ('ppu', 'unlimited'):
        return _SUBSCRIBED_NOTICE_A.format(limit=f"{limit:,}")
    return _FREE_NOTICE_A.format(
        limit=f"{limit:,}",
        sub_limit=f"{get_subscribed_char_limit():,}",
    )


# ---------------------------------------------------------------------------
# Core truncation logic
# ---------------------------------------------------------------------------

def _find_sentence_boundary(text: str, max_pos: int) -> int:
    """Find the last sentence-ending position at or before max_pos.

    Looks for '. ', '! ', '? ' or end-of-sentence at string end.
    Returns -1 if no sentence boundary found.
    """
    # Search for sentence-ending punctuation followed by whitespace or end
    best = -1
    for match in re.finditer(r'[.!?](?:\s|$)', text[:max_pos + 1]):
        # The boundary is right after the punctuation mark
        best = match.start() + 1
    return best


def _find_word_boundary(text: str, max_pos: int) -> int:
    """Find the last word boundary (space) at or before max_pos.

    Returns max_pos if no space found (degenerate case).
    """
    pos = text.rfind(' ', 0, max_pos + 1)
    if pos <= 0:
        return max_pos
    return pos


def truncate_article_text(text: str, tier: str) -> tuple:
    """Truncate article text to the tier-appropriate character limit.

    Args:
        text: The full article text.
        tier: 'free', 'ppu', or 'unlimited'.

    Returns:
        (truncated_text, was_truncated, rule_used)
        - truncated_text: The text, possibly truncated with notice appended.
        - was_truncated: bool — True if text was cut.
        - rule_used: str — 'none', 'sentence_boundary', or 'word_boundary'.
    """
    if not text:
        return text, False, 'none'

    limit = get_char_limit_for_tier(tier)

    if len(text) <= limit:
        return text, False, 'none'

    # Text exceeds limit — must truncate.
    notice = _get_notice(tier, limit)
    notice_len = len(notice)

    # The cut point for content must leave room for the notice to stay within limit.
    # But per spec: "The appended notice must not itself push the text back over the limit."
    # So: content_budget = limit - len(notice)
    content_budget = limit - notice_len

    if content_budget <= 0:
        # Degenerate: limit is smaller than notice. Just return notice.
        logger.warning(
            f"[TRUNCATION] Limit ({limit}) smaller than notice ({notice_len}). "
            f"Returning notice only."
        )
        return notice.strip(), True, 'degenerate'

    # Rule 1: Cut at last sentence boundary at or before content_budget
    sentence_pos = _find_sentence_boundary(text, content_budget)

    # Check if sentence boundary would discard >15% of the allowance
    # "discard more than ~15% of the allowance" means: if the sentence cut
    # results in text shorter than 85% of content_budget
    min_acceptable = int(content_budget * 0.85)

    if sentence_pos > 0 and sentence_pos >= min_acceptable:
        # Good sentence boundary — use it
        truncated = text[:sentence_pos].rstrip() + notice
        logger.info(
            f"[TRUNCATION] tier={tier} | limit={limit} | "
            f"original={len(text)} | cut_at={sentence_pos} | rule=sentence_boundary"
        )
        return truncated, True, 'sentence_boundary'

    # Rule 2: Sentence boundary too far back (>15% loss) — use word boundary
    word_pos = _find_word_boundary(text, content_budget)
    truncated = text[:word_pos].rstrip() + notice
    logger.info(
        f"[TRUNCATION] tier={tier} | limit={limit} | "
        f"original={len(text)} | cut_at={word_pos} | rule=word_boundary"
    )
    return truncated, True, 'word_boundary'


# ---------------------------------------------------------------------------
# Convenience: determine tier from user_id (uses entitlements)
# ---------------------------------------------------------------------------

def truncate_for_user(text: str, user_id: str) -> tuple:
    """Truncate article text based on the user's subscription tier.

    Convenience wrapper that resolves the user's tier from entitlements,
    then delegates to truncate_article_text().

    Args:
        text: The full article text.
        user_id: The user's secret_id.

    Returns:
        (truncated_text, was_truncated, rule_used)
    """
    from entitlements import _get_subscription_tier

    # Determine tier
    try:
        sub_tier = _get_subscription_tier(user_id)
        tier = sub_tier if sub_tier else 'free'
    except Exception as e:
        # Fail closed: if we can't determine tier, apply free limit
        logger.warning(f"[TRUNCATION] Could not determine tier for {user_id}: {e} — applying free limit")
        tier = 'free'

    return truncate_article_text(text, tier)
