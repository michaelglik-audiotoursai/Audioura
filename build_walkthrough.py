#!/usr/bin/env python3
"""build_walkthrough.py — every routine's output, per stop, for Michael to read.

He asked to see the results of each function so he can answer whether a story about
the CATEGORY is acceptable when it lands on the object. That judgement needs the
evidence, not a summary of it.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from story_opportunity_scan import measure, verdict                # noqa: E402
from story_material_check import assess, load_corpus               # noqa: E402
from validate_story import validate_story                          # noqa: E402
from evaluate_story import evaluate_story                          # noqa: E402

RUNS = [('/tmp/final_mfa.json', 'TOUR_MFA_20260812_2030.txt', 'MFA — Picasso, Miró, Dalí: Unbound'),
        ('/tmp/final_fruit.json', 'fruitlands_museum_tour.txt', 'Fruitlands Museum'),
        ('/tmp/pipe_beacon3.json', 'Beacon_Hill__Boston_walking_tour_20260714_135649.txt',
         'Beacon Hill walking tour')]

SLOTS = ('canonical_title', 'english_title', 'artist', 'publisher',
         'printed_by', 'credit_line', 'medium', 'venue')

out = []
W = out.append

W("# Every routine, every stop — the evidence behind the decision\n")
W("Generated 2026-08-13 for Michael. **The question this is here to answer:** is a story ")
W("about the CATEGORY acceptable when it lands on the object? Four of the six silent stops ")
W("retrieved real material about the right general topic — Thomas Cole, Currier & Ives, ")
W("Charles Bulfinch — that is not attached to the specific thing the listener is looking at. ")
W("Everything below is verbatim output, not summary.\n")
W("Reading order per stop: **the delivered tour text**, then matrix → request → search → ")
W("need → material → writer → validate → evaluate.\n")
W("---\n")

for jf, tourfile, label in RUNS:
    if not os.path.exists(jf):
        continue
    rows = json.load(open(jf))
    full = open(os.path.join(HERE, tourfile), encoding='utf-8').read()
    parts = re.split(r'\n(?=Stop \d+:)', full)
    W(f"\n# {label}\n")
    for r in rows:
        n = r.get('stop')
        sel = [p for p in parts if p.startswith(f'Stop {n}:')]
        stop_text = sel[0] if sel else ''
        title = r.get('title', '?')
        W(f"\n## Stop {n} — {title}\n")
        W(f"**Pipeline verdict: `{r.get('status')}`**"
          + (f" · validate `{r.get('validate')}`" if r.get('validate') else "") + "\n")

        W("\n### 0. The tour as delivered (pre-story content)\n")
        W("```")
        W(re.split(r'\n\s*Directions:', stop_text)[0].strip()[:2200])
        W("```\n")

        W("### 1. `interrogation_matrix.build_matrix`\n")
        W("| slot | value | status | rung |")
        W("|---|---|---|---|")
        m = r.get('matrix', {})
        for s in SLOTS:
            c = m.get(s) or {}
            v = (c.get('value') or '—').replace('|', '\\|')[:70]
            W(f"| `{s}` | {v} | {c.get('status', 'ABSENT')} | {c.get('rung') or ''} |")
        W("")

        W("### 2. `Request_to_AI`\n")
        W(f"> {r.get('request', '—')}\n")
        if r.get('unverified'):
            W(f"**Unverified terms in that question:** {', '.join(r['unverified'])} — "
              "asserted by the delivered text, checked by nothing.\n")

        W("### 3. Search (the question drives retrieval, not recall)\n")
        W(f"- retrieved **{r.get('retrieved', '—')}** → kept **{r.get('kept', '—')}**"
          + ("  · second pass fired (principal dropped)" if r.get('second_pass') else "") + "\n")
        W(f"- surviving domains: `{', '.join(r.get('domains', []) or ['—'])}`\n")
        cp = os.path.join(HERE, 'story_lab_state',
                          'pipe_' + re.sub(r'[^a-z0-9]+', '_', title.lower())[:40] + '.txt')
        corpus = ''
        if os.path.exists(cp):
            corpus = load_corpus([cp], {})
            W("**The corpus, verbatim — this is everything the writer is allowed to use:**\n")
            W("```")
            W(open(cp, encoding='utf-8').read().strip()[:2000] or '(EMPTY — search returned nothing)')
            W("```\n")
        else:
            W("**Corpus: none written (search returned nothing).**\n")

        body = re.sub(r'^\s*(?:Stop \d+|Address|Coordinates)\s*:.*$', '',
                      re.split(r'\n\s*Directions:', stop_text)[0], flags=re.M)
        meas = measure(body)
        need = verdict(meas)
        W("### 4. `story_opportunity_scan` — does this stop need a story?\n")
        W(f"**{'YES' if need['needs_additional_story'] else 'NO'}** — {need['why']}\n")
        W("| handle | sentences | agency | stakes | state |")
        W("|---|---|---|---|---|")
        for h in sorted(meas['handles'], key=lambda x: (-x['sentences'], x['surface']))[:10]:
            W(f"| {h['surface'][:38]} | {h['sentences']} | {h['agency']} | {h['stakes']} | {h['state']} |")
        W("")

        W("### 5. `story_material_check` — can the corpus source one?\n")
        if corpus:
            _rank = {'FLAT': 0, 'MENTIONED': 1, 'DANGLING': 2}
            targets = [h['surface'] for h in sorted(
                (h for h in meas['handles'] if h['state'] != 'DEVELOPED'),
                key=lambda h: (_rank.get(h['state'], 3), -h['sentences']))][:8]
            W("| handle | state | passages | missing |")
            W("|---|---|---|---|")
            for t in targets:
                a = assess(t, corpus)
                W(f"| {t[:34]} | **{a['state']}** | {a['passages']} | "
                  f"{', '.join(a['missing']) or '—'} |")
            W("")
            W("*A handle needs all three — a named person, an action, a consequence. "
              "`consequence` is what is missing almost everywhere.*\n")
        else:
            W("No corpus, so nothing to assess.\n")

        W("### 6. `story_writer`\n")
        if r.get('story'):
            W(f"**subject chosen:** {r.get('subject', '—')}\n")
            W(f"> {r['story']}\n")
        else:
            W(f"*No story written — pipeline stopped at `{r.get('status')}`.*\n")

        W("### 7. `Validate_Story`\n")
        if r.get('story') and corpus:
            v = validate_story(r['story'], corpus)
            W(f"**{v['verdict']}**\n")
            W("| sentence | status |")
            W("|---|---|")
            for s in v['sentences']:
                _t = s['text'][:88].replace('|', '/')
                W(f"| {_t} | `{s['status']}` |")
            W("")
        else:
            W("*Not reached.*\n")

        W("### 8. `Evaluate_Story`\n")
        if r.get('scores'):
            s = r['scores']
            W(f"| Historic | Detail | Social | valuation index |")
            W(f"|---|---|---|---|")
            W(f"| {s['historic']} | {s['detail']} | {s['social']} | {s['valuation_index']} |")
            W(f"\n*Sum = {s['historic'] + s['detail'] + s['social']}. They are independent by "
              "design and do not total 100.*\n")
        else:
            W("*Not reached.*\n")
        W("\n---\n")

W("\n# The decision this document is for\n")
W("Four stops — **Hudson River from Fort Putnam, The Print Room, Massachusetts State House, "
  "Cheers Beacon Hill** — retrieved real, usable material about the right general subject and "
  "were silenced because that material is not attached to the specific object or place.\n")
W("Your own review pushed toward strictness: you said Broder arrived as a biography rather "
  "than as *the maker of the object in the case*. Applied strictly, those four stay silent "
  "forever. Loosened to allow category-level material that LANDS on the object, all four "
  "would probably produce stories, and some would be good.\n")
W("**Two separate failures are NOT part of that decision** and are mine to fix regardless:\n")
W("- *The Brothers by John Appleton Brown, 1883* retrieved **0 characters**. Total search "
  "failure, not a story-quality question.\n")
W("- *Le Lézard aux plumes d'or* retrieved pure catalogue — accession numbers and materials. "
  "The fix is fetching the article behind the search teaser (R5), not loosening the rule.\n")

path = os.path.join(HERE, 'STORY_ROUTINES_WALKTHROUGH.md')
open(path, 'w', encoding='utf-8').write('\n'.join(out))
print(path)
