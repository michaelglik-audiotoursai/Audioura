"""[LOCAL-619] One real conclusion for EVERY tour path, built from the FINAL text.

[LOCAL-619B / Michael D634, 2026-10-07] The conclusion is about the TOUR, not a
list of stops. Michael: "Naming all stops, especially if there are more than 3,
will be very annoying to the listeners: the conclusion should be about our tour:
what are the common elements in the stops and the theme of the tour."

LOCAL-619 (merged) replaced the broken "That's N stops — …" splice, but its
conclusion still ENUMERATED: "From X to Y, you have followed the thread … That's
N stops in all. Along the way, a few moments stand out. <stop>: … <stop>: …". For
a 4-stop tour that reads as a roll-call. This module replaces it with a THEMATIC
conclusion — 2 to 4 sentences, about the tour as a whole:

  (a) the THREAD or THEME the stops shared — the tour theme if one was chosen
      (SQ-S6b / theme_thread_discoverer), otherwise derived from the stops'
      common elements (period, movement, subject, place, the people connecting
      them);
  (b) ONE line of MEANING — why it matters, or what to take away;
  (c) OPTIONALLY one named example as an illustration, NEVER a list — at most a
      single delivered title appears in the whole conclusion;
  (d) the stop COUNT may be stated ONLY if it is correct (it is counted from the
      delivered text, so when present it is always correct);
  (e) the RESTAURANT OFFER is the last sentence — the exact house wording.

There is no "From X to Y". A cheap LLM (gpt-4o-mini) may write (a)+(b) FROM THE
DELIVERED STOPS' TEXT ONLY, metered via ``cost_accumulator`` (the network meter).
It must contain NO fact that is not in the delivered text; that is enforced with
the existing claim/G4 machinery (``claim_check.check_paragraph`` against the
delivered stops as the corpus), and on ANY failure — no key, network error, an
unsupported claim, a smuggled stop list, a "From…to…" — the builder FALLS BACK to
a deterministic thematic template built from the stops' common elements. The
template is also what ships when no API key is available, so the conclusion is
always present and always true.

``build_conclusion`` builds the block; ``rebuild_conclusion`` is the single
finalization pass: it STRIPS whatever trailing conclusion/recap/stub a path
produced (the LOCAL-619 From→to form, a pool/overview closing, a "That's N
stops" splice) and APPENDS the one built here, preserving the trailing
``Sources:`` block. Deterministic template path is idempotent; the LLM path is
only taken on the first build (``rebuild`` strips an existing thematic opener and
would re-call the LLM, so the every-path caller passes ``use_llm`` only once —
see the wiring note on ``rebuild_conclusion``).
"""

from __future__ import annotations

import os
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

# Conclusion openers used to detect an already-built conclusion so a rebuild
# STRIPS it before appending the freshly-built one. Three families are matched,
# all anchored to the start of a line (no DOTALL) so a narration sentence can
# never be mistaken for the conclusion:
#   * the NEW thematic openers this module now writes (``_THEMATIC_OPENER``);
#   * the LEGACY LOCAL-619 "From X to Y / On this tour you have followed the
#     thread" openers (so a cached/pooled tour's old enumerating conclusion is
#     replaced, not duplicated);
#   * a bare "That's N stops" count opener (``_COUNT_OPENER``).
# ``_THREAD_OPENER`` is the union used by ``_split_tail`` to find where any old
# conclusion begins.

# The deterministic thematic template's first sentence always begins with one of
# these stems; the LLM-written opener is constrained (by prompt + validation) to
# begin with one too, so a rebuilt tour's conclusion is detectable and strippable.
_THEMATIC_LEAD_STEMS = (
    "This tour",
    "Across these stops",
    "Across the stops",
    "Taken together",
    "Together, these",
    "Together these",
    "What connects",
    "The works on this tour",
    "The stops on this tour",
    "On this tour",          # also the legacy single-stop lead
)
_THEMATIC_OPENER = re.compile(
    r'(?im)^(?:' + '|'.join(re.escape(s) for s in _THEMATIC_LEAD_STEMS) + r')\b')

# Legacy LOCAL-619 thread openers (From→to and the single-stop form). Kept so a
# rebuild of a tour that still carries the OLD enumerating conclusion strips it.
_LEGACY_THREAD_OPENER = re.compile(
    r'(?im)^(?:From\s+[^\n]+?\s+to\s+[^\n]+?,\s+you have followed the thread'
    r'|On this tour you have followed the thread)\b',
)
# Union opener: the earliest of a thematic or a legacy thread opener marks where
# any trailing conclusion begins.
_THREAD_OPENER = re.compile(
    r'(?im)^(?:' + '|'.join(re.escape(s) for s in _THEMATIC_LEAD_STEMS) + r'\b'
    r'|From\s+[^\n]+?\s+to\s+[^\n]+?,\s+you have followed the thread\b'
    r'|On this tour you have followed the thread\b)',
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


# A ``Stop N:`` header that got glued onto the end of the previous sentence —
# e.g. a final-stop transition "…: Atelierwand.Stop 3: Atelierwand" where the
# newline before the header was lost. The counter and parser key on a line-start
# header, so a glued header silently vanishes from the count (the listener still
# hears the stop). Match a sentence-ending punctuation immediately followed by a
# "Stop N:" header and re-break the line.
_GLUED_STOP_HEADER = re.compile(r'(?<=[.!?])\s*(Stop\s+\d+:\s)')


def normalise_stop_headers(tour_text: str) -> str:
    """Restore a line break before any ``Stop N:`` header glued to prior text.

    Deterministic and idempotent. A header already at line-start is untouched.
    This makes the stop COUNT reflect every stop the listener actually hears,
    even when an upstream render lost the newline before a header (the live
    '…Atelierwand.Stop 3: Atelierwand' defect).
    """
    if not tour_text:
        return tour_text
    out = _GLUED_STOP_HEADER.sub(r'\n\n\1', tour_text)
    # Collapse any 3+ newline run the re-break may create.
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out


def count_delivered_stops(tour_text: str) -> int:
    """Return the number of ``Stop N:`` headers actually present in the text.

    This is the authoritative stop count AFTER every gate — the number the
    conclusion, ``stops_count`` and the shortfall sentence must all agree with.
    A header glued onto a prior sentence is first re-broken so it is counted
    (see ``normalise_stop_headers``).
    """
    return len(_STOP_HEADER.findall(normalise_stop_headers(tour_text or "")))


def has_thematic_conclusion(tour_text: str) -> bool:
    """True when the text already carries a THEMATIC conclusion this module wrote.

    The every-path finalization guard uses this so the cheap LLM is invoked ONLY
    on the first build (no thematic opener yet). On a re-run or a cache hit the
    opener is already present, so the guard rebuilds deterministically — the
    opener is stripped and re-appended from the same stops — and never re-spends.
    A LEGACY (From→to) conclusion returns False, so a cached tour that still
    carries the old enumerating closing is upgraded to the thematic form once.
    """
    text = normalise_stop_headers(tour_text or "")
    headers = list(_STOP_HEADER.finditer(text))
    search_from = headers[-1].end() if headers else 0
    # [LEAD 2026-10-08] A thematic opener FOLLOWED (or preceded) by a legacy
    # enumerating recap is NOT a correct conclusion: the pool path
    # (stop_pool_assembly._closing_recap) appended "From X to Y… That's N stops…
    # Along the way:" after the fresh thematic one, and the guard preserved both
    # (Museum Folkwang canary, tour 468). Any legacy marker → rebuild.
    if (_LEGACY_THREAD_OPENER.search(text, search_from)
            or re.search(r'(?im)^Along the way:', text[search_from:])):
        return False
    return _THEMATIC_OPENER.search(text, search_from) is not None


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


def _ensure_period(s: str) -> str:
    """Return the clause terminated by a single sentence-ending mark."""
    s = (s or "").strip()
    if not s:
        return s
    return s if s.endswith((".", "!", "?")) else s + "."


# [LOCAL-620 item 6b / D634] Close an unclosed example quote and put the
# sentence's terminator AFTER the closing quote. The LOCAL-619B single-example
# sentence (and, more often, the cheap-LLM thematic body) could drop the closing
# quote on a titled work — the live Dürer conclusion read:
#   … as seen in Dürer's "Ritter, Tod und Teufel. That's 4 stops …
# which leaves the quotation open for the rest of the tour. This balancer scans
# the conclusion block for an opening double-quote with no matching close and
# inserts the closing quote at the end of that quoted span, moving a trailing
# period to sit AFTER the quote (English convention, and what the ticket asks).
_OPEN_DQUOTE = '"'
# curly quotes the LLM sometimes emits
_CURLY_OPEN = "\u201c"
_CURLY_CLOSE = "\u201d"


def balance_quotes(text: str) -> str:
    """Close an unbalanced double-quote in ``text`` and place the period after it.

    Deterministic and idempotent. Handles straight (") and curly (" ") quotes.
    When the number of opening quotes exceeds closings, the final quoted span is
    closed at the end of its sentence (before the sentence terminator), and the
    terminator is re-emitted AFTER the closing quote. Balanced text is returned
    unchanged.
    """
    if not text:
        return text

    # Normalise count across straight + curly. We only repair the common case:
    # exactly one more opener than closer (a single dropped closing quote).
    straight = text.count(_OPEN_DQUOTE)
    curly_open = text.count(_CURLY_OPEN)
    curly_close = text.count(_CURLY_CLOSE)

    # Case A: straight quotes — odd count means one is unclosed.
    if straight % 2 == 1:
        # find the last opening straight quote
        last_open = text.rfind(_OPEN_DQUOTE)
        if last_open == -1:
            return text
        after = text[last_open + 1:]
        # the quoted span runs to the next sentence terminator; close before it
        m = re.search(r'[.!?]', after)
        if m:
            cut = last_open + 1 + m.start()
            terminator = text[cut]
            repaired = (text[:cut].rstrip()
                        + _OPEN_DQUOTE + terminator
                        + text[cut + 1:])
        else:
            # no terminator — append a closing quote at the very end
            repaired = text.rstrip() + _OPEN_DQUOTE
        return repaired

    # Case B: curly quotes — more opens than closes.
    if curly_open > curly_close:
        last_open = text.rfind(_CURLY_OPEN)
        if last_open == -1:
            return text
        after = text[last_open + 1:]
        m = re.search(r'[.!?]', after)
        if m:
            cut = last_open + 1 + m.start()
            terminator = text[cut]
            repaired = (text[:cut].rstrip()
                        + _CURLY_CLOSE + terminator
                        + text[cut + 1:])
        else:
            repaired = text.rstrip() + _CURLY_CLOSE
        return repaired

    return text


# Degenerate / placeholder narration that must never become a recap "fact".
# A stop whose narration failed generation can carry an apology or placeholder;
# the recap must name the work, not echo an error, so such a clause is reduced
# to the bare title.
_DEGENERATE_CLAUSE = re.compile(
    r'(?i)\b(there was an issue|issue with your request|generation_failed|'
    r'assistance needed|please inform|an error occurred|look for this work|'
    r'position yourself to best view|sources?\s*\(|https?://)\b')


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


# [LOCAL-619 #critic] Provenance / accession / institutional-history openers that
# must NOT become the recap "fact". The shared ``_first_recap_sentence`` tries to
# skip these, but its stem list is wrapped as ``\b(acquir|donat|…)\b`` — the
# TRAILING ``\b`` makes each stem fail on the inflected forms that actually occur
# ("acquired", "donated", "founded"), so an accession sentence ("In 1905 … was
# acquired by the museum from …") leaked in as the lead recap fact on the live
# Thyssen/Kunsthalle tours and the critic flagged it (criterion 1/6). This stem
# list has NO trailing boundary, so it matches the inflected forms, and it is
# applied HERE (in the LOCAL-619 module) so the shared pool-path helper and its
# 590/607 tests are untouched.
_PROVENANCE_LEAD = re.compile(
    r'\b(acquir\w*|donat\w*|bequeath\w*|bequest|gifted|gift of|'
    r'reloca\w*|renam\w*|founded|establish\w*|'
    r'entered the\s+\w+\s+collection|part of\s+\w+(?:\'s)?\s+'
    r'(?:private\s+)?collection|accession\w*)\b', re.IGNORECASE)

# A recap sentence should describe the WORK or tell its STORY, not recite
# dimensions/dates alone. Dimensions-only sentences ("…dimensions of 111 by 79
# centimetres") read as filler in a closing (criterion 6) and are deprioritised.
_DIMENSIONS_ONLY = re.compile(
    r'\bdimensions?\b|\bmeasures?\b|\d+\s*(?:by|x|×)\s*\d+\s*(?:cm|centimet)',
    re.IGNORECASE)

# Orientation / viewing-instruction sentences address the LISTENER in the gallery
# ("stand before …", "position yourself …", "as you step closer …"). They belong
# in the stop body, not in a backward-looking recap, so they are rejected here.
_VIEWING_INSTRUCTION = re.compile(
    r'\b(stand before|stand at|position yourself|as you (?:stand|step|approach|'
    r'move|look|enter)|take in the|lean in|from this vantage|look (?:up|closer)|'
    r'notice how|observe the|take a moment)\b', re.IGNORECASE)

_DANGLING_LEAD = re.compile(
    r'^(however|this|that|these|those|it|they|he|she|here|'
    r'such|moreover|thus|hence|as a result|before this|also|and|but)\b',
    re.IGNORECASE)


def _pick_recap_clause(stop: Dict) -> str:
    """Pick ONE recap clause for a stop that NAMES the work and tells its most
    concrete STORY — not an accession/provenance line, and NOT a verbatim copy of
    the stop's own opening sentence.

    The critic's residual complaint after the count was fixed was that the recap
    (a) led with a dry accession fact and (b) repeated the stop's opening sentence
    verbatim, so the close read as a "re-read the dullest line of each stop" list
    rather than a conclusion. This picker:

      1. skips provenance/accession/institutional-history sentences (corrected
         stem matching — see ``_PROVENANCE_LEAD``);
      2. skips the stop's OWN first delivered sentence (kills the verbatim repeat);
      3. skips dangling-pronoun openers (a recap line must stand alone);
      4. prefers a sentence that reads as a story/description; dimensions-only
         sentences are taken only as a last resort;
      5. falls back to the shared ``_first_recap_sentence`` then the bare title,
         so the recap ALWAYS names a real, delivered stop and never fabricates.

    Returns a self-contained "{Title}: {clause}." string (or the title alone).
    """
    title = (stop.get("title") or "").strip()
    narration = (stop.get("narration") or "").strip()
    if not narration:
        return title

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', narration)
                 if s.strip()]
    lead = sentences[0] if sentences else ""

    def _norm(s: str) -> str:
        return re.sub(r'\s+', ' ', s or '').strip().lower().rstrip('.')

    lead_norm = _norm(lead)

    best = ""
    fallback_dims = ""
    for s in sentences:
        if not (30 <= len(s) <= 220):
            continue
        if _norm(s) == lead_norm:           # (2) never echo the stop's opener
            continue
        if _PROVENANCE_LEAD.search(s):      # (1) no accession/provenance lead
            continue
        if _DANGLING_LEAD.match(s):         # (3) must stand alone
            continue
        if _VIEWING_INSTRUCTION.search(s):  # (3b) not a gallery instruction
            continue
        if _DIMENSIONS_ONLY.search(s):      # (4) dimensions-only → last resort
            if not fallback_dims:
                fallback_dims = s
            continue
        best = s
        break

    if not best:
        best = fallback_dims

    if not best:
        # (5) fall back to the shared picker, then title.
        shared = _first_recap_sentence(stop)
        return _clean_recap_clause(shared, title)

    clause = best.rstrip('.')
    if clause.lower().startswith(title.lower()):
        return _clean_recap_clause(clause + ".", title)
    return _clean_recap_clause(f"{title}: {clause}.", title)


def build_conclusion(
    tour_text: str,
    *,
    venue_name: str = "",
    theme: Optional[str] = None,
    restaurant_offer: bool = True,
    offer_text: Optional[str] = None,
    use_llm: bool = False,
    llm_fn=None,
    api_key: Optional[str] = None,
) -> str:
    """Build the ONE **thematic** conclusion block from the FINAL delivered stops.

    [LOCAL-619B / D634] The conclusion is about the TOUR, not a list of stops. It
    is 2 to 4 sentences:

      (a) the THREAD or THEME the stops shared — the discovered tour ``theme`` when
          one is supplied, else a phrase derived from the stops' COMMON ELEMENTS
          (shared period/century, movement, subject, place, or connecting people),
          else the venue's own collection;
      (b) one line of MEANING — why the thread matters / what to take away;
      (c) OPTIONALLY one named example (a single delivered title), never a list;
      (d) the stop COUNT, stated only when correct (it is counted from the
          delivered text, so it is always correct when present);
      (e) the RESTAURANT OFFER as the last sentence.

    There is NO "From X to Y" and NO per-stop roll-call.

    By default the body (a)+(b) is produced by a DETERMINISTIC template built from
    the common elements. When ``use_llm`` is True and an API key / ``llm_fn`` is
    available, a cheap LLM (gpt-4o-mini) writes (a)+(b) FROM THE DELIVERED STOPS'
    TEXT ONLY, metered via ``cost_accumulator``; the draft is accepted only if it
    passes the claim/G4 check (no fact absent from the delivered text), contains
    no "From…to…", and names at most one delivered title. On ANY failure the
    deterministic template is used instead.

    Args:
        tour_text:   the FINAL tour text (post every gate).
        venue_name:  the venue, used as a last-resort thread ("the collection of {venue}").
        theme:       an optional discovered THEME phrase; preferred as the thread.
        restaurant_offer: when True (default) the restaurant offer is the last line.
        offer_text:  an optional richer offer; the restaurant sentence is still last.
        use_llm:     when True, try the cheap-LLM writer first (validated; falls back).
        llm_fn:      optional callable(prompt, api_key) -> str for the LLM pass
                     (defaults to the house gpt-4o-mini client). Injected in tests.
        api_key:     OpenAI key; defaults to ``OPENAI_API_KEY`` from the environment.

    Returns the conclusion block (no trailing Sources), or "" when there are no
    delivered stops.
    """
    tour_text = normalise_stop_headers(tour_text)
    stops = parse_delivered_stops(tour_text)
    n = count_delivered_stops(tour_text)
    if n <= 0 or not stops:
        return ""

    titles = [(s.get("title") or "").strip() for s in stops if (s.get("title") or "").strip()]

    # The thread phrase: discovered theme > derived common element > venue collection.
    common = _derive_common_elements(stops, venue_name=venue_name)
    thread_phrase = (theme or "").strip() or common.get("thread_phrase") or ""
    if not thread_phrase:
        v = (venue_name or "").strip()
        thread_phrase = f"the collection of {v}" if v else "this collection"

    # Build the thematic body (a)+(b)[+c]. Try the LLM first when asked; validate
    # against the delivered stops; fall back to the deterministic template.
    body = ""
    if use_llm:
        body = _llm_thematic_body(
            stops, thread_phrase=thread_phrase, theme=(theme or "").strip(),
            venue_name=venue_name, titles=titles,
            llm_fn=llm_fn, api_key=api_key)
    if not body:
        body = _template_thematic_body(
            stops, thread_phrase=thread_phrase, theme=(theme or "").strip(),
            common=common, titles=titles, n=n)

    # (d) The count, only when correct — appended as its own short sentence so it
    #     is optional and never an enumeration. Omit for a 1-stop overview (a
    #     count sentence on a single stop reads oddly and adds nothing thematic).
    count_sentence = ""
    if n >= 2:
        count_sentence = f"That's {n} stops in all."

    lines: List[str] = []
    para = _ensure_period(body)
    # [LOCAL-620 item 6b] Close any unclosed example quote and move the period
    # after it (the live Dürer "Ritter, Tod und Teufel. defect).
    para = balance_quotes(para)
    if count_sentence:
        para = (para + " " + count_sentence).strip()
    lines.append(para)

    # (e) The restaurant offer as the VERY LAST sentence.
    if restaurant_offer:
        lines.append("")
        lines.append(_normalise_offer(offer_text))

    return "\n".join(lines).strip()


# ── Common-element derivation (deterministic, no network) ────────────────────
#
# When no theme was discovered the thread must still be TRUE and about the tour.
# We derive it from what the delivered stops SHARE: a common century/period, a
# recurring subject word, or a connecting person. Everything is lifted from the
# delivered narration so the thread never states a fact the tour did not deliver.

_CENTURY_WORD = {
    15: "fifteenth", 16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
    19: "nineteenth", 20: "twentieth", 21: "twenty-first",
}

# Subject / genre words that, when shared across stops, make a true thematic
# thread. Each maps to the noun phrase used in the thread sentence.
_SUBJECT_WORDS = {
    "portrait": "portraiture", "portraits": "portraiture",
    "landscape": "landscape", "landscapes": "landscape",
    "still life": "still life", "still-life": "still life",
    "seascape": "the sea", "marine": "the sea",
    "mytholog": "myth and allegory", "allegor": "myth and allegory",
    "religious": "religious devotion", "biblical": "religious devotion",
    "sacred": "religious devotion", "altarpiece": "religious devotion",
    "history painting": "history painting",
    "nude": "the human figure", "figure": "the human figure",
    "sculpture": "sculpture", "sculptures": "sculpture",
    "impressionis": "Impressionism", "cubis": "Cubism",
    "baroque": "the Baroque", "renaissance": "the Renaissance",
    "romantic": "Romanticism", "realis": "realism",
    "abstract": "abstraction", "modern": "modern art",
}


def _derive_common_elements(stops: List[Dict], *, venue_name: str = "") -> Dict:
    """Derive the stops' COMMON ELEMENTS from the delivered narration.

    Returns a dict with:
      thread_phrase : a short noun phrase for the thread sentence, or "";
      meaning       : a one-line "why it matters" clause keyed to the thread;
      shared_terms  : the concrete shared terms found (for the template body);
      period_label  : a human century/period label when stops share one, or "".
    All values are grounded in the delivered text (no invention).
    """
    narrations = [(s.get("narration") or "") for s in stops]
    joined = " \n ".join(narrations)
    low = joined.lower()
    n_stops = len([s for s in stops if (s.get("title") or "").strip()])

    # Shared century: a century that appears in the narration of >= 2 stops (or
    # the only century present on a 1-stop overview).
    def _centuries(text: str) -> set:
        cents = set()
        for y in re.findall(r'\b(1[0-9]{3}|20[0-2][0-9])\b', text):
            cents.add((int(y) - 1) // 100 + 1)
        for m in re.finditer(r'\b(\d{1,2})(?:st|nd|rd|th)\s+century\b', text,
                             re.IGNORECASE):
            cents.add(int(m.group(1)))
        return cents

    per_stop_cents = [_centuries(t) for t in narrations]
    cent_counts: Dict[int, int] = {}
    for cset in per_stop_cents:
        for c in cset:
            cent_counts[c] = cent_counts.get(c, 0) + 1
    shared_cents = sorted(c for c, k in cent_counts.items()
                          if k >= max(2, 1 if n_stops == 1 else 2))
    period_label = ""
    if shared_cents:
        if len(shared_cents) == 1:
            w = _CENTURY_WORD.get(shared_cents[0])
            if w:
                period_label = f"the {w} century"
        else:
            lo = _CENTURY_WORD.get(min(shared_cents))
            hi = _CENTURY_WORD.get(max(shared_cents))
            if lo and hi:
                period_label = f"the {lo} to {hi} centuries"

    # Shared subject/genre: a subject word present in >= 2 stops' narration.
    subject_phrase = ""
    subj_hits: Dict[str, int] = {}
    for text in narrations:
        tl = text.lower()
        seen = set()
        for key, phrase in _SUBJECT_WORDS.items():
            if key in tl and phrase not in seen:
                subj_hits[phrase] = subj_hits.get(phrase, 0) + 1
                seen.add(phrase)
    shared_subjects = sorted((p for p, k in subj_hits.items() if k >= 2),
                             key=lambda p: -subj_hits[p])
    if shared_subjects:
        subject_phrase = shared_subjects[0]

    # Assemble the thread phrase from the strongest shared element.
    thread_phrase = ""
    if subject_phrase and period_label:
        thread_phrase = f"{subject_phrase} in {period_label}"
    elif subject_phrase:
        thread_phrase = subject_phrase
    elif period_label:
        v = (venue_name or "").strip()
        thread_phrase = (f"the art of {period_label} at {v}" if v
                         else f"the art of {period_label}")

    # A one-line meaning keyed to the thread (generic but TRUE; it asserts no
    # fact about any specific work, only the value of having followed the thread).
    if subject_phrase:
        meaning = (f"Seen together, the works show how differently that subject "
                   f"could be imagined.")
    elif period_label:
        meaning = (f"Set side by side, they trace how taste and technique shifted "
                   f"across {period_label}.")
    else:
        meaning = ("Taken together, the stops add up to more than any one of them "
                   "seen alone.")

    return {
        "thread_phrase": thread_phrase,
        "meaning": meaning,
        "shared_terms": shared_subjects + ([period_label] if period_label else []),
        "period_label": period_label,
        "subject_phrase": subject_phrase,
    }


def _template_thematic_body(
    stops: List[Dict], *, thread_phrase: str, theme: str, common: Dict,
    titles: List[str], n: int,
) -> str:
    """Deterministic thematic body (a)+(b)[+c] — the fallback and the no-key path.

    Produces 2 sentences: the THREAD sentence and the MEANING sentence. When the
    thread is a derived/venue phrase (not a strong subject/period), ONE delivered
    title may be named as a single illustrative example — never a list, never
    "From X to Y".
    """
    thread_phrase = (thread_phrase or "this collection").strip()
    meaning = common.get("meaning") or (
        "Taken together, the stops add up to more than any one of them seen alone.")

    # (a) THREAD — "This tour drew together …". No From→to, no roll-call.
    if theme:
        thread_sentence = f"This tour followed one thread: {thread_phrase}."
    else:
        thread_sentence = f"Across these stops, one thread runs through: {thread_phrase}."

    # (c) OPTIONAL single example — only when the thread is generic (no strong
    # subject/period element), to keep the close concrete. At most ONE title.
    example_sentence = ""
    strong = bool(common.get("subject_phrase") or common.get("period_label"))
    if not strong and titles:
        example = _best_example_title(stops) or titles[0]
        if example:
            example_sentence = f"{example} is one you might carry with you."

    parts = [thread_sentence, meaning]
    if example_sentence:
        parts.append(example_sentence)
    return " ".join(_ensure_period(p) for p in parts if p).strip()


def _best_example_title(stops: List[Dict]) -> str:
    """Pick ONE delivered title to name as the single illustrative example.

    Prefers a stop whose narration carries a concrete, non-provenance story (so
    the one named work is a memorable one), else the first delivered title.
    """
    for s in stops:
        title = (s.get("title") or "").strip()
        narration = (s.get("narration") or "").strip()
        if not title or not narration:
            continue
        sentences = [x.strip() for x in re.split(r'(?<=[.!?])\s+', narration)
                     if x.strip()]
        for sent in sentences[1:]:
            if not (30 <= len(sent) <= 220):
                continue
            if _PROVENANCE_LEAD.search(sent) or _DIMENSIONS_ONLY.search(sent):
                continue
            if _VIEWING_INSTRUCTION.search(sent) or _DANGLING_LEAD.match(sent):
                continue
            return title
    for s in stops:
        title = (s.get("title") or "").strip()
        if title:
            return title
    return ""


# ── Cheap-LLM thematic writer (metered) + claim/G4 validation ────────────────

_LLM_THEMATIC_PROMPT = """You are writing the CLOSING of an audio museum tour. The listener has just
heard {n} short stops. Below is the FULL delivered narration of every stop.

DELIVERED STOPS:
{stops_block}

Write a 2-sentence conclusion ABOUT THE TOUR AS A WHOLE — not a list of the
stops. Sentence 1 names the common THREAD or THEME connecting the stops ({thread_hint}).
Sentence 2 says in one line why that thread matters or what to take away.

HARD RULES:
- Use ONLY facts that appear in the delivered narration above. State NO date,
  name, place, number or claim that is not already in that text.
- Do NOT list the stops. Name AT MOST ONE work, and only as a single example.
- Do NOT write "From X to Y". Do NOT count the stops.
- Begin sentence 1 with "This tour", "Across these stops", or "Together, these".
- Keep it under 60 words total. Return ONLY the two sentences, nothing else."""


def _default_thematic_llm(prompt: str, api_key: str) -> Optional[str]:
    """One gpt-4o-mini chat-completion, metered via cost_accumulator. Returns the
    assistant text or None on any failure. Mirrors the house gate client."""
    if not api_key:
        return None
    import json as _json
    try:
        import requests as _req
    except Exception:
        return None
    model = os.environ.get("CONCLUSION_LLM_MODEL", "gpt-4o-mini")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}"}
    data = {
        "model": model,
        "messages": [
            {"role": "system",
             "content": "You write audio-tour closings. Use only the facts given."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
        "max_tokens": 160,
    }
    try:
        resp = _req.post("https://api.openai.com/v1/chat/completions",
                         headers=headers, data=_json.dumps(data), timeout=30)
        if resp.status_code != 200:
            return None
        j = resp.json()
        text = j["choices"][0]["message"]["content"].strip()
        # Meter the call via the tour's cost accumulator (the network meter).
        try:
            import cost_accumulator
            usage = j.get("usage", {}) or {}
            cost_accumulator.add_llm_usage(
                int(usage.get("prompt_tokens", 0) or 0),
                int(usage.get("completion_tokens", 0) or 0),
                model)
        except Exception:
            pass
        return text
    except Exception:
        return None


def _llm_thematic_body(
    stops: List[Dict], *, thread_phrase: str, theme: str, venue_name: str,
    titles: List[str], llm_fn=None, api_key: Optional[str] = None,
) -> str:
    """Ask a cheap LLM to write (a)+(b) from the delivered stops' text ONLY, then
    VALIDATE the draft with the existing claim/G4 machinery. Returns the accepted
    body, or "" to signal the caller should fall back to the template.

    A draft is REJECTED (→ "") when it:
      * is empty / unparseable;
      * contains a "From … to …" construction;
      * names more than one delivered title (an enumeration);
      * states the stop count;
      * carries a factual claim NOT supported by the delivered narration
        (``claim_check.check_paragraph`` with the delivered stops as the corpus).
    """
    api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
    fn = llm_fn or _default_thematic_llm
    if not api_key and llm_fn is None:
        return ""

    stops_block = "\n\n".join(
        f"Stop {i+1}: {(s.get('title') or '').strip()}\n{(s.get('narration') or '').strip()}"
        for i, s in enumerate(stops)
    )
    thread_hint = (f"the chosen theme is \"{theme}\"" if theme
                   else f"for example {thread_phrase}" if thread_phrase
                   else "derive it from what the works share")
    prompt = _LLM_THEMATIC_PROMPT.format(
        n=len([s for s in stops if (s.get("title") or "").strip()]),
        stops_block=stops_block[:12000],
        thread_hint=thread_hint,
    )

    try:
        draft = fn(prompt, api_key)
    except Exception:
        return ""
    if not draft or not draft.strip():
        return ""
    draft = draft.strip().strip('"').strip()

    if not _thematic_draft_ok(draft, stops=stops, titles=titles,
                              venue_name=venue_name):
        return ""
    return draft


def _thematic_draft_ok(draft: str, *, stops: List[Dict], titles: List[str],
                       venue_name: str) -> bool:
    """Validate an LLM-written thematic body. True iff it is safe to ship."""
    low = draft.lower()

    # No "From … to …" construction (the enumerating opener the ticket bans).
    if re.search(r'\bfrom\s+.+?\s+to\s+.+?,', draft, re.IGNORECASE):
        return False
    # Must not state the stop count.
    if re.search(r"that['\u2019]?s\s+\d+\s+stops?|\b\d+\s+stops?\b", low):
        return False
    # Name AT MOST ONE delivered title (no enumeration / roll-call).
    named = 0
    for t in titles:
        tnorm = re.sub(r'\s+', ' ', t).strip()
        if len(tnorm) < 4:
            continue
        if re.search(r'\b' + re.escape(tnorm) + r'\b', draft, re.IGNORECASE):
            named += 1
    if named > 1:
        return False

    # The claim/G4 check: NO factual claim absent from the delivered narration.
    # The delivered stops' narration IS the corpus; a draft that smuggles any new
    # date/number/attribution/proper-noun predicate is rejected.
    try:
        import claim_check
        passages = [(s.get("narration") or "").strip() for s in stops
                    if (s.get("narration") or "").strip()]
        result = claim_check.check_paragraph(
            draft, stop_title="", venue_name=(venue_name or ""),
            passages=passages, other_stop_passages=None)
        vc = result.get("verdict_counts", {}) or {}
        bad = int(vc.get("unsupported", 0)) + int(vc.get("contradicted", 0))
        if bad > 0:
            return False
    except Exception:
        # If the checker cannot run, be conservative and reject the LLM draft so
        # the deterministic (always-true) template ships instead.
        return False
    return True


# [LOCAL-620 item 6c / D634] Drop an ORPHAN one-sentence paragraph that names a
# work which is NOT one of the delivered stops. Städel (tour 462) carried, between
# the last stop body and the conclusion, a stray one-line paragraph:
#   "Hieronymus Bosch's 'Ecce Homo' was created around 1476."
# — a leftover after G4 removed sentences, naming a work the tour never delivered.
# This is a different KIND of defect from the conclusion recap: it sits in the
# body tail. We remove any one-sentence paragraph AFTER the last Stop header whose
# only named work is not among the delivered stop titles.

# A quoted or titled work reference inside a paragraph: 'X', "X", or a
# "<Artist>'s <Title>" possessive construction.
_QUOTED_WORK_RE = re.compile(r"['\u2018\u201c\"]([^'\u2019\u201d\"]{3,80})['\u2019\u201d\"]")


def _paragraph_names_only_undelivered_work(paragraph: str,
                                           delivered_titles: List[str]) -> bool:
    """True when a one-sentence paragraph's named work is NOT a delivered stop.

    Conservative: only fires when the paragraph is a SINGLE sentence, names a
    quoted/titled work, and NONE of the delivered titles appears in it. A
    paragraph that mentions a delivered title (even in passing) is kept.
    """
    p = (paragraph or "").strip()
    if not p:
        return False
    # single sentence only
    sents = [s for s in re.split(r'(?<=[.!?])\s+', p) if s.strip()]
    if len(sents) != 1:
        return False
    quoted = _QUOTED_WORK_RE.findall(p)
    if not quoted:
        return False
    low = p.lower()
    for t in delivered_titles:
        tn = re.sub(r'\s+', ' ', (t or '')).strip().lower()
        if len(tn) >= 4 and tn in low:
            return False  # names a delivered work — keep
        # also match the quoted span against the delivered title
        for q in quoted:
            qn = re.sub(r'\s+', ' ', q).strip().lower()
            if len(qn) >= 4 and (qn in tn or tn in qn):
                return False
    return True


def drop_orphan_work_paragraphs(tour_text: str) -> "tuple[str, Dict]":
    """Remove orphan one-sentence paragraphs (naming an undelivered work) that sit
    AFTER the last delivered stop body.

    Deterministic, idempotent. Returns (new_text, report). The region scanned is
    only the tail after the last ``Stop N:`` header, so stop bodies and the
    conclusion/Sources are never touched by this pass (the caller runs it on the
    body before the conclusion is built).
    """
    report = {"dropped": 0}
    text = tour_text or ""
    if not text.strip():
        return text, report

    delivered_titles = []
    for m in _STOP_HEADER.finditer(text):
        raw = (m.group(2) if m.lastindex and m.lastindex >= 2 else m.group(0)).strip()
        raw = re.sub(r',\s*\d{3,4}\s*$', '', raw)
        raw = re.sub(r'\s+by\s+.+$', '', raw, flags=re.IGNORECASE)
        if raw:
            delivered_titles.append(raw.strip())

    headers = list(_STOP_HEADER.finditer(text))
    if not headers:
        return text, report
    last_end = headers[-1].end()

    head = text[:last_end]
    tail = text[last_end:]

    # Split the tail into paragraphs, drop orphan ones.
    paras = re.split(r'(\n\s*\n)', tail)
    out_paras = []
    dropped = 0
    for seg in paras:
        if seg.strip() == "" or re.fullmatch(r'\n\s*\n', seg):
            out_paras.append(seg)
            continue
        if _paragraph_names_only_undelivered_work(seg, delivered_titles):
            dropped += 1
            continue
        out_paras.append(seg)
    report["dropped"] = dropped
    if dropped == 0:
        return text, report
    new_tail = "".join(out_paras)
    new_text = head + new_tail
    new_text = re.sub(r'\n{3,}', '\n\n', new_text)
    return new_text, report


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

    # Find where the trailing conclusion begins: the earliest of a thematic/legacy
    # thread opener or a bare "That's N stops" count opener that sits AFTER the
    # last stop header. Everything from there to the end is the old conclusion.
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
    # [LOCAL-620 item 6c] Drop an orphan one-sentence paragraph (naming an
    # undelivered work) that sits after the last stop body (the Städel 462 defect).
    body, _orphan_rep = drop_orphan_work_paragraphs(body)
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
    use_llm: bool = False,
    llm_fn=None,
    api_key: Optional[str] = None,
) -> str:
    """The single finalization pass: replace any trailing conclusion with the one
    built from the FINAL text.

    Strips whatever trailing conclusion/recap/stub the path produced (fresh,
    pool, cache, by-reference, overview) — the LOCAL-619 From→to form, a pool /
    overview closing, or a "That's N stops" splice — builds the unified THEMATIC
    conclusion, and re-appends it followed by the preserved Sources block.

    ``use_llm`` (with ``llm_fn`` / ``api_key``) asks ``build_conclusion`` to let a
    cheap LLM write the thematic body (validated by the claim/G4 check, falling
    back to the deterministic template). The DETERMINISTIC path is idempotent;
    the LLM path is non-deterministic, so an every-path caller should pass
    ``use_llm=True`` ONCE on the first build and leave it False on any re-run (the
    thematic opener is still stripped and rebuilt deterministically on re-runs).

    Safe on text with no stops (returned unchanged).
    """
    if not tour_text or not tour_text.strip():
        return tour_text
    # Recover any ``Stop N:`` header glued onto a prior sentence so the count and
    # the parsed stop list reflect every stop the listener actually hears.
    tour_text = normalise_stop_headers(tour_text)
    if count_delivered_stops(tour_text) <= 0:
        return tour_text

    body, sources_block = _split_tail(tour_text)
    conclusion = build_conclusion(
        tour_text,
        venue_name=venue_name,
        theme=theme,
        restaurant_offer=restaurant_offer,
        offer_text=offer_text,
        use_llm=use_llm,
        llm_fn=llm_fn,
        api_key=api_key,
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
