#!/usr/bin/env python3
"""run_local744_verify_salem.py — LOCAL-744 single-arm VERIFICATION re-run.

After the first live run showed the model guessing the WRONG filming place for
the TV series *Salem* ("Salem, Massachusetts") and the fail-closed corroboration
(correctly) refusing it, the lookup was changed to DERIVE the filming place
directly from the work's Wikipedia article ("It was filmed in Shreveport,
Louisiana"). This single-arm run re-verifies the headline case end to end,
against the real model + real Wikipedia, within the remaining task budget.

Salem only — "the episode 1 of season 1 biking tour, Salem, MA" (5 stops). The
Orientation MUST now OPEN with "...filmed in Shreveport, Louisiana, not in
Salem...". Rows additive is_test=true, lat/lng NULL. No DELETE (D141). Spend is
measured relative to a baseline captured at start; capped at $0.45 for THIS run.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-744')
except Exception as _meter_err:
    print(f"[LOCAL-744] live_run_meter unavailable ({_meter_err})")

import re
import socket
import time

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.45')
_os.environ['COST_HARD_LIMIT_USD'] = '0.45'
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'enforce')
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')

HARD_CAP_USD = 0.45
HOST = socket.gethostname()
ARM = ("SALEM", "the episode 1 of season 1 biking tour, Salem, MA", "biking", 5)

print("=== LOCAL-744 single-arm VERIFY (Salem, biking, 5 stops) ===", flush=True)
print(f"host: {HOST}  cap(this run): ${HARD_CAP_USD}  cache_off pool_off gate=enforce",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


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


_ORIENTATION_RE = re.compile(r"(?mi)^Orientation:\s*(.+)$")
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")


def _orientation_opening(text):
    m = _ORIENTATION_RE.search(text)
    if not m:
        return None
    body = m.group(1).strip()
    sents = re.split(r"(?<=[.!?])\s+", body)
    return " ".join(sents[:2]).strip()


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-744 {location.split(',')[0][:40]} {slug} {int(time.time())}"
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
                 f"LOCAL-744 verify fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


_before = _scalar("SELECT count(*) FROM audio_tours")
_before_test = _scalar("SELECT count(*) FROM audio_tours WHERE is_test=true")
_spend_base = float(_scalar(
    "SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host=%s", (HOST,)) or 0.0)
print(f"[db] rows BEFORE: {_before} (is_test {_before_test}); "
      f"spend baseline host {HOST}: ${_spend_base:.4f}", flush=True)

slug, location, tour_type, stops = ARM
t0 = time.time()
text, _p, _c = generate_tour_text(
    location, tour_type, f"/app/tours/LOCAL744_VERIFY_{slug}.txt", stops, user_id=None)
elapsed = time.time() - t0

if not text:
    print(f"OUTCOME [{slug}]: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
    _sys.exit(1)

delivered = _tc.count_delivered_stops(text)
opening = _orientation_opening(text)
print(f"OUTCOME [{slug}]: DELIVERED — {len(text)} chars, {delivered} stops, "
      f"{elapsed:.1f}s", flush=True)
print("  --- STOP LIST ---", flush=True)
for h in _STOP_HEADER_RE.findall(text):
    print(f"  STOP TITLE: {h.strip()[:100]}", flush=True)
print("  --- ORIENTATION OPENING (verbatim) ---", flush=True)
print(f"  ORIENTATION_OPENING[{slug}]: {opening}", flush=True)
low = (text or '').lower()
print(f"  ORIENTATION_STATES_FILMING: {('filmed in' in low) or ('could not confirm where' in low)}",
      flush=True)
print(f"  SAYS_SHREVEPORT: {'shreveport' in low}", flush=True)

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
    print(f"STORED audio_tours id = {nid} (is_test=true, lat/lng NULL)", flush=True)
    print(f"LOCAL744_TOUR_ID_{slug}={nid}", flush=True)
try:
    with open(f"/app/tours/LOCAL744_VERIFY_{slug}_delivered.txt", "w",
              encoding="utf-8") as _df:
        _df.write(text)
except Exception:
    pass

_after = _scalar("SELECT count(*) FROM audio_tours")
_after_test = _scalar("SELECT count(*) FROM audio_tours WHERE is_test=true")
_spend_now = float(_scalar(
    "SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host=%s", (HOST,)) or 0.0)
print(f"[db] rows AFTER: {_after} (is_test {_after_test}); "
      f"THIS RUN spend: ${max(0.0, _spend_now - _spend_base):.4f} "
      f"(cap ${HARD_CAP_USD})", flush=True)
print(f"RESULT {slug}: id={nid} outcome=DELIVERED "
      f"cost=${tour_cost:.4f} secs={elapsed:.1f}", flush=True)
print(f"RESULT {slug} ORIENTATION: {opening}", flush=True)
print("=== LOCAL-744 verify complete ===", flush=True)
