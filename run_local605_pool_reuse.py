#!/usr/bin/env python3
"""run_local605_pool_reuse.py — LOCAL-605 live pool-reuse delivery check.

Runs INSIDE a disposable container (docker run --rm --name local605-gen ...),
never against the audioura-* stack. Requests ONE pooled McMullen tour (5 stops;
the pool already holds 10, so N<=K serves entirely from the pool — the stop-pool
reuse path, zero new generation, trivially under the $0.30 cap).

It then runs the SAME resolver the service uses (tour_coordinates.
resolve_tour_coordinates) over the delivered text, and prints:
  * the delivery path (should be 'pool'),
  * the raw coordinates the generator returned (the bug: (None, None)),
  * the RESOLVED tour-level coordinates + their source (the fix),
so the fix is observable on a real pooled delivery.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

os.environ.setdefault("STORIED_MODE", "true")
# Hard cost ceiling as a belt-and-suspenders cap (a pooled N<=K delivery issues
# no new generation, so cost is ~$0 regardless).
os.environ.setdefault("COST_HARD_LIMIT_USD", "0.30")

LOCATION = os.environ.get("LOCAL605_LOCATION",
                          "McMullen Museum of Art, Boston College, Boston, MA")
TOUR_TYPE = os.environ.get("LOCAL605_TYPE", "museum")
STOPS = int(os.environ.get("LOCAL605_STOPS", "5"))
OUT = os.path.join(os.environ.get("LOCAL605_OUTDIR", HERE), "LOCAL605_mcmullen_pool.txt")

import generate_tour_text as g  # noqa: E402
from tour_coordinates import resolve_tour_coordinates, coordinates_present  # noqa: E402

print("=" * 74)
print(f"LOCAL-605 live pool-reuse: {LOCATION} / {TOUR_TYPE} / {STOPS} stops")
print("=" * 74, flush=True)

t0 = time.time()
text, _out, raw_coords = g.generate_tour_text(LOCATION, TOUR_TYPE, OUT, STOPS)
wall = time.time() - t0

cost = dict(getattr(g, "_LAST_GENERATION_COST", {}) or {})
path = getattr(g, "_LAST_DELIVERY_PATH", "?")
n_stops = len(re.findall(r'^Stop\s+\d+:', text or "", re.M))

resolved, source = resolve_tour_coordinates(text or "", LOCATION, raw_coords, path=path)

print("\n" + "=" * 74)
print("LOCAL-605 RESULT")
print("=" * 74)
print(f"  delivery_path         : {path}")
print(f"  pool_reuse            : {cost.get('pool_reuse', False)}")
print(f"  reused/new stops      : {cost.get('breakdown', {}).get('reused_stops')}/"
      f"{cost.get('breakdown', {}).get('new_stops')}")
print(f"  delivered stops       : {n_stops}")
print(f"  new_cost (LLM)        : ${cost.get('total_cost', 0.0):.4f}")
print(f"  wall                  : {wall:.0f}s")
print(f"  RAW generator coords  : {raw_coords}   <- the LOCAL-605 bug (None,None on pooled)")
print(f"  RESOLVED tour coords  : ({resolved[0]}, {resolved[1]})  source={source}")
print(f"  coordinates present?  : {coordinates_present(resolved)}")
print("=" * 74, flush=True)

if not coordinates_present(resolved):
    print("FAIL: pooled delivery resolved NO coordinates (fail-closed would reject).")
    sys.exit(1)
print("OK: pooled delivery carries real tour-level coordinates.")
