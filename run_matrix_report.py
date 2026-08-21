#!/usr/bin/env python3
"""run_matrix_report.py — one matrix per stop, with its rotation list.

Michael, 2026-08-21: *"show me one matrix per stop with a list of credit_line
sets for discussion."*

NOTE ON THE NAME. He calls it the "credit_line list"; it lives in `focus_fact`.
`credit_line` cannot carry a rotating fact because LOCAL-406 regex-parses donor
and printer out of that field, so a fact written there is read as a person's
name — LOCAL-491 gave the rotating fact its own slot for exactly this reason.

Three sources feed each matrix, in descending order of authority:

  1. the exhibition checklist   what the SHOW says is on display
  2. the object record  [D501]  what the MUSEUM says about the object
  3. the stop's own text [D502] what WE said and did not substantiate

(3) never becomes a fact. It becomes a QUESTION to research — the door the text
opened and did not walk through. The answer still comes from retrieval and still
faces every gate.

Reads the delivered tour text from a STEP0/TOUR file so the hooks are mined from
POST-GATE prose (the sentence gates run at PHASE 5.156-5.159, after the matrix is
built — mining pre-gate text would hook a sentence about to be deleted).
"""
import json
import os
import re
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

VENUE = 'Museum of Fine Arts, Boston'
EXHIBITION = 'Picasso, Miro, Dali: Unbound'
TOUR_FILE = sys.argv[1] if len(sys.argv) > 1 else 'STEP0_BASELINE_20260820_1459.txt'

from venue_resolver import resolve_venue                       # noqa: E402
from exhibition_checklist import find_exhibition_checklist     # noqa: E402
from generate_tour_text import match_work_for_stop             # noqa: E402
from story_pass import MATRIX_KEYS, MATRIX_SLOTS               # noqa: E402
from story_worthiness import assess_stop_worthiness            # noqa: E402
from story_roles import roles_in, ROLES                        # noqa: E402
from story_focus_fact import candidate_facts_with_hooks        # noqa: E402
from object_record import enrich_matrix                        # noqa: E402
from text_fold import is_placeholder                           # noqa: E402


def rule(c='─', n=80):
    print(c * n)


def stops_from_tour(path):
    """(title, body) per stop, from the delivered tour."""
    text = open(os.path.join(HERE, path)).read()
    parts = re.split(r'^Stop \d+:\s*(.+)$', text, flags=re.M)
    out = []
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1]
        body = re.sub(r'^\s*(Address|Coordinates|Directions):.*$', '', body,
                      flags=re.M)
        out.append((parts[i].strip(), body.strip()))
    return out


print(f"tour file : {TOUR_FILE}")
entity = resolve_venue(VENUE, 'Boston')
venue_url = getattr(entity, 'official_url', '') or ''
print(f"venue     : {getattr(entity, 'name', '?')}   {venue_url}\n")

result = find_exhibition_checklist(
    venue_base_url=venue_url, exhibition_name=EXHIBITION, venue_name=VENUE,
    venue_language=getattr(entity, 'language', 'en') or 'en')
works = getattr(result, 'works', []) or []

rows = []
for idx, (title, body) in enumerate(stops_from_tour(TOUR_FILE), 1):
    work = match_work_for_stop(title, works) or {}
    base = {
        'canonical_title': title,
        'english_title': work.get('english_title', '') or title,
        'artist': work.get('artist', '') or '',
        'publisher': work.get('publisher', '') or '',
        'printed_by': work.get('printed_by', '') or work.get('printer', '') or '',
        'medium': work.get('medium', '') or '',
        'credit_line': work.get('credit_line', '') or '',
        'venue_name': VENUE,
        'focus_fact': '',
    }
    # [D500] a placeholder is an absence
    for k, v in list(base.items()):
        if v and is_placeholder(v):
            base[k] = ''
    checklist_filled = {k for k, v in base.items() if v}
    enriched, rep = enrich_matrix(base, venue_url, verbose=False)
    rows.append((idx, title, body, base, enriched, rep, checklist_filled))

for idx, title, body, base, m, rep, checklist_filled in rows:
    print()
    rule('═')
    print(f"  STOP {idx}: {title}")
    rule('═')

    print("\n  MATRIX")
    labels = dict(MATRIX_SLOTS)
    labels['focus_fact'] = 'Focus fact (7b)'
    extra = [k for k in ('provenance', 'publication_year', 'catalogue_raisonne',
                         'accession_number') if m.get(k)]
    for k in list(MATRIX_KEYS) + extra:
        val = (m.get(k) or '').strip()
        if k in checklist_filled:
            src = 'checklist'
        elif val and k in rep.get('filled', []):
            src = 'OBJECT RECORD'
        elif val:
            src = 'derived'
        else:
            src = '—'
        shown = val if val else '(empty)'
        if len(shown) > 62:
            shown = shown[:59] + '...'
        print(f"    {labels.get(k, k):<19} {shown:<64} {src}")

    agents = roles_in(m, 'museum')
    n_ag = sum(1 for r in ROLES if agents[r])
    print(f"\n  AGENTS {n_ag}/3   " + ',  '.join(
        f"{r}={agents[r]['value']}" if agents[r] else f"{r}=—" for r in ROLES))
    v = assess_stop_worthiness(m)
    print(f"  WORTHINESS {v['score']}/4  mine={v['worth_mining']}  ({v['why']})")

    cands = candidate_facts_with_hooks(m, body, VENUE)
    print(f"\n  FOCUS-FACT LIST — {len(cands)} candidate(s), tried in this order")
    print("  (step 7b takes the next one whenever a story fails validation or "
          "scores low)")
    rule()
    for n, c in enumerate(cands, 1):
        kind = 'HOOK ' if c['key'].startswith('hook:') else 'FACT '
        print(f"   {n}. [{kind}] {c['fact']}")
        print(f"           why: {c['why']}")
        if c.get('source_sentence'):
            s = c['source_sentence']
            print(f"           from: \"{s[:88]}{'...' if len(s) > 88 else ''}\"")
    if not cands:
        print("   (none — nothing to rotate to)")

print()
rule('═')
print("  No query issued. No story written. Nothing spent beyond the checklist")
print("  and one object-record lookup per stop.")
rule('═')

out = os.path.join(HERE, 'MATRIX_REPORT.json')
with open(out, 'w') as fh:
    json.dump([{'stop': t, 'matrix': m, 'object_record': rep,
                'agents': {r: (roles_in(m, 'museum')[r] or {}) for r in ROLES},
                'focus_facts': candidate_facts_with_hooks(m, b, VENUE)}
               for _, t, b, _, m, rep, _ in rows], fh, indent=2, ensure_ascii=False)
print(f"\nmachine-readable -> {os.path.basename(out)}")
