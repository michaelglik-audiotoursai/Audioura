#!/usr/bin/env python3
"""run_local599_container.py — LOCAL-599 live acceptance (ISOLATED container).

Runs `MassArt Art Museum, Boston, MA`, 7 stops, through the REAL generation path
with the LOCAL-599 branch code. MassArt has NO Wikidata item of its own; this
run exercises the new Wikidata-independent official-site discovery + the existing
site-first (exhibit_museum) path.

Reports: the site-discovery lines + tier, the 7 stop titles, the BLOCKER 3 lines,
Stop 1's opening section in full, Tour total, wall time, and the
venue_corpus / stop_pool row counts for this venue (the only DB writes allowed).

Usage (inside the isolated container):
    python3 run_local599_container.py
"""
import os
import re
import sys
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # tour-OUTPUT cache off
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '2.00'        # ticket cap $2

LOCATION = 'MassArt Art Museum, Boston, MA'
STOPS = 7
OUT = '/app/tours/LOCAL599_MASSART_RUN.txt'

print("=== LOCAL-599 isolated live run ===", flush=True)
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
    print("STOP TITLES:", flush=True)
    for m in titles:
        print(f"   {m.strip()[:120]}", flush=True)

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

# ---- DB row counts for this venue (the only writes allowed) ----
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
    for tbl, pat in (('venue_corpus', '%massart%'), ('venue_corpus', '%maam%')):
        try:
            cur.execute(f"SELECT count(*) FROM {tbl} WHERE lower(venue_name) LIKE %s", (pat,))
            print(f"  {tbl} LIKE {pat}: {cur.fetchone()[0]}", flush=True)
        except Exception as _e:
            print(f"  {tbl} LIKE {pat}: query error {_e}", flush=True)
            conn.rollback()
    try:
        cur.execute("SELECT count(*) FROM stop_pool WHERE lower(venue_name) LIKE %s", ('%massart%',))
        print(f"  stop_pool LIKE %massart%: {cur.fetchone()[0]}", flush=True)
    except Exception as _e:
        print(f"  stop_pool: query error {_e}", flush=True)
        conn.rollback()
    cur.close()
    conn.close()
except Exception as _db_e:
    print(f"  DB row-count unavailable: {_db_e}", flush=True)

print(f"\nTour total: ${_cost:.4f}  cache_hit={_cache_hit}  wall_time={elapsed:.1f}s", flush=True)
print(f"OUT: {out_file}", flush=True)
