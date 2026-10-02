#!/usr/bin/env python3
"""Build the credit_line worksheet for a tour — offline, deterministic, free.

Michael asked for the tour text plus "at least credit_line" so he can write one
worked example of a story sentence that ties a PERSON to the OBJECT.

`credit_line` is the story keyword: the person the story gets built around, picked
out of the stop's own sentences by `interrogation_matrix._pick_credit_line`.

BEWARE THE NAME COLLISION (already recorded in `story_pipeline.py`): in
`work_story_searcher`, `credit_line` means the museum's credit line — "Gift of
Boris Fridman" — and is regex-mined for a donor. Here it means the story keyword.
Feeding one into the other cost two full pipeline runs.

No LLM, no search, no cost. Re-run freely.

    python3 story_worksheet.py [TOUR_FILE]
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from interrogation_matrix import build_matrix, extract_stops     # noqa: E402
from story_opportunity_scan import measure                       # noqa: E402

DEFAULT_TOUR = 'TOUR_MFA_20260812_2030.txt'

SLOTS = ['canonical_title', 'english_title', 'artist', 'publisher', 'printed_by',
         'medium', 'venue', 'credit_line']

EXCLUDED_SLOTS = ['canonical_title', 'english_title', 'artist', 'publisher',
                  'printed_by', 'venue', 'medium']


def build(tour_path: str) -> str:
    full = open(tour_path, encoding='utf-8').read()
    stops = extract_stops(full)
    out = io.StringIO()
    w = out.write

    w(f"# credit_line worksheet — `{os.path.basename(tour_path)}`\n\n")
    w("Offline and deterministic — no LLM, no search, no cost.\n")
    w(f"Re-run with `python3 story_worksheet.py {os.path.basename(tour_path)}`.\n\n")
    w("`credit_line` is **the story keyword**: the person the story gets built\n")
    w("around, picked out of the stop's own sentences. A story keyword that is not a\n")
    w("person cannot produce a sentence tying a person to the object.\n\n")
    w("Handle states, for reading the ladders below:\n")
    w("**FLAT** established but carrying no stakes (the best place to attach a story) ·\n")
    w("**MENTIONED** named, barely used · **DANGLING** named once and dropped ·\n")
    w("**DEVELOPED** already carries the stop, so never a keyword.\n\n---\n\n")

    for n in sorted(stops):
        s = stops[n]
        m = build_matrix(s['text'], tour_context=full)
        cl = m.get('credit_line') or {}
        value = cl.get('value') or ''

        w(f"## Stop {n} — {s['title']}\n\n")
        w(f"### credit_line: **{value or '(ABSENT)'}**\n")
        w(f"`{cl.get('status', 'ABSENT')}` · via `{cl.get('source') or '—'}`\n\n")

        w("| slot | value | status |\n|---|---|---|\n")
        for k in SLOTS:
            c = m.get(k) or {}
            v = (c.get('value') or '').replace('|', r'\|')
            w(f"| `{k}` | {v or '—'} | {c.get('status', 'ABSENT')} |\n")
        w("\n")

        # The ladder the keyword was chosen from, and what was struck off it.
        excluded = [(k, (m.get(k) or {}).get('value', '')) for k in EXCLUDED_SLOTS]
        excluded = [(k, v) for k, v in excluded if v]
        handles = measure(s['text']).get('handles', [])
        people = [h for h in handles
                  if h['kind'] == 'proper noun' and h['state'] != 'DEVELOPED']

        w("<details><summary>the people this stop names, and why each was or was not "
          "chosen</summary>\n\n")
        w("| person named | state | sentences | struck off because |\n|---|---|---|---|\n")
        for h in sorted(people, key=lambda h: -h.get('sentences', 0)):
            hf = h['surface'].lower()
            why = ''
            for k, v in excluded:
                if hf in v.lower() or v.lower() in hf:
                    why = f'already the `{k}` slot'
                    break
            if not why and hf.split() and hf.split()[0] in (
                    'the', 'at', 'in', 'on', 'le', 'la', 'les', 'a', 'an',
                    'au', 'du', 'des', 'un', 'une'):
                why = 'starts with an article/preposition'
            mark = ' **← chosen**' if hf == (value or '').lower() else ''
            w(f"| {h['surface']}{mark} | {h['state']} | {h.get('sentences', 0)} | "
              f"{why or '—'} |\n")
        w("\n</details>\n\n")

        w("**One sentence tying this person to THIS object:**\n\n")
        w("> _(write it here)_\n\n")
        w("---\n\n")

    return out.getvalue()


def main():
    tour = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TOUR
    tour = tour if os.path.isabs(tour) else os.path.join(HERE, tour)
    dest = os.path.splitext(tour)[0] + '_CREDIT_LINES.md'
    open(dest, 'w', encoding='utf-8').write(build(tour))
    print(dest)


if __name__ == '__main__':
    main()
