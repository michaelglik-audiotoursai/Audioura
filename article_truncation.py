"""
Article Truncation — Per-plan character-limit gating for news articles.
=======================================================================

Truncates article text at the LISTENER'S PLAN limit before delivery. This is the
single source of truth for how long an article is — both the text the listener
reads AND the audio that is synthesised (LOCAL-708 / D670). The audio path in
news_processor_service synthesises exactly this truncated text; it no longer
carries its own separate 5,000-char cap.

Per-plan limits live in the `plans` table, column `article_char_limit`
(migration 039), one value per D613 plan level (l1/l2/l3/l4/admin/tester):

    l1     5,000      l3    10,000      admin  15,000
    l2     5,000      l4    15,000      tester 15,000

The listener's plan is resolved with the SAME entitlement lookup the tour quota
uses — subscription_levels.get_device_state(user_id) → level → plans row. A
device with no row is L1 (install default). If the column is NULL/missing, or
the lookup fails, we fall back to a CODE DEFAULT of 5,000 (fail-safe, smallest).

Env overrides remain as a GLOBAL CEILING (emergency throttle, no redeploy —
same mechanism as PRICING_MULTIPLIER in SUBSCRIBED_DESIGN.md §Configuration):

    NEWS_FREE_CHAR_LIMIT       = 5000   (floor-tier value; legacy free tier +
                                         the "entry plan" number shown in the
                                         upsell notice)
    NEWS_SUBSCRIBED_CHAR_LIMIT = 15000  (GLOBAL CEILING — no plan is ever
                                         allowed to exceed this)

Any per-plan value is clamped to NEWS_SUBSCRIBED_CHAR_LIMIT, so lowering that
env var throttles every plan at once without a code change.

Truncation rules (unchanged):
  1. Cut at the last sentence boundary (. ! ?) at or before the limit.
  2. If the sentence-boundary cut would discard >15% of the allowance, fall
     back to the last word boundary.
  3. The appended notice does NOT push text over the limit (it replaces
     content, not adds to it).

User-facing copy (D58: no cost, no dollar figure, no token count):
  - Entry plans (limit == the floor value), truncated: names the limit and what
    a bigger plan lifts it to. Invitation.
  - Higher plans, truncated: names the limit only. No upsell.
  - Not truncated: no notice at all.

Backward compatibility:
  truncate_article_text(text, tier) and get_char_limit_for_tier(tier) still
  accept the legacy wallet tier strings 'free'/'ppu'/'unlimited' (free → floor,
  ppu/unlimited → ceiling) so existing callers and tests keep working. New code
  should call truncate_for_user(text, user_id), which resolves the per-plan
  limit from the plans table.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# Smallest, safest limit. Used when the plan row has no article_char_limit
# (NULL / column missing on an un-migrated DB) or the entitlement lookup fails.
CODE_DEFAULT_CHAR_LIMIT = 5000

# ---------------------------------------------------------------------------
# Runtime configuration — env vars, no code change to adjust.
# ---------------------------------------------------------------------------

def get_free_char_limit() -> int:
    """Floor-tier article character limit (reads env each call).

    This is the legacy free-tier value and the number shown in the upsell notice
    as the 'entry plan' allowance.
    """
    return int(os.environ.get("NEWS_FREE_CHAR_LIMIT", str(CODE_DEFAULT_CHAR_LIMIT)))


def get_subscribed_char_limit() -> int:
    """Global ceiling article character limit (reads env each call).

    No plan is allowed to exceed this; lowering it throttles every plan at once.
    """
    return int(os.environ.get("NEWS_SUBSCRIBED_CHAR_LIMIT", "15000"))


def _apply_env_ceiling(limit: int) -> int:
    """Clamp a per-plan limit to the global env ceiling.

    The ceiling (NEWS_SUBSCRIBED_CHAR_LIMIT) is an emergency throttle: a per-plan
    value can never produce more text than the ceiling allows. A per-plan value
    below the ceiling is honoured as-is.
    """
    ceiling = get_subscribed_char_limit()
    if limit is None or limit <= 0:
        limit = CODE_DEFAULT_CHAR_LIMIT
    return min(limit, ceiling)


# ---------------------------------------------------------------------------
# Per-plan limit resolution (the entitlement lookup the tour quota uses)
# ---------------------------------------------------------------------------

def _resolve_plan_article_limit(user_id: str) -> int:
    """Read the listener's plan's article_char_limit from the `plans` table.

    Resolution path (identical to the tour-quota gate):
        subscription_levels.get_device_state(user_id) → level
        → plans.article_char_limit for that level.

    Returns the raw per-plan limit (NOT yet env-clamped). Falls back to
    CODE_DEFAULT_CHAR_LIMIT on NULL column, missing column, unknown level, empty
    user, or any DB/import error (fail-safe: smallest limit).
    """
    if not user_id or not str(user_id).strip():
        return CODE_DEFAULT_CHAR_LIMIT

    try:
        import subscription_levels
    except Exception as e:  # pragma: no cover - import safety
        logger.warning(f"[TRUNCATION] subscription_levels unavailable: {e} — code default")
        return CODE_DEFAULT_CHAR_LIMIT

    conn = None
    try:
        conn = subscription_levels._get_conn()
        cur = conn.cursor()
        # Resolve the device's level via the same lookup the tour quota uses.
        state = subscription_levels.get_device_state(cur, user_id)
        level = state.get('level') if isinstance(state, dict) else None
        if not level:
            cur.close()
            return CODE_DEFAULT_CHAR_LIMIT
        # Read the per-plan article_char_limit. Column may not exist on an
        # un-migrated DB — that raises, and we fall back to the code default.
        cur.execute(
            "SELECT article_char_limit FROM plans WHERE plan_id = %s",
            (level,),
        )
        row = cur.fetchone()
        cur.close()
        if row and row[0] is not None:
            return int(row[0])
        return CODE_DEFAULT_CHAR_LIMIT
    except Exception as e:
        # Missing column, connection failure, unknown level, etc. — fail safe.
        logger.warning(
            f"[TRUNCATION] Could not read plan article_char_limit for {user_id}: {e} "
            f"— applying code default ({CODE_DEFAULT_CHAR_LIMIT})"
        )
        return CODE_DEFAULT_CHAR_LIMIT
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def get_article_limit_for_user(user_id: str) -> int:
    """Return the effective article character limit for a listener's plan.

    Per-plan value from the plans table, clamped to the global env ceiling.
    """
    return _apply_env_ceiling(_resolve_plan_article_limit(user_id))


# ---------------------------------------------------------------------------
# Legacy tier-string selection (backward compatibility)
# ---------------------------------------------------------------------------

def get_char_limit_for_tier(tier: str) -> int:
    """Return the character limit for a legacy wallet tier string.

    Retained for backward compatibility with callers/tests that pass the retired
    wallet tiers. 'ppu'/'unlimited' map to the global ceiling; everything else
    (including 'free') maps to the floor value.

    Args:
        tier: 'free', 'ppu', or 'unlimited'.
    """
    if tier in ('ppu', 'unlimited'):
        return get_subscribed_char_limit()
    return get_free_char_limit()


# ---------------------------------------------------------------------------
# Notice text (D58: no cost, no dollar figure, no "to save cost")
# ---------------------------------------------------------------------------

# --- ENTRY PLAN (limit == floor value) ---
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

# --- HIGHER PLAN (limit above the floor) ---
# Candidate A (shipping): names the limit only
_SUBSCRIBED_NOTICE_A = (
    "\n\nThis article has been shortened to {limit} characters."
)
# Candidate B (alternate): slightly different phrasing
_SUBSCRIBED_NOTICE_B = (
    "\n\nThis article exceeds the {limit}-character limit and has been shortened."
)


def _notice_for_limit(limit: int) -> str:
    """Return the truncation notice for an effective character `limit`.

    An ENTRY-PLAN limit (equal to the floor value, NEWS_FREE_CHAR_LIMIT) gets the
    invitation that names the higher ceiling. Any higher limit gets the
    limit-only notice (no upsell). Ships Candidate A for both.
    """
    floor = get_free_char_limit()
    if limit <= floor:
        return _FREE_NOTICE_A.format(
            limit=f"{limit:,}",
            sub_limit=f"{get_subscribed_char_limit():,}",
        )
    return _SUBSCRIBED_NOTICE_A.format(limit=f"{limit:,}")


def _get_notice(tier: str, limit: int) -> str:
    """Return the truncation notice for the given legacy tier.

    Retained for backward compatibility (tests import this). 'ppu'/'unlimited'
    get the limit-only notice; everything else gets the upsell.
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


def _truncate_to_limit(text: str, limit: int) -> tuple:
    """Truncate `text` to an effective character `limit`, appending the notice
    appropriate for that limit. The notice is chosen by _notice_for_limit (entry
    plan → upsell; higher plan → limit only).

    Returns (truncated_text, was_truncated, rule_used).
    """
    if not text:
        return text, False, 'none'

    if limit is None or limit <= 0:
        limit = CODE_DEFAULT_CHAR_LIMIT

    if len(text) <= limit:
        return text, False, 'none'

    # Text exceeds limit — must truncate.
    notice = _notice_for_limit(limit)
    notice_len = len(notice)

    # The cut point for content must leave room for the notice to stay within
    # the limit — "the appended notice must not itself push the text back over
    # the limit." So: content_budget = limit - len(notice).
    content_budget = limit - notice_len

    if content_budget <= 0:
        # Degenerate: limit is smaller than the notice. Just return the notice.
        logger.warning(
            f"[TRUNCATION] Limit ({limit}) smaller than notice ({notice_len}). "
            f"Returning notice only."
        )
        return notice.strip(), True, 'degenerate'

    # Rule 1: Cut at last sentence boundary at or before content_budget.
    sentence_pos = _find_sentence_boundary(text, content_budget)

    # Rule 2 trigger: if the sentence cut would discard >15% of the allowance
    # (i.e. land below 85% of content_budget), fall back to the word boundary.
    min_acceptable = int(content_budget * 0.85)

    if sentence_pos > 0 and sentence_pos >= min_acceptable:
        truncated = text[:sentence_pos].rstrip() + notice
        logger.info(
            f"[TRUNCATION] limit={limit} | original={len(text)} | "
            f"cut_at={sentence_pos} | rule=sentence_boundary"
        )
        return truncated, True, 'sentence_boundary'

    # Rule 2: sentence boundary too far back (>15% loss) — use word boundary.
    word_pos = _find_word_boundary(text, content_budget)
    truncated = text[:word_pos].rstrip() + notice
    logger.info(
        f"[TRUNCATION] limit={limit} | original={len(text)} | "
        f"cut_at={word_pos} | rule=word_boundary"
    )
    return truncated, True, 'word_boundary'


def truncate_article_text(text: str, tier: str) -> tuple:
    """Truncate article text to the legacy-tier-appropriate character limit.

    Backward-compatible entry point for callers/tests that pass a wallet tier
    string. New code should prefer truncate_for_user(text, user_id).

    Args:
        text: The full article text.
        tier: 'free', 'ppu', or 'unlimited'.

    Returns:
        (truncated_text, was_truncated, rule_used)
    """
    if not text:
        return text, False, 'none'
    limit = get_char_limit_for_tier(tier)
    return _truncate_to_limit(text, limit)


# ---------------------------------------------------------------------------
# Convenience: resolve the listener's per-plan limit and truncate.
# ---------------------------------------------------------------------------

def truncate_for_user(text: str, user_id: str) -> tuple:
    """Truncate article text to the listener's PLAN limit (LOCAL-708 / D670).

    Resolves the plan's article_char_limit via the same entitlement lookup the
    tour quota uses (subscription_levels.get_device_state → plans row), clamps it
    to the global env ceiling, then truncates with the boundary rules + notice.

    This is the single source of truth for article length: the audio path
    synthesises exactly the text this returns.

    Args:
        text: The full article text.
        user_id: The listener's secret_id / device id.

    Returns:
        (truncated_text, was_truncated, rule_used)
    """
    if not text:
        return text, False, 'none'

    # Fail-safe: any resolution error inside get_article_limit_for_user already
    # yields the code default, but wrap again so truncation never raises.
    try:
        limit = get_article_limit_for_user(user_id)
    except Exception as e:
        logger.warning(
            f"[TRUNCATION] Could not determine plan limit for {user_id}: {e} "
            f"— applying code default ({CODE_DEFAULT_CHAR_LIMIT})"
        )
        limit = _apply_env_ceiling(CODE_DEFAULT_CHAR_LIMIT)

    return _truncate_to_limit(text, limit)
