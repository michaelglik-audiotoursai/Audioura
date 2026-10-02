#!/usr/bin/env python3
"""story_record_extract.py — recover the starting point from the delivered text.

Michael's ask, 2026-08-13: take "Original" — the stop 2 text exactly as it shipped —
and produce the starting-point record from it, with the fields filled in.

THE ONE THING THIS ROUTINE MUST NOT DO
--------------------------------------
It must not confuse "the text says X" with "X is true".

Read Original naively and you extract `publisher = The Hogarth Press`. That is the
fabrication Michael caught (D427). A record built that way launders an invention
into a fact and then feeds it back to the query builder, which searches for it,
finds nothing, and the stop gets thinner — while looking better instrumented.

So every field carries a STATUS, never a bare value:

    CLAIMED     the text asserts it; nothing has checked it
    GROUNDED    the text asserts it AND the corpus contains it
    CONTRADICTED the corpus says something else
    ABSENT      the text never says it

A CLAIMED field is not usable as a search key. It is a question to go answer.

    python3 story_record_extract.py --text-file ORIGINAL_stop2.txt
    python3 story_record_extract.py --text-file ORIGINAL_stop2.txt \\
        --corpus story_lab_state/stop2_survivors.txt
"""
import argparse
import json
import os
import re
import sys
import textwrap
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_opportunity_scan import _fold, split_sentences   # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURAL FIELDS — the scaffolding the tour format already carries
# ═══════════════════════════════════════════════════════════════════════════════

_STOP_LINE = re.compile(r'^\s*(?:top|stop)\s*(\d+)\s*:\s*(.+?)\s*$', re.I | re.M)
_FIELD = lambda name: re.compile(rf'^\s*{name}\s*:\s*(.+?)\s*$', re.I | re.M)
_ADDRESS = _FIELD('Address')
_COORDS = _FIELD('Coordinates')
_DIRECTIONS = _FIELD('Directions')

# "Your final stop in Museum of Fine Arts, Boston: Au Soleil du Plafond."
_VENUE_IN_DIRECTIONS = re.compile(
    r'\bstop\s+(?:in|at)\s+(.+?)(?::|\.|$)', re.I)

# A parenthetical gloss we added ourselves: "Le Lézard aux plumes d'or (The Lizard…)"
_GLOSS = re.compile(r'^(.*?)\s*\(([^)]{4,60})\)\s*$')


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE FIELDS — who the prose says did what
# ═══════════════════════════════════════════════════════════════════════════════

_ROLE_PATTERNS = [
    ('publisher',   r'\b(?:published|issued|released)\s+by\s+(?P<v>[A-Z][^.,;:]{2,55})'),
    ('publisher',   r'\bcommissioned\s+by\s+(?P<v>[A-Z][^.,;:]{2,55})'),
    ('publisher',   r'\bpublishers?\s+such\s+as\s+(?P<v>[A-Z][^.,;:]{2,55})'),
    ('printed_by',  r'\bprinted\s+by\s+(?P<v>[A-Z][^.,;:]{2,55})'),
    ('printed_by',  r'\bat\s+the\s+(?P<v>[A-Z][^.,;:]{2,55})\s+(?:workshop|atelier|press)'),
    ('artist',      r'(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)[^.]{0,80}?\billustrat(?:ing|ed)\b'),
    ('artist',      r'\billustrated\s+by\s+(?P<v>[A-Z][^.,;:]{2,55})'),
    ('writer',      r"(?P<v>[A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)+)'s\s+(?:seminal\s+)?(?:work|text|essay|book)"),
    ('writer',      r'\bwritten\s+by\s+(?P<v>[A-Z][^.,;:]{2,55})'),
    ('credit_line', r'\b((?:gift|bequest)\s+of\s+[A-Z][^.,;:]{2,55})'),
]

# Physical form words. The medium is what the thing IS, and Original never says.
_MEDIUM_TERMS = (
    'lithograph', 'etching', 'drypoint', 'aquatint', 'woodcut', 'engraving',
    'illustrated book', 'livre d\'artiste', 'vellum', 'sheepskin', 'lambskin',
    'portfolio', 'suite', 'oil on canvas', 'watercolour', 'watercolor', 'bronze',
)

_GALLERY = re.compile(r'\b((?:[A-Z][a-zà-ÿ]+\s+)+Gallery)\b')
# An exhibition NAME is a title, not the word "exhibition". "The exhibition at the
# Torf Gallery" names a room, not a show.
_EXHIBITION_NAMED = re.compile(
    r'\bexhibition\s+["“]([^"”]{4,70})["”]|["“]([^"”]{4,70})["”]\s+exhibition', re.I)


def _clean(v: str) -> str:
    v = re.sub(r'\s+', ' ', v).strip().rstrip('.,;:')
    return re.sub(r'\s+(?:and|in|to|for|with|this|the|a)$', '', v, flags=re.I).strip()


def _sentence_with(text: str, pos: int) -> str:
    start = max(text.rfind('.', 0, pos), text.rfind('\n', 0, pos)) + 1
    end = text.find('.', pos)
    return text[start:(len(text) if end == -1 else end + 1)].strip()


def extract(text: str) -> Dict[str, Dict]:
    """Build the starting-point record from the delivered text alone."""
    rec: Dict[str, Dict] = {}

    def put(field, value, source, kind='CLAIMED'):
        value = _clean(value) if value else ''
        if not value:
            return
        if field in rec and rec[field]['value']:
            if _fold(value) not in _fold(rec[field]['value']):
                rec[field].setdefault('also', []).append(value)
            return
        rec[field] = {'value': value, 'status': kind, 'source': source}

    m = _STOP_LINE.search(text)
    raw_title = m.group(2).strip() if m else ''
    gloss = _GLOSS.match(raw_title) if raw_title else None
    if gloss:
        put('canonical_title', gloss.group(1), 'stop heading', 'STRUCTURAL')
        put('english_title', gloss.group(2), 'parenthetical gloss in the heading', 'STRUCTURAL')
    elif raw_title:
        put('canonical_title', raw_title, 'stop heading', 'STRUCTURAL')
        put('english_title', raw_title, 'title is already English — no gloss present',
            'STRUCTURAL')

    for field, pat in (('address', _ADDRESS), ('coordinates', _COORDS)):
        mm = pat.search(text)
        if mm:
            put(field, mm.group(1), f'{field} line', 'STRUCTURAL')

    dm = _DIRECTIONS.search(text)
    if dm:
        vm = _VENUE_IN_DIRECTIONS.search(dm.group(1))
        if vm:
            put('venue', vm.group(1), 'Directions line', 'STRUCTURAL')

    for field, pat in _ROLE_PATTERNS:
        for mm in re.finditer(pat, text):
            put(field, mm.group('v'), _sentence_with(text, mm.start()))

    gm = _GALLERY.search(text)
    if gm:
        put('gallery', gm.group(1), _sentence_with(text, gm.start()))

    em = _EXHIBITION_NAMED.search(text)
    if em:
        put('exhibition_name', em.group(1) or em.group(2), _sentence_with(text, em.start()))

    low = text.lower()
    found_medium = [t for t in _MEDIUM_TERMS if t in low]
    if found_medium:
        put('medium', ', '.join(found_medium), 'physical-form words in the prose')

    return rec


REQUIRED = ['canonical_title', 'english_title', 'artist', 'writer', 'publisher',
            'printed_by', 'credit_line', 'medium', 'exhibition_name', 'gallery',
            'venue', 'address', 'coordinates']


def ground(rec: Dict[str, Dict], corpus: str) -> None:
    """Promote CLAIMED → GROUNDED, or mark it as unsupported by the corpus."""
    if not corpus:
        return
    fc = _fold(corpus)
    for field, cell in rec.items():
        if cell['status'] != 'CLAIMED':
            continue
        v = _fold(cell['value'])
        tokens = [t for t in v.split() if len(t) >= 4 and t not in ('the', 'press')]
        if v in fc or (tokens and all(re.search(r'\b' + re.escape(t) + r'\b', fc)
                                      for t in tokens)):
            cell['status'] = 'GROUNDED'
        else:
            cell['status'] = 'UNSUPPORTED'


_MARK = {'STRUCTURAL': '  ', 'GROUNDED': '  ', 'CLAIMED': '? ',
         'UNSUPPORTED': '! ', 'ABSENT': '! '}


def report(rec: Dict[str, Dict], had_corpus: bool) -> None:
    print(f"\n{'=' * 78}\nTHE STARTING POINT, RECOVERED FROM THE DELIVERED TEXT\n{'=' * 78}\n")
    for field in REQUIRED:
        cell = rec.get(field) or {'value': '', 'status': 'ABSENT', 'source': ''}
        mark = _MARK[cell['status']]
        val = cell['value'] or '—'
        print(f" {mark}{field:16} = {val}")
        if cell.get('also'):
            print(f"   {'':16}   (also claimed: {'; '.join(cell['also'])})")
        if cell['status'] in ('CLAIMED', 'UNSUPPORTED') and cell.get('source'):
            print(textwrap.fill(f'from: "{cell["source"]}"', width=72,
                                initial_indent='   ' + ' ' * 16 + '   ',
                                subsequent_indent='   ' + ' ' * 19))

    claimed = [f for f, c in rec.items() if c['status'] == 'CLAIMED']
    unsupported = [f for f, c in rec.items() if c['status'] == 'UNSUPPORTED']
    absent = [f for f in REQUIRED if f not in rec]

    print(f"\n{'-' * 78}")
    print(f"  STRUCTURAL {sum(1 for c in rec.values() if c['status'] == 'STRUCTURAL'):2}   "
          f"GROUNDED {sum(1 for c in rec.values() if c['status'] == 'GROUNDED'):2}   "
          f"CLAIMED {len(claimed):2}   UNSUPPORTED {len(unsupported):2}   "
          f"ABSENT {len(absent):2}")
    if not had_corpus:
        print("\n  No corpus given, so nothing could be promoted past CLAIMED. A CLAIMED")
        print("  field is what the delivered text asserts and nothing has checked —")
        print("  it is a QUESTION TO GO ANSWER, never a search key. Reading this text")
        print("  naively yields publisher = 'The Hogarth Press', which is the invention")
        print("  the tour shipped (D427).")
    if unsupported:
        print(f"\n  UNSUPPORTED — the text asserts these and the corpus does not carry them:")
        for f in unsupported:
            print(f"    · {f} = {rec[f]['value']}")
    if absent:
        print(f"\n  ABSENT — the delivered text never says these: {', '.join(absent)}")
    print('=' * 78)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--text-file', required=True)
    p.add_argument('--corpus', action='append', default=[])
    p.add_argument('--json', dest='as_json', action='store_true')
    p.add_argument('--out', default='')
    a = p.parse_args()

    text = open(a.text_file, encoding='utf-8').read()
    rec = extract(text)

    corpus = ''
    if a.corpus:
        from story_material_check import load_corpus
        corpus = load_corpus(a.corpus, {})
        ground(rec, corpus)

    if a.as_json:
        print(json.dumps(rec, ensure_ascii=False, indent=2))
    else:
        report(rec, bool(corpus))
    if a.out:
        json.dump(rec, open(a.out, 'w'), ensure_ascii=False, indent=2)
        print(f"  -> {a.out}")


if __name__ == '__main__':
    main()
