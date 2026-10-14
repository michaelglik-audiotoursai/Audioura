#!/usr/bin/env python3
"""run_local576_live.py — LOCAL-576 live-artifact run.

The exact field-test request from tour 388 (2026-10-04), 5 stops, on the current
tree. Reports the delivered stop list and order, every [LOCAL-576] line, and the
per-stop writer activity, plus total cost. OpenAI hard cap enforced at $1.50 via
COST_HARD_LIMIT_USD.

D261 host env is set below (DATABASE_URL @localhost:5433, DISABLE_TOUR_CACHE,
STORIED_MODE). Reads keys from .env.
"""
import json
import os
import re
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_envfile = os.path.join(HERE, '.env')
if os.path.exists(_envfile):
    for line in open(_envfile):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# D261 host env
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ['STORIED_MODE'] = 'true'
# OpenAI hard cap for this run.
os.environ['COST_HARD_LIMIT_USD'] = '1.50'

from generate_tour_text import generate_tour_text          # noqa: E402
import generate_tour_text as _gtt                          # noqa: E402

REQUEST = ("biking tour in a loop from Crystal Lake to Paul Revere via "
           "Commonwealth Avenue Mall & Boston Common, MA")
TOUR_TYPE = ''      # the full request is the location; nothing to prepend
STOPS = 5

OUT = os.path.join(HERE, 'LOCAL576_live')
os.makedirs(OUT, exist_ok=True)
PATH = os.path.join(OUT, 'tour388_rerun.txt')


def main():
    print('=' * 72)
    print(f'LOCAL-576 LIVE: {REQUEST!r}  ({STOPS} stops)')
    print('=' * 72, flush=True)
    t0 = time.time()
    try:
        text, outfile, coords = generate_tour_text(REQUEST, TOUR_TYPE, PATH, STOPS)
    except Exception as e:
        wall = time.time() - t0
        print(f'\nEXCEPTION after {wall:.0f}s — {type(e).__name__}: {e}', flush=True)
        traceback.print_exc()
        with open(os.path.join(OUT, 'LOCAL576_live_result.json'), 'w') as f:
            json.dump({'ok': False, 'error': f'{type(e).__name__}: {e}',
                       'wall_s': round(wall, 1)}, f, indent=2)
        return
    wall = time.time() - t0
    cost = dict(_gtt._LAST_GENERATION_COST or {})

    # Parse the delivered stop list from the tour text (Stop N: Name).
    stops = re.findall(r'(?mi)^\s*Stop\s+(\d+)\s*[:\-]\s*(.+?)\s*$', text or '')
    rec = {
        'ok': bool(text),
        'wall_s': round(wall, 1),
        'chars': len(text or ''),
        'delivered_stops': [{'n': int(n), 'name': nm} for n, nm in stops],
        'delivered_count': len(stops),
        'total_api_cost_usd': round(cost.get('total_cost', 0.0), 6),
        'first_coordinates': coords,
    }
    with open(os.path.join(OUT, 'LOCAL576_live_result.json'), 'w') as f:
        json.dump(rec, f, indent=2)
    print(f'\n{"=" * 72}')
    print(f'  delivered {rec["delivered_count"]} stop(s), wall={rec["wall_s"]}s, '
          f'cost=${rec["total_api_cost_usd"]:.4f}')
    for s in rec['delivered_stops']:
        print(f'    Stop {s["n"]}: {s["name"]}')
    print(f'{"=" * 72}', flush=True)


if __name__ == '__main__':
    main()
