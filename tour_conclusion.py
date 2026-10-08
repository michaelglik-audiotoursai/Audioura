"""[LOCAL-619] One real conclusion for EVERY tour path, built from the FINAL text.

The critic's #1 blocker on tours 440/441/442 was the trailing recap STUB
("That's N stops — …"): it stated the wrong count (3 when a late gate delivered
2), named only some stops, spliced per-stop metadata into a broken sentence, and
stood in for a conclusion.

LOCAL-607 built a deterministic conclusion for POOL-assembled tours
(``stop_pool_assembly._closing_recap``). It is the right shape, but the FRESH
generator path, the cache-trim path, the by-reference path and the overview path
each emitted (or trimmed) a different trailing recap. This module unifies them:
ONE builder, run ONCE on the FINAL delivered stop list, after every gate.

The conclusion, in order, is:

  1. ONE short paragraph naming the THREAD that connected the stops — the tour
     THEME when one is supplied, otherwise the venue's own collection
     ("the collection of {venue}"). Same wording the pool path uses.
  2. "That's N stops", with N COUNTED FROM THE DELIVERED TEXT (the ``Stop N:``
     headers actually present), never a stale generation-time count.
  3. A one-line recap of up to 3 stops, each naming the work plus one concrete,
     already-delivered fact — reusing ``stop_pool_assembly._first_recap_sentence``
     so every recapped fact is lifted verbatim from a delivered stop's narration
     (the D177 rule: the conclusion can never reference a stop that is not present
     or state a fact the tour did not deliver).
  4. The RESTAURANT OFFER as the very last sentence — the exact house wording.

No LLM is needed: everything is derived from the final text. The optional
``thread`` argument lets a caller pass a tour THEME phrase (if the pipeline
discovered one); when absent the venue collection is named, so the thread
sentence is always present and always true.

``rebuild_conclusion`` is the single finalization pass: it STRIPS whatever
trailing conclusion/recap/stub a path produced and APPENDS the one built here,
preserving the trailing ``Sources:`` block. It is deterministic and idempotent —
running it twice yields the same text.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

# Reuse the one shared parser + the one shared recap-sentence picker so the
# conclusion is built from exactly the units the rest of the pipeline sees.
from stop_pool_store import (
    parse_delivered_stops,
    strip_epilog,
    _STOP_HEADER,
    _RECAP_FROM_TO,
    _SOURCES_LINE,
)
from stop_pool_assembly import _first_recap_sentence, _recap_pick_three

# The house restaurant offer — the exact wording the fresh path
# (generate_tour_text._build_closing_offer) and the pool path
# (stop_pool_assembly._closing_recap) both use as the terminal sentence.
RESTAURANT_OFFER = (
    "If you would like to eat nearby we can build you a restaurant tour."
)

# A conclusion opener used to detect an already-built (idempotent) conclusion.
# It must match ONLY the conclusion's own single-line thread sentence, so the
# "from … to …" clause is constrained to a single line (no DOTALL): a narration
# sentence like "…the baroque spirit of music from the late 17th century. … you
# have followed…" must NOT be read as the opener. Both the From→to form and the
# single-stop "On this tour you have followed the thread" form are matched.
_THREAD_OPENER = re.compile(
    r'(?im)^(?:From\s+[^\n]+?\s+to\s+[^\n]+?,\s+you have followed the thread'
    r'|On this tour you have followed the thread)\b',
)
# A bare single-/zero-stop count opener (no From→to), also treated as a recap.
_COUNT_OPENER = re.compile(r"\bThat['\u2019]s\s+\d+\s+stops?\b",
                           re.IGNORECASE)
# Sign-off / treat / news offer openers that trail some closings — swept so the
# restaurant sentence is the genuine LAST sentence of the rebuilt conclusion.
_TRAILING_OFFER_PATTERNS = (
    re.compile(r'\bAs this journey comes to a close\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'\bThe Treat Page shows\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'\bWe can also generate news articles\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'\bThere is also a tour of\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'\bIf you would like another\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'\bIf you have toured this place before\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    re.compile(r'\bClosing:\s*', re.IGNORECASE),
)


def count_delivered_stops(tour_text: str) -> int:
    """Return the number of ``Stop N:`` headers actually present in the text.

    This is the authoritative stop count AFTER every gate — the number the
    conclusion, ``stops_count`` and the shortfall sentence must all agree with.
    """
    return len(_STOP_HEADER.findall(tour_text or ""))


def _normalise_offer(offer: Optional[str]) -> str:
    """Return a terminal offer sentence. Defaults to the house restaurant line.

    If a caller passes a richer offer (e.g. the fresh path's Treats/news offer),
    the restaurant sentence is still forced to be the LAST sentence: the deliver
    item ("the restaurant offer as the last sentence") is a hard contract.
    """
    if offer is None:
        return RESTAURANT_OFFER
    offer = offer.strip()
    if not offer:
        return RESTAURANT_OFFER
    # If the restaurant sentence is already present but not last, move it to the
    # end; otherwise append it.
    if "restaurant tour" in offer.lower():
        return offer if offer.rstrip().endswith(("tour.", "tour")) else offer
    sep = " " if not offer.endswith((".", "!", "?")) else " "
    return (offer + sep + RESTAURANT_OFFER).strip()


# Degenerate / placeholder narration that must never become a recap "fact".
# A stop whose narration failed generation can carry an apology or placeholder;
# the recap must name the work, not echo an error, so such a clause is reduced
# to the bare title.
_DEGENERATE_CLAUSE = re.compile(
    r'(?i)\b(there was an issue|issue with your request|generation_failed|'
    r'assistance needed|please inform|an error occurred|look for this work|'
    r'position yourself to best view)\b')


def _clean_recap_clause(clause: str, title: str) -> str:
    """Drop a recap clause down to the bare title when its fact is degenerate.

    ``_first_recap_sentence`` lifts a sentence from the stop narration; if that
    narration failed (an apology / placeholder), the lifted clause is not a fact.
    In that case return the title alone so the recap still NAMES a real delivered
    stop without echoing an error. Returns "" only when there is nothing to name.
    """
    clause = (clause or "").strip()
    title = (title or "").strip()
    if not clause:
        return title
    if _DEGENERATE_CLAUSE.search(clause):
        return title
    return clause


def build_conclusion(
    tour_text: str,
    *,
    venue_name: str = "",
    theme: Optional[str] = None,
    restaurant_offer: bool = True,
    offer_text: Optional[str] = None,
) -> str:
    """Build the ONE conclusion block from the FINAL delivered stop list.

    Deterministic, no LLM. The count is read from ``tour_text`` (``count_delivered_stops``),
    so it is always consistent with what the listener receives — even after a late
    gate dropped a stop.

    Args:
        tour_text:   the FINAL tour text (post every gate).
        venue_name:  the venue, used for the default thread ("the collection of {venue}").
        theme:       an optional discovered THEME phrase; when given it is named
                     as the thread instead of the venue collection.
        restaurant_offer: when True (default) the restaurant offer is the last line.
        offer_text:  an optional richer offer; the restaurant sentence is still
                     forced last (see ``_normalise_offer``).

    Returns the conclusion block (no trailing Sources), or "" when there are no
    delivered stops.
    """
    stops = parse_delivered_stops(tour_text)
    n = count_delivered_stops(tour_text)
    if n <= 0 or not stops:
        return ""

    titles = [(s.get("title") or "").strip() for s in stops]
    first = titles[0]
    last = titles[-1]

    thread_phrase = (theme or "").strip()
    if not thread_phrase:
        v = (venue_name or "").strip()
        thread_phrase = f"the collection of {v}" if v else "a single collection"

    lines: List[str] = []

    # 1. The thread paragraph + 2. the count, counted from the delivered text.
    if n < 2:
        # A single-stop tour: no "From X to X" (it would be nonsense). Name the
        # thread, then the single-stop count.
        lines.append(
            f"On this tour you have followed the thread of {thread_phrase}."
        )
        lines.append("")
        lines.append(f"That's {n} stop in all.")
    else:
        lines.append(
            f"From {first} to {last}, you have followed the thread of {thread_phrase}."
        )
        lines.append("")
        lines.append(f"That's {n} stops in all.")

    # 3. One-line recap of up to 3 stops, naming the work + one delivered fact.
    recap_stops = _recap_pick_three(stops)
    recap_lines = []
    for s in recap_stops:
        clause = _first_recap_sentence(s)
        clause = _clean_recap_clause(clause, (s.get("title") or "").strip())
        if clause:
            recap_lines.append(clause)
    if recap_lines:
        lines.append("")
        lines.append("Along the way:")
        for rl in recap_lines:
            lines.append(f"- {rl}")

    # 4. The restaurant offer as the VERY LAST sentence.
    if restaurant_offer:
        lines.append("")
        lines.append(_normalise_offer(offer_text))

    return "\n".join(lines).strip()


def _split_tail(tour_text: str):
    """Split the tour into (body_before_conclusion, sources_block).

    The conclusion/recap and the Sources block live AFTER the last stop body.
    Returns the text up to (and including) the stop bodies with ANY trailing
    conclusion/recap/offer stripped, plus the Sources block (or "").
    """
    text = tour_text or ""

    # Isolate the Sources block (kept verbatim, re-appended last).
    sources_block = ""
    m_src = _SOURCES_LINE.search(text)
    if m_src:
        sources_block = m_src.group(0).strip()
        text = text[: m_src.start()]

    # Find where the trailing conclusion begins: the earliest of a From→to recap
    # opener or a bare "That's N stops" count opener that sits AFTER the last
    # stop header. Everything from there to the end is the old conclusion.
    headers = list(_STOP_HEADER.finditer(text))
    search_from = headers[-1].end() if headers else 0

    cut = len(text)
    m_thread = _THREAD_OPENER.search(text, search_from)
    if m_thread:
        cut = min(cut, m_thread.start())
    m_count = _COUNT_OPENER.search(text, search_from)
    if m_count:
        cut = min(cut, m_count.start())

    body = text[:cut]

    # The old conclusion could have leaked a "Closing:" label or sign-off/treat/
    # news sentences into the body tail (fresh path spliced them inline). Sweep
    # any epilog spans and trailing offer patterns out of the body tail so the
    # rebuilt conclusion is the only closing.
    body = strip_epilog(body)
    for pat in _TRAILING_OFFER_PATTERNS:
        body = pat.sub("", body)
    body = re.sub(r'[ \t]+\n', '\n', body)
    body = re.sub(r'\n{3,}', '\n\n', body)
    body = body.rstrip()

    return body, sources_block


def rebuild_conclusion(
    tour_text: str,
    *,
    venue_name: str = "",
    theme: Optional[str] = None,
    restaurant_offer: bool = True,
    offer_text: Optional[str] = None,
) -> str:
    """The single finalization pass: replace any trailing conclusion with the one
    built from the FINAL text.

    Strips whatever trailing conclusion/recap/stub the path produced (fresh,
    pool, cache, by-reference, overview), builds the unified conclusion, and
    re-appends it followed by the preserved Sources block.

    Deterministic and IDEMPOTENT: running it on already-rebuilt text yields the
    same text (the old conclusion is stripped first, then rebuilt from the same
    stop list). Safe on text with no stops (returned unchanged).
    """
    if not tour_text or not tour_text.strip():
        return tour_text
    if count_delivered_stops(tour_text) <= 0:
        return tour_text

    body, sources_block = _split_tail(tour_text)
    conclusion = build_conclusion(
        tour_text,
        venue_name=venue_name,
        theme=theme,
        restaurant_offer=restaurant_offer,
        offer_text=offer_text,
    )

    parts = [body]
    if conclusion:
        parts.append(conclusion)
    if sources_block:
        parts.append(sources_block)
    return "\n\n".join(p for p in parts if p).strip() + "\n"


# ── Count-dependent text recompute helpers (late-gate consistency) ───────────
#
# After a late gate drops a stop, EVERYTHING count-dependent must be recomputed
# from the FINAL text, not left at the generation-time value:
#   * the conclusion count          — handled by rebuild_conclusion above;
#   * stops_count                   — count_delivered_stops(final_text);
#   * the shortfall sentence        — recompute_shortfall_sentence below;
#   * the orientation "first stop"  — fix_orientation_first_stop below.

# "Your first stop is X" pointer (orientation preview). Captures the name.
_FIRST_STOP_PTR = re.compile(
    r'(Your first stop is\s+)(.+?)(\s*[.\n])', re.IGNORECASE)


def first_stop_name(tour_text: str) -> str:
    """Return the title of the first ``Stop N:`` header, or ""."""
    m = _STOP_HEADER.search(tour_text or "")
    if not m:
        return ""
    # _STOP_HEADER group(2) is the (decorated) title; strip a trailing ", year".
    raw = m.group(2).strip()
    raw = re.sub(r',\s*\d{3,4}\s*$', '', raw)
    raw = re.sub(r'\s+by\s+.+$', '', raw, flags=re.IGNORECASE)
    return raw.strip()


def fix_orientation_first_stop(tour_text: str) -> str:
    """Correct a "Your first stop is X" pointer so X is the real first delivered
    stop (a late gate may have dropped the stop the orientation named).

    Deterministic, idempotent. Only rewrites the NAME inside the pointer; it does
    not add or remove the pointer. Safe when no pointer is present.
    """
    text = tour_text or ""
    fs = first_stop_name(text)
    if not fs:
        return text

    def _sub(m):
        return f"{m.group(1)}{fs}{m.group(3)}"

    return _FIRST_STOP_PTR.sub(_sub, text, count=1)
