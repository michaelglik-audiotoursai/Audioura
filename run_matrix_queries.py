#!/usr/bin/env python3
"""run_matrix_queries.py — D506: the REAL query mechanism, both engines.

Michael, 2026-08-22: *"how did you come up with such queries based on the matrix?
The queries I see are senseless: they are not built upon matrix where all or
almost all fields are used."*

**He is right, and the error was mine.** D504/D505 called a `build_query()` I
wrote in an afternoon — `<artist> "<title>" <event-term>` — while the actual
mechanism has existed since LOCAL-406 and was extended by LOCAL-423 to carry
Michael's own framing. I bypassed it without noticing it was there.

**The mechanism is `work_story_searcher.synthesize_queries`**, and its shape is
D366 (2026-08-11):

    "The query is framed for a standing visitor, not for a catalogue:
     'What story can be told to visitors of {exhibition} about {work},
     {credit_line}?' Ours ask '"Le Lézard aux plumes d'or" Joan Miró'.
     That difference is the whole reason our queries return auction listings."

It builds from ELEVEN matrix fields — title, local title, artist, publisher,
printer, collaborator, donor, credit line, medium, exhibition, venue — and asks
WHY things happened, not just what they are.

**And it has been running on three of them.** D426 found on 2026-08-13 that
`exhibition_name` never reaches the stop record, so LOCAL-423's two
visitor-framed queries have never executed in production. Nine days later that
was still true; `printer` and `collaborator` were missing too. Fixed in D506.

Measured on Au Soleil du Plafond:

    production stop record ->  4 queries, none naming a person but the artist
    full matrix            -> 15 queries, incl. the donor's motive, the
                              collaboration's reason, and the printer's workshop

This script runs the full-matrix queries through both engines.
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

CEILING_USD = float(os.environ.get('MATRIX_QUERY_CEILING', '5.00'))

from work_story_searcher import (synthesize_queries, _serp_search,
                                 normalize_domain, _classify_domain_quick,
                                 set_venue_domain)                    # noqa: E402
from material_kind import classify_material                           # noqa: E402
from story_relevance import relevance_of, RELEVANT, WEAK, IRRELEVANT  # noqa: E402
from cost_rates import search_cost                                    # noqa: E402
from story_leads import _gemini                                       # noqa: E402

VENUE = 'Museum of Fine Arts, Boston'
EXHIBITION = 'Picasso, Miró, Dalí: Unbound'
GEMINI_COST_PER_CALL = 0.004

# The matrices as they stand AFTER D501's object-record enrichment. Stop 1 is
# the only one with a record; 2 and 3 are what the checklist alone provides,
# which is the honest production state for them.
STOPS = [
    {'canonical_title': "Le Lézard aux plumes d’or (The Lizard with Golden Feathers)",
     'english_title': "Le Lézard aux plumes d’or", 'artist': 'Joan Miró',
     'publisher': 'Louis Broder', 'printer': 'Mourlot', 'printed_by': 'Mourlot',
     'credit_line': 'Gift of Boris Fridman', 'collaborator': '',
     'medium': "Illustrated book with forty color lithographs; publisher's vellum",
     'extra': ['Miró', 'Broder', 'Mourlot', 'Fridman']},
    {'canonical_title': 'Au Soleil du Plafond', 'english_title': 'Au Soleil du Plafond',
     'artist': 'Juan Gris', 'publisher': '', 'printer': '', 'printed_by': '',
     'credit_line': '', 'collaborator': 'Pierre Reverdy', 'medium': '',
     'extra': ['Gris', 'Reverdy', 'Pierre Reverdy', 'Tériade', 'Verve']},
    {'canonical_title': 'Moses and Monotheism', 'english_title': 'Moses and Monotheism',
     'artist': 'Salvador Dalí', 'publisher': '', 'printer': '', 'printed_by': '',
     'credit_line': '', 'collaborator': 'Sigmund Freud', 'medium': 'Illustrations',
     'extra': ['Dalí', 'Freud', 'Sigmund Freud', 'Hogarth']},
]

# D366's framing, given to the answering engine as the question itself rather
# than as a search string. Serper gets the query; Gemini gets the question.
GEMINI_PROMPT = """What story can be told to visitors of the exhibition
"{exhibition}" about {work}?

What is known about it:
{matrix}

Search for it, then answer with FACTS ONLY, each in one sentence with its source
in brackets. Prefer things a visitor standing in front of it cannot see for
themselves: why it was made, who decided, what went wrong, what it cost someone.
If you find nothing reliable, say exactly "NO RELIABLE INFORMATION".
Do not praise the work. Do not describe how it looks. Maximum 6 sentences."""


def sentences_of(t):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', t or '')
            if len(s.strip()) > 20]


def judge_block(sentences, matrix, extra, context):
    judged = []
    for s in sentences:
        r = relevance_of(s, matrix, context, extra)
        r['sentence'] = s
        judged.append(r)
    kept = [j['sentence'] for j in judged if j['verdict'] in (RELEVANT, WEAK)]
    return (judged,
            classify_material([j['sentence'] for j in judged]) if judged else {},
            classify_material(kept) if kept else {})


set_venue_domain('http://www.mfa.org/')
rows, n_serp, n_gem = [], 0, 0
t0 = time.time()

for stop in STOPS:
    extra = stop.pop('extra')
    matrix = dict(stop)
    record = dict(stop, venue_city='Boston, MA', venue_lang='en',
                  venue_name=VENUE, exhibition_name=EXHIBITION)
    queries = synthesize_queries(record)
    print(f"\n=== {stop['canonical_title'][:52]} — {len(queries)} matrix queries",
          file=sys.stderr)

    for qi, query in enumerate(queries, 1):
        if search_cost(n_serp) + n_gem * GEMINI_COST_PER_CALL > CEILING_USD:
            print("  CEILING", file=sys.stderr)
            break
        raw, _ = _serp_search(query)
        n_serp += 1
        results = []
        for r in raw:
            dom = normalize_domain(r.get('url', ''))
            snip = r.get('snippet', '') or ''
            sj, _b, _a = judge_block(sentences_of(snip), matrix, extra, snip)
            results.append({'title': r.get('title', ''), 'url': r.get('url', ''),
                            'domain': dom,
                            'tier': _classify_domain_quick(dom) or 'unverified',
                            'snippet': snip, 'sentences': sj})
        sj = [j for r in results for j in r['sentences']]
        kept = [j['sentence'] for j in sj if j['verdict'] in (RELEVANT, WEAK)]
        s_before = classify_material([j['sentence'] for j in sj]) if sj else {}
        s_after = classify_material(kept) if kept else {}
        rows.append({'stop': stop['canonical_title'], 'q': qi, 'query': query,
                     'engine': 'serper', 'n_results': len(results),
                     'results': results, 'sentences': sj,
                     'kind_before_gate': s_before.get('kind', 'none'),
                     'kind_after_gate': s_after.get('kind', 'none'),
                     'best_after': s_after.get('best_sentence', ''),
                     'n_relevant': sum(1 for j in sj if j['verdict'] == RELEVANT),
                     'n_weak': sum(1 for j in sj if j['verdict'] == WEAK),
                     'n_irrelevant': sum(1 for j in sj if j['verdict'] == IRRELEVANT)})
        print(f"  q{qi:<2} serp {s_before.get('kind','-'):<8}->"
              f"{s_after.get('kind','-'):<8} {query[:56]}", file=sys.stderr)

    # Gemini gets ONE call per stop with the whole matrix — the D366 framing is
    # a question about the work, not a search string, so splitting it into 15
    # would ask the same question fifteen times.
    mat = '\n'.join(f'  {k}: {v}' for k, v in matrix.items() if v)
    text, err = '', ''
    try:
        text = _gemini(GEMINI_PROMPT.format(exhibition=EXHIBITION,
                                            work=stop['canonical_title'],
                                            matrix=mat), grounded=True) or ''
    except Exception as e:
        err = f'{type(e).__name__}: {e}'
    n_gem += 1
    gj, g_before, g_after = judge_block(sentences_of(text), matrix, extra, text)
    rows.append({'stop': stop['canonical_title'], 'q': 0,
                 'query': 'D366 framing, full matrix', 'engine': 'gemini',
                 'text': text, 'error': err, 'sentences': gj, 'results': [],
                 'kind_before_gate': g_before.get('kind', 'none'),
                 'kind_after_gate': g_after.get('kind', 'none'),
                 'best_after': g_after.get('best_sentence', ''),
                 'n_relevant': sum(1 for j in gj if j['verdict'] == RELEVANT),
                 'n_weak': sum(1 for j in gj if j['verdict'] == WEAK),
                 'n_irrelevant': sum(1 for j in gj if j['verdict'] == IRRELEVANT),
                 'no_info': 'NO RELIABLE INFORMATION' in text.upper()})
    print(f"  GEM  {g_before.get('kind','-')} -> {g_after.get('kind','-')}",
          file=sys.stderr)

cost = search_cost(n_serp) + n_gem * GEMINI_COST_PER_CALL
json.dump({'serp_queries': n_serp, 'gemini_calls': n_gem,
           'cost_usd': round(cost, 4), 'elapsed_s': round(time.time() - t0, 1),
           'rows': rows},
          open(os.path.join(HERE, 'MATRIX_QUERY_RESULTS.json'), 'w'),
          indent=2, ensure_ascii=False)
print(f"\n{n_serp} serp + {n_gem} gemini, ~${cost:.3f}", file=sys.stderr)
