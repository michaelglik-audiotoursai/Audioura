#!/usr/bin/env python3
"""theme_stop_guard.py — LOCAL-650 fix 1.

A WALKING-tour stop must be a real, geocodable PLACE, never the request's THEME.

Michael, 2026-10-09 (tours 557 and the Oct-6 baseline, both the request
"Walking tour in Boston dedicated to Massachusetts politics and current affairs,
Boston, MA", 5 stops):

    Stop 5 = "Massachusetts politics and current affairs", Address N/A.

The request's THEME phrase had become a point of interest. A POI must be a real
place a listener can stand at. A candidate whose NAME is the request's theme
phrase — or a subset of it — must be rejected and replaced by a real place that
fits the theme. The same goes for any TOPIC-LIKE name: a phrase with no proper
noun of a place in it, or one that joins abstract nouns with "and"
("politics and current affairs", "power and public engagement").

This module is pure, deterministic and offline. It is used two ways:

  * As DETECTORS at selection time (``is_theme_phrase_stop`` / ``topic_like_name``)
    so the generator never promotes a theme phrase to a stop, and in the Phase 3A
    prompt as an explicit constraint.
  * As a FINAL, every-path TEXT guard on the delivered tour
    (``rename_theme_phrase_stops``) that recovers the request theme from the tour's
    own title line, finds a stop whose header is the theme phrase (or topic-like),
    and renames it to a REAL place — preferring a proper-noun place the stop's own
    narration already names (tour 557's Stop 5 narration names "University of
    Massachusetts Boston", which is exactly where its coordinates sit), then a
    theme-appropriate curated fallback. The stop keeps its coordinates and body;
    only the misleading header (and, when derivable, the Address) changes.

Nothing here calls the network or an LLM.
"""
import re
from typing import List, Optional, Tuple

try:
    from stop_pool_store import _STOP_HEADER, _SOURCES_LINE
except Exception:  # pragma: no cover - defensive fallback
    _STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)
    _SOURCES_LINE = re.compile(r'(?ms)^\s*Sources:\s.*\Z')


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation and request-theme recovery
# ─────────────────────────────────────────────────────────────────────────────

# Words we drop before comparing a stop name to a theme phrase: tour-form words,
# articles, prepositions. "Walking tour in Boston dedicated to <theme>" becomes
# "<theme>" once these and the city tail are stripped.
_STOP_WORDS = {
    'a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or', 'with',
    'tour', 'tours', 'walking', 'walk', 'self', 'guided', 'self-guided', 'audio',
    'dedicated', 'about', 'themed', 'theme', 'around', 'near', 'through',
    'exploring', 'discover', 'featuring',
}

# Lead-in phrases that introduce the theme in a request string.
_THEME_LEADIN_RE = re.compile(
    r'(?i)\b(?:dedicated\s+to|devoted\s+to|about|focused\s+on|focusing\s+on|'
    r'centered\s+on|centred\s+on|exploring|on\s+the\s+theme\s+of|themed\s+(?:on|around))\s+')

# A city/region tail: ", Boston, MA" / ", London, United Kingdom".
_CITY_TAIL_RE = re.compile(r',\s*[^,]+(?:,\s*[^,]+)?\s*$')

# Place-type nouns whose presence marks a name as naming a real PLACE, so it is
# NOT topic-like even if it also contains abstract words.
_PLACE_NOUNS = (
    'house', 'hall', 'square', 'park', 'garden', 'gardens', 'street', 'avenue',
    'bridge', 'library', 'museum', 'gallery', 'cathedral', 'church', 'chapel',
    'temple', 'synagogue', 'mosque', 'university', 'college', 'school',
    'institute', 'building', 'tower', 'monument', 'memorial', 'statue',
    'market', 'station', 'wharf', 'pier', 'dock', 'common', 'green', 'plaza',
    'court', 'courthouse', 'capitol', 'statehouse', 'state house', 'city hall',
    'theatre', 'theater', 'cemetery', 'burying', 'ground', 'fort', 'castle',
    'palace', 'estate', 'mansion', 'villa', 'center', 'centre', 'field',
    'stadium', 'arena', 'observatory', 'lighthouse', 'mill', 'factory',
    'warehouse', 'hotel', 'inn', 'tavern', 'club', 'society', 'academy',
    'basilica', 'abbey', 'priory', 'arch', 'gate', 'fountain', 'obelisk',
    'reservoir', 'lake', 'pond', 'river', 'harbor', 'harbour', 'bay', 'beach',
    'hill', 'point', 'island', 'quay', 'esplanade', 'promenade', 'boulevard',
    'road', 'lane', 'alley', 'walk', 'trail', 'path', 'yard', 'depot',
    'terminal', 'airport', 'exchange', 'bank', 'hospital', 'asylum', 'armory',
    'armoury', 'arsenal', 'barracks', 'embassy', 'consulate', 'residence',
)

# Abstract/topic nouns that, when joined by "and" with no place noun, signal a
# topic phrase rather than a place.
_ABSTRACT_HINTS = (
    'politics', 'affairs', 'history', 'culture', 'art', 'arts', 'science',
    'sciences', 'literature', 'music', 'architecture', 'religion', 'philosophy',
    'economy', 'economics', 'society', 'governance', 'government', 'law',
    'justice', 'reform', 'revolution', 'war', 'peace', 'trade', 'commerce',
    'industry', 'innovation', 'power', 'engagement', 'identity', 'heritage',
    'legacy', 'life', 'events', 'current affairs', 'current events', 'activism',
    'movement', 'movements', 'struggle', 'rights', 'freedom', 'democracy',
    'immigration', 'migration', 'labor', 'labour', 'education', 'health',
    'environment', 'nature', 'landscape', 'spirituality', 'faith', 'folklore',
    'legend', 'legends', 'myth', 'myths', 'tradition', 'traditions', 'theme',
    'topic', 'subject', 'overview', 'discussion', 'discussions', 'insights',
)


def _norm(s: str) -> str:
    """Lowercase, collapse whitespace, drop surrounding punctuation."""
    s = re.sub(r'\s+', ' ', (s or '').strip().lower())
    s = s.strip(' .,:;"\'()[]')
    return s


def _content_words(s: str) -> List[str]:
    """Significant words of a phrase (stop-words removed)."""
    toks = re.findall(r"[a-z0-9][a-z0-9'\-]*", _norm(s))
    return [t for t in toks if t not in _STOP_WORDS]


def extract_request_theme(text_or_request: str) -> str:
    """Recover the request's THEME phrase from a tour's title line or a raw request.

    "Step-by-Step Audio Guided Tour: Walking tour in Boston dedicated to
    Massachusetts politics and current affairs, Boston, MA"
        -> "Massachusetts politics and current affairs"

    When there is no explicit "dedicated to / about …" lead-in, returns "" (there
    is no distinct theme to protect against — a plain "Walking tour in Newton, MA"
    has no theme phrase that could wrongly become a stop).
    """
    s = (text_or_request or "").strip()
    if not s:
        return ""
    # If a full tour text was passed, take the title line.
    first_line = s.split("\n", 1)[0]
    m = re.match(r'(?i)^step-by-step[^:]*:\s*(.+)$', first_line)
    req = m.group(1).strip() if m else first_line.strip()
    # Drop a trailing city/region tail so the theme does not absorb ", Boston, MA".
    req_wo_city = _CITY_TAIL_RE.sub('', req).strip() or req
    m2 = _THEME_LEADIN_RE.search(req_wo_city)
    if not m2:
        return ""
    theme = req_wo_city[m2.end():].strip(' .,:;"\'')
    return theme


# ─────────────────────────────────────────────────────────────────────────────
# Detectors
# ─────────────────────────────────────────────────────────────────────────────

def is_theme_phrase_stop(stop_name: str, request_theme: str) -> bool:
    """True when ``stop_name`` IS the request theme phrase, or a subset of it.

    • Exact match after normalisation.
    • The stop name's content words are all contained in the theme phrase's content
      words (the stop is a slice of the theme — "current affairs" of
      "politics and current affairs").
    • The theme phrase's content words are all contained in the stop name
      (the stop restates the whole theme, possibly reordered).
    A stop that merely SHARES a word with the theme ("State House" vs a politics
    theme) is NOT flagged — it must be a subset in one direction.
    """
    sn = _norm(stop_name)
    th = _norm(request_theme)
    if not sn or not th:
        return False
    if sn == th:
        return True
    sw = set(_content_words(stop_name))
    tw = set(_content_words(request_theme))
    if not sw or not tw:
        return False
    # Subset in either direction, requiring at least 2 shared content words so a
    # single common word (e.g. "Boston") never trips it.
    if sw and sw.issubset(tw) and len(sw) >= 2:
        return True
    if tw and tw.issubset(sw) and len(tw) >= 2:
        return True
    return False


def _has_place_noun(name: str) -> bool:
    low = _norm(name)
    for pn in _PLACE_NOUNS:
        if re.search(r'\b' + re.escape(pn) + r'\b', low):
            return True
    return False


def _has_proper_place_token(name: str) -> bool:
    """A heuristic proper-noun signal: a Capitalised word that is NOT merely the
    first word of the phrase (so "Massachusetts politics" — only the first word is
    capitalised — does not count, but "Boston Common" or "Old State House" does).

    Possessives ("Paul Revere's") and multi-cap names ("JFK") also count.
    """
    words = (name or "").split()
    if not words:
        return False
    caps = [w for w in words if re.match(r"^[A-Z][A-Za-z'’.\-]*$", w)]
    # If any capitalised word appears after the first position, or there are >=2
    # capitalised words, treat it as a proper place name.
    if len(caps) >= 2:
        return True
    for i, w in enumerate(words):
        if i == 0:
            continue
        if re.match(r"^[A-Z][A-Za-z'’.\-]*$", w):
            return True
    return False


def topic_like_name(name: str) -> bool:
    """True when ``name`` reads like a TOPIC rather than a place.

    A name is topic-like when it has NO place noun and NO proper-noun place token
    AND either:
      • it joins words with "and" where an abstract/topic noun is present
        ("politics and current affairs", "power and public engagement"), or
      • it is built only from abstract/topic nouns ("political history",
        "state political landscape").
    A real place name ("Old State House", "Boston Common", "JFK Library") always
    has a place noun or a proper token, so it is never flagged.
    """
    n = _norm(name)
    if not n:
        return False
    if _has_place_noun(name):
        return False
    if _has_proper_place_token(name):
        return False
    low = n
    has_abstract = any(re.search(r'\b' + re.escape(a) + r'\b', low)
                       for a in _ABSTRACT_HINTS)
    if not has_abstract:
        return False
    # "and" joining words, OR a short all-abstract phrase.
    if re.search(r'\band\b', low):
        return True
    cw = _content_words(name)
    if cw and all(
        any(re.search(r'\b' + re.escape(a) + r'\b', w) or w == a
            for a in _ABSTRACT_HINTS) or w in _STOP_WORDS
        for w in cw
    ):
        return True
    # A 1–4 word abstract phrase with no place signal at all.
    if 1 <= len(cw) <= 4 and has_abstract:
        return True
    return False


def stop_name_is_not_a_place(stop_name: str, request_theme: str = "") -> bool:
    """Convenience predicate for selection: the name must be rejected because it is
    the theme phrase (when a theme is known) or because it is topic-like."""
    if request_theme and is_theme_phrase_stop(stop_name, request_theme):
        return True
    return topic_like_name(stop_name)


# ─────────────────────────────────────────────────────────────────────────────
# Deriving a real place to replace a theme-phrase stop
# ─────────────────────────────────────────────────────────────────────────────

# Theme-appropriate curated fallbacks, keyed by a topic token found in the theme.
# Used ONLY when the stop's own narration names no proper-noun place. Each is a
# real, geocodable place that fits the theme.
_CURATED_BY_TOPIC = {
    'politics': "Massachusetts State House",
    'political': "Massachusetts State House",
    'government': "Massachusetts State House",
    'governance': "Massachusetts State House",
    'affairs': "Boston Public Library",
    'history': "Old South Meeting House",
    'revolution': "Old South Meeting House",
    'literature': "Boston Public Library",
    'art': "Museum of Fine Arts, Boston",
}

# A proper-noun place phrase inside narration: a run of Capitalised words,
# optionally containing small joiners (of/the/and), ending on a place noun OR
# being a multi-word proper name. We extract candidates and prefer the one that
# carries a place noun.
_PROPER_RUN_RE = re.compile(
    r"\b([A-Z][A-Za-z'’.\-]+(?:\s+(?:of|the|and|de|du|la|le|at|for)\s+|\s+)"
    r"(?:[A-Z][A-Za-z'’.\-]+)(?:\s+(?:of|the|and)\s+[A-Z][A-Za-z'’.\-]+|\s+"
    r"[A-Z][A-Za-z'’.\-]+)*)")


def derive_real_place_from_block(block_text: str) -> str:
    """Find the best real PLACE named in a stop's own narration.

    Prefers the longest proper-noun run that contains a place noun (e.g.
    "University of Massachusetts Boston"); otherwise the longest proper-noun run.
    Returns "" when the narration names no proper place.
    """
    if not block_text:
        return ""
    # Strip the header and field lines; only look at narration/orientation prose.
    lines = []
    for ln in block_text.split("\n"):
        if _STOP_HEADER.match(ln):
            continue
        if re.match(r'(?i)^\s*(address|coordinates|type/specialty|specific '
                    r'examples|operational details|museum information|orientation|'
                    r'directions|sources?|hours|opening hours|visiting hours)\s*:',
                    ln):
            # keep the Orientation VALUE (prose after the label) — it often names
            # the place ("at the edge of the University of Massachusetts Boston").
            m = re.match(r'(?i)^\s*orientation\s*:\s*(.+)$', ln)
            if m:
                lines.append(m.group(1))
            continue
        lines.append(ln)
    prose = " ".join(l for l in lines if l.strip())
    cands = []
    for m in _PROPER_RUN_RE.finditer(prose):
        phrase = re.sub(r'\s+', ' ', m.group(1)).strip(' .,')
        if len(phrase.split()) < 2:
            continue
        cands.append(phrase)
    if not cands:
        return ""
    # Prefer a candidate carrying a place noun; among those, the longest.
    with_place = [c for c in cands if _has_place_noun(c)]
    pool = with_place or cands
    pool.sort(key=lambda c: (len(c.split()), len(c)), reverse=True)
    return pool[0]


def _curated_fallback(request_theme: str) -> str:
    tw = set(_content_words(request_theme))
    for topic, place in _CURATED_BY_TOPIC.items():
        if topic in tw:
            return place
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Every-path TEXT guard
# ─────────────────────────────────────────────────────────────────────────────

def _tour_category(text: str) -> str:
    m = re.search(r'(?im)^Tour-Category:\s*(.+?)\s*$', text or "")
    return _norm(m.group(1)) if m else ""


def _stop_blocks(text: str) -> List[Tuple[int, int, str]]:
    """[(start, end, header_name)] for each Stop block, body-only (before Sources)."""
    src = _SOURCES_LINE.search(text)
    end_body = src.start() if src else len(text)
    headers = [h for h in _STOP_HEADER.finditer(text) if h.start() < end_body]
    out = []
    for i, h in enumerate(headers):
        start = h.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else end_body
        out.append((start, end, h.group(2).strip()))
    return out


def find_theme_phrase_stops(text: str) -> List[Tuple[int, str, str]]:
    """Return [(stop_number, header_name, reason)] for stops that are the theme
    phrase or topic-like. Walking/outdoor tours only (museum headers are works)."""
    cat = _tour_category(text)
    if cat in ('museum', 'building', 'venue'):
        return []
    theme = extract_request_theme(text)
    out = []
    for (s, e, name) in _stop_blocks(text):
        num_m = _STOP_HEADER.match(text[s:e])
        num = int(num_m.group(1)) if num_m else 0
        if theme and is_theme_phrase_stop(name, theme):
            out.append((num, name, f"name is the request theme phrase '{theme}'"))
        elif topic_like_name(name):
            out.append((num, name, "name is topic-like (no proper place)"))
    return out


def rename_theme_phrase_stops(text: str,
                              curated_fallback: Optional[str] = None
                              ) -> Tuple[str, List[dict]]:
    """Rename any theme-phrase / topic-like WALKING stop to a real place.

    For each offending stop, choose a replacement name:
      1. a proper-noun place its own narration names (preferred — matches the
         stop's coordinates, as tour 557's Stop 5 narrates "University of
         Massachusetts Boston" at its UMass coordinates), else
      2. the caller-supplied ``curated_fallback``, else
      3. a theme-appropriate curated place.
    The stop keeps its coordinates and body; only the ``Stop N:`` header is
    rewritten (and, when the stop had an empty/absent Address, a note is NOT
    fabricated — the real name + existing coordinates are enough for the map).

    Returns ``(new_text, changes)`` where ``changes`` is a list of
    ``{'stop': n, 'from': old, 'to': new, 'source': 'narration'|'curated'}``.
    Idempotent: a stop already named a real place is left untouched.
    """
    cat = _tour_category(text)
    if cat in ('museum', 'building', 'venue'):
        return text, []
    theme = extract_request_theme(text)
    blocks = _stop_blocks(text)
    if not blocks:
        return text, []

    # Names already used by OTHER stops — never rename to a duplicate.
    all_names = {_norm(n) for (_s, _e, n) in blocks}

    changes: List[dict] = []
    # Rebuild back-to-front so offsets stay valid.
    pieces: List[str] = []
    prev_end = len(text)
    # Tail after the last block (Sources etc.)
    pieces.append(text[blocks[-1][1]:prev_end])
    for i in range(len(blocks) - 1, -1, -1):
        start, end, name = blocks[i]
        seg = text[start:end]
        num_m = _STOP_HEADER.match(seg)
        num = int(num_m.group(1)) if num_m else (i + 1)

        offending = (theme and is_theme_phrase_stop(name, theme)) or topic_like_name(name)
        if offending:
            replacement = derive_real_place_from_block(seg)
            source = 'narration'
            if (not replacement) or _norm(replacement) in (all_names - {_norm(name)}) \
                    or is_theme_phrase_stop(replacement, theme) or topic_like_name(replacement):
                replacement = (curated_fallback or _curated_fallback(theme) or "").strip()
                source = 'curated'
            # Only rewrite if we found a genuine, distinct, real place name.
            if replacement and _norm(replacement) != _norm(name) \
                    and _norm(replacement) not in (all_names - {_norm(name)}) \
                    and not topic_like_name(replacement) \
                    and not (theme and is_theme_phrase_stop(replacement, theme)):
                new_header = re.sub(
                    r'^(Stop\s+\d+:\s*).+?(\s*)$',
                    lambda m: f"{m.group(1)}{replacement}",
                    seg.split("\n", 1)[0])
                rest = seg.split("\n", 1)[1] if "\n" in seg else ""
                seg = new_header + ("\n" + rest if rest else "")
                all_names.discard(_norm(name))
                all_names.add(_norm(replacement))
                changes.append({'stop': num, 'from': name, 'to': replacement,
                                'source': source})
        pieces.append(seg)
        prev_end = start
    pieces.append(text[:blocks[0][0]])
    new_text = "".join(reversed(pieces))
    return new_text, changes


if __name__ == "__main__":  # pragma: no cover
    import sys
    with open(sys.argv[1], encoding="utf-8") as f:
        t = f.read()
    print("request theme:", repr(extract_request_theme(t)))
    print("offending stops:", find_theme_phrase_stops(t))
    fixed, ch = rename_theme_phrase_stops(t)
    print("changes:", ch)
