"""run_local603_preflight.py — LOCAL-603 (D618) live acceptance (ISOLATED container).

Runs TWO single-venue requests through the REAL generation path and reports the
MEASURED preflight cost per call (grounded requests, search queries, dollars):

  1. WNDR Museum, Boston, MA (7 stops)  → EXPECT the `venue_closed` refusal.
     Prints the clean-fail JSON and the preflight cost line.
  2. Griffin Museum of Photography, Winchester, MA (5 stops) → still DELIVERS.
     Prints the preflight cost and the `Tour total:`.

The preflight runs inside generate_tour_text via venue_preflight.safe_preflight,
which flows through story_leads.gemini_with_sources(grounded=True) — so the
LOCAL-594 grounding meter counts it. We reset the meter immediately before each
generation and read it immediately after, then isolate the preflight's own share
by also reading the meter right after the preflight runs is not possible across
the call boundary; instead the WNDR run (which gates BEFORE any other grounded
call) measures the preflight in isolation, and we price it with cost_rates.

Usage (inside the isolated container, name local603-gen):
    python3 run_local603_preflight.py
"""
import json
import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # tour-OUTPUT cache off
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('COST_HARD_LIMIT_USD', '1.00')   # per-tour OpenAI cap

from generate_tour_text import generate_tour_text  # noqa: E402
import story_leads  # noqa: E402
from cost_rates import grounding_query_cost  # noqa: E402

GIT_SHA = (open('/app/.git_sha').read().strip()
           if os.path.exists('/app/.git_sha') else '?')


def _preflight_meter_snapshot():
    return (story_leads.get_grounding_requests(),
            story_leads.get_grounding_queries())


def _run(label, location, stops):
    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}", flush=True)
    print(f"location : {location}", flush=True)
    print(f"stops    : {stops} (requested)", flush=True)
    print(f"git_sha  : {GIT_SHA}", flush=True)

    # Reset the grounding meter so the figure we read reflects THIS generation.
    story_leads.reset_grounding_requests()

    # Measure the preflight in isolation by calling it directly FIRST (its answer
    # is cached for 7 days, so the subsequent generate_tour_text run reads the
    # cache and does not pay a second time — proving the "about $0.02–0.05" claim).
    import venue_preflight as vpf
    _city = ','.join(p.strip() for p in location.split(',')[1:]).strip()
    _venue = location.split(',')[0].strip()
    _pf_t0 = time.time()
    pf = vpf.safe_preflight(_venue, _city)
    _pf_dt = time.time() - _pf_t0
    pf_reqs, pf_qs = _preflight_meter_snapshot()
    pf_cost = grounding_query_cost(pf_qs)
    print(f"\n--- PREFLIGHT (measured) ---", flush=True)
    print(f"  status      : {pf.get('status')}", flush=True)
    print(f"  hours        : {pf.get('hours') or '(none)'}", flush=True)
    print(f"  admission    : {pf.get('admission') or '(none)'}", flush=True)
    print(f"  highlights   : {len(pf.get('current_exhibitions_or_highlights') or [])}", flush=True)
    print(f"  grounding sources: {len(pf.get('grounding_sources') or [])}", flush=True)
    print(f"  PREFLIGHT COST: requests={pf_reqs} queries={pf_qs} "
          f"${pf_cost:.4f}  ({_pf_dt:.1f}s)", flush=True)

    g = vpf.gate(_venue, _city, pf)
    if g:
        print(f"  GATE: {g['error_code']} — {g['message']}", flush=True)

    # Now the full generation path (reads the cached preflight; its gate, if any,
    # fires and refuses before any further spend).
    out = f"/app/tours/LOCAL603_{re.sub(r'[^A-Za-z0-9]+', '_', _venue)[:30]}.txt"
    t0 = time.time()
    text, out_file, _ = generate_tour_text(location, 'museum', out, stops)
    elapsed = time.time() - t0

    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cost = (_LAST_GENERATION_COST or {}).get('total_cost', 0.0)
        _tour_total = (_LAST_GENERATION_COST or {}).get('tour_total_cost', _cost)
        _grounding_cost = (_LAST_GENERATION_COST or {}).get('grounding_cost', 0.0)
    except Exception:
        _cost = _tour_total = _grounding_cost = 0.0

    print(f"\n--- GENERATION RESULT ---", flush=True)
    if not text:
        print(f"OUTCOME: NO TOUR TEXT (refusal/block) after {elapsed:.1f}s", flush=True)
        try:
            from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
            print("CLEAN-FAIL EVIDENCE JSON:", flush=True)
            print(json.dumps(_LAST_CLEAN_FAIL_EVIDENCE, ensure_ascii=False, indent=2),
                  flush=True)
        except Exception as e:
            print(f"  evidence unavailable: {e}", flush=True)
    else:
        titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
        print(f"OUTCOME: TOUR DELIVERED — {len(text)} chars, {len(titles)} stops", flush=True)
        _m1 = re.search(r'(?ms)^\s*Stop\s+1\s*[:\-].*?(?=^\s*Stop\s+2\s*[:\-]|\Z)', text)
        print("\n--- STOP 1 (opening section) ---", flush=True)
        print((_m1.group(0).strip()[:1200] if _m1 else "(Stop 1 not found)"), flush=True)

    print(f"\nTour total: ${_tour_total:.4f}  (OpenAI=${_cost:.4f} "
          f"grounding=${_grounding_cost:.4f})  wall={elapsed:.1f}s", flush=True)
    return {'label': label, 'text': bool(text),
            'preflight_requests': pf_reqs, 'preflight_queries': pf_qs,
            'preflight_cost': pf_cost, 'tour_total': _tour_total}


results = []
results.append(_run("RUN 1 — WNDR (expect venue_closed)",
                    "WNDR museum, Boston, MA", 7))
results.append(_run("RUN 2 — Griffin (expect delivery)",
                    "Griffin Museum of Photography, Winchester, MA", 5))

# ---- venue_preflight_cache row count ----
print(f"\n{'=' * 70}\nDB ROWS (venue_preflight_cache)\n{'=' * 70}", flush=True)
try:
    import venue_preflight as vpf
    db_url = os.environ.get('DATABASE_URL')
    print(f"  venue_preflight_cache rows: {vpf.cache_row_count(db_url)}", flush=True)
except Exception as e:
    print(f"  cache row-count unavailable: {e}", flush=True)

print(f"\n{'=' * 70}\nSUMMARY — measured preflight cost per call\n{'=' * 70}", flush=True)
for r in results:
    print(f"  {r['label']}", flush=True)
    print(f"      preflight: requests={r['preflight_requests']} "
          f"queries={r['preflight_queries']} ${r['preflight_cost']:.4f}", flush=True)
    print(f"      tour_total=${r['tour_total']:.4f}  "
          f"delivered={r['text']}", flush=True)
