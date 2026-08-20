#!/usr/bin/env python3
"""run_step2_and_3a.py — step 2 (who needs a story) and step 3a (the matrix).

Michael, 2026-08-20: *"identify which stops require stories, and then produce the
matrix the first query should be based on and stop there, let me analyze."*

STOPS BEFORE ANY QUERY IS ISSUED. Nothing here touches SERP, no story is written,
no money is spent beyond the exhibition-checklist retrieval that step 1 already
does.

**One thing worth saying out loud, because it changes how the list reads.**
Michael's ordering is step 2 then step 3. As BUILT, step 2 consumes the matrix —
`assess_stop_worthiness(matrix)` scores four signals that are all matrix slots.
So the real order is: the checklist gives the facts, 3a assembles them into the
matrix, and step 2 then reads that matrix to decide who is worth mining. Not a
defect; the matrix comes from step 1's checklist, not from any query. But it does
mean 3a is upstream of 2, and a stop with an empty matrix is unworthy BY
CONSTRUCTION rather than by judgement.

This reproduces exactly what production does — same checklist call, same
LOCAL-419 enrichment, same D498 slot vocabulary, same LOCAL-486 scorer — so the
numbers here are the numbers a real run would produce.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')

LOCATION = 'Picasso, Miro, Dali: Unbound exhibition at MFA, Boston, MA'
VENUE = 'Museum of Fine Arts, Boston'
EXHIBITION = 'Picasso, Miro, Dali: Unbound'
STOP_NAMES = [
    'Le Lézard aux plumes d’or (The Lizard with Golden Feathers)',
    'Au Soleil du Plafond',
    'Moses and Monotheism',
]

from venue_resolver import resolve_venue                      # noqa: E402
from exhibition_checklist import find_exhibition_checklist    # noqa: E402
from generate_tour_text import match_work_for_stop            # noqa: E402
from story_pass import MATRIX_KEYS, MATRIX_SLOTS              # noqa: E402
from story_worthiness import assess_stop_worthiness           # noqa: E402


def rule(c='─', n=78):
    print(c * n)


print(f"request : {LOCATION}\n")

entity = resolve_venue(VENUE, 'Boston')
print(f"venue   : {entity.name if entity else '(unresolved)'}")
print(f"site    : {getattr(entity, 'official_url', '') or '(none)'}")
print(f"language: {getattr(entity, 'language', '') or '(none)'}\n")

result = find_exhibition_checklist(
    venue_base_url=getattr(entity, 'official_url', '') or '',
    exhibition_name=EXHIBITION,
    venue_name=VENUE,
    venue_language=getattr(entity, 'language', 'en') or 'en',
)
works = getattr(result, 'works', []) or []
print(f"checklist: path={getattr(result, 'path', '?')} works={len(works)} "
      f"url={getattr(result, 'exhibition_url', '') or getattr(result, 'url', '')}\n")

rows = []
for i, name in enumerate(STOP_NAMES, 1):
    work = match_work_for_stop(name, works) or {}
    # Exactly production's LOCAL-419 enrichment, then D498's slot assembly.
    sources = {
        'canonical_title': name,
        'english_title': work.get('english_title', '') or '',
        'artist': work.get('artist', '') or '',
        'publisher': work.get('publisher', '') or '',
        'printed_by': work.get('printed_by', '') or work.get('printer', '') or '',
        'medium': work.get('medium', '') or '',
        'credit_line': work.get('credit_line', '') or '',
        'venue_name': VENUE,
        'focus_fact': '',   # step 7b sets this only after a failed attempt
    }
    matrix = {k: sources[k] for k in MATRIX_KEYS}
    verdict = assess_stop_worthiness(matrix)
    rows.append((i, name, work, matrix, verdict))

# ─── STEP 2 ──────────────────────────────────────────────────────────────────
print()
rule('═')
print("STEP 2 — WHICH STOPS REQUIRE A STORY   (story_worthiness, LOCAL-486)")
rule('═')
print("Four independent signals. A stop is mined on ANY ONE of them; only a stop")
print("scoring zero is skipped. That asymmetry is deliberate — a wrong 'no' costs")
print("a story, a wrong 'yes' costs a few queries.\n")
print(f"  {'#':<3}{'stop':<46}{'score':<7}{'mine?':<7}signals")
rule()
for i, name, work, matrix, v in rows:
    sig = ', '.join(k for k, on in v['signals'].items() if on) or '(none)'
    print(f"  {i:<3}{name[:44]:<46}{v['score']}/4    "
          f"{'YES' if v['worth_mining'] else 'no ':<7}{sig}")
rule()

# ─── STEP 3a ─────────────────────────────────────────────────────────────────
print()
rule('═')
print("STEP 3a — THE MATRIX THE FIRST QUERY WILL BE BUILT FROM   (D498)")
rule('═')
print("Nine slots. These, and only these, are what the query synthesiser and the")
print("story prompt can see. An empty slot is a question the system cannot ask.\n")
labels = dict(MATRIX_SLOTS)
labels['focus_fact'] = 'Focus fact (7b)'
for i, name, work, matrix, v in rows:
    rule()
    print(f"  STOP {i}: {name}")
    rule()
    for k in MATRIX_KEYS:
        val = matrix[k]
        mark = ' ' if val else '!'
        shown = val if val else '(EMPTY)'
        if len(shown) > 60:
            shown = shown[:57] + '...'
        print(f"   {mark} {labels.get(k, k):<18} {shown}")
    filled = sum(1 for k in MATRIX_KEYS if matrix[k])
    print(f"     -> {filled}/{len(MATRIX_KEYS)} filled; empty: "
          f"{[k for k in MATRIX_KEYS if not matrix[k]] or 'none'}")

print()
rule('═')
print("STOPPING HERE. No query issued, no story written, no ranking performed.")
rule('═')

out = os.path.join(HERE, 'STEP2_3A_MATRIX.json')
with open(out, 'w') as fh:
    json.dump([{'stop': n, 'matrix': m, 'worthiness': v}
               for _, n, _, m, v in rows], fh, indent=2, ensure_ascii=False)
print(f"\nmachine-readable copy -> {os.path.basename(out)}")
