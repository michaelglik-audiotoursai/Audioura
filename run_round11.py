#!/usr/bin/env python3
"""run_round11.py — six venues, because n=2 is not evidence.

Round 10 came back clean on two tours. Declaring the quality phase finished on two
tours is the same mistake as trusting a report over a diff. This spans museum,
walking, facility, restaurant and transport so a clean result means something.

Round 7 is the batch two kiro critics reviewed. Six parked tasks (LOCAL-527..532)
describe defects found in it. Before paying agents to fix those, regenerate the same
two venues on the current tree and see which defects survive:

  D583  possessive excision no longer welds words ("Archdiocesethe")
  D584  the person-cap no longer caps a person called "church", and now actually
        caps the person it was written for
  D586  a stop that admits it has no content is now a scored defect

Same venues, same stop count, same tour_type as round 7 so the comparison holds.
"""
import os
import sys
import time
import json
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ['DISABLE_TOUR_CACHE'] = '1'      # force real generation, no cache hits
os.environ['STORIED_MODE'] = 'true'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('SNIPPET_CAP_PER_STOP', '20')

from generate_tour_text import generate_tour_text  # noqa: E402
import generate_tour_text as _gtt  # noqa: E402  [LOCAL-533] read _LAST_GENERATION_COST
import tour_quality as tq  # noqa: E402

OUT = os.path.join(HERE, 'TOURS_FOR_REVIEW', 'round11')
os.makedirs(OUT, exist_ok=True)

VENUES = [
    ('CHURCH_1',  'Our Lady Help of Christians Catholic Church, Newton MA', 'museum', 4),
    ('LOGAN_1',   'Boston Logan International Airport, Boston MA', 'facility', 4),
    ('LASCARIS',  'Palais Lascaris, Nice, France', 'museum', 6),
    ('STNICHOLAS','St Nicholas Orthodox Cathedral, Nice, France', 'museum', 4),
    ('RIVIERA',   'French Riviera coastal path, Nice, France', 'walking', 4),
    ('FANEUIL',   'Faneuil Hall Marketplace, Boston MA', 'walking', 4),
]

summary = []
for name, location, tour_type, stops in VENUES:
    print(f'\n{"="*70}\n{name}: {location} ({tour_type}, {stops} stops)\n{"="*70}',
          flush=True)
    t0 = time.time()
    path = os.path.join(OUT, f'{name}.txt')
    try:
        text, _, _ = generate_tour_text(location, tour_type, path, stops)
        wall = time.time() - t0
        if not text:
            summary.append({'name': name, 'ok': False, 'error': 'empty text',
                            'wall_s': round(wall, 1)})
            print(f'{name}: FAILED — empty text after {wall:.0f}s', flush=True)
            continue
        open(path, 'w').write(text)
        scored = tq.score_tour(text, stops, is_building_tour=True)
        # [LOCAL-533] Read the cost record straight from the module global rather
        # than parsing it out of the log — parsing the log is how grounding cost
        # got lost. This captures BOTH billing channels: OpenAI tokens
        # (total_cost) and grounded Google-Search requests (grounding_cost).
        _cost = dict(_gtt._LAST_GENERATION_COST or {})
        rec = {'name': name, 'ok': True, 'wall_s': round(wall, 1),
               'chars': len(text), 'defects': scored['defects'],
               'metrics': scored['metrics'],
               'cost': {
                   'total_api_cost_usd': round(_cost.get('total_cost', 0.0), 6),
                   'total_tokens': _cost.get('total_tokens', 0),
                   'grounding_cost_usd': round(_cost.get('grounding_cost', 0.0), 6),
                   'grounding_requests': _cost.get('grounding_requests', 0),
                   'tour_total_cost_usd': round(_cost.get('tour_total_cost', 0.0), 6),
                   'cache_hit': _cost.get('cache_hit', False),
               }}
        summary.append(rec)
        print(f'\n{name}: {len(text)} chars in {wall:.0f}s', flush=True)
        print(f'   defects: {list(scored["defects"].keys()) or "CLEAN"}', flush=True)
        print(f'   people:  {scored["metrics"].get("named_people")}', flush=True)
        print(f'   cost:    API ${rec["cost"]["total_api_cost_usd"]:.4f} '
              f'({rec["cost"]["total_tokens"]} tok) + grounding '
              f'${rec["cost"]["grounding_cost_usd"]:.4f} '
              f'({rec["cost"]["grounding_requests"]} req) = '
              f'${rec["cost"]["tour_total_cost_usd"]:.4f}', flush=True)
    except Exception as e:
        wall = time.time() - t0
        summary.append({'name': name, 'ok': False, 'error': f'{type(e).__name__}: {e}',
                        'wall_s': round(wall, 1)})
        print(f'{name}: EXCEPTION after {wall:.0f}s — {type(e).__name__}: {e}',
              flush=True)
        traceback.print_exc()

with open(os.path.join(OUT, 'ROUND11_SUMMARY.json'), 'w') as f:
    json.dump(summary, f, indent=2)
print('\n' + '=' * 70)
for r in summary:
    if r.get('ok'):
        print(f'  {r["name"]:10} OK   {r["wall_s"]:6.0f}s  '
              f'defects={list(r["defects"].keys()) or "CLEAN"}')
    else:
        print(f'  {r["name"]:10} FAIL {r["wall_s"]:6.0f}s  {r["error"][:60]}')
