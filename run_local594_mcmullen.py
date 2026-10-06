#!/usr/bin/env python3
"""run_local594_mcmullen.py — LOCAL-594 measurement + live check.

Generates ONE real 7-stop McMullen Museum tour and reports, truthfully:

  * the cost lines Michael sees — Total API cost / Grounding / Tour total — with
    grounding priced by the Google billing unit (search QUERIES @ $0.014);
  * per-stop grounded REQUESTS and QUERIES, and which call site issued them, by
    tapping story_production_loop.run_for_stop (the D511 credit_line loop) and the
    global story_leads query/request counters;
  * the story-gate result per stop (did a story reach the stop?).

Run inside an ISOLATED container only (docker run --rm --name local594-gen ...),
never against the live audioura-* stack. Total cap $3 including Gemini — this is
ONE tour.

Env knobs this driver sets:
  STORY_LOOP_MAX_GROUNDED  — the per-stop grounded cap (set 1 for the cut, or a
                             large number for the BEFORE baseline).
  LOCAL594_LABEL           — printed tag (BEFORE / AFTER).
"""
import os
import sys
import time
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_envfile = os.path.join(HERE, '.env')
if os.path.exists(_envfile):
    for line in open(_envfile):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ['STORIED_MODE'] = 'true'
# Fresh generation only — a cache hit would issue zero grounded requests and
# measure nothing. Disable the stop pool and the tour cache for a true fresh run.
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.setdefault('STORY_LOOP_ENABLED', '1')

LABEL = os.environ.get('LOCAL594_LABEL', 'AFTER')
# [LOCAL-594 r2] Parameterized so the same driver runs McMullen AND the Freedom
# Trail walking tour. Defaults preserve the original McMullen 7-stop behaviour.
LOCATION = os.environ.get('LOCAL594_LOCATION', 'McMullen Museum of Art, Boston College, Boston, MA')
TOUR_TYPE = os.environ.get('LOCAL594_TYPE', 'museum')
STOPS = int(os.environ.get('LOCAL594_STOPS', '7'))
_SLUG = os.environ.get('LOCAL594_SLUG', 'MCMULLEN')
# [LOCAL-594 r2] Write outputs into the mounted tours/ dir when present so .txt
# and .json survive a --rm container; fall back to HERE for a bare local run.
_OUTDIR = os.path.join(HERE, 'tours') if os.path.isdir(os.path.join(HERE, 'tours')) else HERE
OUT = os.path.join(_OUTDIR, f'LOCAL594_{_SLUG}_{LABEL}.txt')

import story_leads  # noqa: E402
import story_production_loop as _spl  # noqa: E402
from generate_tour_text import generate_tour_text  # noqa: E402
import generate_tour_text as _gtt  # noqa: E402

# ── per-stop grounding tap ───────────────────────────────────────────────────
# Wrap run_for_stop so each stop reports its grounded requests, serp queries, and
# whether a story reached it. The global story_leads counter captures grounded
# requests + QUERIES across ALL call sites (D511 loop, story_leads.run, venue
# resolution), so the two together separate the per-stop driver from the rest.
_PER_STOP = []
_orig_run_for_stop = _spl.run_for_stop


def _tapped_run_for_stop(matrix, stop_text, *a, **kw):
    gr0 = story_leads.get_grounding_requests()
    gq0 = story_leads.get_grounding_queries()
    out = _orig_run_for_stop(matrix, stop_text, *a, **kw)
    rec = {
        'title': (matrix or {}).get('canonical_title', '?')[:40],
        'loop_grounded_requests': out.get('grounded_requests'),
        'loop_gem_calls': out.get('gem_calls'),
        'loop_serp_queries': out.get('serp_queries'),
        'global_grounded_requests_delta': story_leads.get_grounding_requests() - gr0,
        'global_grounded_queries_delta': story_leads.get_grounding_queries() - gq0,
        'story_reached': bool(out.get('story')),
        'story_index': out.get('index'),
        'stories': len(out.get('stories', []) or []),
        'examined': out.get('examined'),
    }
    _PER_STOP.append(rec)
    print(f"  [LOCAL-594 TAP] stop '{rec['title']}': "
          f"loop grounded_req={rec['loop_grounded_requests']} "
          f"gem_calls={rec['loop_gem_calls']} serp_q={rec['loop_serp_queries']} | "
          f"global grounded_req+={rec['global_grounded_requests_delta']} "
          f"queries+={rec['global_grounded_queries_delta']} | "
          f"story={'YES' if rec['story_reached'] else 'no'} "
          f"idx={rec['story_index']} stories={rec['stories']} "
          f"examined={rec['examined']}", flush=True)
    return out


_spl.run_for_stop = _tapped_run_for_stop
# generate_tour_text imports run_for_stop locally (from story_production_loop
# import run_for_stop as _d511_run), so patch the attribute BEFORE generation.

story_leads.reset_grounding_requests()

print("=" * 74)
print(f"LOCAL-594 [{LABEL}] : {LOCATION} / {TOUR_TYPE} / {STOPS} stops")
print(f"  STORY_LOOP_MAX_GROUNDED={os.environ.get('STORY_LOOP_MAX_GROUNDED', '(default 1)')}  "
      f"STORY_LEADS_GROUNDED={os.environ.get('STORY_LEADS_GROUNDED', '(default off)')}")
print("=" * 74, flush=True)

t0 = time.time()
text, path, _ = generate_tour_text(LOCATION, TOUR_TYPE, OUT, STOPS)
wall = time.time() - t0

cost = dict(_gtt._LAST_GENERATION_COST or {})
total_gr = story_leads.get_grounding_requests()
total_gq = story_leads.get_grounding_queries()

print("\n" + "=" * 74)
print(f"LOCAL-594 [{LABEL}] RESULT")
print("=" * 74)
print(f"  wall={wall:.0f}s  chars={len(text) if text else 0}")
print(f"  Total API cost (LLM): ${cost.get('total_cost', 0):.4f} "
      f"({cost.get('total_tokens', 0)} tokens)")
print(f"  Grounding:            ${cost.get('grounding_cost', 0):.4f} "
      f"({cost.get('grounding_queries', total_gq)} queries, "
      f"{cost.get('grounding_requests', total_gr)} requests)")
print(f"  Tour total:           ${cost.get('tour_total_cost', 0):.4f}")
print(f"  ---")
print(f"  WHOLE-TOUR grounded requests (all call sites): {total_gr}")
print(f"  WHOLE-TOUR grounded queries  (all call sites): {total_gq}")
_stops_with_story = sum(1 for r in _PER_STOP if r['story_reached'])
print(f"  Stops with a story (gate PASS / cleared): {_stops_with_story}/{len(_PER_STOP)}")
print(f"  Loop stories per stop: {[r['stories'] for r in _PER_STOP]}")
print(f"  Per-stop grounded requests (D511 loop): "
      f"{[r['loop_grounded_requests'] for r in _PER_STOP]}")
_max_per_stop = max([r['loop_grounded_requests'] or 0 for r in _PER_STOP] or [0])
print(f"  Max grounded requests on any one stop (D511 loop): {_max_per_stop} "
      f"(cap target: <= 1)")

summary = {
    'label': LABEL,
    'location': LOCATION, 'stops': STOPS, 'wall_s': round(wall, 1),
    'cost': cost,
    'whole_tour_grounded_requests': total_gr,
    'whole_tour_grounded_queries': total_gq,
    'stops_with_story': _stops_with_story,
    'per_stop': _PER_STOP,
}
with open(os.path.join(_OUTDIR, f'LOCAL594_{_SLUG}_{LABEL}.json'), 'w') as fh:
    json.dump(summary, fh, indent=2)
print(f"\n  wrote tours/LOCAL594_{_SLUG}_{LABEL}.json")
print("=" * 74)
