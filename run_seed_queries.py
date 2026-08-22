#!/usr/bin/env python3
"""run_seed_queries.py — D504: turn every seed into a query, run it, judge it.

Michael, 2026-08-22: *"generate queries and run them ... then let's evaluate the
results."*

**One query per seed.** Anchored and evaluative seeds get DIFFERENT queries,
because they are asking different questions (D503):

  ANCHORED    the phrase names a real entity, so the query VERIFIES it.
              "Pierre Reverdy, the French poet linked to Surrealism"
              -> Pierre Reverdy "Au Soleil du Plafond" Juan Gris
              A result that contradicts it is a fabrication caught.

  EVALUATIVE  the phrase is our own abstraction, so no query can confirm it.
              "Reverdy's poetic prowess" — nothing will ever return "prowess".
              The query hunts for the EVENT that would justify it, using
              D489(c)'s event vocabulary rather than the phrase's own words.
              Searching the phrase verbatim is LOCAL-457's error: exact-phrase
              searching a string that exists nowhere.

**Judging is by the instruments we already have, not by a new opinion.** Each
seed's results are scored with `snippet_ranker` (so D495's market demotion
applies) and classified with `material_kind` — the same eventful/active/inert
verdict step 3d uses. A seed "worked" if its results contain an ACTION WITH AN
AGENT, which is the same bar the generator is held to (D493, LOCAL-495).

**Cost.** Serper is $0.001/query, so 37 seeds is about four cents. Michael
budgeted $13; the ceiling below is set at $2.00, which is 2000 queries — far
more than this can issue — purely so a loop bug cannot spend the budget.
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

HARD_COST_CEILING = float(os.environ.get('SEED_QUERY_CEILING', '2.00'))

from story_seeds import seeds_for_stop, ANCHORED                 # noqa: E402
from work_story_searcher import _serp_search, normalize_domain, \
    _classify_domain_quick, set_venue_domain                     # noqa: E402
from snippet_ranker import rank_and_cap_snippets                 # noqa: E402
from material_kind import classify_material                      # noqa: E402
from cost_rates import search_cost                               # noqa: E402
from text_fold import fold                                       # noqa: E402

BASELINE = 'STEP0_BASELINE_20260820_1459.txt'
VENUE = 'Museum of Fine Arts, Boston'
KNOWN = {'Juan Gris', 'Pierre Reverdy', 'Joan Miró', 'Louis Broder',
         'Boris Fridman', 'Salvador Dalí', 'Sigmund Freud', 'Mourlot',
         'Torf', 'Linde Family'}

# D489(c)'s event vocabulary. An evaluative phrase cannot be searched for
# directly, so the query asks for the KIND of thing that would justify it.
_EVENT_TERMS = ('history', 'commissioned', 'refused', 'destroyed', 'abandoned',
                'unfinished', 'delayed', 'dispute')

_STOPWORDS = {'the', 'a', 'an', 'of', 'to', 'in', 'with', 'and', 'that',
              'this', 'its', 'their', 'for', 'as', 'how', 'not', 'only',
              'but', 'also', 'from', 'into', 'by', 'on', 'at', 'is', 'are'}


def build_query(seed, stop_title, artist):
    """One seed -> one query string, plus the reason for its shape."""
    work = re.sub(r'\s*\([^)]*\)\s*', ' ', stop_title).strip()
    anchor = (seed.get('anchor') or '').strip()

    if seed['class'] == ANCHORED:
        # Verify the claim: the named party, the work, and the artist.
        who = anchor or ' '.join(
            w for w in re.findall(r"[A-ZÀ-Þ][\w'’\-]+", seed['text'])[:2])
        parts = [p for p in (who, f'"{work}"', artist) if p]
        return ' '.join(dict.fromkeys(parts)), 'verify the named claim'

    # Evaluative: search for the event, never the adjective.
    content = [w for w in re.findall(r"[a-zà-ÿ'’\-]{4,}", seed['text'].lower())
               if w not in _STOPWORDS][:2]
    who = anchor or artist
    # NOT hash(): Python randomises string hashing per process, so the same
    # seed drew a different event term on every run and the experiment could
    # not be reproduced. Content-derived and stable.
    term = _EVENT_TERMS[sum(ord(c) for c in seed['id'] + seed['text'])
                        % len(_EVENT_TERMS)]
    parts = [p for p in (who, f'"{work}"', term) if p]
    return ' '.join(dict.fromkeys(parts)), \
        f'the phrase is ours; hunt the event ({term}) behind it'


def load_stops():
    text = open(os.path.join(HERE, BASELINE)).read()
    parts = re.split(r'^Stop \d+:\s*(.+)$', text, flags=re.M)
    out = []
    for i in range(1, len(parts) - 1, 2):
        body = re.sub(r'^\s*(Address|Coordinates|Directions):.*$', '',
                      parts[i + 1], flags=re.M)
        out.append((parts[i].strip(), body))
    return out


ARTISTS = {'Le Lézard': 'Joan Miró', 'Au Soleil': 'Juan Gris',
           'Moses': 'Salvador Dalí'}


def artist_for(title):
    for k, v in ARTISTS.items():
        if k.lower() in title.lower():
            return v
    return ''


set_venue_domain('http://www.mfa.org/')
queries_run = 0
rows = []
t0 = time.time()

for stop_title, body in load_stops():
    artist = artist_for(stop_title)
    seeds = seeds_for_stop(body, KNOWN)
    print(f"\n=== {stop_title[:60]} — {len(seeds)} seeds", file=sys.stderr)
    for seed in seeds:
        if search_cost(queries_run + 1) > HARD_COST_CEILING:
            print("  COST CEILING REACHED — stopping", file=sys.stderr)
            break
        query, why = build_query(seed, stop_title, artist)
        results, _lat = _serp_search(query)
        queries_run += 1

        for r in results:
            r['domain'] = normalize_domain(r.get('url', ''))
            r['tier'] = _classify_domain_quick(r['domain']) or 'unverified'

        ranked, report = rank_and_cap_snippets(
            results, artist=artist, work_title=stop_title,
            category='museum')
        snippets = [r.get('snippet', '') for r in ranked if r.get('snippet')]
        # LIST of passages, not a joined string. `classify_material` iterates
        # its argument, so a string is scanned CHARACTER BY CHARACTER and every
        # verdict comes back `inert` with sentences == chars. The first run of
        # this script reported 37/37 inert on exactly that bug — D423's shape,
        # caught by checking the instrument against a text whose answer is known
        # before believing a uniform zero.
        kind = classify_material(snippets) if snippets else {}

        rows.append({
            'stop': stop_title, 'id': seed['id'], 'class': seed['class'],
            'kind_of_seed': seed['kind'], 'seed': seed['seed'],
            'ask': seed['ask'], 'query': query, 'why': why,
            'n_results': len(results), 'n_ranked': len(ranked),
            'market_demoted': report.get('market_demoted', 0),
            't1t2': report.get('tier1_tier2_in_output', 0),
            'material_kind': kind.get('kind', 'none'),
            'eventful_sentences': kind.get('eventful_sentences', 0),
            'active': kind.get('active_sentences', 0),
            'staked': kind.get('staked_sentences', 0),
            'best_sentence': kind.get('best_sentence', ''),
            'top': [{'title': r.get('title', '')[:110],
                     'snippet': r.get('snippet', '')[:300],
                     'domain': r.get('domain', ''), 'tier': r.get('tier', '')}
                    for r in ranked[:3]],
        })
        print(f"  {seed['id']:<5} {seed['class']:<10} q={query[:58]:<58} "
              f"n={len(results):<2} kind={kind.get('kind', '-')}", file=sys.stderr)

elapsed = time.time() - t0
cost = search_cost(queries_run)
out = {'queries': queries_run, 'cost_usd': round(cost, 4),
       'elapsed_s': round(elapsed, 1), 'rows': rows}
with open(os.path.join(HERE, 'SEED_QUERY_RESULTS.json'), 'w') as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)
print(f"\n{queries_run} queries, ${cost:.4f}, {elapsed:.0f}s "
      f"-> SEED_QUERY_RESULTS.json", file=sys.stderr)
