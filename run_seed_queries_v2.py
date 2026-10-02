#!/usr/bin/env python3
"""run_seed_queries_v2.py — D505: both engines, every result kept, relevance gated.

Michael, 2026-08-22: *"conduct the relevance gating ... show me the results not
just evaluation ... I want to see all 37 as they are reported from AI ... please
include in addition to SERP also Gemini ... I expect to see all 74."*

Three changes from D504:

1. **Two engines.** Serper (the production path) and Gemini with Grounding —
   which searches and cites INSIDE the call rather than reciting, so it is a
   genuine second retrieval, not a second opinion about the same snippets.
   `story_leads._gemini` already implements it and had no caller on this path.

2. **Every result is kept verbatim.** D504 stored the top 3 ranked snippets; this
   stores everything both engines returned, so the raw document is the evidence
   and not a summary of it.

3. **Relevance gating (D505).** Each candidate sentence is judged against the
   stop's own entities before its `material_kind` verdict counts. The Szampanier
   case — an etching of a destroyed synagogue in Ukraine, scored `eventful` for
   the query `Juan Gris "Au Soleil du Plafond" destroyed` — is what this is for.

**Cost.** Serper $0.001/query. Gemini flash with grounding is a few tenths of a
cent per call. 37 + 37 lands near $0.30 against a $13 budget; the ceiling below
is a guard against a loop bug, not a budget.
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
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')

HARD_CEILING_USD = float(os.environ.get('SEED_QUERY_CEILING', '3.00'))

from story_seeds import seeds_for_stop, ANCHORED                  # noqa: E402
from work_story_searcher import (_serp_search, normalize_domain,
                                 _classify_domain_quick, set_venue_domain)  # noqa: E402
from material_kind import classify_material                       # noqa: E402
from story_relevance import (relevance_of, RELEVANT, WEAK,
                             IRRELEVANT)                          # noqa: E402
from cost_rates import search_cost                                # noqa: E402
from story_leads import _gemini                                   # noqa: E402
from run_seed_queries import build_query, load_stops, artist_for, KNOWN  # noqa: E402

VENUE = 'Museum of Fine Arts, Boston'
GEMINI_COST_PER_CALL = 0.004   # flash + grounding, conservative

MATRICES = {
    'Le Lézard': {'canonical_title': "Le Lézard aux plumes d’or",
                  'artist': 'Joan Miró', 'publisher': 'Louis Broder',
                  'printed_by': 'Mourlot',
                  'credit_line': 'Gift of Boris Fridman'},
    'Au Soleil': {'canonical_title': 'Au Soleil du Plafond',
                  'artist': 'Juan Gris', 'publisher': '', 'printed_by': '',
                  'credit_line': ''},
    'Moses': {'canonical_title': 'Moses and Monotheism',
              'artist': 'Salvador Dalí', 'publisher': '', 'printed_by': '',
              'credit_line': ''},
}
EXTRA = {'Le Lézard': ['Miró', 'Broder', 'Mourlot', 'Fridman'],
         'Au Soleil': ['Gris', 'Reverdy', 'Pierre Reverdy', 'Tériade', 'Verve'],
         'Moses': ['Dalí', 'Freud', 'Sigmund Freud', 'Hogarth']}


def matrix_for(title):
    for k, v in MATRICES.items():
        if k.lower() in title.lower():
            return v, EXTRA[k]
    return {}, []


def sentences_of(text):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text or '')
            if len(s.strip()) > 20]


GEMINI_PROMPT = """You are helping research one object in a museum exhibition.

Object : {work}
Artist : {artist}
Venue  : {venue}

Question: {ask}

Answer ONLY with facts you can attribute to a real source. For each fact give one
sentence and the source in brackets. If you do not know, say exactly
"NO RELIABLE INFORMATION". Do not speculate, do not praise the work, do not
describe how it looks. Maximum 5 sentences."""


def judge(sentences, matrix, extra, context=''):
    """Relevance first, then material kind on what survives."""
    judged = []
    for s in sentences:
        r = relevance_of(s, matrix, context, extra)
        r['sentence'] = s
        judged.append(r)
    kept = [j['sentence'] for j in judged if j['verdict'] in (RELEVANT, WEAK)]
    return judged, (classify_material(kept) if kept else {}), \
        (classify_material([j['sentence'] for j in judged]) if judged else {})


set_venue_domain('http://www.mfa.org/')
rows, n_serp, n_gem = [], 0, 0
t0 = time.time()

for stop_title, body in load_stops():
    artist = artist_for(stop_title)
    matrix, extra = matrix_for(stop_title)
    seeds = seeds_for_stop(body, KNOWN)
    print(f"\n=== {stop_title[:56]} — {len(seeds)} seeds", file=sys.stderr)

    for seed in seeds:
        if search_cost(n_serp) + n_gem * GEMINI_COST_PER_CALL > HARD_CEILING_USD:
            print("  CEILING REACHED", file=sys.stderr)
            break
        query, why = build_query(seed, stop_title, artist)

        # ---- engine 1: Serper -------------------------------------------
        serp_raw, _ = _serp_search(query)
        n_serp += 1
        serp_results = []
        for r in serp_raw:
            dom = normalize_domain(r.get('url', ''))
            snip = r.get('snippet', '') or ''
            sj, k_after, k_before = judge(sentences_of(snip), matrix, extra, snip)
            serp_results.append({
                'title': r.get('title', ''), 'url': r.get('url', ''),
                'domain': dom, 'tier': _classify_domain_quick(dom) or 'unverified',
                'snippet': snip, 'sentences': sj,
            })
        # [D505] AGGREGATE FROM THE PER-RESULT JUDGEMENTS. The first version
        # judged every sentence against ALL EIGHT snippets concatenated, so the
        # anaphora rescue — "a sentence with no entity of its own inherits WEAK
        # relevance if its snippet establishes one" — fired on every sentence in
        # the batch. The Szampanier synagogue line inherited "Juan Gris" from a
        # DIFFERENT result and was kept, which is precisely the case this gate
        # exists to reject. A sentence's context is ITS OWN snippet, never the
        # neighbours'.
        s_judged = [j for r in serp_results for j in r['sentences']]
        s_kept = [j['sentence'] for j in s_judged
                  if j['verdict'] in (RELEVANT, WEAK)]
        s_before = classify_material([j['sentence'] for j in s_judged]) if s_judged else {}
        s_after = classify_material(s_kept) if s_kept else {}

        # ---- engine 2: Gemini, grounded ---------------------------------
        gem_text, gem_err = '', ''
        try:
            gem_text = _gemini(GEMINI_PROMPT.format(
                work=stop_title, artist=artist, venue=VENUE, ask=seed['ask']),
                grounded=True) or ''
        except Exception as e:
            gem_err = f'{type(e).__name__}: {e}'
        n_gem += 1
        g_judged, g_after, g_before = judge(sentences_of(gem_text), matrix,
                                            extra, gem_text)

        rows.append({
            'stop': stop_title, 'id': seed['id'], 'class': seed['class'],
            'seed': seed['seed'], 'ask': seed['ask'],
            'query': query, 'why': why,
            'serp': {
                'n_results': len(serp_results), 'results': serp_results,
                'sentences': s_judged,
                'kind_before_gate': s_before.get('kind', 'none'),
                'kind_after_gate': s_after.get('kind', 'none'),
                'best_before': s_before.get('best_sentence', ''),
                'best_after': s_after.get('best_sentence', ''),
                'n_relevant': sum(1 for j in s_judged if j['verdict'] == RELEVANT),
                'n_weak': sum(1 for j in s_judged if j['verdict'] == WEAK),
                'n_irrelevant': sum(1 for j in s_judged if j['verdict'] == IRRELEVANT),
            },
            'gemini': {
                'text': gem_text, 'error': gem_err, 'sentences': g_judged,
                'kind_before_gate': g_before.get('kind', 'none'),
                'kind_after_gate': g_after.get('kind', 'none'),
                'best_before': g_before.get('best_sentence', ''),
                'best_after': g_after.get('best_sentence', ''),
                'n_relevant': sum(1 for j in g_judged if j['verdict'] == RELEVANT),
                'n_weak': sum(1 for j in g_judged if j['verdict'] == WEAK),
                'n_irrelevant': sum(1 for j in g_judged if j['verdict'] == IRRELEVANT),
                'no_info': 'NO RELIABLE INFORMATION' in gem_text.upper(),
            },
        })
        print(f"  {seed['id']:<5} serp={s_before.get('kind','-'):<8}->"
              f"{s_after.get('kind','-'):<8} gem={g_before.get('kind','-'):<8}->"
              f"{g_after.get('kind','-'):<8} {query[:44]}", file=sys.stderr)

cost = search_cost(n_serp) + n_gem * GEMINI_COST_PER_CALL
out = {'serp_queries': n_serp, 'gemini_calls': n_gem,
       'cost_usd': round(cost, 4), 'elapsed_s': round(time.time() - t0, 1),
       'rows': rows}
with open(os.path.join(HERE, 'SEED_QUERY_RESULTS_V2.json'), 'w') as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
print(f"\n{n_serp} serp + {n_gem} gemini = {n_serp + n_gem} calls, "
      f"~${cost:.3f}, {out['elapsed_s']:.0f}s", file=sys.stderr)
