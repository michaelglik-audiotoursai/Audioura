#!/usr/bin/env python3
"""run_adjudicated_stories.py — D509: 37 challenged, adjudicated stories.

For each of the 37 credit_lines:

  1. take the round-1 Gemini answer and its sources (already held, D508)
  2. extract its checkable claims
  3. CHALLENGE each with Serper queries built from the claim's own terms
  4. hand the round-1 answer plus the retrieved evidence back to Gemini and make
     it adjudicate claim by claim, then write the story
  5. keep the adjudication table alongside the story so every sentence is
     traceable

Serper is used, and used differently from D507: not to answer the question but
to supply the evidence the claims are judged against. That is the division of
labour the last two days established — Gemini narrates, retrieval adjudicates.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

CEILING_USD = float(os.environ.get('ADJUDICATE_CEILING', '8.00'))
CHALLENGES_PER_CLAIM = int(os.environ.get('CHALLENGE_QUERIES', '1'))
CLAIMS_PER_ANSWER = int(os.environ.get('CLAIMS_PER_ANSWER', '4'))

from story_adjudicate import (claims_of, challenge_queries_for,
                              ADJUDICATION_PROMPT, count_statuses)    # noqa: E402
from story_leads import gemini_with_sources                           # noqa: E402
from work_story_searcher import (_serp_search, normalize_domain,
                                 _classify_domain_quick, set_venue_domain)  # noqa: E402
from story_relevance import relevance_of, RELEVANT, WEAK              # noqa: E402
from material_kind import classify_material                           # noqa: E402
from cost_rates import search_cost                                    # noqa: E402
from run_credit_line_queries import matrix_for, sentences_of, EXHIBITION  # noqa: E402

GEMINI_COST = 0.006
AGENTS = {'Le Lézard': ['Broder', 'Mourlot'], 'Au Soleil': ['Reverdy', 'Tériade'],
          'Moses': ['Freud']}


def agents_for(title):
    for k, v in AGENTS.items():
        if k.lower() in title.lower():
            return v
    return []


set_venue_domain('http://www.mfa.org/')
d = json.load(open(os.path.join(HERE, 'CREDIT_LINE_RESULTS.json')))
out_rows, n_serp, n_gem = [], 0, 0
t0 = time.time()

for row in d['rows']:
    matrix, extra = matrix_for(row['stop'])
    work = matrix.get('canonical_title', row['stop'])
    r1 = row['gemini']
    claims = claims_of(r1.get('sentences', []), limit=CLAIMS_PER_ANSWER)

    if search_cost(n_serp) + n_gem * GEMINI_COST > CEILING_USD:
        print('  CEILING', file=sys.stderr)
        break

    # ---- 3. challenge ---------------------------------------------------
    evidence, challenges = [], []
    for c in claims:
        for q in challenge_queries_for(c['claim'], work, agents_for(row['stop']),
                                       limit=CHALLENGES_PER_CLAIM):
            raw, _ = _serp_search(q)
            n_serp += 1
            found = []
            for res in raw:
                dom = normalize_domain(res.get('url', ''))
                snip = res.get('snippet', '') or ''
                for s in sentences_of(snip):
                    v = relevance_of(s, matrix, snip, extra)
                    if v['verdict'] in (RELEVANT, WEAK):
                        found.append({'sentence': s, 'domain': dom,
                                      'url': res.get('url', ''),
                                      'tier': _classify_domain_quick(dom) or 'unverified'})
            challenges.append({'claim': c['claim'], 'query': q,
                               'n_relevant': len(found), 'evidence': found[:6]})
            evidence.extend(found[:6])

    # De-duplicate evidence, keep provenance for the prompt.
    seen, ev_lines = set(), []
    for e in evidence:
        key = e['sentence'][:70]
        if key in seen:
            continue
        seen.add(key)
        ev_lines.append(f"[{e['domain']}] {e['sentence']}")
    ev_block = '\n'.join(ev_lines[:40]) or '(no independent evidence retrieved)'

    # ---- 4. adjudicate + write ------------------------------------------
    res2 = gemini_with_sources(ADJUDICATION_PROMPT.format(
        work=work, exhibition=EXHIBITION,
        answer=r1.get('text', '') or '(no earlier answer)',
        evidence=ev_block))
    n_gem += 1
    text2 = res2['text'] or ''
    m = re.search(r'PART\s*2.*?$', text2, re.S | re.I)
    story = re.sub(r'^PART\s*2[^\n]*\n', '', m.group(0)).strip() if m else ''
    part1 = text2[:m.start()] if m else text2
    counts = count_statuses(part1)

    judged = []
    for s in sentences_of(story):
        v = relevance_of(s, matrix, story, extra)
        v['sentence'] = s
        judged.append(v)
    kept = [j['sentence'] for j in judged if j['verdict'] in (RELEVANT, WEAK)]
    kind = classify_material(kept) if kept else {}

    out_rows.append({
        'stop': row['stop'], 'id': row['id'], 'class': row['class'],
        'credit_line': row['credit_line'],
        'round1_text': r1.get('text', ''), 'round1_sources': r1.get('sources', []),
        'claims': claims, 'challenges': challenges,
        'adjudication': part1.strip(), 'counts': counts,
        'story': story, 'story_sources': res2['sources'],
        'story_kind': kind.get('kind', 'none'),
        'story_best': kind.get('best_sentence', ''),
        'tells_disagreement': bool(re.search(
            r'some sources|others say|disagree|dispute|while other', story, re.I)),
        'error': res2['error'],
    })
    print(f"  {row['stop'][:14]:<14} {row['id']:<5} claims={len(claims)} "
          f"ev={len(ev_lines):<3} {counts} kind={kind.get('kind','-')}",
          file=sys.stderr)

cost = search_cost(n_serp) + n_gem * GEMINI_COST
json.dump({'serp_queries': n_serp, 'gemini_calls': n_gem,
           'cost_usd': round(cost, 4), 'elapsed_s': round(time.time() - t0, 1),
           'rows': out_rows},
          open(os.path.join(HERE, 'ADJUDICATED_STORIES.json'), 'w'),
          indent=2, ensure_ascii=False)
print(f"\n{n_serp} serper + {n_gem} gemini, ~${cost:.3f}", file=sys.stderr)
