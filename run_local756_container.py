#!/usr/bin/env python3
"""run_local756_container.py — LOCAL-756 live acceptance (ISOLATED container).

Runs inside a DISPOSABLE container (name: local756-gen, --rm, spare port; NEVER
an audioura-* service container). Arms, in order:

  1. SALEMWITCH_FRESH — "The Salem Witch Museum, Salem MA" (4 stops), cache OFF,
     pool OFF. Must GENERATE (tier exhibit_museum), not clean-fail. This writes
     the venue_corpus cache row for the next arm.
  2. SALEMWITCH_HIT   — the SAME request, cache ON, pool OFF. The cache HIT path
     must ALSO generate (LOCAL-756 A: candidate list built from the sourced
     exhibit names; junk 'Discounts And Discount Partners' never a stop).
  3. DANVERS          — "Walking tour in Danvers, MA including Witchcraft Victims
     Memorial" (4 stops). We SEED our OWN pool rows (the four field stops, none
     of them the memorial) under a dedicated is_test pool key, then request. The
     pool must NOT serve as-is (LOCAL-756 B): the memorial is generated as a stop
     or ANNOUNCED — never silently dropped. We clean up ONLY our own seeded pool
     rows at the end (never shared rows).
  4. GARDNER          — "Isabella Stewart Gardner Museum, Boston" (4 stops), an
     ART-museum regression: unchanged, still generates.

Rows stored additive is_test=true, lat/lng NULL. No DELETE of audio_tours except
our own is_test rows (we do not delete any here). Budget ≤ $1.50 for the whole
task, enforced by a RESERVE GATE before each arm. Paid calls are written to the
shared meter log via the _meter bootstrap (PAID_API_LOG).
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-756')
except Exception as _meter_err:
    print(f"[LOCAL-756] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import re
import socket
import time

_os.environ['STORIED_MODE'] = 'true'
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
_os.environ['COST_HARD_LIMIT_USD'] = '1.50'
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'enforce')
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')

HARD_CAP_USD = 1.50
RESERVE_USD = 0.40
HOST = socket.gethostname()

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
import generate_tour_text as _g  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=_os.environ.get('DB_PORT', '5432'),
        dbname=_os.environ.get('DB_NAME', 'audiotours'),
        user=_os.environ.get('DB_USER', 'admin'),
        password=_os.environ.get('DB_PASSWORD', 'password123'))


def _db_url():
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return dburl
    return (f"postgresql://{_os.environ.get('DB_USER','admin')}:"
            f"{_os.environ.get('DB_PASSWORD','password123')}@"
            f"{_os.environ.get('DB_HOST','development-postgres-2-1')}:"
            f"{_os.environ.get('DB_PORT','5432')}/"
            f"{_os.environ.get('DB_NAME','audiotours')}")


def _scalar(sql, args=()):
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, args)
            v = cur.fetchone()[0]
        conn.close(); return v
    except Exception as e:
        print(f"  [db] query failed: {e}", flush=True); return None


def _row_count():
    return _scalar("SELECT count(*) FROM audio_tours")


def _test_row_count():
    return _scalar("SELECT count(*) FROM audio_tours WHERE is_test = true")


def _host_spend():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


_SPEND_BASELINE = None


def _spend_so_far():
    cur = _host_spend()
    if cur is None:
        return None
    if _SPEND_BASELINE is None:
        return cur
    return max(0.0, cur - _SPEND_BASELINE)


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_ORIENTATION_RE = re.compile(r"(?mi)^Orientation:\s*(.+)$")


def _titles(text):
    return [t.strip() for t in _STOP_HEADER_RE.findall(text)]


def _orientation_opening(text):
    m = _ORIENTATION_RE.search(text)
    if not m:
        lines = (text or '').split('\n')
        seen = False
        for ln in lines:
            if not seen:
                if re.match(r'^\s*Stop\s+1\b', ln):
                    seen = True
                continue
            s = ln.strip()
            if s and not re.match(r'^(Address|Coordinates|Type/Specialty|'
                                  r'Specific Examples|Directions|GPS Coordinates):', s):
                return s[:400]
        return None
    body = m.group(1).strip()
    sents = re.split(r"(?<=[.!?])\s+", body)
    return " ".join(sents[:3]).strip()


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-756 {location.split(',')[0][:40]} {slug} {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audio_tours
                    (tour_name, request_string, number_requested,
                     tour_content, stops_count, creator_type, storied_mode,
                     is_test, track, tour_kind, description, lat, lng)
                VALUES (%s, %s, %s, %s, %s, 'Test', true, true, 'beta', 'full',
                        %s, NULL, NULL)
                RETURNING id
                """,
                (name, location, n_stops, text, n_stops,
                 f"LOCAL-756 live ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


# ── DANVERS pool seeding (our OWN is_test rows; cleaned up at the end) ─────────
DANVERS_REQUEST = ("Walking tour in Danvers, MA including Witchcraft Victims "
                   "Memorial")
DANVERS_FIELD_STOPS = [
    "The Rebecca Nurse Homestead",
    "Endicott Park",
    "Danvers State Hospital",
    "Danvers Town Hall",
]
_seeded_pool_keys = []


def _seed_danvers_pool():
    """Seed the four field stops into the pool under the current pool key for
    the Danvers request (reproducing tour 736's state), so the delivery gate is
    exercised against a real pool. These are OUR rows and are removed in
    _cleanup_danvers_pool (we never touch shared/production rows)."""
    try:
        import stop_pool_store as pool
        dburl = _db_url()
        identity = pool.resolve_venue_identity(DANVERS_REQUEST)
        key = pool._pool_key(identity, "walking")
        _seeded_pool_keys.append(key)
        conn = pool.psycopg2.connect(dburl); conn.autocommit = True
        pool._ensure_table(conn)
        with conn.cursor() as cur:
            for i, title in enumerate(DANVERS_FIELD_STOPS):
                cur.execute(
                    """
                    INSERT INTO stop_pool
                        (pool_key, title_norm, venue_identity, tour_type,
                         pool_version, title, narration, order_seq)
                    VALUES (%s,%s,%s,'walking',%s,%s,%s,%s)
                    ON CONFLICT (pool_key, title_norm) DO NOTHING
                    """,
                    (key, pool._title_norm(title), identity,
                     pool.POOL_VERSION, title,
                     f"{title}. (seeded LOCAL-756 is_test pool row.)", i))
        conn.close()
        print(f"  [LOCAL-756] seeded {len(DANVERS_FIELD_STOPS)} Danvers pool "
              f"rows under key {key!r} (our own is_test rows)", flush=True)
    except Exception as e:
        print(f"  [LOCAL-756] Danvers pool seed failed ({e})", flush=True)


def _cleanup_danvers_pool():
    try:
        import stop_pool_store as pool
        conn = pool.psycopg2.connect(_db_url()); conn.autocommit = True
        with conn.cursor() as cur:
            for key in _seeded_pool_keys:
                cur.execute("DELETE FROM stop_pool WHERE pool_key = %s", (key,))
                print(f"  [LOCAL-756] cleaned up seeded pool rows for key {key!r}",
                      flush=True)
        conn.close()
    except Exception as e:
        print(f"  [LOCAL-756] Danvers pool cleanup skipped ({e})", flush=True)


def _run_arm(slug, location, tour_type, stops, cache_on=False, pool_on=False):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] arm={slug} spend_so_far="
          f"${spend if spend is not None else '?'} + reserve ${RESERVE_USD} "
          f"vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return (slug, None, 'SKIPPED_CAP', None, None, None, 0.0, 0.0)

    _os.environ['DISABLE_TOUR_CACHE'] = '0' if cache_on else '1'
    _os.environ['DISABLE_STOP_POOL'] = '0' if pool_on else '1'
    print(f"=== [{slug}] generating: {location!r} ({stops} stops, {tour_type}; "
          f"cache_on={cache_on} pool_on={pool_on}) ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL756_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None, None, None, 0.0, time.time() - t0)
    elapsed = time.time() - t0
    _tier = getattr(_g, '_LAST_VERIFICATION_TIER', '') or ''
    if not text:
        _ev = dict(getattr(_g, '_LAST_CLEAN_FAIL_EVIDENCE', {}) or {})
        print(f"OUTCOME [{slug}]: NO TOUR TEXT after {elapsed:.1f}s "
              f"(tier={_tier!r}, clean_fail={_ev})", flush=True)
        return (slug, None, 'NO_TEXT', None, _tier, None, 0.0, elapsed)

    delivered = _tc.count_delivered_stops(text)
    opening = _orientation_opening(text)
    print(f"OUTCOME [{slug}]: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"tier={_tier!r}, wall {elapsed:.1f}s", flush=True)
    print("  --- STOP LIST ---", flush=True)
    for h in _titles(text):
        print(f"  STOP TITLE: {h[:100]}", flush=True)
    print("  --- ORIENTATION OPENING (verbatim) ---", flush=True)
    print(f"  ORIENTATION_OPENING[{slug}]: {opening}", flush=True)

    try:
        _np = list(getattr(_g, '_LAST_NAMED_PLACE_ANNOUNCEMENTS', []) or [])
        for _a in _np:
            print(f"  NAMED_PLACE_ANNOUNCEMENT[{slug}]: {_a}", flush=True)
    except Exception:
        pass

    tour_cost = 0.0
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] {slug} tour_total=${tour_cost:.4f}", flush=True)
    except Exception:
        pass

    nid = _store(location, text, delivered, slug)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true, lat/lng NULL)", flush=True)
        print(f"LOCAL756_TOUR_ID_{slug}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL756_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return (slug, nid, 'DELIVERED', opening, _tier, delivered, tour_cost, elapsed)


print("=== LOCAL-756 isolated live run (Salem fresh+hit, Danvers pool, Gardner) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}", flush=True)
print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
_SPEND_BASELINE = _host_spend() or 0.0
print(f"[db] paid_api_calls spend baseline for host {HOST}: ${_SPEND_BASELINE:.4f}",
      flush=True)

results = []
# 1 + 2: Salem fresh, then cache hit (same request).
results.append(_run_arm("SALEMWITCH_FRESH",
                        "The Salem Witch Museum, Salem MA", "museum", 4,
                        cache_on=False, pool_on=False))
results.append(_run_arm("SALEMWITCH_HIT",
                        "The Salem Witch Museum, Salem MA", "museum", 4,
                        cache_on=True, pool_on=False))
# 3: Danvers with a seeded pool (pool ON so the delivery gate runs).
_seed_danvers_pool()
try:
    results.append(_run_arm("DANVERS", DANVERS_REQUEST, "walking", 4,
                            cache_on=False, pool_on=True))
finally:
    _cleanup_danvers_pool()
# 4: Gardner art-museum regression.
results.append(_run_arm("GARDNER",
                        "Isabella Stewart Gardner Museum, Boston", "museum", 4,
                        cache_on=False, pool_on=False))

_run_spend = _spend_so_far()
_abs_spend = _host_spend()
print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] THIS RUN spend (host {HOST}): "
      f"${_run_spend if _run_spend is not None else '?'} (cap ${HARD_CAP_USD}); "
      f"host cumulative now ${_abs_spend if _abs_spend is not None else '?'}",
      flush=True)
print("=== LOCAL-756 run complete ===", flush=True)
for _slug, _id, _outcome, _opening, _tier, _delivered, _cost, _secs in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"tier={_tier!r} stops={_delivered} cost=${_cost if _cost else 0.0:.4f} "
          f"secs={_secs:.1f}", flush=True)
    if _opening:
        print(f"RESULT {_slug} ORIENTATION: {_opening}", flush=True)
