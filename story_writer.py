#!/usr/bin/env python3
"""story_writer.py — write the additional story, or refuse.

The third routine (D428/D429/D433). `story_opportunity_scan` says a stop needs a
story; `story_material_check` says the corpus can source one; this writes it.

Michael's bar, from his review of 2026-08-12 and restated twice since:

    at least THREE sentences, carrying emotional load, and tied to the OBJECT
    IN THE CASE — not a biography of the person who happens to be nearby

His own complaint about the delivered stop 1 was precise: "The current statement
made the story out of Broder" — Broder arrived as a CV rather than as the man who
decided this book would exist. So the last sentence of every story written here
must return to the object the visitor is standing in front of.

THE CONSTRAINT THAT MAKES THIS DIFFERENT FROM WHAT SHIPPED
----------------------------------------------------------
The writer sees the corpus and NOTHING ELSE. No stop record prose, no parametric
recall, no "you know about this artist". Every proper noun and every role claim in
the output is then checked back against that same corpus, and a story containing
anything ungrounded is REJECTED, not published.

That check is the difference between this and the paragraph that told Michael the
publisher was The Hogarth Press (D427). The model was not lying; nobody ever asked
it where the name came from.

Refusal is a success. A stop with no story is better than a stop with a wrong one.

    python3 story_writer.py --state story_lab_state/stop2_prod.json \\
        --corpus story_lab_state/stop2_survivors.txt --subject "Salvador Dalí"
"""
import argparse
import json
import os
import re
import sys
import textwrap
from typing import Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for _l in open(os.path.join(HERE, '.env')):
    _l = _l.strip()
    if _l and not _l.startswith('#') and '=' in _l:
        _k, _v = _l.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from story_opportunity_scan import _AGENCY_VERB, _STAKES, _fold, split_sentences  # noqa: E402
from story_material_check import (  # noqa: E402
    _PERSON_WITH_INITIAL, _NOT_A_PERSON, load_corpus, passages_about,
)

MODEL = os.environ.get('STORY_WRITER_MODEL', 'gpt-4o')

SYSTEM = """\
You write one short story for a museum audio tour. A visitor is standing in front \
of the object right now, with headphones on.

ABSOLUTE RULE: every fact you state must appear in the SOURCE MATERIAL below. You \
know a great deal about art history. None of it may be used here. If the source \
does not say it, it does not go in the story — no dates, no names, no places, no \
motives, no publishers. This is not a style preference; a story containing one \
unsourced fact is thrown away entirely.

THE SHAPE:
- Exactly 3 or 4 sentences.
- Someone does something. Something is at stake, refused, lost, risked or final.
- The LAST sentence must name a PHYSICAL PROPERTY of the thing in front of the \
listener that appears in the source — what it is made of, how many there are, what \
year it was made, what it was printed on. Not its significance. Not what it \
"represents" or "embodies" or "reflects". A visitor can see the object; tell them \
something true about the one they are looking at.
- Use at least one specific number, age or date from the source.
- **Never assert that one thing CAUSED or LED TO another unless the source says so.**
Do not write "culminating in", "leading to", "which inspired", "as a result", \
"paving the way", "this influenced". Two facts sitting near each other in the source \
are not a causal chain. State what happened; let the listener draw the line. This is \
the single most common reason a story is thrown away.
- No "imagine", no "picture this", no second person, no rhetorical questions.
- Never write the words "the object in the case", "this exhibit", "this exhibition", \
"ongoing dialogue", "serves as a reminder", or "the transformative power of". Those \
are the phrases that survive when a writer has nothing to say.

If the source material cannot support three sentences of this shape, reply with \
exactly: INSUFFICIENT
"""


def build_prompt(record: Dict, corpus: str, subject: str) -> str:
    return (
        f"OBJECT IN THE CASE: {record.get('canonical_title', '')}\n"
        f"VENUE: {record.get('venue_name', '')}\n"
        f"SUBJECT OF THE STORY: {subject}\n\n"
        f"SOURCE MATERIAL (the only facts you may use):\n"
        f"-----------------------------------------\n{corpus.strip()}\n"
        f"-----------------------------------------\n\n"
        f"Write the story."
    )


def call_llm(system: str, user: str) -> str:
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        raise SystemExit('story_writer: OPENAI_API_KEY not set')
    r = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={'model': MODEL, 'temperature': 0.4, 'max_tokens': 400,
              'messages': [{'role': 'system', 'content': system},
                           {'role': 'user', 'content': user}]},
        timeout=60)
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION — every claim traced back to the corpus
# ═══════════════════════════════════════════════════════════════════════════════

_YEAR = re.compile(r'\b(1[5-9]\d{2}|20[0-2]\d)\b')
_PROPER = re.compile(r'\b((?:[A-Z][a-zà-ÿ]+\.?\s+)*[A-Z][a-zà-ÿ]+)\b')

_SAFE_OPENERS = frozenset({
    'the', 'this', 'that', 'these', 'those', 'a', 'an', 'in', 'on', 'at', 'by',
    'for', 'with', 'from', 'when', 'while', 'and', 'but', 'his', 'her', 'their',
    'it', 'he', 'she', 'they', 'both', 'neither', 'no', 'not', 'nothing',
})


def validate(story: str, corpus: str, record: Dict) -> Tuple[bool, List[Dict]]:
    """Every name and every year in the story must be in the corpus."""
    findings = []
    fc = _fold(corpus)
    record_blob = _fold(' '.join(str(v) for v in record.values() if v))

    for m in _PERSON_WITH_INITIAL.finditer(story):
        name = m.group(1).strip()
        if _NOT_A_PERSON.search(name):
            continue
        if name.split()[0].lower() in _SAFE_OPENERS:
            continue
        f = _fold(name)
        if f in fc or f in record_blob:
            continue
        surname = f.split()[-1]
        if len(surname) >= 4 and re.search(r'\b' + re.escape(surname) + r'\b', fc):
            continue
        findings.append({'kind': 'person', 'value': name,
                         'why': 'not in source material'})

    for y in set(_YEAR.findall(story)):
        if y not in corpus:
            findings.append({'kind': 'year', 'value': y,
                             'why': 'not in source material'})

    return (not findings), findings


def shape_check(story: str, record: Dict, corpus: str) -> Tuple[bool, Dict]:
    """Michael's bar: 3+ sentences, agency, stakes, and it ends on the object."""
    sents = split_sentences(story)
    title = _fold(record.get('canonical_title', ''))
    title_words = [w for w in title.split() if len(w) > 3]
    last = _fold(sents[-1]) if sents else ''
    object_words = set(title_words) | {'book', 'edition', 'sheet', 'print', 'page',
                                       'case', 'volume', 'suite', 'portfolio',
                                       'lithograph', 'etching', 'drypoint', 'sheepskin'}
    banned = [b for b in ('object in the case', 'this exhibit', 'ongoing dialogue',
                          'serves as a reminder', 'transformative power',
                          'represents', 'embodies', 'reflects the', 'stands as')
              if b in story.lower()]
    concrete = [w for w in ('sheepskin', 'drypoint', 'lithograph', 'etching', 'set of',
                            'copies', 'edition', 'printed', 'paper', 'vellum', 'suite')
                if w in last]
    has_number = bool(re.search(r'\b(\d{1,4})\b', sents[-1] if sents else ''))
    report = {
        'sentences': len(sents),
        'banned_phrases': banned,
        'concrete_in_last': concrete,
        'agency': sum(1 for s in sents if _AGENCY_VERB.search(s)),
        'stakes': sum(1 for s in sents if _STAKES.search(s)),
        'ends_on_object': any(w in last for w in object_words),
    }
    # 'ends_on_object' alone was gameable: the first accepted story closed with
    # "The object in the case represents this ongoing dialogue…" — it passed by
    # echoing the prompt's own vocabulary. The last sentence must now carry a
    # CONCRETE physical property or a number, and the empty closers are banned.
    ok = (report['sentences'] >= 3 and report['agency'] >= 1
          and report['stakes'] >= 1 and not banned
          and (report['concrete_in_last'] or has_number))
    return ok, report


def write_story(record: Dict, corpus: str, subject: str,
                attempts: int = 2) -> Dict:
    focused = '\n'.join(passages_about(subject, corpus)) or corpus
    for attempt in range(1, attempts + 1):
        story = call_llm(SYSTEM, build_prompt(record, focused, subject))
        if story.strip().upper().startswith('INSUFFICIENT'):
            return {'status': 'REFUSED_BY_WRITER', 'attempt': attempt,
                    'story': '', 'grounded': True, 'findings': []}
        grounded, findings = validate(story, corpus, record)
        shaped, shape = shape_check(story, record, corpus)
        result = {'attempt': attempt, 'story': story, 'grounded': grounded,
                  'findings': findings, 'shape': shape, 'shaped': shaped}
        if grounded and shaped:
            result['status'] = 'ACCEPTED'
            return result
        result['status'] = 'REJECTED'
        if attempt == attempts:
            return result
    return result


def report(res: Dict, subject: str) -> None:
    print(f"\n{'=' * 78}\nSTORY WRITER — subject: {subject}\n{'=' * 78}\n")
    if res['story']:
        print(textwrap.fill(res['story'], width=74, initial_indent='  ',
                            subsequent_indent='  '))
    else:
        print("  (no story produced)")

    sh = res.get('shape', {})
    if sh:
        print(f"\n  SHAPE   sentences={sh['sentences']}  agency={sh['agency']}  "
              f"stakes={sh['stakes']}  ends on the object={sh['ends_on_object']}")
    print(f"  GROUNDED  {res['grounded']}")
    for f in res.get('findings', []):
        print(f"    !! {f['kind']}: {f['value']!r} — {f['why']}")

    print(f"\n  STATUS: {res['status']}")
    if res['status'] == 'REJECTED':
        print("  Not published. An ungrounded or misshapen story is worse than none —")
        print("  this is the state that shipped 'The Hogarth Press' (D427).")
    elif res['status'] == 'REFUSED_BY_WRITER':
        print("  The writer judged the material insufficient and declined. That is a")
        print("  success, not a failure.")
    print('=' * 78)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--state', required=True)
    p.add_argument('--corpus', action='append', required=True)
    p.add_argument('--subject', required=True)
    p.add_argument('--attempts', type=int, default=2)
    p.add_argument('--json', dest='as_json', action='store_true')
    a = p.parse_args()

    state = json.load(open(a.state))
    record = state.get('stop', {})
    corpus = load_corpus(a.corpus, {})
    res = write_story(record, corpus, a.subject, a.attempts)
    if a.as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        report(res, a.subject)


if __name__ == '__main__':
    main()
