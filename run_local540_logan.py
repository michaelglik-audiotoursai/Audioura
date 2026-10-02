#!/usr/bin/env python3
"""run_local540_logan.py — live end-to-end acceptance for LOCAL-540.

Generates the tour Round 9 shipped with defects — Boston Logan International
Airport, facility, 4 stops — through the NOW-WIRED generation path, with the
cache disabled so it is a real generation. Captures:

  * the LOCAL-540 log lines (scorer ran / defect seen / retry issued),
  * whether the retry removed the defect (honestly, "it did not" is acceptable),
  * the two-channel cost (OpenAI + grounding), both WITH and WITHOUT the retry.

Reads _LAST_GENERATION_COST and _LAST_SCORE_RECORD straight from the module, the
LOCAL-533 instrument, rather than parsing the log.
"""
import os
import sys
import time
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for _line in open(os.path.join(HERE, '.env')):
    _line = _line.strip()
    if _line and not _line.startswith('#') and '=' in _line:
        _k, _v = _line.split('=', 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

os.environ['DISABLE_TOUR_CACHE'] = '1'          # force real generation
os.environ['STORIED_MODE'] = 'true'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('SNIPPET_CAP_PER_STOP', '20')

from generate_tour_text import generate_tour_text
import generate_tour_text as _gtt
import tour_quality as tq

OUT = os.path.join(HERE, 'TOURS_FOR_REVIEW', 'local540')
os.makedirs(OUT, exist_ok=True)

LOCATION = 'Boston Logan International Airport, Boston MA'
TOUR_TYPE = 'facility'
STOPS = 4

print(f'\n{"="*72}\nLOCAL-540 LIVE: {LOCATION} ({TOUR_TYPE}, {STOPS} stops)\n{"="*72}',
      flush=True)

t0 = time.time()
path = os.path.join(OUT, 'LOGAN_1.txt')
text, out_file, coords = generate_tour_text(LOCATION, TOUR_TYPE, path, STOPS)
wall = time.time() - t0

cost = dict(_gtt._LAST_GENERATION_COST or {})
score = cost.get('score') or {}

print(f'\n{"="*72}\nLOCAL-540 RESULT\n{"="*72}', flush=True)
print(f'wall: {wall:.0f}s  chars: {len(text) if text else 0}', flush=True)

# independent re-score of the delivered text (belt and braces)
if text:
    final = tq.score_tour(text, requested_stops=STOPS, is_building_tour=True)
    print(f'delivered-text defects (independent re-score): '
          f'{sorted(final["defects"].keys()) or "CLEAN"}', flush=True)

print('\n-- score record --', flush=True)
print(f'  defects_before: {sorted(score.get("defects_before", {}).keys())}', flush=True)
print(f'  defects_after : {sorted(score.get("defects_after", {}).keys())}', flush=True)
print(f'  retried       : {score.get("retried")}', flush=True)
print(f'  removed       : {score.get("removed")}', flush=True)
print(f'  remaining     : {score.get("remaining")}', flush=True)
print(f'  clean_after   : {score.get("clean_after")}', flush=True)

rc = score.get('retry_cost', {}) or {}
cwo = score.get('cost_without_retry', {}) or {}
gr_cost = cost.get('grounding_cost', 0.0)
gr_req = cost.get('grounding_requests', 0)

print('\n-- two-channel cost --', flush=True)
print(f'  WITH retry:', flush=True)
print(f'    OpenAI    : ${cost.get("total_cost", 0.0):.6f} '
      f'({cost.get("total_tokens", 0)} tokens)', flush=True)
print(f'    grounding : ${gr_cost:.6f} ({gr_req} requests)', flush=True)
print(f'    tour total: ${cost.get("tour_total_cost", 0.0):.6f}', flush=True)
print(f'  retry alone : ${rc.get("total_cost", 0.0):.6f} '
      f'({rc.get("total_tokens", 0)} tokens)', flush=True)
print(f'  WITHOUT retry (OpenAI channel minus the retry):', flush=True)
print(f'    OpenAI    : ${cwo.get("total_cost", 0.0):.6f} '
      f'({cwo.get("total_tokens", 0)} tokens)', flush=True)
print(f'    grounding : ${gr_cost:.6f} ({gr_req} requests)  '
      f'(unchanged — the retry issues no grounded requests)', flush=True)
print(f'    tour total: ${cwo.get("total_cost", 0.0) + gr_cost:.6f}', flush=True)

summary = {
    'location': LOCATION, 'tour_type': TOUR_TYPE, 'stops': STOPS,
    'wall_s': round(wall, 1), 'chars': len(text) if text else 0,
    'score': score,
    'cost': {
        'with_retry': {
            'openai_usd': round(cost.get('total_cost', 0.0), 6),
            'openai_tokens': cost.get('total_tokens', 0),
            'grounding_usd': round(gr_cost, 6),
            'grounding_requests': gr_req,
            'tour_total_usd': round(cost.get('tour_total_cost', 0.0), 6),
        },
        'retry_alone': {
            'openai_usd': round(rc.get('total_cost', 0.0), 6),
            'openai_tokens': rc.get('total_tokens', 0),
        },
        'without_retry': {
            'openai_usd': round(cwo.get('total_cost', 0.0), 6),
            'openai_tokens': cwo.get('total_tokens', 0),
            'grounding_usd': round(gr_cost, 6),
            'grounding_requests': gr_req,
            'tour_total_usd': round(cwo.get('total_cost', 0.0) + gr_cost, 6),
        },
    },
}
with open(os.path.join(OUT, 'LOCAL540_SUMMARY.json'), 'w') as f:
    json.dump(summary, f, indent=2)
print(f'\nSaved: {path}', flush=True)
print(f'Saved: {os.path.join(OUT, "LOCAL540_SUMMARY.json")}', flush=True)
