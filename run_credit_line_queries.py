#!/usr/bin/env python3
"""run_credit_line_queries.py — D507: 37 credit_lines × 2 engines = 74 retrievals.

Michael, 2026-08-22: *"generate a document with all 37 stories per each AI: 37
for Serper with your Serper version of question and also 37 for Gemini with the
query constructed fully with 'What story can be told to visitors of {exhibition}
about {work}, {credit_line}?'"*

One credit_line (D503 seed) -> one question -> two encodings (D507):

  SERPER  compiled keywords: quoted work + named agents + `why` + year
  GEMINI  the question verbatim, with the matrix attached

Every result is stored whole and every sentence carries a D505 relevance verdict.
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

CEILING_USD = float(os.environ.get('CREDIT_QUERY_CEILING', '6.00'))

from story_seeds import seeds_for_stop                                # noqa: E402
from story_query import compile_for_serper, compile_for_gemini        # noqa: E402
from work_story_searcher import (_serp_search, normalize_domain,
                                 _classify_domain_quick, set_venue_domain)  # noqa: E402
from material_kind import classify_material                           # noqa: E402
from story_relevance import relevance_of, RELEVANT, WEAK, IRRELEVANT  # noqa: E402
from cost_rates import search_cost                                    # noqa: E402
from story_leads import _gemini                                       # noqa: E402

VENUE = 'Museum of Fine Arts, Boston'
EXHIBITION = 'Picasso, Miró, Dalí: Unbound'
GEMINI_COST = 0.006
BASELINE = 'STEP0_BASELINE_20260820_1459.txt'
KNOWN = {'Juan Gris', 'Pierre Reverdy', 'Joan Miró', 'Louis Broder',
         'Boris Fridman', 'Salvador Dalí', 'Sigmund Freud', 'Mourlot', 'Torf'}

MATRICES = {
    'Le Lézard': ({'canonical_title': "Le Lézard aux plumes d’or (The Lizard with Golden Feathers)",
                   'english_title': "Le Lézard aux plumes d’or", 'artist': 'Joan Miró',
                   'publisher': 'Louis Broder', 'printed_by': 'Mourlot',
                   'printer': 'Mourlot', 'collaborator': '',
                   'credit_line': 'Gift of Boris Fridman', 'publication_year': '1971',
                   'medium': "Illustrated book with forty color lithographs",
                   'venue_name': VENUE},
                  ['Miró', 'Broder', 'Mourlot', 'Fridman']),
    'Au Soleil': ({'canonical_title': 'Au Soleil du Plafond', 'english_title': 'Au Soleil du Plafond',
                   'artist': 'Juan Gris', 'publisher': '', 'printed_by': '', 'printer': '',
                   'collaborator': 'Pierre Reverdy', 'credit_line': '', 'medium': '',
                   'venue_name': VENUE},
                  ['Gris', 'Reverdy', 'Pierre Reverdy', 'Tériade', 'Verve']),
    'Moses': ({'canonical_title': 'Moses and Monotheism', 'english_title': 'Moses and Monotheism',
               'artist': 'Salvador Dalí', 'publisher': '', 'printed_by': '', 'printer': '',
               'collaborator': 'Sigmund Freud', 'credit_line': '', 'medium': 'Illustrations',
               'venue_name': VENUE},
              ['Dalí', 'Freud', 'Sigmund Freud', 'Hogarth']),
}

GEMINI_PROMPT = """{question}

What is already known about the work:
{matrix}

Search, then answer with FACTS ONLY — each one sentence, with its source in
brackets. Prefer what a visitor standing in front of it cannot see for
themselves: why it was made, who decided, what went wrong, what it cost someone.
If you find nothing reliable, say exactly "NO RELIABLE INFORMATION".
Do not praise the work. Do not describe how it looks. Maximum 6 sentences."""


def sentences_of(t):
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', t or '')
            if len(s.strip()) > 20]


def judge(sentences, matrix, extra, context):
    judged = []
    for s in sentences:
        r = relevance_of(s, matrix, context, extra)
        r['sentence'] = s
        judged.append(r)
    kept = [j['sentence'] for j in judged if j['verdict'] in (RELEVANT, WEAK)]
    return (judged,
            classify_material([j['sentence'] for j in judged]) if judged else {},
            classify_material(kept) if kept else {})


def matrix_for(title):
    for k, (m, e) in MATRICES.items():
        if k.lower() in title.lower():
            return m, e
    return {}, []


def load_stops():
    text = open(os.path.join(HERE, BASELINE)).read()
    parts = re.split(r'^Stop \d+:\s*(.+)$', text, flags=re.M)
    return [(parts[i].strip(),
             re.sub(r'^\s*(Address|Coordinates|Directions):.*$', '',
                    parts[i + 1], flags=re.M))
            for i in range(1, len(parts) - 1, 2)]


def main():
    set_venue_domain('http://www.mfa.org/')
    rows, n_serp, n_gem = [], 0, 0
    t0 = time.time()

    for stop_title, body in load_stops():
        matrix, extra = matrix_for(stop_title)
        seeds = seeds_for_stop(body, KNOWN)
        print(f"\n=== {stop_title[:52]} — {len(seeds)} credit_lines", file=sys.stderr)

        for seed in seeds:
            if search_cost(n_serp) + n_gem * GEMINI_COST > CEILING_USD:
                print("  CEILING", file=sys.stderr)
                break
            cl = seed['seed']
            sq = compile_for_serper(matrix, cl)
            gq = compile_for_gemini(matrix, cl, EXHIBITION)

            raw, _ = _serp_search(sq)
            n_serp += 1
            results = []
            for r in raw:
                dom = normalize_domain(r.get('url', ''))
                snip = r.get('snippet', '') or ''
                sj, _b, _a = judge(sentences_of(snip), matrix, extra, snip)
                results.append({'title': r.get('title', ''), 'url': r.get('url', ''),
                                'domain': dom,
                                'tier': _classify_domain_quick(dom) or 'unverified',
                                'snippet': snip, 'sentences': sj})
            sj = [j for r in results for j in r['sentences']]
            kept = [j['sentence'] for j in sj if j['verdict'] in (RELEVANT, WEAK)]
            s_before = classify_material([j['sentence'] for j in sj]) if sj else {}
            s_after = classify_material(kept) if kept else {}

            mat = '\n'.join(f'  {k}: {v}' for k, v in matrix.items() if v)
            gtext, gerr = '', ''
            try:
                gtext = _gemini(GEMINI_PROMPT.format(question=gq, matrix=mat),
                                grounded=True) or ''
            except Exception as e:
                gerr = f'{type(e).__name__}: {e}'
            n_gem += 1
            gj, g_before, g_after = judge(sentences_of(gtext), matrix, extra, gtext)

            rows.append({
                'stop': stop_title, 'id': seed['id'], 'class': seed['class'],
                'kind_of_seed': seed['kind'], 'credit_line': cl,
                'serper': {'query': sq, 'n_results': len(results), 'results': results,
                           'sentences': sj,
                           'kind_before_gate': s_before.get('kind', 'none'),
                           'kind_after_gate': s_after.get('kind', 'none'),
                           'best_after': s_after.get('best_sentence', ''),
                           'n_relevant': sum(1 for j in sj if j['verdict'] == RELEVANT),
                           'n_weak': sum(1 for j in sj if j['verdict'] == WEAK),
                           'n_irrelevant': sum(1 for j in sj if j['verdict'] == IRRELEVANT)},
                'gemini': {'question': gq, 'text': gtext, 'error': gerr,
                           'sentences': gj,
                           'kind_before_gate': g_before.get('kind', 'none'),
                           'kind_after_gate': g_after.get('kind', 'none'),
                           'best_after': g_after.get('best_sentence', ''),
                           'n_relevant': sum(1 for j in gj if j['verdict'] == RELEVANT),
                           'n_weak': sum(1 for j in gj if j['verdict'] == WEAK),
                           'n_irrelevant': sum(1 for j in gj if j['verdict'] == IRRELEVANT),
                           'no_info': 'NO RELIABLE INFORMATION' in gtext.upper()},
            })
            print(f"  {seed['id']:<5} serp {s_before.get('kind','-'):<8}->"
                  f"{s_after.get('kind','-'):<8} gem {g_before.get('kind','-'):<8}->"
                  f"{g_after.get('kind','-'):<8} | {sq[:44]}", file=sys.stderr)

    cost = search_cost(n_serp) + n_gem * GEMINI_COST
    json.dump({'serp_queries': n_serp, 'gemini_calls': n_gem,
               'cost_usd': round(cost, 4), 'elapsed_s': round(time.time() - t0, 1),
               'rows': rows},
              open(os.path.join(HERE, 'CREDIT_LINE_RESULTS.json'), 'w'),
              indent=2, ensure_ascii=False)
    print(f"\n{n_serp} serper + {n_gem} gemini = {n_serp + n_gem}, ~${cost:.3f}",
          file=sys.stderr)


if __name__ == "__main__":
    main()
