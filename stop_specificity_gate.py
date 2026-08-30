#!/usr/bin/env python3
"""stop_specificity_gate.py — LOCAL-469: The paragraph must be about THIS stop.

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
`stop_name` for a sibling stop's name throughout the paragraph and ask whether
the SWAPPED passage now contains any claim that is false or nonsensical for the
new stop. If nothing breaks, the paragraph was never about this stop; it is
transferable. Asking "what breaks when you move it?" returns a check with an
answer.

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

def _split_paragraphs(text: str) -> List[str]:
    """Split a description into paragraphs on blank lines.

    Descriptions in this codebase are stored with paragraphs separated by blank
    lines (see the Cimiez tour). A single-block description is one paragraph.
    """
    if not text:
        return []
    parts = re.split(r'\n\s*\n', text.strip())
    return [p.strip() for p in parts if p.strip()]


def _substitute_stop_name(paragraph: str, stop_name: str, sibling: str) -> str:
    """Replace every occurrence of `stop_name` (and its salient fragments) with
    `sibling`. Whole-word, case-insensitive, longest-fragment-first so we do not
    leave a half-swapped name behind."""
    if not stop_name or not sibling:
        return paragraph
    out = paragraph
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


def _detect_named_entities(paragraph: str, stop_name: str,
                           sibling_stop_names: Optional[List[str]] = None) -> List[str]:
    """Return distinct person / work / titled-entity names in the paragraph.

    Excludes the stop's own name and sibling stop names (those are the stops, not
    incidental references) but does NOT exclude well-known names: Michael's
    Example B (Fitzgerald) is precisely a well-known name that still needs a
    stated relationship. That is the whole reason this is a separate gate.
    """
    found: List[str] = []
    seen = set()
    stop_frag = {stop_name.lower()} if stop_name else set()
    for sn in (sibling_stop_names or []):
        stop_frag.add((sn or '').lower())

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
        (It is also mangled to "Pons Abbey" by the person regex; filtering the
        facility tail drops both the mangled and the whole form.)

    Excludes the stop's own name and sibling stop names, but does NOT exclude
    well-known persons: Example B's Fitzgerald is precisely a well-known person
    who still needs a stated relationship — that is why this is a separate gate.
    """
    found: List[str] = []
    seen = set()
    stop_frag = {stop_name.lower()} if stop_name else set()
    for sn in (sibling_stop_names or []):
        stop_frag.add((sn or '').lower())

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
            if n.split()[-1].lower() in _NON_PERSON_TAIL:
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


# Geography terms that the person regex may capture but which are the SETTING,
# not a name-dropped person or work. Kept small and specific.
_GEOGRAPHY_TERMS = {
    'french riviera', 'riviera', 'côte d\'azur', 'cote d azur',
    'mediterranean', 'mediterranean sea', 'atlantic', 'atlantic ocean',
    'pacific', 'pacific ocean', 'the alps', 'alps', 'french alps',
}


def _fold(s: str) -> str:
    import unicodedata
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

_TRANSFERABLE_PROMPT = """A paragraph from an audio tour was written about the stop "{stop}".
Below is that same paragraph with the stop name mechanically replaced by "{sibling}".

SWAPPED PARAGRAPH:
"{swapped}"

Question: reading ONLY the swapped paragraph, does it contain ANY specific claim
(an event, a date, a person, a named work, a physical feature, a documented fact)
that is FALSE or NONSENSICAL for "{sibling}"?

- If YES (something concrete breaks when moved), the original was specific to its
  stop. Answer: SPECIFIC.
- If NO (nothing breaks — it reads as a true, natural passage about "{sibling}"
  too, because it only makes generic scene-setting / mood / instructional claims),
  the paragraph is transferable. Answer: TRANSFERABLE.

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
                                sibling_stop_names: List[str],
                                api_key: str = None,
                                llm_fn: Callable[[str, str, str], Optional[str]] = None,
                                model: str = None) -> Dict:
    """Is `paragraph` transferable off `stop_name` onto a sibling stop?

    Returns {'transferable': bool, 'reason': str, 'confidence': 'high'|'medium'|'low'}.

    Method: substitute a sibling stop name in, ask the model whether any concrete
    claim now breaks. No break ⇒ the paragraph was never about this stop.

    Fail-safe: with no model available (no api_key and no llm_fn), returns
    transferable=False at low confidence — the caller must never delete without a
    verdict.
    """
    para = (paragraph or '').strip()
    if not para:
        return {'transferable': False, 'reason': 'empty paragraph', 'confidence': 'low'}

    siblings = [s for s in (sibling_stop_names or []) if s and s != stop_name]
    if not siblings:
        # Nothing to substitute against — cannot run the substitution test.
        return {'transferable': False,
                'reason': 'no sibling stop to substitute against',
                'confidence': 'low'}

    caller = llm_fn or (lambda p, k, m: _default_llm(p, k, m))

    # Run the test against up to two siblings. The verdict is TRANSFERABLE only
    # if the paragraph survives the move to EVERY sibling tried (i.e. nothing
    # breaks for any of them). One broken claim anywhere ⇒ SPECIFIC.
    tried = 0
    reasons = []
    for sibling in siblings[:2]:
        swapped = _substitute_stop_name(para, stop_name, sibling)
        if swapped.strip() == para.strip():
            # Stop name never appeared; substitution is a no-op. This alone is a
            # strong signal the paragraph does not mention its stop, but we still
            # need the model to judge whether its claims are stop-specific.
            pass
        prompt = _TRANSFERABLE_PROMPT.format(
            stop=stop_name, sibling=sibling, swapped=swapped,
        )
        raw = caller(prompt, api_key, model)
        if raw is None:
            continue
        tried += 1
        parsed = _parse_verdict(raw)
        if parsed['verdict'] == 'SPECIFIC':
            return {'transferable': False,
                    'reason': parsed['reason'] or f'a claim breaks when moved to {sibling}',
                    'confidence': 'high'}
        if parsed['verdict'] == 'TRANSFERABLE':
            reasons.append(parsed['reason'] or f'nothing breaks when moved to {sibling}')

    if tried == 0:
        # Model never answered — fail safe, do not delete.
        return {'transferable': False,
                'reason': 'no model verdict available',
                'confidence': 'low'}

    # Every sibling we tried came back TRANSFERABLE.
    confidence = 'high' if tried >= 2 else 'medium'
    return {'transferable': True,
            'reason': reasons[0] if reasons else 'nothing breaks when the stop name is swapped',
            'confidence': confidence}


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
    para = (paragraph or '').strip()
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

            # Part 1 — the substitution test.
            spec = check_paragraph_specificity(
                para, stop_name, siblings, api_key=api_key, llm_fn=llm_fn, model=model,
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
