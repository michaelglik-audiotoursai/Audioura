#!/usr/bin/env python3
"""measure_local674_walking.py — LOCAL-674 research-ONLY A/B for WALKING stops.

No narration, no tour generation: for each walking stop we RECONSTRUCT the exact
per-stop story-lead question the pipeline sends (story_query.compile_for_seed on a
PLACE matrix — the same prompt the D511 per-stop grounded narrate receives), then
answer it under each backend and SCORE the evidence:

  arms:
    gemini       — story_leads.gemini_with_sources(grounded=True)  (the baseline)
    serper       — serper_research.serper_research                  (LOCAL-648)
    serper_plus  — serper_plus_research.serper_plus_research        (LOCAL-674)

  per-stop score (a cheap model, gpt-4.1-mini, judges; the full dump is saved so
  the judgement can be checked by hand):
    * dated_named_facts  — distinct facts that carry BOTH a date/year AND a named
      person/body/place (the walking-story currency; filler like "$26.5 million …
      1969" with no named actor does NOT count);
    * consequence        — at least one fact states a consequence (what the event
      caused / led to / changed);
    * n_sources          — distinct sources returned.
  A composite `evidence_score = dated_named_facts + (2 if consequence else 0)` is
  reported so arms can be ranked; the raw counts are kept for inspection.

Three walking requests, five real stops each (the Boston 557 stops + two more
requested in the ticket). Costs a few cents per arm (Serper $0.001/query, the
gpt-4.1-mini extractor/judge, one grounded Gemini request per stop).

CAP: LOCAL674_MAX_USD (default $1.20 for this offline arm, under the $2.50 total).
Spend is read per arm from the network meter (paid_api_calls jsonl) by byte
offset — never estimated. Check `paid_api_calls` before the run.

    python3 measure_local674_walking.py                 # all requests
    python3 measure_local674_walking.py --limit 1       # Boston only
    python3 measure_local674_walking.py --arms gemini,serper_plus
writes LOCAL674_walking_measurement.json
"""
import argparse
import json
import os
import re
import sys
import time
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import story_leads            # noqa: E402
import serper_research        # noqa: E402
import serper_plus_research   # noqa: E402
from story_query import compile_for_seed  # noqa: E402


# ── the walking requests and their real stops (places, not objects) ───────────
# Boston = the 557 tour's five verified stops (COST_TIME_RESULTS 2026-10-10).
# The other two are the ticket's examples. Each stop is a PLACE: the matrix has a
# canonical_title (the place) and venue_name (itself), no artist/credit_line —
# which is exactly why the object-oriented Serper backend struggles here.
REQUESTS: List[Dict] = [
    {
        'request': 'Walking tour of historic political Boston',
        'city': 'Boston, Massachusetts, United States',
        'stops': ['Old State House', 'Faneuil Hall', 'Boston City Hall',
                  'Massachusetts State House', 'Boston Athenaeum'],
    },
    {
        'request': 'Walking tour of the Freedom Trail, Boston',
        'city': 'Boston, Massachusetts, United States',
        'stops': ['Massachusetts State House', 'Park Street Church',
                  'Granary Burying Ground', "King's Chapel", 'Old South Meeting House'],
    },
    {
        'request': 'Walking tour of Old Nice, France',
        'city': 'Nice, France',
        'stops': ['Cours Saleya', 'Nice Cathedral', 'Place Rossetti',
                  'Palais Lascaris', 'Colline du Château'],
    },
]


def reconstruct_question(place: str, city: str) -> Dict:
    """Replay the REAL per-stop question builder for a PLACE stop. The walking
    pipeline carries a place as the matrix canonical_title/venue_name with no
    object fields, so compile_for_seed produces the generic prose-seed question —
    exactly what research_with_sources/gemini_with_sources receives for a walking
    stop."""
    matrix = {'canonical_title': place, 'venue_name': place}
    seed = {'kind': 'prose', 'seed': '', 'ask': ''}
    prompt = compile_for_seed(seed, matrix, exhibition=city)
    return {'place': place, 'city': city, 'prompt': prompt}


# ── cheap-model fact extraction + walking-evidence scoring ────────────────────
_SCORE_PROMPT = """\
You are scoring the RESEARCH EVIDENCE for one stop on a walking tour. Below is the
text a researcher produced about the place "{place}" ({city}).

Judge ONLY what the text asserts. Output a single JSON object and nothing else:

{{"dated_named_facts": <count of DISTINCT facts that contain BOTH a specific
     date or year AND a named person, body, or place — e.g. "In 1770 Crispus
     Attucks was killed here"; a bare figure with no named actor like
     "cost $26.5 million in 1969" does NOT count>,
  "dated_named_examples": [<up to 5 short quotes of those facts>],
  "has_consequence": <true if at least one fact states a CONSEQUENCE — what an
     event caused, led to, ended, or changed — else false>,
  "filler": <true if the text is mostly generic description/praise with little
     dated, named, consequential history, else false>}}

TEXT:
{text}
"""


def _cheap(prompt: str, model: str = 'gpt-4.1-mini', max_tokens: int = 700) -> str:
    import requests
    key = os.environ.get('OPENAI_API_KEY')
    if not key:
        return ''
    try:
        r = requests.post('https://api.openai.com/v1/chat/completions',
                          headers={'Authorization': f'Bearer {key}',
                                   'Content-Type': 'application/json'},
                          json={'model': model, 'temperature': 0.0,
                                'max_tokens': max_tokens,
                                'messages': [{'role': 'user', 'content': prompt}]},
                          timeout=60)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content'] or ''
    except Exception:
        return ''


def score_evidence(place: str, city: str, text: str) -> Dict:
    if not (text or '').strip():
        return {'dated_named_facts': 0, 'dated_named_examples': [],
                'has_consequence': False, 'filler': True, 'evidence_score': 0}
    out = _cheap(_SCORE_PROMPT.format(place=place, city=city, text=text[:4000]))
    m = re.search(r'\{.*\}', out, re.S)
    d = {}
    if m:
        try:
            d = json.loads(m.group(0))
        except ValueError:
            d = {}
    dnf = int(d.get('dated_named_facts', 0) or 0)
    cons = bool(d.get('has_consequence', False))
    d['dated_named_facts'] = dnf
    d['has_consequence'] = cons
    d['filler'] = bool(d.get('filler', False))
    d.setdefault('dated_named_examples', [])
    d['evidence_score'] = dnf + (2 if cons else 0)
    return d


# ── per-arm spend from the network meter ──────────────────────────────────────
def _meter_log_path() -> str:
    return os.environ.get('PAID_API_LOG', '/meterlogs/paid_api_calls.jsonl')


def _log_offset() -> int:
    try:
        return os.path.getsize(_meter_log_path())
    except OSError:
        return 0


def _read_meter_since(byte_offset: int):
    recs = []
    try:
        with open(_meter_log_path(), 'r') as fh:
            fh.seek(byte_offset)
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except ValueError:
                    continue
            return recs, fh.tell()
    except FileNotFoundError:
        return [], byte_offset


def _spend_of(recs, kinds=None) -> float:
    tot = 0.0
    for r in recs:
        if r.get('status') != 200:
            continue
        if kinds and r.get('kind') not in kinds:
            continue
        tot += float(r.get('usd') or 0.0)
    return tot


_ARMS = {
    'gemini': (lambda prompt: story_leads.gemini_with_sources(prompt, grounded=True),
               {'gemini'}),
    'serper': (lambda prompt: serper_research.serper_research(prompt),
               {'serper', 'openai'}),
    'serper_plus': (lambda prompt: serper_plus_research.serper_plus_research(prompt),
                    {'serper', 'openai'}),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=len(REQUESTS))
    ap.add_argument('--arms', default='gemini,serper,serper_plus')
    ap.add_argument('--max-usd', type=float,
                    default=float(os.environ.get('LOCAL674_MAX_USD', '1.20')))
    args = ap.parse_args()
    arms = [a.strip() for a in args.arms.split(',') if a.strip() in _ARMS]

    print('=' * 78)
    print('LOCAL-674 — research-ONLY A/B for WALKING stops')
    print(f'arms: {arms}   cap: ${args.max_usd:.2f}   meter: {_meter_log_path()}')
    print('=' * 78)

    start_off = _log_offset()
    results = []
    stopped = False
    for req in REQUESTS[:args.limit]:
        if stopped:
            break
        print('\n' + '#' * 78)
        print(f"REQUEST: {req['request']}  ({req['city']})")
        print('#' * 78)
        for place in req['stops']:
            recs_so_far, _ = _read_meter_since(start_off)
            spent = _spend_of(recs_so_far)
            if spent >= args.max_usd:
                print(f"[cap] ${spent:.4f} >= ${args.max_usd:.2f} — stopping.")
                stopped = True
                break
            q = reconstruct_question(place, req['city'])
            print('─' * 70)
            print(f"STOP: {place}")
            row = {'request': req['request'], 'city': req['city'],
                   'place': place, 'prompt': q['prompt'], 'arms': {}}
            for arm in arms:
                fn, kinds = _ARMS[arm]
                off = _log_offset()
                t0 = time.time()
                try:
                    res = fn(q['prompt'])
                except Exception as e:
                    res = {'text': '', 'sources': [], 'error': f'{type(e).__name__}: {e}'}
                secs = time.time() - t0
                arecs, _ = _read_meter_since(off)
                usd = _spend_of(arecs, kinds=kinds)
                text = res.get('text', '') or ''
                score = score_evidence(place, req['city'], text)
                row['arms'][arm] = {
                    'text': text, 'error': res.get('error', ''),
                    'n_sources': len(res.get('sources', []) or []),
                    'sources': res.get('sources', []) or [],
                    'queries': res.get('queries', []) or [],
                    'seconds': round(secs, 1), 'usd': round(usd, 5),
                    'score': score,
                }
                print(f"  {arm:12s} evidence={score['evidence_score']:2d} "
                      f"(dated_named={score['dated_named_facts']}, "
                      f"consequence={'Y' if score['has_consequence'] else 'n'}, "
                      f"filler={'Y' if score['filler'] else 'n'})  "
                      f"src={len(res.get('sources', []) or [])}  "
                      f"{secs:4.1f}s  ${usd:.5f}"
                      f"{'  ERR:' + res['error'] if res.get('error') else ''}")
            results.append(row)

    # ── summary ──
    all_recs, _ = _read_meter_since(start_off)
    summary = {'rate_tag': _rate_tag(), 'arms': {}, 'n_stops': len(results)}
    for arm in arms:
        rows = [r['arms'][arm] for r in results if arm in r['arms']]
        n = len(rows) or 1
        summary['arms'][arm] = {
            'mean_evidence_score': round(sum(x['score']['evidence_score'] for x in rows) / n, 2),
            'mean_dated_named_facts': round(sum(x['score']['dated_named_facts'] for x in rows) / n, 2),
            'stops_with_consequence': sum(1 for x in rows if x['score']['has_consequence']),
            'stops_filler': sum(1 for x in rows if x['score']['filler']),
            'mean_sources': round(sum(x['n_sources'] for x in rows) / n, 2),
            'total_usd': round(sum(x['usd'] for x in rows), 5),
            'usd_per_stop': round(sum(x['usd'] for x in rows) / n, 5),
            'mean_seconds': round(sum(x['seconds'] for x in rows) / n, 1),
        }
    summary['total_run_usd'] = round(_spend_of(all_recs), 5)

    print('\n' + '=' * 78)
    print('SUMMARY')
    print('=' * 78)
    print(json.dumps(summary, indent=2))

    out = os.environ.get('LOCAL674_OUT_JSON') or os.path.join(
        HERE, 'LOCAL674_walking_measurement.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({'summary': summary, 'results': results}, fh,
                  indent=2, ensure_ascii=False)
    print(f"\nwrote {out}")


def _rate_tag() -> str:
    try:
        sys.path.insert(0, os.path.join(HERE, '_meter'))
        import paid_api_meter as _m
        return getattr(_m, 'RATE_TAG', '?')
    except Exception:
        return '?'


if __name__ == '__main__':
    main()
