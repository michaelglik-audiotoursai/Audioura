#!/usr/bin/env python3
"""run_local653_container.py — LOCAL-653 live verification (ISOLATED container).

TWO FRESH Courtauld tours through the REAL generation path, cache + pool OFF, to
confirm the site-candidate guards: the venue, a sibling institution ("Courtauld
Institute") and a bare artist name ("Paul Cézanne") must NOT be stops, and a
marketing prefix ("Van Gogh's iconic …") must be stripped from the stop title.

  1. The Courtauld, 3 stops, fresh  (run 1)
  2. The Courtauld, 3 stops, fresh  (run 2)

For each tour we report: delivered stop count, wall time, the stop titles, the
LOCAL-653 detectors — venue_as_stop (MUST pass: no stop title is the venue or a
sibling institution), artist_name_as_stop (no stop title is a bare artist name),
marketing_prefix_in_title (no stop title carries a possessive-artist prefix) —
the tour's own cost, and spend from paid_api_calls for this host. Each delivered
SPOKEN text is stored as ONE additive is_test row for critique.sh / detectors.py.
is_test rows are the ONLY rows written. No DELETE.

HARD CAP $1.50 COMBINED (ticket), enforced by tests/live_run_meter.py across ALL
providers, plus a RESERVE GATE before each tour. Row counts printed before/after.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-653')
except Exception as _meter_err:
    print(f"[LOCAL-653] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

# Fresh tours, storied mode, cache + pool off (ticket requirement).
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.50')
os.environ['COST_HARD_LIMIT_USD'] = '1.50'
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 1.50
RESERVE_USD = 0.55        # start a tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

VENUE = 'The Courtauld Gallery, London, United Kingdom'
# (location, stops, tour_type, slug)
TOURS = [
    (VENUE, 3, 'museum', 'COURTAULD_1'),
    (VENUE, 3, 'museum', 'COURTAULD_2'),
]

print("=== LOCAL-653 isolated live verification (Courtauld 3 stops, fresh, x2) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(combined): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402
from site_candidate_guard import (  # noqa: E402
    is_venue_or_sibling_title, is_artist_name_alone, strip_marketing_prefix,
    venue_core_name)

# The venue's known artists (used only to flag a bare-artist stop title in the
# detector; the generator derives its own set from SPARQL at run time).
_KNOWN_ARTISTS = [
    'Paul Cézanne', 'Georges Seurat', 'Edgar Degas', 'Édouard Manet',
    'Vincent van Gogh', 'Pierre-Auguste Renoir', 'Paul Gauguin',
    'Peter Paul Rubens', 'Sandro Botticelli', 'Amedeo Modigliani',
]


def _conn():
    import psycopg2
    dburl = os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'postgres-2'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))


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


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


def _detectors(text):
    headers = [h.strip() for h in re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)]
    delivered = _tc.count_delivered_stops(text)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    # LOCAL-653 detectors on the DELIVERED stop titles.
    venue_as_stop = [h for h in headers if is_venue_or_sibling_title(h, VENUE)]
    artist_as_stop = [h for h in headers
                      if is_artist_name_alone(h, _KNOWN_ARTISTS)]
    marketing_titles = []
    for h in headers:
        clean, artist = strip_marketing_prefix(h)
        if clean != h:
            marketing_titles.append((h, clean, artist))
    return {
        "headers": [h[:70] for h in headers],
        "delivered": delivered, "stated": stated,
        "venue_as_stop_PASS": not venue_as_stop,
        "venue_as_stop_offenders": venue_as_stop,
        "artist_name_as_stop_PASS": not artist_as_stop,
        "artist_as_stop_offenders": artist_as_stop,
        "marketing_prefix_PASS": not marketing_titles,
        "marketing_offenders": marketing_titles,
    }


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-653 {location.split(',')[0][:40]} {slug} {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audio_tours
                    (tour_name, request_string, number_requested,
                     tour_content, stops_count, creator_type, storied_mode,
                     is_test, track, tour_kind, description)
                VALUES (%s, %s, %s, %s, %s, 'Test', true, true, 'beta', 'full', %s)
                RETURNING id
                """,
                (name, location, n_stops, text, n_stops,
                 f"LOCAL-653 live verification ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one(location, stops, tour_type, slug):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap "
              f"(${spend:.4f}+${RESERVE_USD} > ${HARD_CAP_USD})", flush=True)
        return (slug, None, 'SKIPPED_CAP', None)

    print(f"=== generating: {location} ({stops} stops, {tour_type}) [{slug}] ===",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL653_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None)
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME {slug}: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return (slug, None, 'NO_TEXT', None)

    d = _detectors(text)
    print(f"OUTCOME {slug}: DELIVERED {len(text)} chars, {d['delivered']} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in d['headers']:
        print(f"  STOP TITLE: {h}", flush=True)
    print(f"  [LOCAL-653 detectors] venue_as_stop_PASS={d['venue_as_stop_PASS']} "
          f"(offenders={d['venue_as_stop_offenders']})", flush=True)
    print(f"  [LOCAL-653 detectors] artist_name_as_stop_PASS="
          f"{d['artist_name_as_stop_PASS']} "
          f"(offenders={d['artist_as_stop_offenders']})", flush=True)
    print(f"  [LOCAL-653 detectors] marketing_prefix_PASS="
          f"{d['marketing_prefix_PASS']} (offenders={d['marketing_offenders']})",
          flush=True)
    tour_cost = None
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"  [cost] tour_total=${tour_cost:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, d['delivered'], slug)
    if nid:
        print(f"  STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"  LOCAL653_TOUR_ID_{slug}={nid}", flush=True)
    return (slug, nid, 'DELIVERED', {"wall_s": round(elapsed, 1),
                                     "tour_cost": tour_cost, **d})


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _ttype, _slug in TOURS:
    results.append(_run_one(_loc, _stops, _ttype, _slug))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-653 run complete ===", flush=True)
for _slug, _id, _outcome, _m in results:
    _extra = ""
    if _m:
        _extra = (f" wall={_m['wall_s']}s cost=${_m['tour_cost']} "
                  f"stops={_m['delivered']} venue_as_stop_PASS={_m['venue_as_stop_PASS']} "
                  f"artist_PASS={_m['artist_name_as_stop_PASS']} "
                  f"marketing_PASS={_m['marketing_prefix_PASS']}")
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}{_extra}",
          flush=True)
