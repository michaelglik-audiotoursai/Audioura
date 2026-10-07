"""run_local602_wndr.py — LOCAL-602 live acceptance (ISOLATED container).

Runs `WNDR museum, Boston, MA`, 7 stops, through the REAL generation path on the
LOCAL-602 branch. WNDR is a CHAIN with a JavaScript-only site — the exact field
case (tour 397) that shipped a 1-stop "Overview" with NULL coordinates.

Proves the LOCAL-602 deliverables on live data:
  * the branch / site discovery lines (identical-shell detection, branch page,
    sitemap / embedded-JSON / Serper fallbacks);
  * the stop titles, each with its source URL;
  * Stop 1's opening section in full (shortfall sentence + coordinates visible);
  * the coordinates on the delivered stop(s);
  * the BLOCKER 3 three lines;
  * Tour total.

The stop pool is DISABLED so the run needs no Postgres and touches no audioura-*
container. Usage (isolated container named local602-gen):
    python3 run_local602_wndr.py
"""
import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # tour-OUTPUT cache off
os.environ['DISABLE_STOP_POOL'] = '1'             # isolated: no DB, no pool reuse
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '2.00'        # ticket cap $2

LOCATION = 'WNDR museum, Boston, MA'
STOPS = 7
OUT = os.environ.get('LOCAL602_OUT', '/out/LOCAL602_WNDR_RUN.txt')
os.makedirs(os.path.dirname(OUT), exist_ok=True)

print("=== LOCAL-602 isolated live run ===", flush=True)
print(f"location : {LOCATION}", flush=True)
print(f"stops    : {STOPS} (requested)", flush=True)
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}", flush=True)
print(f"git_sha  : {open('/app/.git_sha').read().strip() if os.path.exists('/app/.git_sha') else '?'}", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

try:
    from generate_tour_text import _LAST_GENERATION_COST
    _cost = (_LAST_GENERATION_COST or {}).get('total_cost', 0.0)
    _cache_hit = (_LAST_GENERATION_COST or {}).get('cache_hit', False)
except Exception:
    _cost, _cache_hit = 0.0, False

try:
    from generate_tour_text import _LAST_VERIFICATION_TIER
except Exception:
    _LAST_VERIFICATION_TIER = ''

try:
    from generate_tour_text import _LAST_SITE_FIRST_SOURCES as _SF_SOURCES
except Exception:
    _SF_SOURCES = []

try:
    from generate_tour_text import _LAST_TOUR_KIND
except Exception:
    _LAST_TOUR_KIND = ''

print("\n================ RESULT ================", flush=True)
print(f"TIER: {_LAST_VERIFICATION_TIER}   TOUR_KIND: {_LAST_TOUR_KIND}", flush=True)

if not text:
    print(f"OUTCOME: NO TOUR TEXT (clean-fail or block) after {elapsed:.1f}s", flush=True)
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
        print(f"  tour_kind : {_LAST_TOUR_KIND}", flush=True)
        print(f"  evidence  : {_LAST_CLEAN_FAIL_EVIDENCE}", flush=True)
    except Exception as e:
        print(f"  evidence unavailable: {e}", flush=True)
else:
    titles = re.findall(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text)
    print(f"OUTCOME: TOUR DELIVERED — {len(text)} chars, {len(titles)} stops", flush=True)

    # ---- Stop titles, each with its source URL ----
    print("\nSTOP TITLES + SOURCE URLS:", flush=True)
    _src_by_name = {s['name'].strip().lower(): s for s in (_SF_SOURCES or [])}
    for _t in titles:
        _t = _t.strip()
        _name = re.sub(r'(?i)^\s*stop\s+\d+\s*[:\-]\s*', '', _t).strip()
        _rec = _src_by_name.get(_name.lower())
        print(f"   {_t[:100]}", flush=True)
        if _rec:
            print(f"        source: {_rec['source_url']}  [{_rec['kind']}/{_rec['status']}]", flush=True)

    if _SF_SOURCES:
        print("\nSITE-FIRST SOURCES (recorded during generation):", flush=True)
        for s in _SF_SOURCES:
            print(f"   - {s['name']}  →  {s['source_url']}  [{s['kind']}/{s['status']}]", flush=True)

    # ---- Stop 1 opening section (coordinates + shortfall sentence visible) ----
    print("\n================ STOP 1 (opening section, full) ================", flush=True)
    _m1 = re.search(r'(?ms)^\s*Stop\s+1\s*[:\-].*?(?=^\s*Stop\s+2\s*[:\-]|\Z)', text)
    print(_m1.group(0).strip() if _m1 else "(Stop 1 not found)", flush=True)

    # ---- Coordinates on every delivered stop ----
    print("\n================ COORDINATES ================", flush=True)
    _coord_lines = re.findall(r'(?mi)^Coordinates:\s*(-?\d+\.?\d*\s*,\s*-?\d+\.?\d*)\s*$', text)
    print(f"  Coordinates: lines found: {len(_coord_lines)} / {len(titles)} stop(s)", flush=True)
    for c in _coord_lines:
        print(f"    {c}", flush=True)
    if not _coord_lines:
        print("    (none — would be the field defect; see tour text)", flush=True)

    # ---- BLOCKER 3 content-QA gate ----
    print("\n================ BLOCKER 3 (content-QA factual gate) ================", flush=True)
    try:
        import content_qa_runner
        _loc_parts = LOCATION.split(',')
        _venue_name_raw = _loc_parts[0].strip()
        _city_raw = _loc_parts[1].strip() if len(_loc_parts) > 1 else ''
        _region_raw = _loc_parts[2].strip() if len(_loc_parts) > 2 else ''
        _venue_tokens = set(w.lower() for w in re.split(r'[\s\-]+', _venue_name_raw) if len(w) >= 3)
        _vctx = {
            'venue_tokens': _venue_tokens, 'city': _city_raw, 'region': _region_raw,
            'artist': '', 'tier': _LAST_VERIFICATION_TIER or '',
        }
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

print(f"\nTour total: ${_cost:.4f}  cache_hit={_cache_hit}  wall_time={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
