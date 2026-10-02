#!/usr/bin/env python3
"""story_material_check.py — can the corpus actually source the story we want?

The second of the two routines (D428). `story_opportunity_scan.py` says a stop
NEEDS another story and names the handles to hang it on. This one asks the
question that must never be merged with that one:

    for each of those handles, does the corpus contain enough to write from?

THE BAR — three things, all of them from the corpus, none from memory:

    1. a named PERSON
    2. a specific ACTION that person took   (a verb; a date makes it stronger)
    3. a CONSEQUENCE — something risked, refused, lost, survived, or first/last

Michael's own worked example is the shape: an edition destroyed in 1967. Person,
action, consequence, three sentences. Anything short of all three is PARTIAL, and
PARTIAL does not authorise prose — it authorises another search.

WHY THE SEPARATION IS THE POINT
-------------------------------
"Needs a story" and "can have a story" must be free to disagree. When a stop needs
one and nothing can source it, the correct output is SILENCE. The alternative is
what shipped on 2026-08-12: an empty publisher slot filled with "The Hogarth
Press" (D427). This routine is allowed to return nothing, and returning nothing is
a success.

    python3 story_material_check.py --state story_lab_state/stop2_prod.json \
        --corpus story_lab_state/stop2_page_text.txt
"""
import argparse
import json
import os
import re
import sys
import textwrap
import unicodedata
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_opportunity_scan import (  # noqa: E402
    _AGENCY_VERB, _STAKES, _PROPER_SPAN, _fold, measure, split_sentences, verdict,
)

_YEAR = re.compile(r'\b(1[5-9]\d{2}|20[0-2]\d)\b')

# Donors and collectors are written with middle initials far more often than
# artists are — "Lois B. Torf", "Michael K. Torf". The shared _PROPER_SPAN breaks
# on the "B." and yields nothing, so the one person who could carry the story is
# invisible exactly in the donor case. Own pattern here.
_PERSON_WITH_INITIAL = re.compile(
    r'\b([A-Z][a-zà-ÿ]+(?:\s+[A-Z]\.)*'
    r'(?:\s+(?:de|du|von|van|di|del|des)\s+|\s+)[A-Z][a-zà-ÿ]+)\b'
)

_CONTINUES = re.compile(r'^\s*(He|She|They|It|His|Her|Their)\b')

# Institutions and rooms are not protagonists. They can be the SUBJECT of a story
# ("who is the Torf Gallery named for") but the story itself needs a human.
_NOT_A_PERSON = re.compile(
    r'\b(gallery|museum|press|editions?|verve|society|foundation|'
    r'university|institute|company|workshop|atelier|rights)\b', re.IGNORECASE)


def load_corpus(paths: List[str], state: Dict) -> str:
    """Read the grounding corpus, with museum-site navigation stripped.

    Raw `page_text` is mostly menu: "Getting Here / Dining / Groups / Talks".
    Left in, every capitalised nav pair is offered as a person and the material
    check reports a cast of characters that does not exist. `exhibition_checklist`
    already solved this for its own extractor — reuse it rather than re-guess.
    """
    from exhibition_checklist import _filter_nav_from_page_text
    chunks = []
    for p in paths or []:
        if os.path.exists(p):
            chunks.append(_filter_nav_from_page_text(open(p, encoding='utf-8').read()))
    for s in state.get('ranked_snippets', []) or state.get('search_results', []) or []:
        if s.get('snippet'):
            chunks.append(s['snippet'])
    return '\n'.join(chunks)


def _corpus_units(corpus: str) -> List[str]:
    """Split the corpus into units. A newline ends a unit as firmly as a full stop —
    scraped pages are full of unpunctuated lines, and treating a whole block as one
    'sentence' drags unrelated names into every passage."""
    units = []
    for line in corpus.split('\n'):
        units.extend(split_sentences(line))
    return [u for u in units if u.strip()]


def passages_about(handle: str, corpus: str) -> List[str]:
    """Corpus sentences that mention this handle. Accent-folded (D243)."""
    key = _fold(handle)
    tail = key.split()[-1] if key.split() else key
    units = _corpus_units(corpus)
    hit = []
    for i, s in enumerate(units):
        f = _fold(s)
        if key in f or (len(tail) >= 4 and re.search(r'\b' + re.escape(tail) + r'\b', f)):
            hit.append(i)
    # Carry the run across pronoun continuations — the same defect fixed in
    # story_opportunity_scan. "…gave it to a collector who refused to break up the
    # set. She would not sell a single sheet." The consequence lives in the second
    # sentence and names nothing, so a literal-match window drops precisely the
    # part that makes it a story.
    extended = set(hit)
    for i in hit:
        j = i + 1
        while j < len(units) and _CONTINUES.match(units[j]):
            extended.add(j)
            j += 1
    return [units[i].strip() for i in sorted(extended)]


def assess(handle: str, corpus: str) -> Dict:
    """Does the corpus carry person + action + consequence for this handle?"""
    passages = passages_about(handle, corpus)
    blob = ' '.join(passages)

    people = []
    for m in _PERSON_WITH_INITIAL.finditer(blob):
        cand = m.group(1).strip()
        if _NOT_A_PERSON.search(cand) or _fold(cand) == _fold(handle):
            continue
        if cand not in people:
            people.append(cand)

    actions = [s for s in passages if _AGENCY_VERB.search(s)]
    consequences = [s for s in passages if _STAKES.search(s)]
    years = sorted(set(_YEAR.findall(blob)))

    have = {'person': bool(people), 'action': bool(actions), 'consequence': bool(consequences)}
    missing = [k for k, v in have.items() if not v]

    if not passages:
        state = 'NO MATERIAL'
    elif not missing:
        state = 'SOURCEABLE'
    else:
        state = 'PARTIAL'

    return {
        'handle': handle, 'state': state, 'missing': missing,
        'passages': len(passages), 'people': people[:6], 'years': years[:6],
        'action_example': actions[0] if actions else '',
        'consequence_example': consequences[0] if consequences else '',
    }


def report(need: Dict, results: List[Dict], corpus_chars: int) -> None:
    print(f"\n{'=' * 78}\nSTORY MATERIAL CHECK\n{'=' * 78}")
    print(f"\n  QUESTION 1 — does this stop need another story?")
    print(f"    {'YES' if need['needs_additional_story'] else 'NO'}")
    print(textwrap.fill(need['why'], width=72, initial_indent='    ',
                        subsequent_indent='    '))

    print(f"\n  QUESTION 2 — can the corpus source one?   corpus = {corpus_chars} chars")
    if not corpus_chars:
        print("    corpus is EMPTY — nothing can be sourced, and that is a corpus")
        print("    failure, not a story failure. Do not proceed to writing.")

    print(f"\n{'-' * 78}\n  {'handle':22} {'passages':>8}  state         missing\n{'-' * 78}")
    for r in results:
        mark = {'SOURCEABLE': '  ', 'PARTIAL': '· ', 'NO MATERIAL': '! '}[r['state']]
        print(f" {mark}{r['handle'][:21]:22} {r['passages']:>8}  {r['state']:12}  "
              f"{', '.join(r['missing']) or '—'}")

    for r in results:
        if r['state'] == 'NO MATERIAL':
            continue
        print(f"\n  {r['handle']} — {r['state']}")
        if r['people']:
            print(f"      people:      {', '.join(r['people'])}")
        if r['years']:
            print(f"      years:       {', '.join(r['years'])}")
        if r['action_example']:
            print(textwrap.fill(r['action_example'][:200], width=70,
                                initial_indent='      action:      ',
                                subsequent_indent='                   '))
        if r['consequence_example']:
            print(textwrap.fill(r['consequence_example'][:200], width=70,
                                initial_indent='      consequence:  ',
                                subsequent_indent='                   '))

    sourceable = [r for r in results if r['state'] == 'SOURCEABLE']
    partial = [r for r in results if r['state'] == 'PARTIAL']

    print(f"\n{'=' * 78}")
    if need['needs_additional_story'] and sourceable:
        print(f"  VERDICT: WRITE — needs a story, and {len(sourceable)} handle(s) can be sourced")
        print(f"           {', '.join(r['handle'] for r in sourceable)}")
    elif need['needs_additional_story'] and not sourceable:
        print("  VERDICT: SILENCE — this stop needs another story and the corpus")
        print("           cannot source one. Writing anything here means inventing it.")
        if partial:
            print(f"\n           {len(partial)} handle(s) are PARTIAL — the correct next")
            print("           action is another SEARCH, not another sentence:")
            for r in partial:
                print(f"             · {r['handle']}: corpus lacks {', '.join(r['missing'])}")
    else:
        print("  VERDICT: NOTHING TO DO — the stop already carries a story.")
    print('=' * 78)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--state', required=True)
    p.add_argument('--corpus', action='append', default=[],
                   help='corpus file (repeatable); state snippets are added automatically')
    p.add_argument('--json', dest='as_json', action='store_true')
    a = p.parse_args()

    state = json.load(open(a.state))
    text = (state.get('tour_orientation', '') + '\n' + state.get('tour_prose', '')).strip()
    corpus = load_corpus(a.corpus, state)

    m = measure(text)
    need = verdict(m)
    # FLAT first: a subject already established but carrying no stakes is the
    # strongest place to attach a story. DANGLING handles are the fallback.
    handles = ([h['surface'] for h in m['handles'] if h['state'] == 'FLAT']
               + [h['surface'] for h in m['handles'] if h['state'] == 'DANGLING'])
    results = [assess(h, corpus) for h in handles]

    if a.as_json:
        print(json.dumps({'need': need, 'material': results,
                          'corpus_chars': len(corpus)}, ensure_ascii=False, indent=2))
    else:
        report(need, results, len(corpus))


if __name__ == '__main__':
    main()
