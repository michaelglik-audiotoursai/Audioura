"""run_local599b_massart.py — LOCAL-599B r2 live acceptance (ISOLATED container).

Runs `MassArt Art Museum, Boston, MA`, 7 stops, through the REAL generation path
on the r2 branch. MassArt has NO Wikidata item of its own, so this exercises:
  * LOCAL-599 Wikidata-independent official-site discovery (→ maam.massart.edu),
  * LOCAL-599B exhibition extraction that follows /exhibition/<slug> detail links
    from the /exhibitions index (NOT the home page's 'Make with MAAM' program),
    fills to N current-first (current exhibitions → named spaces → upcoming →
    past), and
  * the D611 opening section (About + address + hours-with-days + admission),
    folded into Stop 1 by the stop-pool orchestrator's first-tour branch.

The generator routes through stop_pool_orchestrator.maybe_generate_with_pool
automatically (STORIED_MODE=true + DATABASE_URL set + empty pool for this venue),
which is the ONLY path that folds the opening section — the r1 runner's gap.

Reports: site-discovery lines + tier, the 7 stop titles EACH WITH ITS SOURCE URL,
Stop 1's opening section in full, the BLOCKER 3 lines, Tour total, wall time, and
the venue_corpus / stop_pool row counts for this venue.

Usage (inside the isolated container, name local599b-gen):
    python3 run_local599b_massart.py
"""

# [LOCAL-613] Meter + cap this isolated run. auto_meter installs the per-task
# TEST_GEMINI_MAX_USD cap (default $1.00, ALL providers combined) at the grounding
# counter and writes ONE cost_ledger row (user_id='LOCAL-599B', description='test run')
# at process exit — even if the cap or any error stops the run. One line; every
# future harness should do the same.
import os as _os613  # noqa: E402
import sys as _sys613  # noqa: E402
_sys613.path.insert(0, _os613.path.join(
    _os613.path.dirname(_os613.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter  # noqa: E402
    _live_run_meter.auto_meter('LOCAL-599B')
except Exception as _meter_err:  # metering must never break a run
    print(f"[LOCAL-613] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")
import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # tour-OUTPUT cache off
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '2.00'        # ticket cap $2

LOCATION = 'MassArt Art Museum, Boston, MA'
STOPS = 7
OUT = '/app/tours/LOCAL599B_MASSART_RUN.txt'

print("=== LOCAL-599B r2 isolated live run ===", flush=True)
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

print("\n================ RESULT ================", flush=True)
print(f"TIER: {_LAST_VERIFICATION_TIER}", flush=True)
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

    # ---- Stop titles, each with its source URL (D611) ----
    print("\nSTOP TITLES + SOURCE URLS:", flush=True)
    # Map a delivered title to the site-first source URL recorded during generation.
    _src_by_name = {s['name'].strip().lower(): s for s in (_SF_SOURCES or [])}
    for m in titles:
        _t = m.strip()
        # strip the "Stop N:" prefix for lookup
        _name = re.sub(r'(?i)^\s*stop\s+\d+\s*[:\-]\s*', '', _t).strip()
        _rec = _src_by_name.get(_name.lower())
        if _rec:
            print(f"   {_t[:90]}", flush=True)
            print(f"        source: {_rec['source_url']}  "
                  f"[{_rec['kind']}/{_rec['status']}]", flush=True)
        else:
            print(f"   {_t[:90]}", flush=True)
            print(f"        source: (opening/other — see Sources block)", flush=True)

    if _SF_SOURCES:
        print("\nSITE-FIRST SOURCES (recorded during generation):", flush=True)
        for s in _SF_SOURCES:
            print(f"   - {s['name']}  →  {s['source_url']}  [{s['kind']}/{s['status']}]",
                  flush=True)

    # ---- Stop 1 opening section, in full ----
    print("\n================ STOP 1 (opening section, full) ================", flush=True)
    _m1 = re.search(r'(?ms)^\s*Stop\s+1\s*[:\-].*?(?=^\s*Stop\s+2\s*[:\-]|\Z)', text)
    print(_m1.group(0).strip() if _m1 else "(Stop 1 not found)", flush=True)

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

# ---- DB row counts for this venue ----
print("\n================ DB ROWS (venue_corpus / stop_pool) ================", flush=True)
try:
    import psycopg2
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'postgres-2'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'),
    )
    cur = conn.cursor()
    try:
        cur.execute("SELECT count(*) FROM stop_pool WHERE pool_key ILIKE %s OR venue_identity ILIKE %s",
                    ('%massart%', '%massart%'))
        print(f"  stop_pool (pool_key/venue_identity LIKE %massart%): {cur.fetchone()[0]}", flush=True)
    except Exception as _e:
        print(f"  stop_pool: query error {_e}", flush=True)
        conn.rollback()
    cur.close()
    conn.close()
except Exception as _db_e:
    print(f"  DB row-count unavailable: {_db_e}", flush=True)

print(f"\nTour total: ${_cost:.4f}  cache_hit={_cache_hit}  wall_time={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
