#!/usr/bin/env python3
"""run_local593b_container.py — LOCAL-593 r2 live acceptance (ISOLATED container).

Runs a museum request through the REAL generation path with the r2 branch code
mounted over /app, then runs the content-QA gate exactly as
generate_tour_text_service does — i.e. venue_context carries ONLY the
resolver-derived venue_tokens (the r1 #1 sibling_venues mechanism was reverted
in r2). Reports the BLOCKER 3 lines, stop titles, cost and wall-time.

Parameterised via env so one image serves both ticket runs:
    LOCAL593B_LOCATION   e.g. 'McMullen Museum of Art, Boston College, Chestnut Hill, MA'
    LOCAL593B_STOPS      e.g. '7'
    LOCAL593B_CAP_USD    e.g. '1.00'
    LOCAL593B_OUT        output path (default under /app/tours)

Usage (inside the isolated container):
    python3 run_local593b_container.py
"""
import os
import re
import sys
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'          # tour-OUTPUT cache off; venue_corpus stays on
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')

LOCATION = os.environ.get('LOCAL593B_LOCATION', 'Harvard Art Museums, Cambridge, MA')
STOPS = int(os.environ.get('LOCAL593B_STOPS', '7'))
CAP = os.environ.get('LOCAL593B_CAP_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = CAP          # ticket cap
_safe = re.sub(r'[^A-Za-z0-9]+', '_', LOCATION)[:40].strip('_')
OUT = os.environ.get('LOCAL593B_OUT', f'/app/tours/LOCAL593B_{_safe}.txt')

print("=== LOCAL-593 r2 isolated live run ===", flush=True)
print(f"location : {LOCATION}", flush=True)
print(f"stops    : {STOPS} (requested)", flush=True)
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${CAP}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

# Cost
try:
    from generate_tour_text import _LAST_GENERATION_COST
    _cost = (_LAST_GENERATION_COST or {}).get('total_cost', 0.0)
    _cache_hit = (_LAST_GENERATION_COST or {}).get('cache_hit', False)
except Exception:
    _cost, _cache_hit = 0.0, False

print("\n================ RESULT ================", flush=True)
if not text:
    print(f"OUTCOME: NO TOUR TEXT (clean-fail or block) after {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE, _LAST_TOUR_KIND
        print(f"  tour_kind : {_LAST_TOUR_KIND}", flush=True)
        print(f"  evidence  : {_LAST_CLEAN_FAIL_EVIDENCE}", flush=True)
    except Exception as e:
        print(f"  evidence unavailable: {e}", flush=True)
else:
    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    print(f"OUTCOME: TOUR DELIVERED — {len(text)} chars, {len(titles)} stops", flush=True)
    print("STOP TITLES:", flush=True)
    for m in titles:
        print(f"   {m.strip()[:120]}", flush=True)

    # ---- BLOCKER 3 content-QA gate (mirror the current service wiring) ----
    print("\n================ BLOCKER 3 (content-QA factual gate) ================", flush=True)
    try:
        import content_qa_runner
        # Build venue_context exactly as generate_tour_text_service does now:
        # venue_tokens (resolver-derived) + city/region/artist/tier. No
        # sibling_venues (r1 #1 reverted in r2).
        _loc_parts = LOCATION.split(',')
        _venue_name_raw = _loc_parts[0].strip()
        _city_raw = _loc_parts[1].strip() if len(_loc_parts) > 1 else ''
        _region_raw = _loc_parts[2].strip() if len(_loc_parts) > 2 else ''
        _venue_tokens = set(w.lower() for w in re.split(r'[\s\-]+', _venue_name_raw) if len(w) >= 3)
        try:
            from generate_tour_text import _LAST_VERIFICATION_TIER
        except Exception:
            _LAST_VERIFICATION_TIER = ''
        _vctx = {
            'venue_tokens': _venue_tokens, 'city': _city_raw, 'region': _region_raw,
            'artist': '', 'tier': _LAST_VERIFICATION_TIER or '',
        }
        print(f"  venue_context.venue_tokens = {sorted(_vctx['venue_tokens'])}", flush=True)
        content_qa_runner.PASS_COUNT = 0
        content_qa_runner.FAIL_COUNT = 0
        content_qa_runner.FACTUAL_FAIL_COUNT = 0
        try:
            content_qa_runner.run_qa(text, venue_context=_vctx)
        except SystemExit:
            pass
        print(f"  BLOCKER 3 line 1 — PASS checks:          {content_qa_runner.PASS_COUNT}", flush=True)
        print(f"  BLOCKER 3 line 2 — style FAIL checks:    {content_qa_runner.FAIL_COUNT}", flush=True)
        print(f"  BLOCKER 3 line 3 — FACTUAL FAIL checks:  {content_qa_runner.FACTUAL_FAIL_COUNT}", flush=True)
    except Exception as _qa_e:
        print(f"  content-QA gate error: {_qa_e}", flush=True)

print(f"\nCOST/TIME: total_cost=${_cost:.4f}  cache_hit={_cache_hit}  wall_time={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
