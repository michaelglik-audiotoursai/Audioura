#!/usr/bin/env python3
"""run_local543_live.py — LOCAL-543 live-artifact gate.

Generate the SAME venue that produced round9/CHURCH_1 — Our Lady Help of
Christians Catholic Church, Newton MA, museum, 4 stops — on the current tree, and
report the per-claim provenance counts from that real run. The point of the run is
the sourced/unsourced numbers and the new evidence file that carries them.

Gemini may return HTTP 402 (prepayment credits depleted). If a grounded call is
needed and fails, this still writes whatever the run produced and prints the
provenance line; it does not fabricate a run.
"""
import json
import os
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

os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['STORIED_MODE'] = 'true'

from generate_tour_text import generate_tour_text          # noqa: E402
import generate_tour_text as _gtt                          # noqa: E402
import tour_quality as tq                                  # noqa: E402

OUT = os.path.join(HERE, 'LOCAL543_live')
os.makedirs(OUT, exist_ok=True)

LOCATION = 'Our Lady Help of Christians Catholic Church, Newton MA'
TOUR_TYPE = 'museum'
STOPS = 4


def main():
    path = os.path.join(OUT, 'CHURCH_1_live.txt')
    print(f'{"="*72}\nLOCAL-543 LIVE: {LOCATION} ({TOUR_TYPE}, {STOPS} stops)\n{"="*72}',
          flush=True)
    t0 = time.time()
    try:
        text, _, _ = generate_tour_text(LOCATION, TOUR_TYPE, path, STOPS)
    except Exception as e:
        wall = time.time() - t0
        print(f'\nEXCEPTION after {wall:.0f}s — {type(e).__name__}: {e}', flush=True)
        traceback.print_exc()
        # Persist a stub so the failure is an artifact, not a claim.
        with open(os.path.join(OUT, 'LOCAL543_live_result.json'), 'w') as f:
            json.dump({'ok': False, 'error': f'{type(e).__name__}: {e}',
                       'wall_s': round(wall, 1)}, f, indent=2)
        return
    wall = time.time() - t0
    cost = dict(_gtt._LAST_GENERATION_COST or {})
    prov = cost.get('provenance') or {}
    scored = tq.score_tour(text or '', STOPS, is_building_tour=False)
    rec = {
        'ok': bool(text),
        'wall_s': round(wall, 1),
        'chars': len(text or ''),
        'defects': scored['defects'],
        'unsourced_person_event': 'unsourced_person_event' in scored['defects'],
        'provenance_counts': prov,
        'grounding_requests': cost.get('grounding_requests', 0),
        'grounding_cost_usd': round(cost.get('grounding_cost', 0.0), 6),
        'total_api_cost_usd': round(cost.get('total_cost', 0.0), 6),
    }
    with open(os.path.join(OUT, 'LOCAL543_live_result.json'), 'w') as f:
        json.dump(rec, f, indent=2)
    print(f'\n{"="*72}')
    print(f'  chars={rec["chars"]}  wall={rec["wall_s"]}s')
    print(f'  defects: {list(scored["defects"].keys()) or "CLEAN"}')
    if prov:
        print(f'  PROVENANCE: {prov.get("sourced")}/{prov.get("total")} sourced, '
              f'{prov.get("unsourced")} unsourced '
              f'({prov.get("corpus")} corpus, {prov.get("grounded")} grounded, '
              f'{prov.get("parametric")} parametric)')
    else:
        print('  PROVENANCE: (audit unavailable)')
    print(f'{"="*72}', flush=True)


if __name__ == '__main__':
    main()
