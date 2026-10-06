"""run_local600_massart.py — LOCAL-600 (D616) live acceptance (ISOLATED container).

Runs `MassArt Art Museum, Boston, MA`, 7 stops, through the REAL generation path on
the LOCAL-600 branch, routed through stop_pool_orchestrator.maybe_generate_with_pool
(STORIED_MODE + DATABASE_URL + empty pool for this venue). Proves the two D616
deliverables on live data:

  1. ORDER — each on-view exhibition's stop comes FIRST, immediately followed by
     the stops for its own works (never the r3 works-first order); Stop 1 is a
     show and the orientation names Stop 1's actual title.
  2. SHORTFALL — when verified on-view material can't reach 7, Stop 1's opening
     section carries ONE honest sentence from the real counts (D616).

Reports: site-discovery lines + tier, the stop titles each with its source URL,
Stop 1's opening section in full (so the shortfall sentence + the Stop-1 title are
visible), the BLOCKER 3 three lines, and `Tour total:`.

Usage (inside the isolated container, name local600-gen):
    python3 run_local600_massart.py
"""
import os
import re
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # tour-OUTPUT cache off
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket cap $1.50

LOCATION = 'MassArt Art Museum, Boston, MA'
STOPS = 7
OUT = '/app/tours/LOCAL600_MASSART_RUN.txt'

print("=== LOCAL-600 (D616) isolated live run ===", flush=True)
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
    from generate_tour_text import _LAST_SITE_FIRST_COUNTS as _SF_COUNTS
except Exception:
    _SF_COUNTS = {}

print("\n================ RESULT ================", flush=True)
print(f"TIER: {_LAST_VERIFICATION_TIER}", flush=True)
print(f"SITE-FIRST COUNTS: {_SF_COUNTS}", flush=True)
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
    _src_by_name = {s['name'].strip().lower(): s for s in (_SF_SOURCES or [])}
    for m in titles:
        _t = m.strip()
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

    # ---- Stop 1 opening section, in full (shortfall sentence + Stop-1 title) ----
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
print("\n================ DB ROWS (stop_pool) ================", flush=True)
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
