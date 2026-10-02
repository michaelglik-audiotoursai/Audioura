#!/usr/bin/env python3
"""stop_specificity_gate.py — LOCAL-473 (supersedes LOCAL-472, LOCAL-469).

The paragraph must be about THIS stop.

Michael, ClickUp wdvrdaxa7h:

    "Some paragraphs describing a tour stop either can be used to describe any
     stop, or do not specifically declare the stop relationship. This task is to
     make sure that any paragraph is stop specific. If it is not, the choice
     should be either remove it or make it the stop specific."

Two failure modes, two checks.

── Part 1 · the substitution test, made mechanical ─────────────────────────────
Michael's own test for transferability:

    "if you can substitute the names of places and say the same thing about
     another location, this paragraph is redundant."

We do not ask the model "is this specific?" — that returns an opinion. We swap
`stop_name` for a GENERIC SAME-KIND referent ("another art museum", "another
coastal viewpoint") throughout the paragraph and ask whether the SWAPPED passage
now contains any claim that is false or nonsensical for that other place of the
same kind. If nothing breaks, the paragraph was never about this stop; it is
transferable. Asking "what breaks when you move it?" returns a check with an
answer.

── LOCAL-473 · why this file was rewritten (again) ─────────────────────────────
LOCAL-472 substituted a NAMED SIBLING STOP from the SAME TOUR, not a generic
referent. LEAD ran the real model against Michael's Example A and proved the
verdict then depended on which OTHER stops the tour happened to contain:

    siblings=['Villa Leopolda','Musee Matisse'] -> SPECIFIC (kept)   WRONG
    siblings=['Cap Ferrat']                     -> transferable/medium (kept)
    siblings=['Cap Ferrat','Pointe des Douaniers'] -> transferable/high (removed)

Same paragraph, three answers, decided entirely by the tour's other stops. Root
cause: substituting a DISSIMILAR sibling (a museum for a cape) makes almost any
paragraph look specific — a museum genuinely has no panoramic sea views, so "a
claim breaks", so the model says SPECIFIC. And real tours are mostly dissimilar
stops (the Cimiez tour is a monastery, two museums, Roman ruins and a villa), so
on a real tour LOCAL-472's gate would KEEP generic prose about every stop — the
whole defect unaddressed.

The fix: stop substituting a named sibling. Classify the stop's KIND (viewpoint /
museum / church / ruin / restaurant / park / street / villa) and substitute a
GENERIC same-kind referent, so the test measures the paragraph and nothing else.
Michael said "another LOCATION", not "another stop on this tour." Sibling names
may still be passed for context, but the VERDICT MUST NOT CHANGE because the tour
contains a museum rather than a cape. Confidence is now a function of the model's
verdict on that single, sibling-independent swap — not of how many siblings were
tried (that ambiguity was the LOCAL-472 defect that let medium verdicts through).

── Part 2 · the named-entity relationship rule ─────────────────────────────────
Michael's second test:

    "if the paragraph mentions names or titles of books, movies, etc. it has to
     have some description how the person or the book or the scene relates to the
     Stop."

Narrower than the existing unglossed-reference gate (LOCAL-269), which asks
whether a GENERAL AUDIENCE knows the name — Fitzgerald is in its well-known set,
so it correctly suppresses him and never fires on Example B. This asks a
different question on a different axis: is a RELATIONSHIP TO THIS STOP stated?
    "Fitzgerald wrote Tender Is the Night while staying at the Hôtel du Cap, at
     the far end of this headland"        → relationship stated, keep
    "Fitzgerald was captivated by this scene" → no relationship, flag
If no relationship can be stated from available material, the reference is cut.

── Part 3 · conservative removal (wired at PHASE 5.152) ────────────────────────
Removal is destructive, so it obeys the LOCAL-359 rule: only a `high`-confidence
transferable verdict deletes. And it never empties a stop — the last remaining
paragraph of a stop is kept even if flagged, because an empty stop is worse than
one flabby paragraph.
Michael's second test:

    "if the paragraph mentions names or titles of books, movies, etc. it has to
     have some description how the person or the book or the scene relates to the
     Stop."

Narrower than the existing unglossed-reference gate (LOCAL-269), which asks
whether a GENERAL AUDIENCE knows the name — Fitzgerald is in its well-known set,
so it correctly suppresses him and never fires on Example B. This asks a
different question on a different axis: is a RELATIONSHIP TO THIS STOP stated?
    "Fitzgerald wrote Tender Is the Night while staying at the Hôtel du Cap, at
     the far end of this headland"        → relationship stated, keep
    "Fitzgerald was captivated by this scene" → no relationship, flag
If no relationship can be stated from available material, the reference is cut.

── Part 3 · conservative removal (wired at PHASE 5.152) ────────────────────────
Removal is destructive, so it obeys the LOCAL-359 rule: only a `high`-confidence
transferable verdict deletes. And it never empties a stop — the last remaining
paragraph of a stop is kept even if flagged, because an empty stop is worse than
one flabby paragraph.

── LOCAL-472 · why this file was rewritten ─────────────────────────────────────
LOCAL-469 was rejected for two defects:

  Defect 1 — the entity detector truncated accented multi-word venue names
    ("Musée Matisse" → "Musée Mati"). Root cause (D243): the reused person /
    structure regexes use the character class ``[a-zà-ÿ]``, which matches a
    precomposed ``é`` (U+00E9) but NOT a decomposed ``e`` + combining acute
    (U+0301). macOS stores filenames and often text in NFD (decomposed) form, so
    the same name that reads fine on one machine is silently cut mid-word on
    another. The fix is to NFC-normalize (recompose) every string BEFORE it
    touches a regex, in `_norm`. Detection is now encoding-independent.

  Defect 2 — `_detect_named_entities` was defined twice; the first copy had a
    truncated body (built `found`/`seen`/`stop_frag`, then fell off with no
    return) and was silently shadowed by the second. The dead copy is gone.
    There is exactly one definition now.

Design invariants
  - The LLM client is injectable (`llm_fn`) so the logic is unit-testable with no
    network and no key. The default path is the same requests.post call the rest
    of the gate chain uses (unglossed_reference_gate, unsupported_claim_gate).
  - Entity detection reuses the patterns already in unglossed_reference_gate so
    we do not maintain a second, drifting detector.
  - With no api_key and no llm_fn, Part 1 returns transferable=False at low
    confidence (fail-safe: never delete without a model verdict).
"""
import os
import re
import json
import time
import unicodedata
from typing import Callable, Dict, List, Optional

# Reuse the entity detectors rather than growing a second one (task Part 2:
# "a fifth overlapping gate is worse than extending one that runs").
try:
    from unglossed_reference_gate import (
        _PERSON_PATTERN,
        _TITLED_PERSON,
        _WORK_TITLE_PATTERN,
        _is_well_known,
    )
except Exception:  # pragma: no cover - import guard for standalone use
    _PERSON_PATTERN = re.compile(
        r'\b([A-Z][a-zà-ÿ]+(?:\s+(?:de|du|von|van|di|del|la|le|les|des|d\'|l\')?'
        r'\s*[A-Z][a-zà-ÿ]+)+)\b'
    )
    _TITLED_PERSON = re.compile(
        r'\b((?:King|Queen|Emperor|Empress|Prince|Princess|Duke|Duchess|'
        r'Count|Countess|Baron|Baroness|Pope|Saint|St\.?)\s+'
        r'[A-Z][a-zà-ÿ]+(?:\s+[IVX]+|\s+[a-zà-ÿ]+)*(?:\s+of\s+[A-Z][a-zà-ÿ]+)?)\b'
    )
    _WORK_TITLE_PATTERN = re.compile(r'["“”\'‘’]([^"“”\'‘’]{3,50})["“”\'‘’]')

    def _is_well_known(name):  # type: ignore
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    """[LOCAL-472 / D243] Recompose to NFC before any regex touches the string.

    The person / structure patterns match ``[a-zà-ÿ]``, which covers the
    precomposed accented letters (``é`` = U+00E9) but NOT the decomposed pair
    (``e`` + combining acute U+0301). macOS text is frequently NFD (decomposed),
    so "Musée Matisse" arrives as ``M u s e ´ e   M a t i s s e`` and the regex
    breaks at the combining mark, cutting the name mid-word ("Musée Mati") or
    dropping it entirely. NFC recomposes ``e`` + ´ back into ``é`` so the class
    matches and whole names survive, on every platform.
    """
    if not s:
        return s
    return unicodedata.normalize('NFC', s)


def _split_paragraphs(text: str) -> List[str]:
    """Split a description into paragraphs on blank lines.

    Descriptions in this codebase are stored with paragraphs separated by blank
    lines (see the Cimiez tour). A single-block description is one paragraph.
    """
    if not text:
        return []
    parts = re.split(r'\n\s*\n', _norm(text).strip())
    return [p.strip() for p in parts if p.strip()]


def _substitute_stop_name(paragraph: str, stop_name: str, sibling: str) -> str:
    """Replace every occurrence of `stop_name` (and its salient fragments) with
    `sibling`. Whole-word, case-insensitive, longest-fragment-first so we do not
    leave a half-swapped name behind."""
    if not stop_name or not sibling:
        return paragraph
    out = _norm(paragraph)
    stop_name = _norm(stop_name)
    sibling = _norm(sibling)
    # Full name first, then multi-word fragments, longest first.
    fragments = [stop_name]
    words = [w for w in re.split(r'\s+', stop_name) if len(w) > 3]
    fragments += sorted(words, key=len, reverse=True)
    for frag in fragments:
        out = re.sub(
            r'\b' + re.escape(frag) + r'\b',
            sibling,
            out,
            flags=re.IGNORECASE,
        )
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# [LOCAL-473] STOP-KIND CLASSIFICATION — the generic same-kind referent
# ═══════════════════════════════════════════════════════════════════════════════
#
# LOCAL-472 substituted a NAMED sibling from this tour ("Musée Matisse",
# "Cap Ferrat"). LEAD proved that makes the verdict depend on which stops the
# tour happens to contain: swapping a dissimilar sibling (a museum for a cape)
# makes almost any paragraph look specific, because a concrete-but-generic claim
# ("panoramic sea views") genuinely breaks on the dissimilar kind — so the model
# says SPECIFIC and the generic prose is KEPT. Real tours are mostly dissimilar
# stops, so on a real tour the gate keeps the very prose it exists to delete.
#
# Michael's test is "another LOCATION", not "another stop on THIS tour". So we
# classify the stop's KIND and substitute a GENERIC same-kind referent — "another
# art museum", "another coastal viewpoint". The swap now measures the paragraph
# and the paragraph only; it does not change because the tour contains a museum
# rather than a cape. A paragraph that survives the swap to another place OF THE
# SAME KIND was never about this stop.

# Ordered longest-intent-first: the first kind whose keywords hit wins. Each kind
# maps to a neutral generic referent used verbatim in the substitution. Keywords
# are matched accent-folded and case-insensitively against the stop name.
_STOP_KINDS = [
    ('museum',    'another art museum',
     ('museum', 'musee', 'musée', 'gallery', 'galerie', 'pinacoteca',
      'collection', 'exhibition hall')),
    ('church',    'another historic church',
     ('church', 'cathedral', 'basilica', 'chapel', 'abbey', 'priory',
      'monastery', 'convent', 'cloister', 'shrine', 'temple', 'mosque',
      'synagogue', 'eglise', 'église', 'notre-dame', 'saint', 'sainte',
      'sant', 'santa', 'san ', 'st ', 'st.')),
    ('ruin',      'another ancient ruin',
     ('ruin', 'ruins', 'amphitheatre', 'amphitheater', 'arena', 'forum',
      'aqueduct', 'thermae', 'baths', 'archaeological', 'excavation',
      'necropolis', 'cemenelum', 'roman ')),
    ('viewpoint', 'another coastal viewpoint',
     ('viewpoint', 'lookout', 'overlook', 'belvedere', 'panorama',
      'panoramic', 'cape', 'cap ', "cap d", 'pointe', 'point', 'headland',
      'promontory', 'cliff', 'summit', 'peak', 'terrace', 'vista', 'bay',
      'beach', 'seafront', 'promenade', 'corniche')),
    ('restaurant','another local restaurant',
     ('restaurant', 'brasserie', 'bistro', 'cafe', 'café', 'trattoria',
      'osteria', 'tavern', 'eatery', 'bar', 'winery', 'market hall')),
    ('park',      'another public garden',
     ('park', 'garden', 'jardin', 'gardens', 'arboretum', 'botanical',
      'grove', 'orchard', 'meadow', 'reserve')),
    ('street',    'another old town street',
     ('street', 'avenue', 'boulevard', 'lane', 'alley', 'rue ', 'via ',
      'place ', 'square', 'plaza', 'piazza', 'quarter', 'district',
      'old town', 'quay', 'quai', 'harbour', 'harbor', 'port')),
    ('villa',     'another historic villa',
     ('villa', 'palace', 'palais', 'chateau', 'château', 'castle', 'fort',
      'fortress', 'citadel', 'manor', 'mansion', 'estate', 'residence',
      'hotel particulier')),
]

_GENERIC_PLACE_REFERENT = 'another place of the same kind'


def classify_stop_kind(stop_name: str, description: str = '') -> Dict:
    """[LOCAL-473] Classify the kind of a stop and return the generic same-kind
    referent to substitute against.

    Returns {'kind': str, 'referent': str}. The stop name is checked first; if
    it carries no kind signal, the (optional) description is scanned as a fallback
    so a plainly-named stop ("Cimiez") still classifies from its prose. If nothing
    matches, a neutral generic referent is used so the substitution test always
    runs against SOMETHING generic — never against a named sibling.

    Deterministic: no model call, no network. The verdict downstream depends only
    on the paragraph and this kind — never on which siblings the tour contains.
    """
    name_f = _fold(_norm(stop_name or '')).lower()
    desc_f = _fold(_norm(description or '')).lower()

    for kind, referent, keywords in _STOP_KINDS:
        for kw in keywords:
            if kw in name_f:
                return {'kind': kind, 'referent': referent}
    # Fallback: scan the description for the same signals.
    for kind, referent, keywords in _STOP_KINDS:
        for kw in keywords:
            if kw in desc_f:
                return {'kind': kind, 'referent': referent}
    return {'kind': 'place', 'referent': _GENERIC_PLACE_REFERENT}


# Geography terms that the person regex may capture but which are the SETTING,
# not a name-dropped person or work. Kept small and specific.
_GEOGRAPHY_TERMS = {
    'french riviera', 'riviera', 'côte d\'azur', 'cote d azur',
    'mediterranean', 'mediterranean sea', 'atlantic', 'atlantic ocean',
    'pacific', 'pacific ocean', 'the alps', 'alps', 'french alps',
}


def _fold(s: str) -> str:
    """Strip diacritics for comparison (accent-insensitive matching)."""
    return ''.join(c for c in unicodedata.normalize('NFD', s or '')
                   if unicodedata.category(c) != 'Mn')


def _is_geography(name_low: str) -> bool:
    f = _fold(name_low)
    terms = {_fold(t) for t in _GEOGRAPHY_TERMS}
    if f in terms:
        return True
    for t in terms:
        if t in f or f in t:
            return True
    return False


def _detect_named_entities(paragraph: str, stop_name: str,
                           sibling_stop_names: Optional[List[str]] = None) -> List[str]:
    """Return distinct person / work / titled-entity names in the paragraph.

    Michael's Part-2 rule is about "the person or the book or the scene" — a
    NAMED PERSON, book, film or work. It is NOT about places, regions, bodies of
    water or institutions, which are the SETTING, not a name-dropped work. So:

      - "Scott Fitzgerald"  → person, checked.
      - "Tender Is the Night" (quoted) → work, checked.
      - "French Riviera" / "Mediterranean sea" → region / water → NOT a person or
        work → skipped. (These are also in the unglossed gate's well-known set.)
      - "Saint-Pons Abbey" → an institution/structure, the setting → skipped.
        (Filtering the facility tail drops it whole.)

    Excludes the stop's own name and sibling stop names, but does NOT exclude
    well-known persons: Example B's Fitzgerald is precisely a well-known person
    who still needs a stated relationship — that is why this is a separate gate.

    [LOCAL-472] Input is NFC-normalized first (`_norm`) so accented multi-word
    names are matched whole, never cut mid-word. See `_norm`.
    """
    paragraph = _norm(paragraph)
    stop_name = _norm(stop_name or '')

    found: List[str] = []
    seen = set()
    stop_frag = {stop_name.lower()} if stop_name else set()
    for sn in (sibling_stop_names or []):
        stop_frag.add(_norm(sn or '').lower())

    # Tail words that mark a candidate as a PLACE / STRUCTURE / REGION rather than
    # a person or a work. If the last word of a person-pattern match is one of
    # these, it is the setting, not a name-dropped person/work.
    _NON_PERSON_TAIL = {
        'abbey', 'priory', 'monastery', 'convent', 'cathedral', 'basilica',
        'chapel', 'church', 'villa', 'palais', 'palace', 'château', 'chateau',
        'museum', 'musée', 'musee', 'gallery', 'hotel', 'hôtel', 'fort',
        'riviera', 'sea', 'ocean', 'mountains', 'alps', 'coast', 'bay', 'cape',
        'island', 'river', 'lake', 'valley', 'square', 'street', 'avenue',
        'boulevard', 'district', 'quarter', 'city', 'town', 'village',
        'revolution', 'war', 'empire', 'republic',
    }
    # Accent-folded copy so "Musée"/"Musee" and "Château"/"Chateau" both match.
    _NON_PERSON_TAIL_FOLDED = {_fold(w) for w in _NON_PERSON_TAIL}

    def _is_non_person_tail(word_low: str) -> bool:
        return word_low in _NON_PERSON_TAIL or _fold(word_low) in _NON_PERSON_TAIL_FOLDED

    def _consider(name: str, kind: str):
        n = (name or '').strip()
        if len(n) < 3:
            return
        low = n.lower()
        if low in seen:
            return
        # Skip the stop's own name / siblings.
        if any(low == sf or (sf and (sf in low or low in sf)) for sf in stop_frag if sf):
            return
        # Skip leading-article false positives ("The French", "This Museum").
        if n.split()[0].lower() in ('the', 'this', 'that', 'a', 'an', 'its'):
            return
        # Persons/titled: drop candidates whose last word marks a place/structure.
        if kind in ('person', 'titled'):
            if _is_non_person_tail(n.split()[-1].lower()):
                return
            # A well-known REGION/geography term slipped through as a "person"
            # (e.g. "French Riviera", "Mediterranean") is the setting, not a
            # name-drop. Persons like Fitzgerald are NOT dropped here — only the
            # geography terms the unglossed gate lists under "Geography".
            if _is_geography(low):
                return
        seen.add(low)
        found.append(n)

    for m in _PERSON_PATTERN.finditer(paragraph):
        _consider(m.group(1), 'person')
    for m in _TITLED_PERSON.finditer(paragraph):
        _consider(m.group(1), 'titled')
    for m in _WORK_TITLE_PATTERN.finditer(paragraph):
        _consider(m.group(1), 'work')
    return found


# ═══════════════════════════════════════════════════════════════════════════════
# DEFAULT LLM CLIENT (same shape as the rest of the gate chain)
# ═══════════════════════════════════════════════════════════════════════════════

def _default_llm(prompt: str, api_key: str, model: str = None) -> Optional[str]:
    """One chat-completion call. Returns the assistant text, or None on any
    failure. Mirrors unglossed_reference_gate's requests.post usage so the
    network behaviour is identical to the gates already shipping."""
    if not api_key:
        return None
    import requests as _req
    model = model or os.environ.get('STOP_SPECIFICITY_MODEL', 'gpt-4o-mini')
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You audit audio-tour prose. Answer only in the exact format requested."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }
    try:
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers, data=json.dumps(data), timeout=30,
        )
        if resp.status_code != 200:
            return None
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — the substitution test
# ═══════════════════════════════════════════════════════════════════════════════

_TRANSFERABLE_PROMPT = """A paragraph from an audio tour was written about the stop "{stop}"{kind_clause}.
Below is that same paragraph with the stop name mechanically replaced by a
GENERIC referent, "{referent}" — i.e. some other, unnamed place of the same kind.

SWAPPED PARAGRAPH:
"{swapped}"

Question: reading ONLY the swapped paragraph, does it contain ANY specific claim
(an event, a date, a named person, a named work, a documented fact, or a physical
feature UNIQUE to one particular place — not one shared by every place of this
kind) that is FALSE or NONSENSICAL for "{referent}"?

- If YES (something concrete breaks when moved to another place of the same kind),
  the original was specific to its stop. Answer: SPECIFIC.
- If NO (nothing breaks — it reads as a true, natural passage about "{referent}"
  too, because it only makes generic scene-setting / mood / category-level /
  instructional claims that fit any place of this kind), the paragraph is
  transferable. Answer: TRANSFERABLE.

Do not credit generic sensory or mood claims ("panoramic views", "soak up the
atmosphere", "enduring power of nature") as specific — those are true of any
place of this kind and therefore do NOT break.

Respond with exactly one line:
VERDICT: SPECIFIC | TRANSFERABLE
REASON: <one short clause>
"""


def _parse_verdict(text: str) -> Dict:
    verdict = None
    reason = ''
    for line in (text or '').splitlines():
        line = line.strip()
        m = re.match(r'VERDICT:\s*(SPECIFIC|TRANSFERABLE)', line, re.IGNORECASE)
        if m:
            verdict = m.group(1).upper()
        m = re.match(r'REASON:\s*(.+)', line, re.IGNORECASE)
        if m:
            reason = m.group(1).strip()
    return {'verdict': verdict, 'reason': reason}


def check_paragraph_specificity(paragraph: str,
                                stop_name: str,
                                sibling_stop_names: List[str] = None,
                                api_key: str = None,
                                llm_fn: Callable[[str, str, str], Optional[str]] = None,
                                model: str = None,
                                stop_description: str = '') -> Dict:
    """Is `paragraph` transferable off `stop_name` onto ANOTHER PLACE OF THE SAME
    KIND?

    Returns {'transferable': bool, 'reason': str, 'confidence': 'high'|'medium'|'low',
             'kind': str, 'referent': str}.

    [LOCAL-473] Method changed. LOCAL-472 substituted a NAMED sibling stop from
    THIS tour, which made the verdict depend on which stops the tour happened to
    contain (LEAD: same paragraph, three sibling sets, three different verdicts).
    We now classify the stop's KIND (museum / church / ruin / viewpoint / ...) and
    substitute a GENERIC same-kind referent ("another art museum", "another
    coastal viewpoint"), then ask the model whether any concrete claim breaks.

    Michael's test is "another LOCATION", not "another stop on this tour". A
    paragraph that survives the swap to another place of the same kind was never
    about this stop. Because the swap target is generic and derived only from this
    stop's own kind, the verdict is a function of the paragraph alone — it does
    NOT change because the tour contains a museum rather than a cape.

    `sibling_stop_names` is accepted for signature compatibility and may be logged
    as context, but it does NOT affect the verdict. The test runs identically with
    siblings=[].

    Fail-safe: with no model available (no api_key and no llm_fn), returns
    transferable=False at low confidence — the caller must never delete without a
    verdict.
    """
    para = _norm(paragraph or '').strip()
    kind_info = classify_stop_kind(stop_name, stop_description or para)
    kind = kind_info['kind']
    referent = kind_info['referent']

    base = {'kind': kind, 'referent': referent}
    if not para:
        return {'transferable': False, 'reason': 'empty paragraph',
                'confidence': 'low', **base}

    caller = llm_fn or (lambda p, k, m: _default_llm(p, k, m))

    # Substitute the GENERIC same-kind referent (never a named sibling).
    swapped = _substitute_stop_name(para, stop_name, referent)

    kind_clause = f' (a {kind})' if kind and kind != 'place' else ''
    prompt = _TRANSFERABLE_PROMPT.format(
        stop=stop_name, kind_clause=kind_clause,
        referent=referent, swapped=swapped,
    )
    raw = caller(prompt, api_key, model)
    if raw is None:
        # Model never answered — fail safe, do not delete.
        return {'transferable': False,
                'reason': 'no model verdict available',
                'confidence': 'low', **base}

    parsed = _parse_verdict(raw)
    if parsed['verdict'] == 'SPECIFIC':
        return {'transferable': False,
                'reason': parsed['reason']
                          or f'a claim breaks when moved to {referent}',
                'confidence': 'high', **base}
    if parsed['verdict'] == 'TRANSFERABLE':
        # The swap is deterministic and sibling-independent, so a single clear
        # TRANSFERABLE verdict is high confidence — there is no "how many siblings
        # did we try" ambiguity any more (that was the LOCAL-472 defect).
        return {'transferable': True,
                'reason': parsed['reason']
                          or f'nothing breaks when moved to {referent}',
                'confidence': 'high', **base}

    # Unparseable verdict — fail safe.
    return {'transferable': False,
            'reason': 'model verdict unparseable',
            'confidence': 'low', **base}


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — the named-entity relationship rule
# ═══════════════════════════════════════════════════════════════════════════════

_RELATIONSHIP_PROMPT = """An audio-tour paragraph about the stop "{stop}" names "{entity}".

PARAGRAPH:
"{paragraph}"

Michael's rule: when a paragraph names a person, book, film or work, it must state
HOW that entity relates to THIS stop — a concrete link (wrote/stayed/lived/built/
died/painted/was founded AT or NEAR this stop), not a vague sentiment.

  GROUNDED: "Fitzgerald wrote Tender Is the Night while staying at the Hôtel du Cap
             at the end of this headland."   (states a concrete link to the stop)
  UNGROUNDED: "Fitzgerald was captivated by this scene."   (sentiment, no link)

Does the paragraph state a concrete relationship between "{entity}" and this stop?

Respond with exactly one line:
VERDICT: GROUNDED | UNGROUNDED
REASON: <one short clause>
"""


def _parse_relationship(text: str) -> Dict:
    verdict = None
    reason = ''
    for line in (text or '').splitlines():
        line = line.strip()
        m = re.match(r'VERDICT:\s*(GROUNDED|UNGROUNDED)', line, re.IGNORECASE)
        if m:
            verdict = m.group(1).upper()
        m = re.match(r'REASON:\s*(.+)', line, re.IGNORECASE)
        if m:
            reason = m.group(1).strip()
    return {'verdict': verdict, 'reason': reason}


def check_named_entity_relationships(paragraph: str,
                                     stop_name: str,
                                     sibling_stop_names: List[str] = None,
                                     api_key: str = None,
                                     llm_fn: Callable[[str, str, str], Optional[str]] = None,
                                     model: str = None) -> Dict:
    """Flag named entities (persons / works / titled entities) that carry no
    stated relationship to this stop.

    Returns {'entities': [...], 'ungrounded': [{'entity','reason'}], 'reason': str}.

    Detection is deterministic (reused patterns). The relationship judgement uses
    the model; with no model available it returns the detected entities but flags
    nothing (fail-safe — the caller does not act without a verdict).
    """
    para = _norm(paragraph or '').strip()
    entities = _detect_named_entities(para, stop_name, sibling_stop_names)
    result = {'entities': entities, 'ungrounded': [], 'reason': ''}
    if not entities:
        return result

    caller = llm_fn or (lambda p, k, m: _default_llm(p, k, m))
    for entity in entities:
        prompt = _RELATIONSHIP_PROMPT.format(
            stop=stop_name, entity=entity, paragraph=para,
        )
        raw = caller(prompt, api_key, model)
        if raw is None:
            continue
        parsed = _parse_relationship(raw)
        if parsed['verdict'] == 'UNGROUNDED':
            result['ungrounded'].append({
                'entity': entity,
                'reason': parsed['reason'] or 'no stated relationship to this stop',
            })
    if result['ungrounded']:
        names = ', '.join(u['entity'] for u in result['ungrounded'])
        result['reason'] = f'ungrounded named entity: {names}'
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3 — apply to a whole tour (wired at PHASE 5.152)
# ═══════════════════════════════════════════════════════════════════════════════

def apply_stop_specificity_gate(poi_list: List[Dict],
                                api_key: str = None,
                                llm_fn: Callable[[str, str, str], Optional[str]] = None,
                                model: str = None) -> Dict:
    """Run both checks over every stop's description and remove only
    high-confidence transferable paragraphs.

    Conservative-removal rules (LOCAL-359 + never-empty-a-stop):
      - Only `confidence == 'high'` transferable verdicts delete.
      - The last remaining paragraph of a stop is never deleted.
      - Named-entity relationship findings are REPORTED (logged) but do not
        delete here — an ungrounded name is a flag for the retry/rewrite path,
        not a destructive action, matching the task's "remove OR make specific".

    Mutates `poi_list` in place. Returns a stats dict.
    """
    stats = {
        'stops_checked': 0,
        'paragraphs_checked': 0,
        'paragraphs_removed': 0,
        'stops_affected': 0,
        'transferable_high': 0,
        'transferable_low_conf_kept': 0,
        'last_paragraph_protected': 0,
        'ungrounded_entities': 0,
        'removal_log': [],
        'entity_log': [],
    }

    stop_names = [p.get('name', '') for p in poi_list if p.get('name')]

    for si, poi in enumerate(poi_list):
        desc = poi.get('description', '')
        if not desc or desc.startswith('['):
            continue
        stop_name = poi.get('name', f'Stop {si + 1}')
        siblings = [n for n in stop_names if n and n != stop_name]

        paragraphs = _split_paragraphs(desc)
        if not paragraphs:
            continue
        stats['stops_checked'] += 1

        kept: List[str] = []
        removed_here = 0
        for pi, para in enumerate(paragraphs):
            stats['paragraphs_checked'] += 1

            # Part 2 — report ungrounded named entities (non-destructive here).
            ent = check_named_entity_relationships(
                para, stop_name, siblings, api_key=api_key, llm_fn=llm_fn, model=model,
            )
            for u in ent['ungrounded']:
                stats['ungrounded_entities'] += 1
                stats['entity_log'].append({
                    'stop': stop_name, 'entity': u['entity'], 'reason': u['reason'],
                    'paragraph': para[:100],
                })

            # Part 1 — the substitution test. [LOCAL-473] The whole stop
            # description is passed so kind classification can fall back to the
            # prose when the stop NAME carries no kind signal. Siblings are passed
            # for context/logging only; they do NOT affect the verdict.
            spec = check_paragraph_specificity(
                para, stop_name, siblings, api_key=api_key, llm_fn=llm_fn,
                model=model, stop_description=desc,
            )

            remaining_after = (len(paragraphs) - 1 - pi) + len(kept)
            is_transferable_high = spec['transferable'] and spec['confidence'] == 'high'

            if is_transferable_high:
                stats['transferable_high'] += 1
                # Never empty a stop: keep if this would leave zero paragraphs.
                if len(kept) == 0 and remaining_after == 0:
                    stats['last_paragraph_protected'] += 1
                    kept.append(para)
                    continue
                removed_here += 1
                stats['paragraphs_removed'] += 1
                stats['removal_log'].append({
                    'stop': stop_name,
                    'reason': spec['reason'],
                    'confidence': spec['confidence'],
                    'kind': spec.get('kind', ''),
                    'referent': spec.get('referent', ''),
                    'paragraph': para[:120],
                })
                continue

            if spec['transferable'] and spec['confidence'] != 'high':
                # Flagged but not confident enough to delete (LOCAL-359).
                stats['transferable_low_conf_kept'] += 1
            kept.append(para)

        if removed_here > 0:
            stats['stops_affected'] += 1
            poi_list[si]['description'] = '\n\n'.join(kept)

    return stats
