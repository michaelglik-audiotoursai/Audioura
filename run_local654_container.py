#!/usr/bin/env python3
"""run_local654_container.py — LOCAL-654 live verification (ISOLATED container).

Two FRESH tours through the REAL generation path with the cheap arm **ON**
(``NARRATION_MODEL=gpt-4.1-mini RESEARCH_BACKEND=serper PARALLEL_STOPS=1``),
cache + pool OFF — the exact arm whose logs produced the mid-clause collisions
(597 Uffizi, 599 Art Institute of Chicago). With the splitter fix (commit on
this branch) the welded ``depths.Thousands`` / ``complete it.Leonardo`` boundary
is split at its root, so no sentence-removing gate can weld a mid-clause
collision.

  1. Uffizi Gallery, Florence              3 stops  ON
  2. The Art Institute of Chicago, Chicago 3 stops  ON

Per tour we report: delivered stop count, wall time, the mid-clause collisions
found in the delivered SPOKEN text (the "…into Thousands…" shape — expected
NONE), the lightweight structural detectors, the tour's own cost, and the spend
from paid_api_calls for THIS host. Each delivered text is stored as ONE additive
is_test row (lat/lng left as inserted; is_test=true), which detectors.py and
critique.sh then score by id. is_test rows are the ONLY rows written. NO DELETE.

HARD CAP **$1.20 COMBINED** (ticket), enforced by tests/live_run_meter.py across
ALL providers, plus a RESERVE GATE before each tour. Row counts printed before
and after. At most TWO tours are started.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-654')
except Exception as _meter_err:
    print(f"[LOCAL-654] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped", flush=True)

import os
import re
import socket
import time

# The cheap arm, ON — the ticket's exact env. Fresh (cache + pool off).
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ['NARRATION_MODEL'] = 'gpt-4.1-mini'    # the ON narrator (welds the space)
os.environ['RESEARCH_BACKEND'] = 'serper'         # ON research backend
os.environ['PARALLEL_STOPS'] = '1'                # ON
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['TEST_GEMINI_MAX_USD'] = '1.20'        # ticket combined cap
os.environ['COST_HARD_LIMIT_USD'] = '1.20'
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 1.20
RESERVE_USD = 0.45        # start a tour only if spend + 0.45 <= cap
HOST = socket.gethostname()

# (location, stops, tour_type, slug)
TOURS = [
    ('Uffizi Gallery, Florence, Italy', 3, 'museum', 'UFFIZI_ON'),
    ('The Art Institute of Chicago, Chicago, Illinois, United States', 3, 'museum', 'AIC_ON'),
]

print("=== LOCAL-654 isolated live verify (Uffizi 3 + AIC 3, cheap arm ON) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"env   : NARRATION_MODEL={os.environ['NARRATION_MODEL']} "
      f"RESEARCH_BACKEND={os.environ['RESEARCH_BACKEND']} "
      f"PARALLEL_STOPS={os.environ['PARALLEL_STOPS']}", flush=True)
print(f"caps  : HARD CAP(combined)=${HARD_CAP_USD}  reserve=${RESERVE_USD}  "
      f"cache_off=1 pool_off=1", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402

# ── The mid-clause collision shape (same as tests/test_local654_...) ──────────
# A lowercase word (3+), one space, a Capitalised real word (2nd letter lower),
# the lowercase word NOT ending on sentence/clause punctuation — the
# "…into Thousands…" / "…complete Leonardo…" weld. We report it on the SPOKEN
# text so the ticket's "report the collisions (none)" is a concrete number.
_COLLISION_RE = re.compile(r"(?<![.!?:,;)\]\"'”’])\b([a-z]{3,})\s([A-Z][a-z]{2,})")
_FIELD_RE = re.compile(
    r"^\s*(Museum Information|Address|Coordinates|Type/Specialty|"
    r"Specific Examples|Operational Details|Tour-Category|Sources)\s*:")
# Capitalised words that legitimately open a clause after a lowercase word
# (prepositional/relative joins): "in Florence", "under Verrocchio". These are
# proper-noun OBJECTS, not dropped-into sentence starts. We still PRINT every
# match so a human can eyeball them; the collision COUNT that matters is the
# "sentence-start weld" one, which the splitter fix removes.


def _spoken(text):
    return "\n".join(l for l in (text or "").split("\n") if not _FIELD_RE.match(l))


def _collisions(text):
    sp = _spoken(text)
    return [(m.group(1), m.group(2), sp[max(0, m.start() - 30):m.end() + 20])
            for m in _COLLISION_RE.finditer(sp)]


def _weld_welds(text):
    """The specific no-space weld the mini model emits and the splitter must have
    killed: a period/!/? directly jammed against a Capital+lowercase, with NO
    space. If any survive in delivered text, the fix did not hold."""
    return re.findall(r"[.!?][A-ZÀ-Ý][a-zà-ÿ]", _spoken(text))


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
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    delivered = _tc.count_delivered_stops(text)
    m = re.search(r"That['\u2019]s\s+(\d+)\s+stops?", text)
    stated = m.group(1) if m else "?"
    runon = bool(re.search(r"(?mi)^Stop\s+\d+:.*\b(?:Address|Coordinates|"
                           r"Orientation|Directions):", text))
    return {"headers": [h.strip()[:70] for h in headers],
            "delivered": delivered, "stated": stated, "runon_header": runon}


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-654 {location.split(',')[0][:40]} {slug} {int(time.time())}"
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
                 f"LOCAL-654 live verify ({slug})"))
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

    print(f"=== generating: {location} ({stops} stops, {tour_type}) "
          f"[{slug}] ON ===", flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL654_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {slug}: {e}", flush=True)
        return (slug, None, f'ERROR:{e}', None)
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME {slug}: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return (slug, None, 'NO_TEXT', None)

    d = _detectors(text)
    cols = _collisions(text)
    welds = _weld_welds(text)
    print(f"OUTCOME {slug}: DELIVERED {len(text)} chars, {d['delivered']} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in d['headers']:
        print(f"  STOP TITLE: {h}", flush=True)
    print(f"  [detectors] delivered={d['delivered']} stated='{d['stated']}' "
          f"runon_header={d['runon_header']}", flush=True)
    print(f"  [LOCAL-654] no-space welds (period jammed to Capital) in spoken "
          f"text: {len(welds)}  {welds[:5]}", flush=True)
    print(f"  [LOCAL-654] mid-clause collision candidates "
          f"(lowercase→Capital, no punctuation): {len(cols)}", flush=True)
    for lw, cap, ctx in cols:
        print(f"      · '{lw} {cap}'  …{ctx.strip()}…", flush=True)
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
        print(f"  LOCAL654_TOUR_ID_{slug}={nid}", flush=True)
    return (slug, nid, 'DELIVERED',
            {"wall_s": round(elapsed, 1), "tour_cost": tour_cost,
             "welds": len(welds), "collisions": len(cols), **d})


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
print("=== LOCAL-654 run complete ===", flush=True)
for _slug, _id, _outcome, _m in results:
    _extra = ""
    if _m:
        _extra = (f" wall={_m['wall_s']}s cost=${_m['tour_cost']} "
                  f"stops={_m['delivered']} welds={_m['welds']} "
                  f"collisions={_m['collisions']}")
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome}{_extra}",
          flush=True)
