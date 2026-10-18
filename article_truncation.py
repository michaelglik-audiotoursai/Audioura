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

User-facing copy (D670 addendum; D58 still holds — NAME the plans, never a
price; "$10 Pack" is the plan's own NAME, not a price):
  - A shortened article tells the listener which plan they are on, how long the
    article was cut to (in PAGES, ~3,000 chars ≈ 1 page), which plans give
    longer articles (by NAME and page length), and ends with a "See plans"
    marker the app turns into a button to Your plan. e.g.:
      "Shortened to about 1½ pages on the Introduction plan. The $10 Pack plays
       articles up to about 3 pages, Curator up to 5 — See plans"
  - On the TOP plans (the maximum limit), only the length, no upsell:
      "Shortened to about 5 pages, the maximum."
  - The same notice appears on a TRANSLATED article, worded "listened to and
    translated", localised to the listener's language when the app is
    localised, English otherwise.
  - Not truncated: no notice at all.

Spoken audio notice (D670 addendum 2 — NAME the plans, not "a larger plan"):
  A shortened article's audio ends with one short spoken sentence built from the
  SAME plan data, naming the larger plans and their page lengths, e.g. on
  Introduction: "This article was shortened to about one and a half pages on
  your Introduction plan. The ten-dollar Pack plays articles up to about three
  pages, and the Curator plan up to five." On the top plans: "This article was
  shortened to about five pages, the maximum." Nothing is added when the article
  fits. build_spoken_notice_for_user() / build_spoken_notice() produce this.

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
# Plan metadata (D670 addendum): display name + article_char_limit per D613
# level. These are the FALLBACK values; when the DB is reachable we read the
# live plans table (display_name, article_char_limit) so an operator who edits
# the table by SQL changes the notice too. The fallback matches migration 016
# (names) and migration 039 (limits).
# ---------------------------------------------------------------------------

# plan_id -> (display_name, article_char_limit). Hidden plans (admin/tester)
# are never NAMED in an upsell — they only ever appear as "the maximum".
_PLAN_META_FALLBACK = {
    'l1':     ('Introduction', 5000),
    'l2':     ('Free',         5000),
    'l3':     ('$10 Pack',    10000),
    'l4':     ('Curator',     15000),
    'admin':  ('Administrator', 15000),
    'tester': ('Tester',      15000),
    'free':   ('Introduction', 5000),
    'ppu':    ('Introduction', 5000),
    'unlimited': ('Introduction', 5000),
}

# The plans named in the upsell, smallest-to-largest. Hidden plans (admin,
# tester) are deliberately excluded: the plan page never shows them (migration
# 016 hidden=TRUE), so the notice never invites a listener to them.
_UPSELL_PLAN_ORDER = ('l1', 'l2', 'l3', 'l4')

# ~3,000 characters ≈ 1 page (D670). Page phrases are spelled to match
# Michael's examples: 5,000 → "one and a half", 10,000 → "three", 15,000 →
# "five" (the maximum). We derive the phrase from the limit so a table edit to
# a known value stays in words; any other value falls back to a computed
# half-page-rounded number.
_CHARS_PER_PAGE = 3000

# Exact phrasings for the canonical limits (written, spoken-word).
_PAGE_PHRASE = {
    5000:  ('about 1½ pages',  'about one and a half pages'),
    10000: ('about 3 pages',   'about three pages'),
    15000: ('about 5 pages',   'about five pages'),
}

# Spoken-word forms of the small whole page counts used when a plan's limit is
# not one of the canonical values above.
_SPOKEN_NUMBERS = {
    1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six',
    7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
}


def _pages_for_limit(limit):
    """Return (written_phrase, spoken_phrase) page length for a char limit.

    Canonical limits use the exact phrasings from D670; any other value is
    rounded to the nearest half page and rendered numerically / in words.
    """
    if limit in _PAGE_PHRASE:
        return _PAGE_PHRASE[limit]
    # Round to the nearest half page.
    halves = max(1, round((limit / _CHARS_PER_PAGE) * 2))
    pages = halves / 2.0
    if pages == int(pages):
        n = int(pages)
        written = f"about {n} page" + ("" if n == 1 else "s")
        spoken_n = _SPOKEN_NUMBERS.get(n, str(n))
        spoken = f"about {spoken_n} page" + ("" if n == 1 else "s")
    else:
        whole = int(pages)
        if whole == 0:
            written, spoken = "about half a page", "about half a page"
        elif whole == 1:
            written, spoken = "about 1½ pages", "about one and a half pages"
        else:
            spoken_whole = _SPOKEN_NUMBERS.get(whole, str(whole))
            written = f"about {whole}½ pages"
            spoken = f"about {spoken_whole} and a half pages"
    return written, spoken


# Plan names spelled for speech (TTS): "$10 Pack" reads badly, so spell the
# money word. D58: the plan NAME may carry its own price word; we add no price
# beyond the name itself.
_SPOKEN_PLAN_NAME = {
    'l1': 'Introduction',
    'l2': 'Free',
    'l3': 'ten-dollar Pack',
    'l4': 'Curator',
    'admin': 'Administrator',
    'tester': 'Tester',
}


def _load_plan_meta():
    """Return {plan_id: {'name': str, 'limit': int}} for the upsell plans.

    Reads the live plans table (display_name, article_char_limit) when the DB
    is reachable so an operator's SQL edit flows through to the notice. Falls
    back to _PLAN_META_FALLBACK on any error (un-migrated DB, no connection).
    The returned limits are the RAW per-plan values (not env-clamped).
    """
    meta = {
        pid: {'name': _PLAN_META_FALLBACK[pid][0],
              'limit': _PLAN_META_FALLBACK[pid][1]}
        for pid in _PLAN_META_FALLBACK
    }
    try:
        import subscription_levels
        conn = subscription_levels._get_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT plan_id, display_name, article_char_limit FROM plans"
            )
            for plan_id, display_name, limit in cur.fetchall():
                if plan_id not in meta:
                    meta[plan_id] = {'name': plan_id, 'limit': CODE_DEFAULT_CHAR_LIMIT}
                if display_name:
                    meta[plan_id]['name'] = display_name
                if limit is not None:
                    meta[plan_id]['limit'] = int(limit)
            cur.close()
        finally:
            conn.close()
    except Exception as e:  # pragma: no cover - DB optional
        logger.info(f"[TRUNCATION] plans table unavailable for notice meta: {e} — using fallback")
    return meta


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


def _resolve_level_for_user(user_id: str):
    """Resolve the listener's D613 plan level (l1/l2/l3/l4/admin/tester).

    Same entitlement lookup the tour quota uses. Returns None on empty user or
    any error — the caller then falls back to the floor plan for notice wording.
    """
    if not user_id or not str(user_id).strip():
        return None
    try:
        import subscription_levels
        conn = subscription_levels._get_conn()
        try:
            cur = conn.cursor()
            state = subscription_levels.get_device_state(cur, user_id)
            cur.close()
            return state.get('level') if isinstance(state, dict) else None
        finally:
            conn.close()
    except Exception as e:
        logger.info(f"[TRUNCATION] Could not resolve level for {user_id}: {e}")
        return None


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

# "See plans" marker. The app renders the trailing "See plans" as a button to
# the Your-plan screen; nothing else in the notice is actionable. Kept as a
# constant so the mobile side and the tests agree on the exact token.
SEE_PLANS_MARKER = "See plans"

# ── Legacy notice strings (backward compatibility) ──────────────────────────
# These older constants are still imported by test_local193. They are NOT used
# to build the D670 notice anymore, but kept so legacy callers/tests resolve.
_FREE_NOTICE_A = (
    "\n\nThis article has been shortened to {limit} characters. "
    "Subscribe to read articles up to {sub_limit} characters."
)
_FREE_NOTICE_B = (
    "\n\nYou're reading a shortened version of this article ({limit} characters). "
    "Subscribers can read up to {sub_limit} characters."
)
_SUBSCRIBED_NOTICE_A = (
    "\n\nThis article has been shortened to {limit} characters."
)
_SUBSCRIBED_NOTICE_B = (
    "\n\nThis article exceeds the {limit}-character limit and has been shortened."
)


# ── D670 addendum: on-screen notice naming plans + page lengths ─────────────

def _build_text_notice(level, meta, ceiling, translated=False):
    """Build the on-screen D670 truncation notice.

    - Names the listener's current plan + how long the article was cut to
      (in pages).
    - Lists the visible plans that give longer articles (name + page length).
    - Ends with the "See plans" marker (app renders a button).
    - On a TOP plan (no larger visible plan under the ceiling), only the length
      and "the maximum" — no upsell, no button.
    - `translated=True` swaps "read" for "listened to and translated" wording.
    """
    # Effective (env-clamped) limit for the listener's plan.
    raw = meta.get(level, {}).get('limit') if level else None
    if raw is None:
        raw = get_free_char_limit()
    eff_limit = _apply_env_ceiling(raw)
    written_pages, _spoken = _pages_for_limit(eff_limit)

    plan_name = meta.get(level, {}).get('name') if level else None
    if not plan_name:
        plan_name = meta.get('l1', {}).get('name', 'Introduction')

    # Larger visible plans whose EFFECTIVE (env-clamped) limit exceeds the
    # listener's. A plan the ceiling clamps to the current limit is not larger.
    larger = []
    for pid in _UPSELL_PLAN_ORDER:
        if pid not in meta:
            continue
        lim_eff = _apply_env_ceiling(meta[pid]['limit'])
        if lim_eff <= eff_limit:
            continue
        w, _s = _pages_for_limit(lim_eff)
        larger.append((meta[pid]['name'], w, lim_eff))
    # De-duplicate by effective limit, keep ascending.
    dedup = []
    seen = set()
    for name, w, lim_eff in sorted(larger, key=lambda x: x[2]):
        if lim_eff in seen:
            continue
        seen.add(lim_eff)
        dedup.append((name, w))

    if not dedup:
        # Top plan: length only, "the maximum".
        if translated:
            body = f"Listened to and translated up to {written_pages}, the maximum."
        else:
            body = f"Shortened to {written_pages}, the maximum."
        return "\n\n" + body

    # Entry/mid plan: name the current plan, then the larger plans.
    if translated:
        head = (f"Shortened and translated to {written_pages} on the "
                f"{plan_name} plan.")
    else:
        head = f"Shortened to {written_pages} on the {plan_name} plan."
    # "The $10 Pack plays articles up to about 3 pages, Curator up to 5"
    parts = []
    for i, (name, w) in enumerate(dedup):
        if i == 0:
            parts.append(f"The {name} plays articles up to {w}")
        else:
            # Trailing plans read "Curator up to 5" — drop "about" and "pages".
            tail = (w.replace('about ', '')
                     .replace(' pages', '').replace(' page', ''))
            parts.append(f"{name} up to {tail}")
    longer_sentence = ", ".join(parts) + f" — {SEE_PLANS_MARKER}"
    return "\n\n" + head + " " + longer_sentence


def _notice_for_limit(limit: int) -> str:
    """Return a limit-only truncation notice for an effective character `limit`.

    Retained for the legacy tier path (truncate_article_text) and any caller
    that only has a char limit, not a plan level. The RICH D670 notice (plan
    names + pages + See plans) is built by _build_text_notice from the listener's
    level and is used by truncate_for_user.
    """
    ceiling = get_subscribed_char_limit()
    written_pages, _spoken = _pages_for_limit(limit)
    if limit >= ceiling:
        return f"\n\nShortened to {written_pages}, the maximum."
    # No plan level here — name the ceiling's page length as what a larger plan
    # gives, and the "See plans" marker.
    ceiling_pages, _s = _pages_for_limit(ceiling)
    return (f"\n\nShortened to {written_pages}. A larger plan plays articles up "
            f"to {ceiling_pages} — {SEE_PLANS_MARKER}")


def _get_notice(tier: str, limit: int) -> str:
    """Return the truncation notice for the given legacy tier.

    Retained for backward compatibility (tests import this). Uses the D670
    page-based wording via _notice_for_limit.
    """
    return _notice_for_limit(limit)


# ── D670 addendum 2: spoken audio notice naming the plans ───────────────────

def _build_spoken_notice(level, meta, translated=False):
    """Build the one-sentence spoken notice appended to a shortened article's
    audio. NAMES the plans (D670 addendum 2), built from the SAME plan data as
    the on-screen notice.

    Returns a plain string WITHOUT a leading separator (the caller joins it).
    On a top plan: "This article was shortened to about five pages, the
    maximum." Entry/mid plan (e.g. Introduction): "This article was shortened to
    about one and a half pages on your Introduction plan. The ten-dollar Pack
    plays articles up to about three pages, and the Curator plan up to five."
    """
    raw = meta.get(level, {}).get('limit') if level else None
    if raw is None:
        raw = get_free_char_limit()
    eff_limit = _apply_env_ceiling(raw)
    _written, spoken_pages = _pages_for_limit(eff_limit)

    spoken_plan = _SPOKEN_PLAN_NAME.get(level) if level else None
    if not spoken_plan:
        spoken_plan = _SPOKEN_PLAN_NAME.get('l1', 'Introduction')

    verb = ("shortened and translated to" if translated else "shortened to")

    # Larger visible plans (spoken name + spoken pages), ascending by eff limit.
    larger = []
    for pid in _UPSELL_PLAN_ORDER:
        if pid not in meta:
            continue
        lim_eff = _apply_env_ceiling(meta[pid]['limit'])
        if lim_eff <= eff_limit:
            continue
        _w, sp = _pages_for_limit(lim_eff)
        larger.append((pid, _SPOKEN_PLAN_NAME.get(pid, meta[pid]['name']), sp, lim_eff))
    dedup = []
    seen = set()
    for pid, name, sp, lim_eff in sorted(larger, key=lambda x: x[3]):
        if lim_eff in seen:
            continue
        seen.add(lim_eff)
        dedup.append((name, sp))

    if not dedup:
        return f"This article was {verb} {spoken_pages}, the maximum."

    head = f"This article was {verb} {spoken_pages} on your {spoken_plan} plan."
    parts = []
    for i, (name, sp) in enumerate(dedup):
        if i == 0:
            parts.append(f"The {name} plays articles up to {sp}")
        else:
            tail = (sp.replace('about ', '')
                      .replace(' pages', '').replace(' page', ''))
            parts.append(f"and the {name} plan up to {tail}")
    longer = ", ".join(parts) + "."
    return head + " " + longer


def build_spoken_notice_for_user(user_id, translated=False):
    """Public: the spoken notice for a listener, or '' if it can't be built.

    Only call this when the article WAS truncated for the listener's plan.
    """
    try:
        level = _resolve_level_for_user(user_id)
        meta = _load_plan_meta()
        return _build_spoken_notice(level, meta, translated=translated)
    except Exception as e:
        logger.warning(f"[TRUNCATION] Could not build spoken notice for {user_id}: {e}")
        return ""


def build_spoken_notice(level, translated=False):
    """Public: the spoken notice for a known plan level (no DB lookup of the
    device). Used by tests and callers that already resolved the level."""
    try:
        meta = _load_plan_meta()
        return _build_spoken_notice(level, meta, translated=translated)
    except Exception as e:
        logger.warning(f"[TRUNCATION] Could not build spoken notice for level {level}: {e}")
        return ""




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


def _truncate_to_limit(text: str, limit: int, notice: str = None) -> tuple:
    """Truncate `text` to an effective character `limit`, appending a notice.

    If `notice` is given (the rich D670 notice built from the listener's plan),
    it is used verbatim. Otherwise the limit-only page notice (_notice_for_limit)
    is used — the legacy tier path and any caller without a plan level.

    Returns (truncated_text, was_truncated, rule_used).
    """
    if not text:
        return text, False, 'none'

    if limit is None or limit <= 0:
        limit = CODE_DEFAULT_CHAR_LIMIT

    if len(text) <= limit:
        return text, False, 'none'

    # Text exceeds limit — must truncate.
    if notice is None:
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

def truncate_for_user(text: str, user_id: str, translated: bool = False) -> tuple:
    """Truncate article text to the listener's PLAN limit (LOCAL-708 / D670).

    Resolves the plan's article_char_limit via the same entitlement lookup the
    tour quota uses (subscription_levels.get_device_state → plans row), clamps it
    to the global env ceiling, then truncates with the boundary rules and the
    D670 notice (current plan + page length + which plans give longer + the
    "See plans" marker; top plans get length-only).

    This is the single source of truth for article length: the audio path
    synthesises exactly the text this returns.

    Args:
        text: The full article text.
        user_id: The listener's secret_id / device id.
        translated: True for a translated article — the notice uses the
            "listened to and translated" wording (D670 addendum).

    Returns:
        (truncated_text, was_truncated, rule_used)
    """
    if not text:
        return text, False, 'none'

    # Resolve the level once, then derive both the limit and the rich notice
    # from the same plan data (one source of truth).
    level = None
    try:
        level = _resolve_level_for_user(user_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.info(f"[TRUNCATION] level resolution failed for {user_id}: {e}")

    try:
        limit = get_article_limit_for_user(user_id)
    except Exception as e:
        logger.warning(
            f"[TRUNCATION] Could not determine plan limit for {user_id}: {e} "
            f"— applying code default ({CODE_DEFAULT_CHAR_LIMIT})"
        )
        limit = _apply_env_ceiling(CODE_DEFAULT_CHAR_LIMIT)

    # Build the rich notice from the plan metadata. Fail-safe: fall back to the
    # limit-only page notice if anything goes wrong.
    notice = None
    try:
        meta = _load_plan_meta()
        notice = _build_text_notice(level, meta, get_subscribed_char_limit(),
                                    translated=translated)
    except Exception as e:
        logger.warning(f"[TRUNCATION] Could not build plan notice for {user_id}: {e}")
        notice = None

    return _truncate_to_limit(text, limit, notice=notice)


# ---------------------------------------------------------------------------
# Public helpers for the translation path (LOCAL-708B / D670 addendum)
# ---------------------------------------------------------------------------

def build_text_notice_for_user(user_id, translated=False):
    """Public: the on-screen D670 notice string for a listener's plan.

    Returns the notice WITH its leading '\\n\\n' separator, or '' on error. Only
    meaningful when the article was truncated. Used by the translation service,
    which builds the English notice then translates it into the listener's
    language (English fallback if translation fails / the app isn't localised).
    """
    try:
        level = _resolve_level_for_user(user_id)
        meta = _load_plan_meta()
        return _build_text_notice(level, meta, get_subscribed_char_limit(),
                                  translated=translated)
    except Exception as e:
        logger.warning(f"[TRUNCATION] Could not build text notice for {user_id}: {e}")
        return ""


def truncate_for_user_with_notice(text, user_id, notice):
    """Public: truncate `text` to the listener's plan limit, appending a
    caller-supplied `notice` verbatim (already localised by the caller).

    Used by the translation service so the translated article carries the
    notice in the listener's language rather than the English default.

    Returns (truncated_text, was_truncated, rule_used).
    """
    if not text:
        return text, False, 'none'
    try:
        limit = get_article_limit_for_user(user_id)
    except Exception as e:
        logger.warning(
            f"[TRUNCATION] Could not determine plan limit for {user_id}: {e} "
            f"— code default ({CODE_DEFAULT_CHAR_LIMIT})"
        )
        limit = _apply_env_ceiling(CODE_DEFAULT_CHAR_LIMIT)
    return _truncate_to_limit(text, limit, notice=notice)

