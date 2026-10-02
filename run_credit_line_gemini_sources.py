#!/usr/bin/env python3
"""run_credit_line_gemini_sources.py — D508: re-ask the 37, keep the sources.

Michael: *"could you add another column to your matrix: sources, so I can ask
Gemini for verification?"*

Only the Gemini half is re-run — the Serper results already carry their URLs and
are unchanged. Each answer now stores the pages Gemini actually read, per
sentence, with the redirect URLs resolved so they can be opened.

The Christie's Lot Essay is why this matters: that page confirmed the 1967
abandonment, our SERP snippet stopped 200 characters short of it, and D366
recorded the story as refuted on the strength of the truncated half. A source
column is what makes that checkable by hand instead of by argument.
"""
import json, os, re, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from story_leads import gemini_with_sources                            # noqa: E402
from material_kind import classify_material                            # noqa: E402
from story_relevance import relevance_of, RELEVANT, WEAK, IRRELEVANT   # noqa: E402
from run_credit_line_queries import (MATRICES, EXHIBITION, GEMINI_PROMPT,
                                     matrix_for, sentences_of)         # noqa: E402

d = json.load(open(os.path.join(HERE, 'CREDIT_LINE_RESULTS.json')))
t0, n = time.time(), 0
for row in d['rows']:
    matrix, extra = matrix_for(row['stop'])
    mat = '\n'.join(f'  {k}: {v}' for k, v in matrix.items() if v)
    res = gemini_with_sources(GEMINI_PROMPT.format(
        question=row['gemini']['question'], matrix=mat))
    n += 1
    judged = []
    for s in sentences_of(res['text']):
        r = relevance_of(s, matrix, res['text'], extra); r['sentence'] = s
        # attach the sources Gemini cited for the segment containing it
        srcs = []
        for sup in res['supports']:
            if s[:40] and s[:40] in sup['text']:
                srcs = sup['sources']; break
        r['sources'] = srcs
        judged.append(r)
    kept = [j['sentence'] for j in judged if j['verdict'] in (RELEVANT, WEAK)]
    before = classify_material([j['sentence'] for j in judged]) if judged else {}
    after = classify_material(kept) if kept else {}
    row['gemini'].update(
        text=res['text'], error=res['error'], sentences=judged,
        sources=res['sources'], supports=res['supports'],
        search_queries=res['queries'],
        kind_before_gate=before.get('kind', 'none'),
        kind_after_gate=after.get('kind', 'none'),
        best_after=after.get('best_sentence', ''),
        n_relevant=sum(1 for j in judged if j['verdict'] == RELEVANT),
        n_weak=sum(1 for j in judged if j['verdict'] == WEAK),
        n_irrelevant=sum(1 for j in judged if j['verdict'] == IRRELEVANT),
        no_info='NO RELIABLE INFORMATION' in res['text'].upper())
    print(f"  {row['stop'][:14]:<14} {row['id']:<5} {len(res['sources'])} sources  "
          f"{before.get('kind','-')}->{after.get('kind','-')}", file=sys.stderr)

d['gemini_calls_with_sources'] = n
d['cost_usd'] = round(d.get('cost_usd', 0) + n * 0.006, 4)
json.dump(d, open(os.path.join(HERE, 'CREDIT_LINE_RESULTS.json'), 'w'),
          indent=2, ensure_ascii=False)
print(f"\n{n} gemini calls with sources, {time.time()-t0:.0f}s", file=sys.stderr)
