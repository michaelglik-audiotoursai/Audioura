#!/usr/bin/env python3
"""run_local533_one_tour.py — generate ONE real 4-stop tour and print the full
cost, both channels, then repeat the SAME request to prove a cache hit reports
grounding $0.00.

LOCAL-533 acceptance:
  - a real generated tour prints both the Total API cost line and the Grounding
    line, separately verifiable;
  - a cache hit issues no grounded requests and so reports grounding $0.00.

ONE tour, not a batch — grounded requests cost money. The second pass is a cache
hit (free) that verifies the $0.00 grounding claim.
"""
import os
import sys
import time
import json

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ['STORIED_MODE'] = 'true'
os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('SNIPPET_CAP_PER_STOP', '20')

import story_leads  # noqa: E402
from generate_tour_text import generate_tour_text  # noqa: E402
import generate_tour_text as _gtt  # noqa: E402

LOCATION = 'Our Lady Help of Christians Catholic Church, Newton MA'
TOUR_TYPE = 'museum'
STOPS = 4
OUT = os.path.join(HERE, 'LOCAL533_ONE_TOUR.txt')


def _show(tag):
    c = dict(_gtt._LAST_GENERATION_COST or {})
    print(f"\n[{tag}] _LAST_GENERATION_COST = {json.dumps(c, indent=2)}")
    print(f"[{tag}] story_leads.get_grounding_requests() = "
          f"{story_leads.get_grounding_requests()}")
    return c


# ---- Pass 1: FRESH generation (cache disabled) ------------------------------
os.environ['DISABLE_TOUR_CACHE'] = '1'
print("=" * 70)
print(f"PASS 1 (FRESH): {LOCATION} / {TOUR_TYPE} / {STOPS} stops")
print("=" * 70, flush=True)
t0 = time.time()
text, path, _ = generate_tour_text(LOCATION, TOUR_TYPE, OUT, STOPS)
wall = time.time() - t0
fresh = _show("FRESH")
print(f"[FRESH] wall={wall:.0f}s chars={len(text) if text else 0}")

# ---- Pass 2: CACHE HIT (cache enabled, same request) ------------------------
os.environ['DISABLE_TOUR_CACHE'] = '0'
print("\n" + "=" * 70)
print(f"PASS 2 (CACHE HIT expected): same request")
print("=" * 70, flush=True)
t0 = time.time()
text2, path2, _ = generate_tour_text(LOCATION, TOUR_TYPE, OUT + '.cache', STOPS)
wall2 = time.time() - t0
cached = _show("CACHE")
print(f"[CACHE] wall={wall2:.1f}s chars={len(text2) if text2 else 0}")

# ---- Verdict ----------------------------------------------------------------
print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)
ok = True
if not (fresh.get('grounding_requests', 0) >= 0 and 'grounding_cost' in fresh):
    ok = False
    print("FAIL: fresh generation did not record grounding fields")
else:
    print(f"FRESH:  API ${fresh.get('total_cost',0):.4f} "
          f"({fresh.get('total_tokens',0)} tok) + grounding "
          f"${fresh.get('grounding_cost',0):.4f} "
          f"({fresh.get('grounding_requests',0)} req) = "
          f"${fresh.get('tour_total_cost',0):.4f}")

if cached.get('cache_hit') is True and abs(cached.get('grounding_cost', 1.0)) < 1e-9 \
        and cached.get('grounding_requests', 1) == 0:
    print(f"CACHE:  cache_hit={cached.get('cache_hit')} grounding "
          f"${cached.get('grounding_cost',0):.4f} "
          f"({cached.get('grounding_requests',0)} req)  ✓ $0.00 as required")
else:
    ok = False
    print(f"FAIL: cache hit did not report grounding $0.00 / 0 req: {cached}")

print("\nRESULT:", "PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
