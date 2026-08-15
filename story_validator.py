#!/usr/bin/env python3
"""story_validator.py — the STORY gate: must-not-be-contradicted.

Michael's ruling, D450, 2026-08-14:

    The stop DESCRIPTION must be accurate and relevant — the listener is looking at
    the object while we talk. The STORY is judged differently: it does not have to
    be relevant or confirmed in sources, only free of falsehood and contradiction.
    "We absolutely should not publish a story with wrong facts."

`validate_story.py` implements the DESCRIPTION gate: anything absent from the corpus
is UNSUPPORTED and the story is REJECTED. Applied to a story it is backwards — it
rejected five true, sourced sentences about the Dalí–Freud meeting for being absent
from the stop text, while passing every sentence vague enough to contain no name
(D447, D448).

This module implements the other gate. Absence of evidence is NOT a rejection. Only
a source that names a DIFFERENT answer to the same question is.

THE QUERY SHAPE IS THE WHOLE TRICK (D450)
-----------------------------------------
Gemini asserted "Leonard Woolf accompanied Dalí to meet Freud". Every yes/no
confirmation search failed to settle it, and `story_leads.verify` even CONFIRMED it
against a sentence that never mentions Woolf. One OPEN question —
"who accompanied Salvador Dalí to meet Sigmund Freud in London 1938" — refuted it
with four independent sources naming Stefan Zweig and Edward James.

    A yes/no search cannot tell a false claim from a poorly-indexed true one.
    An open question returns the real filler for the role, and the conflict is
    visible.

    python3 story_validator.py --file story.txt --subject "Salvador Dalí"
"""
import argparse
import os
import re
import sys
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for _l in open(os.path.join(HERE, '.env')):
    _l = _l.strip()
    if _l and not _l.startswith('#') and '=' in _l:
        _k, _v = _l.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from story_opportunity_scan import _fold, split_sentences   # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# WHO IS A PERSON — shared, because both instruments got this wrong
# ═══════════════════════════════════════════════════════════════════════════════

# `World War` and `Maresfield Gardens` were both classified as PEOPLE by
# validate_story AND by evaluate_story (D447, D449). A capitalised bigram is not a
# person. These are the endings and tokens that mean "not a human being".
_NOT_PERSON_TAIL = frozenset({
    'gardens', 'garden', 'square', 'street', 'road', 'avenue', 'lane', 'park',
    'house', 'museum', 'gallery', 'press', 'university', 'college', 'school',
    'hospital', 'church', 'cathedral', 'palace', 'castle', 'bridge', 'station',
    'war', 'wars', 'republic', 'empire', 'kingdom', 'company', 'society',
    'institute', 'foundation', 'academy', 'club', 'hall', 'court', 'studios',
    'studio', 'gmbh', 'ltd', 'inc', 'gate', 'hill', 'heath', 'common',
})

_NOT_PERSON_HEAD = frozenset({
    'the', 'a', 'an', 'this', 'that', 'these', 'those', 'when', 'while', 'during',
    'after', 'before', 'imagine', 'one', 'two', 'both', 'his', 'her', 'their',
    'in', 'on', 'at', 'by', 'for', 'from', 'with', 'and', 'but', 'nazi',
})

# Place and concept words that must never be counted as a person on their own.
_NOT_PERSON_WHOLE = frozenset({
    'world war', 'world war ii', 'surrealism', 'psychoanalysis', 'europe',
    'london', 'vienna', 'paris', 'boston', 'spain', 'england', 'germany',
    'austria', 'hampstead', 'bloomsbury', 'moses', 'god',
})

_NAME_SPAN = re.compile(
    r"\b([A-ZÀ-Þ][\w'’\-]+(?:\s+(?:de|du|von|van|di|del|des|la|le)\s+[A-ZÀ-Þ][\w'’\-]+"
    r"|(?:\s+[A-ZÀ-Þ][\w'’\-]+){0,2}))")


def named_people(text: str, known: Optional[List[str]] = None) -> List[str]:
    """Named human beings in the text.

    Fixes two failures measured 2026-08-14:
      - `World War`, `Maresfield Gardens` counted as people by both instruments.
      - a bare surname ("Freud", "Dalí") counted as nobody, so `Dalí sketches Freud`
        scored ZERO multi-person sentences.
    """
    known = known or []
    surnames = set()
    for k in known:
        parts = _fold(k).split()
        if parts:
            surnames.add(parts[-1])

    out, seen = [], set()
    for m in _NAME_SPAN.finditer(text or ''):
        span = m.group(1).strip()
        f = _fold(span)
        if not f or f in _NOT_PERSON_WHOLE:
            continue
        toks = f.split()
        # "When The Hogarth Press" — strip leading non-name words until none are
        # left. One pass was not enough: it left "The Hogarth", which then read as
        # a person.
        while toks and toks[0] in _NOT_PERSON_HEAD:
            toks = toks[1:]
            span = ' '.join(span.split()[1:])
        if not toks:
            continue
        f = ' '.join(toks)
        if f in _NOT_PERSON_WHOLE:
            continue
        # A place name in ANY position disqualifies. "Nazi-occupied Vienna" was
        # still counted as a person because the whole-string check only matched
        # "vienna" alone.
        if toks[-1] in _NOT_PERSON_TAIL or any(t in _NOT_PERSON_WHOLE for t in toks):
            continue
        # A single token counts only when it is a surname we already know about —
        # that is what makes "Freud sketches" resolve to a person without turning
        # every capitalised word into one.
        if len(toks) == 1 and toks[0] not in surnames:
            continue
        # "Salvador Dalí" and a later bare "Dalí" are ONE person. Counting them
        # twice inflated the Social score by treating a second mention as a second
        # human being.
        last = toks[-1]
        if f in seen or last in seen:
            continue
        seen.add(f)
        seen.add(last)
        out.append(span)
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# WHAT IS EVEN CHECKABLE
# ═══════════════════════════════════════════════════════════════════════════════

# Weather, interior states, and interpretive framing are not falsifiable and under
# D450 they are ALLOWED in a story. They are the sentences that make Freud a living
# human being rather than a label. They are classified, not punished.
_ATMOSPHERE = re.compile(
    r'\b(imagine|picture|sweltering|nervous|anxious|excited|afraid|hoped|dreamed|'
    r'felt|feels|feeling|seemed|seems|appears|perhaps|might have|would have|'
    r'as if|like a|symbolic|symbolis|symboliz|reflects|represents|embodies|'
    r'significan|resonate|evoke)', re.IGNORECASE)

_YEAR = re.compile(r'\b(1[0-9]{3}|20[0-2][0-9])\b')

# Verbs that put a named person into a checkable role with someone or something.
_ROLE_VERB = re.compile(
    r'\b(accompanied|brokered|arranged|introduced|founded|published|printed|'
    r'commissioned|illustrated|wrote|painted|sculpted|designed|created|'
    r'met|married|discovered|invented|bought|sold|donated|gave|left|'
    r'destroyed|refused|translated|edited|photographed)\b', re.IGNORECASE)


def classify(sentence: str, known: List[str]) -> Dict:
    """ATMOSPHERE (allowed, unfalsifiable) or CHECKABLE (has a factual assertion)."""
    people = named_people(sentence, known)
    has_year = bool(_YEAR.search(sentence))
    role = _ROLE_VERB.search(sentence)
    if (people and role) or has_year:
        return {'kind': 'CHECKABLE', 'people': people,
                'relation': role.group(1).lower() if role else '',
                'year': (_YEAR.search(sentence).group(1) if has_year else '')}
    return {'kind': 'ATMOSPHERE', 'people': people, 'relation': '', 'year': ''}


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRADICTION — the open question
# ═══════════════════════════════════════════════════════════════════════════════

def open_question(relation: str, actor: str, context: str) -> str:
    """Ask WHO did it, never 'did X do it'. See the module docstring."""
    return f'who {relation} {context}'.strip()


def contradiction_check(actor: str, relation: str, context: str,
                        known: List[str], in_claim: Optional[List[str]] = None) -> Dict:
    """Does any source name a DIFFERENT party for this role?

    Returns status:
      SUPPORTED       — sources name the actor for this role
      CONTRADICTED    — sources name someone else, repeatedly, and never the actor
      UNCONTRADICTED  — nothing conclusive. ALLOWED under D450.
    """
    from work_story_searcher import _serp_search
    # TWO phrasings, pooled. Measured over three runs of the Woolf claim with a
    # single query: the right alternatives (Stefan Zweig, Edward James) came back
    # EVERY time, but their counts hovered at 1-2 against a threshold of 2, so the
    # false claim was caught 1 run in 3. The signal was real and the sample was too
    # small. Pooling a second phrasing is the cheapest way to stop a true finding
    # depending on which eight results the engine happened to return.
    queries = [open_question(relation, actor, context),
               f'{context} {relation} by'.strip()]
    snippets: List[str] = []
    for qq in queries:
        try:
            r_, _ = _serp_search(qq)
        except Exception:
            continue
        snippets += [(s.get('snippet') or '') for s in r_]
    q = queries[0]

    actor_f = _fold(actor)
    actor_last = actor_f.split()[-1] if actor_f.split() else actor_f

    supports = [s for s in snippets if actor_last and actor_last in _fold(s)]
    if supports:
        return {'status': 'SUPPORTED', 'query': q, 'evidence': supports[0][:220],
                'alternatives': []}

    # Nobody named the actor. Who DID the sources name for this role?
    #
    # Everyone ALREADY IN THE CLAIM must be excluded, not just the actor. First
    # cut only excluded the actor, so the Woolf claim reported its alternatives as
    # "Sigmund Freud (4), Dalí (4)" — the other two people in its own sentence.
    # Right verdict, useless reason, and a false-positive risk on true claims.
    blocked = {actor_f}
    for p in (in_claim or []):
        pf = _fold(p)
        blocked.add(pf)
        if pf.split():
            blocked.add(pf.split()[-1])

    def _is_blocked(pf: str) -> bool:
        last = pf.split()[-1] if pf.split() else pf
        return any(b and (b in pf or pf in b or b == last) for b in blocked)

    # No role-verb filter on the snippet. Measured: requiring one threw away
    #   "at the urging of Austrian writer Stefan Zweig and the poet Edward James,
    #    Freud agreed to a meeting in London in July 1938"
    # which is the single best piece of evidence in the result set, and dropped
    # both real alternatives to one mention each — under the threshold, so the
    # false Woolf claim passed. The actor's absence is what carries the signal;
    # the snippet's grammar does not.
    counts: Dict[str, int] = {}
    ev: Dict[str, str] = {}
    for s in snippets:
        for p in named_people(s, known):
            if _is_blocked(_fold(p)):
                continue
            counts[p] = counts.get(p, 0) + 1
            ev.setdefault(p, s)

    # DID THE SEARCH EVEN LAND ON THE RIGHT SUBJECT? Measured: the TRUE claim
    # "Boris Fridman gave Le Lézard aux plumes d'or to the MFA" was CONTRADICTED
    # three runs in three, with alternatives "ALEXANDER CALDER Lizard" and "Thomas
    # Wargin" — the query had drifted to a different artwork entirely. A
    # contradiction is only meaningful when the results are about the claim. When
    # they are not, we know nothing, and under D450 knowing nothing is ALLOWED.
    anchors = [a for a in re.findall(r"[A-Za-zà-ÿ'’\-]{5,}", context)]
    on_topic = sum(1 for s in snippets
                   if any(_fold(a) in _fold(s) for a in anchors))
    if anchors and on_topic < 2:
        return {'status': 'NO_USABLE_EVIDENCE', 'query': q, 'evidence': '',
                'alternatives': []}

    alts = sorted(counts.items(), key=lambda kv: -kv[1])
    # THE SIGNAL IS THE ACTOR'S TOTAL ABSENCE, not the alternative's frequency.
    # Requiring the alternative twice caught the false Woolf claim only 2 runs in 3
    # even with two pooled queries — Stefan Zweig came back every single time, but
    # sometimes in one snippet and sometimes in two. Frequency of the right answer
    # is an artifact of which results the engine returns; the actor being in NONE
    # of ~16 snippets about exactly this role is not.
    if alts and len(snippets) >= 6:
        return {'status': 'CONTRADICTED', 'query': q,
                'evidence': ev[alts[0][0]][:220],
                'alternatives': [f'{p} ({n})' for p, n in alts[:3]]}
    return {'status': 'UNCONTRADICTED', 'query': q, 'evidence': '',
            'alternatives': [f'{p} ({n})' for p, n in alts[:3]]}


# ═══════════════════════════════════════════════════════════════════════════════

def validate(story: str, subject: str = '', known: Optional[List[str]] = None,
             live: bool = True) -> Dict:
    """The story gate. PASSES unless a sentence is contradicted by sources."""
    known = list(known or [])
    if subject:
        known.append(subject)
    known += named_people(story, known)

    rows = []
    for s in split_sentences(story):
        c = classify(s, known)
        row = {'text': s, 'kind': c['kind'], 'people': c['people'],
               'status': 'ALLOWED', 'query': '', 'evidence': '', 'alternatives': []}
        if c['kind'] == 'CHECKABLE' and c['relation'] and c['people'] and live:
            actor = c['people'][0]
            others = [p for p in c['people'][1:]]
            context = ' '.join(others + ([c['year']] if c['year'] else [])) or subject
            r = contradiction_check(actor, c['relation'], context, known,
                                    in_claim=c['people'])
            row.update({'status': r['status'], 'query': r['query'],
                        'evidence': r['evidence'], 'alternatives': r['alternatives']})
        rows.append(row)

    contradicted = [r for r in rows if r['status'] == 'CONTRADICTED']
    return {'verdict': 'REJECTED_FALSEHOOD' if contradicted else 'PASSES',
            'contradicted': len(contradicted), 'sentences': rows}


def report(res: Dict) -> None:
    print(f"\nVERDICT: {res['verdict']}   ({res['contradicted']} contradicted)\n")
    for r in res['sentences']:
        print(f"  [{r['kind']:10}] [{r['status']:14}] {r['text'][:70]}")
        if r['query']:
            print(f"                              q: {r['query'][:66]}")
        if r['status'] == 'CONTRADICTED':
            print(f"                              sources say: "
                  f"{', '.join(r['alternatives'])}")
            print(f"                              {r['evidence'][:100]}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--file')
    p.add_argument('--text', default='')
    p.add_argument('--subject', default='')
    p.add_argument('--offline', action='store_true')
    a = p.parse_args()
    story = a.text or open(a.file, encoding='utf-8').read()
    report(validate(story, a.subject, live=not a.offline))


if __name__ == '__main__':
    main()
