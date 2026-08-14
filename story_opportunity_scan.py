#!/usr/bin/env python3
"""story_opportunity_scan.py — where does a stop want another story?

Michael's ask, 2026-08-13: build "additional" story generation — the system should
notice that a stop would benefit from a new story, and go get one.

This is the FIRST of the two routines that needs. It answers only:

    which things does this text NAME and then FAIL TO DEVELOP?

That is Michael's own review metric, verbatim: "sentences keywords, adjectives,
people, actions. Words without follow up". He listed four for stop 1 — Book,
Mourlot Frères, the mythic narratives, surreal transformations — and each is a
handle the prose reaches for and drops.

A dangling handle is a story opportunity. The listener's attention has already
been pointed at it and then abandoned.

WHAT THIS ROUTINE DOES NOT DO, DELIBERATELY
-------------------------------------------
It does not ask whether material EXISTS for the story it proposes. That is a
separate routine against the corpus, and keeping the two apart is the whole
design. A stop can want a story that nothing on earth can source; the correct
output there is silence, not prose. Merge these two questions and you have built
a fabrication engine — see D427, where an empty publisher slot was filled by the
model with "The Hogarth Press".

So: this routine proposes. It never supplies.

    python3 story_opportunity_scan.py --state story_lab_state/stop2_prod.json
    python3 story_opportunity_scan.py --text-file stop.txt
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


# ═══════════════════════════════════════════════════════════════════════════════
# HANDLES — the things a text points at
# ═══════════════════════════════════════════════════════════════════════════════

_PROPER_SPAN = re.compile(
    r'\b((?:The\s+|Le\s+|La\s+|Les\s+)?'
    r'[A-Z][a-zà-ÿ]+(?:\s+(?:de|du|von|van|di|del|des|et)\s+|\s+)'
    r'[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)\b'
)
_QUOTED = re.compile(r'["“]([^"”]{3,80})["”]')
# Titles arrive with the sentence punctuation swept inside the closing quote
# ("Moses and Monotheism," / "Moses and Monotheism.") — three handles for one thing.
_TRAILING_PUNCT = re.compile(r'[\s.,;:!?]+$')

# Domain nouns that carry a story if developed and carry nothing if not.
# These are the "Book" case from Michael's review: a book has a writer, an
# illustrator, a publisher and a printer, and naming none of them wastes the word.
_LOADED_TERMS = {
    'book': 'a book has a writer, an illustrator, a publisher and a printer — name them',
    'books': 'a book has a writer, an illustrator, a publisher and a printer — name them',
    'workshop': 'whose workshop, and why did it get this commission',
    'edition': 'how many copies, who owns them now',
    'portfolio': 'who assembled it, and when',
    'archives': 'whose archive, and how did it get there',
    'collaboration': 'two people agreed to something — who asked whom',
    'commission': 'someone paid for this — who, and why',
    'exhibition': 'who curated it, and what were they arguing',
    'gallery': 'who is it named for',
    'illustrations': 'how were they made, and by what process',
    'lithographs': 'printed by whom, on what press',
    'etchings': 'bitten how many times, by whom',
}

_STOPWORD_HANDLES = frozenset({
    'the museum', 'the exhibition', 'the collection', 'the gallery',
})

# Verbs that indicate a HUMAN DID SOMETHING — the raw material of a story.
_AGENCY_VERB = re.compile(
    r'\b(chose|refused|insisted|fought|persuaded|paid|bought|sold|gave|donated|'
    r'destroyed|burned|hid|smuggled|fled|died|survived|founded|abandoned|'
    r'commissioned|rejected|demanded|begged|waited|returned|met|quarrelled|'
    r'quarreled|broke|swore|promised|betrayed|saved|rescued|inherited|'
    # Walking tours and civic places. The list above was tuned on museum material
    # — refused, printed, donated — and scored every building in Boston as having
    # no agency. Louisburg Square came back PARTIAL missing 'action' against a
    # corpus that said "designed by Charles Bulfinch and completed in 1798".
    r'designed|built|constructed|completed|erected|rebuilt|demolished|'
    r'named|renamed|laid|opened|closed|settled|occupied|marched|voted|'
    r'petitioned|sheltered|hid|escaped|elected|appointed|resigned)\b',
    re.IGNORECASE)

# Consequence / stakes markers — the difference between a fact and a story.
#
# v1 included "because" and "so that" and the scan came back NO on a stop Michael
# scored 3/5 for having no stories. Those two words are how exposition explains
# itself — "Dalí chose this text because he considered Freud's exploration rich
# terrain" is a motive attributed by the writer, not a cost paid by anyone. Stakes
# means something was risked, refused, lost or survived. Dropped both.
_STAKES = re.compile(
    r'\b(only|never|no one|nothing|until|despite|although|even though|'
    r'the last|the only|the first|for the first time|would not|could not|'
    r'had to|refused|in the end|by then|too late|instead of|but not|'
    r'at the cost|risked|forced|'
    # Outright destructive and final outcomes. The list above is all CONTRAST —
    # only, never, despite — and could not see the single best consequence in the
    # whole MFA tour: "For technical reasons, Miró decided to DESTROY the
    # lithographs." Destroying your own edition is not a contrast, it is the
    # consequence. Stop 1 stayed SILENCE with that sentence sitting in its corpus.
    r'destroyed|destroy|pulped|burned|burnt|abandoned|scrapped|cancelled|'
    r'canceled|unfinished|incomplete|posthumous(?:ly)?|left\s+half|'
    r'started\s+over|began\s+again|withdrew|withdrawn|lost)\b', re.IGNORECASE)


def _fold(t: str) -> str:
    nfd = unicodedata.normalize('NFD', t or '')
    s = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', s.lower()).strip()


def split_sentences(text: str) -> List[str]:
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"“\'])', text.strip())
    return [p.strip() for p in parts if p.strip()]


def find_handles(text: str) -> List[Dict]:
    """Every thing the text names and could be asked about."""
    handles, seen = [], set()

    def add(surface, kind, note=''):
        key = _fold(surface)
        if not key or key in seen or key in _STOPWORD_HANDLES:
            return
        seen.add(key)
        handles.append({'surface': surface, 'kind': kind, 'note': note})

    for m in _PROPER_SPAN.finditer(text):
        add(m.group(1).strip(), 'proper noun')
    for m in _QUOTED.finditer(text):
        add(_TRAILING_PUNCT.sub('', m.group(1).strip()), 'title')
    low = _fold(text)
    for term, note in _LOADED_TERMS.items():
        if re.search(r'\b' + re.escape(term) + r'\b', low):
            add(term, 'loaded noun', note)
    return handles


# ═══════════════════════════════════════════════════════════════════════════════
# DEVELOPMENT — how much does the text actually SAY about each handle?
# ═══════════════════════════════════════════════════════════════════════════════

_PRONOUN = re.compile(r'\b(he|she|they|him|her|them|his|hers|their)\b', re.IGNORECASE)


def _bridge_pronouns(hits: List[int], sentences: List[str],
                     handles: List[Dict], owner: Dict) -> List[int]:
    """Extend a handle's sentence run across pronoun references.

    Good prose names a person once and then says "he". Requiring the literal name
    in every sentence therefore scores well-written narration BELOW clumsy
    narration, which is backwards. A sentence continues the current subject when
    it carries a personal pronoun and names no competing person.

    Only proper nouns get this. "the exhibition" is not referred to as "he".
    """
    if owner['kind'] != 'proper noun':
        return hits
    others = [_fold(h['surface']) for h in handles
              if h['kind'] == 'proper noun' and h is not owner]
    extended = set(hits)
    for i, s in enumerate(sentences):
        if i in extended or not _PRONOUN.search(s):
            continue
        if not any(i - 1 in extended or i - 1 == j for j in extended):
            continue  # must directly follow a sentence already in the run
        folded = _fold(s)
        if any(o in folded or (o.split()[-1] if o.split() else o) in folded
               for o in others):
            continue  # a competing person is named — do not assume coreference
        extended.add(i)
    return sorted(extended)


def measure(text: str) -> Dict:
    sentences = split_sentences(text)
    handles = find_handles(text)

    for h in handles:
        key = _fold(h['surface'])
        # match on the last significant word too, so "Salvador Dalí" catches "Dalí"
        tail = key.split()[-1] if key.split() else key
        hits = [i for i, s in enumerate(sentences)
                if key in _fold(s) or (len(tail) >= 4 and re.search(
                    r'\b' + re.escape(tail) + r'\b', _fold(s)))]
        h['sentences'] = len(hits)
        h['at'] = _bridge_pronouns(hits, sentences, handles, h) if hits else hits
        # agency: does any sentence show this handle DOING something?
        h['agency'] = sum(1 for i in hits if _AGENCY_VERB.search(sentences[i]))
        h['stakes'] = sum(1 for i in hits if _STAKES.search(sentences[i]))

        # state is assigned below, once the RUN is known — scattering a stake
        # anywhere across six sentences is not the same as putting one inside the
        # three consecutive sentences that would be the story. Judging on the
        # first and reporting on the second is how the verdict and the handle
        # table came to disagree about Salvador Dalí.

    # Story shape: the longest run of consecutive sentences about one handle.
    #
    # v1 asked only "are there 3 consecutive sentences naming the same handle",
    # then checked agency and stakes anywhere in the WHOLE text. That passes any
    # stop whose subject is named throughout — which is every stop. The run itself
    # has to carry the load, or it is a paragraph about someone, not a story.
    best = {'handle': None, 'run': 0, 'agency': 0, 'stakes': 0}
    for h in handles:
        run = longest = 0
        prev = -2
        span, best_span = [], []
        for i in h['at']:
            if i == prev + 1:
                run += 1
                span.append(i)
            else:
                run, span = 1, [i]
            if run > longest:
                longest, best_span = run, list(span)
            prev = i
        h['run'] = longest
        h['run_agency'] = sum(1 for i in best_span if _AGENCY_VERB.search(sentences[i]))
        h['run_stakes'] = sum(1 for i in best_span if _STAKES.search(sentences[i]))
        # A story is about someone. A title or a loaded noun cannot carry one.
        h['can_carry'] = h['kind'] == 'proper noun'

        if longest >= 3 and h['run_agency'] >= 1 and h['run_stakes'] >= 1:
            h['state'] = 'DEVELOPED'
        elif longest >= 3 and h['run_agency'] >= 1:
            # Named repeatedly, shown acting, nothing at stake within the run.
            # This is where stop 2's Salvador Dalí actually sits, and v1 called it
            # DEVELOPED and moved on — which pointed the whole routine at the
            # gallery signage instead of at the subject the stop is about. A flat
            # protagonist is the BEST place to attach a story, not a finished one:
            # the listener already knows who this is.
            h['state'] = 'FLAT'
        elif h['sentences'] >= 2:
            h['state'] = 'MENTIONED'
        else:
            h['state'] = 'DANGLING'
        if (h['can_carry'] and longest >= 3
                and h['run_agency'] >= 1 and h['run_stakes'] >= 1
                and longest > best['run']):
            best = {'handle': h['surface'], 'run': longest,
                    'agency': h['run_agency'], 'stakes': h['run_stakes']}
    if best['handle'] is None:
        # nothing qualifies — report the longest run that exists, for diagnosis
        _lr = max(handles, key=lambda x: x.get('run', 0), default=None)
        if _lr:
            best = {'handle': _lr['surface'], 'run': _lr.get('run', 0),
                    'agency': _lr.get('run_agency', 0), 'stakes': _lr.get('run_stakes', 0),
                    'qualifies': False}

    return {
        'sentence_count': len(sentences),
        'handles': sorted(handles, key=lambda h: (h['sentences'], h['agency'])),
        'longest_run': best,
        'total_agency': sum(1 for s in sentences if _AGENCY_VERB.search(s)),
        'total_stakes': sum(1 for s in sentences if _STAKES.search(s)),
        'sentences': sentences,
    }


def verdict(m: Dict) -> Dict:
    """Michael's bar: at least one story of >=3 sentences carrying emotional load."""
    lr = m['longest_run']
    qualifies = lr.get('qualifies', lr['handle'] is not None)
    has_arc = lr['run'] >= 3
    has_load = lr['agency'] >= 1 and lr['stakes'] >= 1
    dangling = [h for h in m['handles'] if h['state'] == 'DANGLING']

    if qualifies and has_arc and has_load:
        need, why = False, (f"{lr['handle']} carries {lr['run']} consecutive sentences "
                            f"with an action and something at stake")
    elif has_arc and not has_load:
        need, why = True, (f"the longest run ({lr['run']} sentences, {lr['handle']}) has "
                           f"agency={lr['agency']} stakes={lr['stakes']} — someone is "
                           f"described, but nothing is risked, refused or lost. "
                           f"That is exposition, not a story.")
    else:
        need, why = True, (f"longest qualifying run is {lr['run']} sentence(s); the bar "
                           f"is 3 consecutive sentences about one person, carrying an "
                           f"action and a consequence")
    return {'needs_additional_story': need, 'why': why,
            'dangling_count': len(dangling), 'has_arc': has_arc, 'has_load': has_load}


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════════════════════════════════════════

def report(m: Dict, v: Dict) -> None:
    print(f"\n{'=' * 78}\nSTORY OPPORTUNITY SCAN\n{'=' * 78}")
    print(f"\n  {m['sentence_count']} sentences · "
          f"{m['total_agency']} with a person doing something · "
          f"{m['total_stakes']} with stakes")
    print(f"  longest run about one subject: {m['longest_run']['run']} "
          f"({m['longest_run']['handle']})")

    print(f"\n{'-' * 78}\n  WHAT THE TEXT NAMES, AND HOW FAR IT FOLLOWS THROUGH\n{'-' * 78}")
    print(f"\n  {'handle':34} {'sent':>4} {'act':>4} {'stk':>4}  state")
    for h in reversed(m['handles']):
        mark = {'DEVELOPED': '   ', 'FLAT': ' > ', 'MENTIONED': ' · ',
                'DANGLING': ' ! '}[h['state']]
        print(f" {mark}{h['surface'][:33]:34} {h['sentences']:>4} "
              f"{h['agency']:>4} {h['stakes']:>4}  {h['state']}")

    dangling = [h for h in m['handles'] if h['state'] == 'DANGLING']
    if dangling:
        print(f"\n{'-' * 78}\n  STORY OPPORTUNITIES — named once, then dropped\n{'-' * 78}\n")
        for h in dangling:
            print(f"  · {h['surface']}")
            if h['note']:
                print(textwrap.fill(h['note'], width=72,
                                    initial_indent='      ask: ', subsequent_indent='           '))

    print(f"\n{'=' * 78}")
    print(f"  NEEDS AN ADDITIONAL STORY: "
          f"{'YES' if v['needs_additional_story'] else 'NO'}")
    print(textwrap.fill(v['why'], width=74, initial_indent='  ', subsequent_indent='  '))
    print(f"\n  {v['dangling_count']} handle(s) available to hang one on.")
    print("\n  NOT ANSWERED HERE: whether any source can supply these stories. That is")
    print("  the availability check, and it is deliberately a separate routine. A stop")
    print("  that needs a story nothing can source must produce SILENCE, not prose.")
    print('=' * 78)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--state', help='story_lab state json (uses tour_orientation + tour_prose)')
    p.add_argument('--text-file')
    p.add_argument('--json', dest='as_json', action='store_true')
    a = p.parse_args()

    if a.state:
        st = json.load(open(a.state))
        text = (st.get('tour_orientation', '') + '\n' + st.get('tour_prose', '')).strip()
    elif a.text_file:
        text = open(a.text_file, encoding='utf-8').read()
    else:
        sys.exit('story_opportunity_scan: pass --state or --text-file')

    m = measure(text)
    v = verdict(m)
    if a.as_json:
        print(json.dumps({**{k: x for k, x in m.items() if k != 'sentences'},
                          'verdict': v}, ensure_ascii=False, indent=2))
    else:
        report(m, v)


if __name__ == '__main__':
    main()
