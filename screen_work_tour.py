"""[LOCAL-744] An honest filming-location disclosure for screen/book-work tours.

Michael, 2026-10-23, asked for "the episode 1 of season 1 biking tour, Salem, MA"
— WGN America's *Salem* (2014), S1E1 "The Vow". The show was filmed in Shreveport,
Louisiana, so **none of the Salem places a tour visits ever appears on screen**.
The old generator ignored "episode 1 of season 1" and shipped a generic Salem
bike tour with no acknowledgement of this at all.

Michael's priority (2026-10-23 11:3x): *"The tour will say so when the show was
filmed elsewhere — this is the most important part."* He was happy with the Salem
stops and their stories, so this module does NOT touch stop selection. It adds the
one piece that was missing: a single, honest opening in the Orientation that states,
**from a sourced fact**, where the work was filmed and how this tour relates to it.

Three outcomes, and only three:

  1. The work was filmed ELSEWHERE than the toured place, and we have a source:
       "The TV series Salem (WGN America, 2014) was filmed in Shreveport, Louisiana,
        not in Salem, so none of these places appears on screen. This tour visits the
        real Salem, where the story is set."

  2. The toured place IS (one of) the filming location(s), and we have a source:
       "Parts of <work> were filmed in <place>; this tour visits those locations."
     Never claim a specific scene without a source.

  3. We cannot source where it was filmed:
       "We could not confirm where <work> was filmed."
     — never a guess (Michael: "never guess").

A PLAIN place request ("Salem, MA biking tour") names no work, so NO disclosure is
added — no false positives.

Design mirrors geo_refutation.py: the network/LLM lookup is INJECTED, so this
module is pure and its tests run offline. The caller (generate_tour_text) supplies
a real lookup that returns a sourced fact or signals "unknown"; this module decides
what sentence, if any, the Orientation opens with, and splices it in.
"""

import re
from typing import Callable, Dict, Optional


# ── Intent detection ─────────────────────────────────────────────────────────

# A season/episode reference is itself a screen-work signal even when no title is
# written: "episode 1 of season 1", "s1e1", "season 2 episode 3", "the pilot".
_SEASON_EPISODE_RE = re.compile(
    r'\b(?:'
    r's\d+\s*e\d+'                                 # s1e1
    r'|season\s+\d+\s*(?:,|\s)+\s*episode\s+\d+'   # season 1, episode 1
    r'|episode\s+\d+\s+of\s+season\s+\d+'          # episode 1 of season 1
    r'|season\s+\d+\s+episode\s+\d+'               # season 1 episode 1
    r'|\bepisode\s+\d+\b'                          # episode 1
    r'|\bthe\s+pilot\b'                            # the pilot (episode)
    r')',
    re.IGNORECASE,
)

# Words that, in a tour request, name a dramatic/literary WORK rather than a place
# or an activity. Kept deliberately small and specific so a street called "Book
# Street" or a "Movie Theater district" tour does not trip it on its own — these
# only contribute when the request also carries a theme signal (see detect).
_WORK_KEYWORDS = (
    'tv show', 'tv series', 'television series', 'television show',
    'miniseries', 'mini-series', 'sitcom', 'episode', 'season',
    'movie', 'film', 'the movie', 'the film',
    'novel', 'the book', 'book by', 'story by', 'short story',
    'based on the', 'inspired by the', 'filming location', 'filming locations',
    'filmed', 'shot on location',
)

# theme_type values (from analyze_tour_intent) that mean "this is about a work".
_WORK_THEME_TYPES = {'BOOK', 'MOVIE', 'TV', 'FILM', 'SERIES'}


def detect_screen_work(user_request: str, intent: Optional[Dict] = None) -> Optional[Dict]:
    """Return a work descriptor when the request is about a TV/film/book work.

    Returns a dict ``{"theme_type", "theme_name", "signal"}`` or ``None``.

    Two independent signals, OR'd together:
      * ``intent.theme_type`` is BOOK/MOVIE/TV/FILM/SERIES (the LLM intent pass
        already classified it as a themed tour and may carry ``theme_name``);
      * the raw request text carries a season/episode reference or a work keyword
        — this catches "episode 1 of season 1 … Salem, MA", which names NO title
        but is unmistakably a screen-work request (the exact 716 miss).

    A plain place request ("Salem, MA biking tour") matches neither and returns
    None — no disclosure, no false positive.
    """
    req = user_request or ''
    req_lower = req.lower()
    intent = intent or {}

    theme_type = (intent.get('theme_type') or '').strip().upper()
    theme_name = (intent.get('theme_name') or '').strip() or None

    # A season/episode reference is the STRONGEST and most specific signal, and it
    # is unambiguously television. It overrides the intent pass's theme_type (the
    # live LOCAL-744 run showed intent classify "episode 1 of season 1 … Salem"
    # as MOVIE, which then mis-framed the work as a film). Detect it up front.
    _has_season_episode = bool(_SEASON_EPISODE_RE.search(req))

    # A theme_name that is really just the episode/season phrase (no title was
    # typed) is NOT a usable title — drop it so we never say "the film episode 1
    # of season 1". The sourced lookup supplies the real title.
    if theme_name and (_SEASON_EPISODE_RE.search(theme_name)
                       or re.fullmatch(r'(?i)[\s,]*(?:the\s+)?(?:episode|season|pilot|'
                                       r's\d+e\d+)[\s\d,]*', theme_name or '')):
        theme_name = None

    signal = None
    if _has_season_episode:
        signal = 'season/episode reference in request'
        theme_type = 'TV'
    elif theme_type in _WORK_THEME_TYPES:
        signal = f'intent.theme_type={theme_type}'
    else:
        # A bare work keyword counts only as a screen/book signal, not as proof of
        # a place name — but it is enough to WANT a disclosure. Require a clear
        # keyword so "a book shop tour" alone does not trip it.
        for kw in _WORK_KEYWORDS:
            if kw in req_lower:
                signal = f'work keyword: {kw!r}'
                break

    if not signal:
        return None

    # Best-effort theme_type when the intent pass did not set one but the text did.
    if theme_type not in _WORK_THEME_TYPES:
        if _SEASON_EPISODE_RE.search(req) or any(
                k in req_lower for k in ('tv show', 'tv series', 'episode', 'season',
                                         'sitcom', 'miniseries')):
            theme_type = 'TV'
        elif any(k in req_lower for k in ('movie', 'film')):
            theme_type = 'MOVIE'
        elif any(k in req_lower for k in ('novel', 'book', 'story')):
            theme_type = 'BOOK'
        else:
            theme_type = 'WORK'

    return {'theme_type': theme_type, 'theme_name': theme_name, 'signal': signal}


# ── Disclosure construction ──────────────────────────────────────────────────

def _norm_place(s: str) -> str:
    """Casefold + collapse whitespace + drop trailing punctuation for comparison."""
    return re.sub(r'\s+', ' ', (s or '').strip().lower()).strip(' .,;:')


def _toured_place_label(location: str) -> str:
    """Human label for the toured place, stripped of tour-type/theme noise.

    "episode 1 of season 1 biking tour, Salem, MA" → "Salem".
    "the episode 1 of season 1 tour, Shreveport, Louisiana" → "Shreveport".
    Prefers the first comma-separated segment that looks like a proper place name;
    falls back to the last capitalised token run.
    """
    raw = location or ''
    # Remove parentheticals and the obvious request noise.
    cleaned = re.sub(r'\([^)]*\)', ' ', raw)
    _NOISE = re.compile(
        r'\b(?:the\s+)?(?:episode|season)\s+\d+(?:\s+of\s+(?:season\s+)?\d+)?\b'
        r'|\bs\d+\s*e\d+\b'
        r'|\b(?:biking|cycling|walking|driving|bike|walk|drive|driving|self[-\s]?guided|'
        r'audio|guided|tour|tours)\b',
        re.IGNORECASE,
    )
    # [LOCAL-749] A segment that names the WORK or the theme ("Salem TV series filming
    # locations", "real locations mentioned in Salem TV show") is never the place.
    # Drop those segments before choosing; keep the old behaviour if nothing is left.
    _THEME = re.compile(
        r'\b(?:tv|series|show|shows|film|films|filmed|filming|movie|movies|locations?|'
        r'mentioned|episodes?|seasons?|novel|book|story|stories|real)\b',
        re.IGNORECASE,
    )
    raw_segs = re.sub(r'\([^)]*\)', ' ', raw).split(',')
    place_segs = [_NOISE.sub(' ', seg) for seg in raw_segs if not _THEME.search(seg)]
    cleaned = _NOISE.sub(' ', cleaned)
    # Prefer a comma segment with a capitalised word (e.g. "Salem, MA").
    for seg in (place_segs or cleaned.split(',')):
        seg = seg.strip(' ,.-')
        if seg and re.search(r'[A-Z][a-z]+', seg):
            # Drop a trailing bare state abbreviation ("Salem MA" → "Salem").
            m = re.match(r'(.+?)[\s,]+[A-Z]{2}$', seg)
            city = (m.group(1) if m else seg).strip()
            if city:
                return city
    # Fallback: any capitalised run.
    caps = re.findall(r'[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*', cleaned)
    return caps[0].strip() if caps else (raw.split(',')[0].strip() if raw else '')


def _work_phrase(work: Dict, fact: Optional[Dict]) -> str:
    """How to NAME the work at the START of a sentence ("The TV series Salem").

    A sourced lookup can correct/complete the title (the request named no title at
    all for the 716 case); fall back to the intent's theme_name, else a generic
    "work" noun keyed off theme_type.
    """
    name = None
    if fact and isinstance(fact, dict):
        name = (fact.get('work_name') or '').strip() or None

    if not name:
        name = (work.get('theme_name') or '').strip() or None

    # A sourced lookup may correct the KIND too (the request's "episode/season"
    # heuristic can be wrong — e.g. the work turns out to be a film). Prefer the
    # lookup's work_kind when it supplied one.
    kind = None
    if fact and isinstance(fact, dict):
        _wk = (fact.get('work_kind') or '').strip().lower()
        kind = {'tv': 'TV series', 'tv series': 'TV series', 'series': 'TV series',
                'television series': 'TV series', 'miniseries': 'TV series',
                'film': 'film', 'movie': 'film',
                'book': 'book', 'novel': 'book'}.get(_wk)
    if not kind:
        tt = (work.get('theme_type') or '').upper()
        kind = {'TV': 'TV series', 'SERIES': 'TV series', 'MOVIE': 'film',
                'FILM': 'film', 'BOOK': 'book'}.get(tt, 'work')
    if name:
        return f'The {kind} {name}'
    return f'The {kind}'


def _work_phrase_mid(work: Dict, fact: Optional[Dict]) -> str:
    """Mid-sentence form of _work_phrase ("the TV series Salem")."""
    p = _work_phrase(work, fact)
    return 'the' + p[3:] if p.startswith('The ') else p


def _work_ref_noconfirm(work: Dict) -> str:
    """How to refer to the work in "we could not confirm where ___ was filmed",
    WITHOUT the lookup (so it never leans on an unconfirmed title).

    With a real title from intent: "the TV series Salem". Without one (the
    title-less "episode 1 of season 1" case): "this TV series" / "this film" /
    "this book" — natural, and it never invents a name.
    """
    name = (work.get('theme_name') or '').strip() or None
    tt = (work.get('theme_type') or '').upper()
    kind = {'TV': 'TV series', 'SERIES': 'TV series', 'MOVIE': 'film',
            'FILM': 'film', 'BOOK': 'book'}.get(tt, 'work')
    if name:
        return f'the {kind} {name}'
    return f'this {kind}'


def build_filming_disclosure(work: Dict, location: str,
                             lookup_fn: Callable[[Dict, str], Optional[Dict]]) -> Optional[str]:
    """Build the sourced Orientation opening for a screen/book-work tour.

    ``lookup_fn(work, location)`` is INJECTED (so this is pure/offline-testable).
    It returns one of:

      * ``{"filmed_place": "Shreveport, Louisiana", "source": "...", "work_name": "Salem"}``
        — where the work was filmed, with a source. ``work_name`` is optional.
      * ``{"filmed_here": True, "source": "...", "work_name": "..."}``
        — the toured place IS (a) filming location, with a source.
      * ``None`` (or a dict with no usable sourced place) — we could not confirm.

    A result is only trusted when it carries a ``source`` — an unsourced claim is
    treated as "could not confirm" (Michael: never guess).

    Returns the disclosure string (one or two sentences) or ``None`` when ``work``
    is falsy. It always returns SOMETHING for a real work — even "could not
    confirm" — because the honest framing is the whole point.
    """
    if not work:
        return None

    toured = _toured_place_label(location)
    try:
        fact = lookup_fn(work, location)
    except Exception:
        # A crashing lookup is inconclusive, never a licence to guess.
        fact = None

    fact = fact if isinstance(fact, dict) else None
    phrase = _work_phrase(work, fact)          # "The TV series Salem"
    mid = _work_phrase_mid(work, fact)         # "the TV series Salem"

    # Guard: a usable fact must carry a source. No source → cannot confirm.
    sourced = fact is not None and (fact.get('source') or '').strip()

    if not sourced:
        return f"We could not confirm where {_work_ref_noconfirm(work)} was filmed."

    # Case 2: the toured place is itself a filming location.
    if fact.get('filmed_here'):
        where = (fact.get('filmed_place') or toured or 'here').strip()
        return (f"Parts of {mid} were filmed in {where}; "
                f"this tour visits those real places.")

    filmed_place = (fact.get('filmed_place') or '').strip()
    if not filmed_place:
        # Sourced but no place extracted — treat as cannot-confirm (never guess).
        return f"We could not confirm where {_work_ref_noconfirm(work)} was filmed."

    # The sourced filming place CONTAINS the toured place → it was filmed here.
    if toured and _norm_place(toured) in _norm_place(filmed_place):
        return (f"Parts of {mid} were filmed in {filmed_place}; "
                f"this tour visits those real places.")

    # Case 1: filmed elsewhere than the toured place.
    not_here = f", not in {toured}" if toured else ""
    tail = (f" This tour visits the real {toured}, where the story is set."
            if toured else " This tour visits the real places where the story is set.")
    return (f"{phrase} was filmed in {filmed_place}{not_here}, "
            f"so none of these places appears on screen.{tail}")


# ── Injection into the Orientation ───────────────────────────────────────────

_ORIENTATION_LABEL_RE = re.compile(r'(?mi)^(\s*Orientation:\s*)')


def inject_orientation_disclosure(final_text: str, disclosure: str) -> str:
    """Splice ``disclosure`` in as the FIRST sentence(s) of the Orientation.

    Prefers an explicit "Orientation:" label (the generator's first-stop opening
    carries one — see tour 716). When present, the disclosure is inserted right
    after the label so it leads the spoken opening. When no label exists (some
    templates open the first stop without one), the disclosure is prepended to the
    first non-empty narrative paragraph after the stop header.

    Idempotent-ish: if the disclosure text already appears verbatim, the text is
    returned unchanged (never doubled).
    """
    if not final_text or not disclosure:
        return final_text
    if disclosure.strip() and disclosure.strip() in final_text:
        return final_text

    disclosure = disclosure.strip()

    m = _ORIENTATION_LABEL_RE.search(final_text)
    if m:
        insert_at = m.end()
        return final_text[:insert_at] + disclosure + ' ' + final_text[insert_at:]

    # No "Orientation:" label — prepend to the first narrative paragraph that
    # follows the first stop header ("Stop 1: …" or "Stop 1 is …").
    lines = final_text.split('\n')
    seen_stop1 = False
    for i, line in enumerate(lines):
        if not seen_stop1:
            if re.match(r'^\s*Stop\s+1\b', line):
                seen_stop1 = True
            continue
        stripped = line.strip()
        if not stripped:
            continue
        # Skip the structured field lines; land on the first prose paragraph.
        if re.match(r'^(Address|Coordinates|Type/Specialty|Specific Examples|'
                    r'Directions|GPS Coordinates):', stripped):
            continue
        lines[i] = disclosure + ' ' + line
        return '\n'.join(lines)

    # No stop structure found at all — open the whole text with the disclosure.
    return disclosure + '\n\n' + final_text


def inject_named_place_after_welcome(final_text: str, sentence: str) -> str:
    """Place the LOCAL-799 named-place sentence AFTER the welcome, as its OWN
    paragraph — never inside a stop's Orientation line.

    The "welcome" is the tour-level prolog ("You are about to embark on a journey
    …") that opens Stop 1. On tour 467 the LOCAL-751 code spliced the announcement
    into the Orientation LINE, so the listener heard "We could not confirm …" as
    the first thing on the route. The ticket wants one natural sentence that reads
    after the welcome, e.g. "One place you asked for, White Sand Dunes, could not
    be confirmed, so it isn't included."

    Placement, in order of preference:
      1. Right after the prolog/welcome paragraph (located structurally via
         prolog_structure_validator.extract_prolog_from_tour_content), as a new
         paragraph.
      2. If no prolog is found, after the Stop 1 Orientation PARAGRAPH (the block
         ending at the blank line after "Orientation:"), as a new paragraph —
         still outside the Orientation line itself.
      3. If no stop structure is found, open the whole text with the sentence.

    Idempotent: if the sentence already appears verbatim, the text is returned
    unchanged (never doubled).
    """
    if not final_text or not sentence:
        return final_text
    sentence = sentence.strip()
    if not sentence or sentence in final_text:
        return final_text

    # 1) After the welcome/prolog paragraph.
    try:
        from prolog_structure_validator import extract_prolog_from_tour_content
        prolog = (extract_prolog_from_tour_content(final_text) or "").strip()
    except Exception:
        prolog = ""
    if prolog:
        # The prolog may be stored as one or more paragraphs; anchor on its LAST
        # paragraph so we land immediately after the whole welcome.
        last_para = prolog.split('\n\n')[-1].strip()
        idx = final_text.find(last_para)
        if idx != -1:
            insert_at = idx + len(last_para)
            return (final_text[:insert_at] + '\n\n' + sentence
                    + final_text[insert_at:])

    # 2) After the Stop 1 Orientation PARAGRAPH (not inside the line).
    m = re.search(r'Orientation:\s*.+?(?:\n\n|\Z)', final_text, re.DOTALL)
    if m:
        insert_at = m.end()
        sep = '' if final_text[:insert_at].endswith('\n\n') else '\n\n'
        return (final_text[:insert_at].rstrip('\n') + '\n\n' + sentence
                + '\n\n' + final_text[insert_at:].lstrip('\n')) \
            if final_text[insert_at:].strip() else \
            (final_text[:insert_at].rstrip('\n') + '\n\n' + sentence + '\n')

    # 3) No stop structure — open the text with the sentence.
    return sentence + '\n\n' + final_text
