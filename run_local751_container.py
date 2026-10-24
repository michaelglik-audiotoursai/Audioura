#!/usr/bin/env python3
"""run_local751_container.py — LOCAL-751 live acceptance (ISOLATED container).

Four FRESH tours in ONE disposable container (name: local751-gen, --rm, spare
port; NEVER an audioura-* service container):

  1. EXHIBIT MUSEUM  — "The Salem Witch Museum, Salem MA" (4 stops). 0 catalogued
     works, but a reachable site that names its exhibits → must GENERATE (tier
     exhibit_museum), not clean-fail.
  2. EXHIBIT MUSEUM  — "Salem Museum of Torture, Salem MA" (4 stops). Same shape.
  3. WALKING + NAMED — "Walking tour in Danvers, MA including Witchcraft Victims
     Memorial" (4 stops). The area must parse to Danvers, MA (clause cut) and the
     named memorial must be KEPT if it verifies or ANNOUNCED if not — never
     silently dropped.
  4. ART MUSEUM (REGRESSION) — "Isabella Stewart Gardner Museum, Boston"
     (4 stops). Unchanged behaviour: a catalogued art museum still generates.

For each arm: the delivered stop list, the VERBATIM Orientation opening, the
verification tier, $ and seconds. Rows stored additive is_test=true, lat/lng
NULL. Row counts before/after. No DELETE (D141). Budget ≤ $1.50 for the whole
task, enforced by a RESERVE GATE before each arm.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-751')
except Exception as _meter_err:
    print(f"[LOCAL-751] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import re
import socket
import time

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
_os.environ['COST_HARD_LIMIT_USD'] = '1.50'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
# The existence gate must DROP fabricated stops and KEEP real ones — run it in
# enforce so the named-place policy (kept when verified / announced when not) is
# exercised live.
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'enforce')
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')

HARD_CAP_USD = 1.50
RESERVE_USD = 0.40          # start an arm only if spend + 0.40 <= cap
HOST = socket.gethostname()

ARMS = [
    ("SALEMWITCH", "The Salem Witch Museum, Salem MA", "museum", 4),
    ("TORTURE", "Salem Museum of Torture, Salem MA", "museum", 4),
    ("DANVERS", "Walking tour in Danvers, MA including Witchcraft Victims Memorial",
     "walking", 4),
    ("GARDNER", "Isabella Stewart Gardner Museum, Boston", "museum", 4),
]

# [LOCAL-751] Optional arm subset (comma-separated slugs) for a cheap verification
# re-run, e.g. LOCAL751_ARMS=DANVERS,GARDNER. Default: all four.
_arm_filter = (_os.environ.get('LOCAL751_ARMS') or '').strip()
if _arm_filter:
    _want = {s.strip().upper() for s in _arm_filter.split(',') if s.strip()}
    ARMS = [a for a in ARMS if a[0] in _want]

print("=== LOCAL-751 isolated live run (exhibit museums + named place + Gardner) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}  "
      f"cache_off=1 pool_off=1 gate=enforce", flush=True)

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
        # Fall back to the first non-empty narrative line after Stop 1.
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
        name = f"LOCAL-751 {location.split(',')[0][:40]} {slug} {int(time.time())}"
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
                 f"LOCAL-751 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_arm(slug, location, tour_type, stops):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] arm={slug} spend_so_far="
          f"${spend if spend is not None else '?'} + reserve ${RESERVE_USD} "
          f"vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return (slug, None, 'SKIPPED_CAP', None, None, None, 0.0, 0.0)
    print(f"=== [{slug}] generating: {location!r} ({stops} stops, {tour_type}) ===",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL751_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None, None, None, 0.0, time.time() - t0)
    elapsed = time.time() - t0
    _tier = getattr(_g, '_LAST_VERIFICATION_TIER', '') or ''
    if not text:
        # A clean-fail/refusal returns no text. Report the tier + evidence so the
        # exhibit-museum case is unambiguous if it refuses.
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

    # Named-place announcement (DANVERS arm) — print verbatim if present.
    try:
        _np = list(getattr(_g, '_LAST_NAMED_PLACE_ANNOUNCEMENTS', []) or [])
        if _np:
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
        print(f"LOCAL751_TOUR_ID_{slug}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL751_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return (slug, nid, 'DELIVERED', opening, _tier, delivered, tour_cost, elapsed)


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
_SPEND_BASELINE = _host_spend() or 0.0
print(f"[db] paid_api_calls spend baseline for host {HOST}: ${_SPEND_BASELINE:.4f} "
      f"(this run is measured RELATIVE to this)", flush=True)

results = []
for _slug, _loc, _tt, _n in ARMS:
    results.append(_run_arm(_slug, _loc, _tt, _n))

_run_spend = _spend_so_far()
_abs_spend = _host_spend()
print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] THIS RUN spend (host {HOST}): ${_run_spend if _run_spend is not None else '?'} "
      f"(cap ${HARD_CAP_USD}); host cumulative now ${_abs_spend if _abs_spend is not None else '?'}",
      flush=True)
print("=== LOCAL-751 run complete ===", flush=True)
for _slug, _id, _outcome, _opening, _tier, _delivered, _cost, _secs in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"tier={_tier!r} stops={_delivered} cost=${_cost if _cost else 0.0:.4f} "
          f"secs={_secs:.1f}", flush=True)
    if _opening:
        print(f"RESULT {_slug} ORIENTATION: {_opening}", flush=True)
