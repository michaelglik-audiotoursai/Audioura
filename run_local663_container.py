#!/usr/bin/env python3
"""run_local663_container.py — LOCAL-663 live acceptance (ISOLATED container).

Two defects from tour 557 v10 (Kiro 6.5) / live tour 649:
  1. "The victims were Boston Massacre." — the tragedy-context composer
     back-filled an EVENT (and a date fragment) as if it were a victim, a false
     copula LOCAL-660's degrade guard never saw because this is a different path.
  2. Faneuil Hall Stop 4 (1837 Lovejoy meeting) shipped "in late 1837, the hall
     hosted another turning point. The outcry in the hall was immediate." with
     the event itself gone — a removal pass dropped the event sentence and left
     its cataphoric lead-in and its backward consequence dangling.

This harness proves the fixes end-to-end on ONE FRESH PAID tour through the real
generation path: the same Boston "Massachusetts politics and current affairs"
WALKING request, 5 stops, fresh, NORMAL arm (no NARRATION_MODEL /
RESEARCH_BACKEND override). It runs deterministic detectors over the delivered
text and prints PASS/FAIL, then reports stops and spend.

ONE paid tour only. HARD CAP $0.60 for the WHOLE task, enforced by
tests/live_run_meter.py plus a RESERVE GATE before the tour. The delivered SPOKEN
text is stored as ONE additive is_test row. is_test rows are the ONLY rows
written. No DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-663')
except Exception as _meter_err:
    print(f"[LOCAL-663] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import re
import socket
import time

# NORMAL ARM: no NARRATION_MODEL, no RESEARCH_BACKEND override.
_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.60')
_os.environ['COST_HARD_LIMIT_USD'] = '0.60'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EDITOR', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 0.60
RESERVE_USD = 0.40          # start the tour only if spend + 0.40 <= cap
HOST = socket.gethostname()

TOURS = [
    ('Walking tour in Boston dedicated to Massachusetts politics and current '
     'affairs, Boston, MA', 5, 'walking', 'BOSTONWALK'),
]

print("=== LOCAL-663 isolated live run (Boston walking 5, ONE paid tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"NORMAL ARM  HARD CAP(task): ${HARD_CAP_USD}  reserve: ${RESERVE_USD}  "
      f"cache_off=1 pool_off=1", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=_os.environ.get('DB_HOST', 'postgres-2'),
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


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


# ───────────────────────── Two deterministic detectors ──────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")

# Bug 1: "<plural subject> (were|are) <EventName>." — a copula equating a subject
# with a capitalised EVENT. The exact shipped shape plus the general one.
_VICTIMS_WERE_EVENT = re.compile(
    r'\bThe\s+victims\s+were\s+(?:the\s+)?[A-Z][\w’\'-]+(?:\s+[A-Z][\w’\'-]+)*\s*\.',
)
_COPULA_BARE_EVENT = re.compile(
    r'\b(?:victims|those\s+killed|the\s+dead|the\s+fallen|they)\s+(?:were|are)\s+'
    r'(?:the\s+)?(?:[A-Z][\w’\'-]+\s+){0,3}'
    r'(?:Massacre|War|Riot|Battle|Party|Uprising|Revolt|Siege)\b',
)

# Bug 2: a cataphoric LEAD-IN or a reaction CONSEQUENCE with no event told in
# the same stop. We detect an ORPHAN: a stop body that contains "another turning
# point" / "a pivotal moment" OR "The outcry/response ... was immediate" but
# that names no concrete event (meeting/murder/speech/vote/protest/riot) nearby.
_LEAD_ORPHAN = re.compile(
    r'\b(?:another|a|the)\s+(?:great\s+|defining\s+|pivotal\s+|dramatic\s+)*'
    r'(?:turning\s+point|pivotal\s+moment|defining\s+moment|watershed)\b', re.I)
_CONSEQUENCE_ORPHAN = re.compile(
    r'\bThe\s+(?:immediate\s+|public\s+|ensuing\s+)*'
    r'(?:outcry|outrage|response|reaction|backlash|uproar)\b', re.I)
# An actual event being told (so the lead-in / consequence is grounded).
_EVENT_TOLD = re.compile(
    r'\b(meeting|assembly|gathering|convened|convention|rally|speech|address|'
    r'spoke|debate|vote|voted|petition|murder|killed|assassinat\w*|riot|'
    r'protest|demonstrat\w*|arrest\w*|trial|resolution|declared|signed|'
    r'passed|abolition\w*|Lovejoy|Phillips|Garrison)\b', re.I)


def _stop_bodies(text):
    """Yield (title, body) per stop (body = text until the next Stop header)."""
    parts = re.split(r"(?mi)^(Stop\s+\d+:.*)$", text)
    # parts: [pre, header1, body1, header2, body2, ...]
    out = []
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ''
        out.append((header, body))
    return out


def detect_bug1_victims_copula(text):
    """No 'The victims were <Event>.' / plural-subject copula equating people
    with a capitalised event name anywhere in the delivered text."""
    hits = []
    for m in _VICTIMS_WERE_EVENT.finditer(text):
        # Accept a REAL person list ("The victims were Crispus Attucks, ...");
        # reject when the predicate is a known event head-word.
        seg = m.group(0)
        if re.search(r'\b(Massacre|War|Riot|Battle|Party|Uprising|Revolt|'
                     r'Siege|Tragedy|Affair|Incident)\b', seg):
            hits.append(seg.strip())
    hits += [m.group(0).strip() for m in _COPULA_BARE_EVENT.finditer(text)]
    return (not hits), f"copula_event_hits={hits}"


def detect_bug2_orphan_leadin(text):
    """No stop whose body teases 'another turning point' / 'The outcry …' with
    no actual event told in the same stop."""
    orphans = []
    for header, body in _stop_bodies(text):
        has_lead = bool(_LEAD_ORPHAN.search(body))
        has_cons = bool(_CONSEQUENCE_ORPHAN.search(body))
        if (has_lead or has_cons) and not _EVENT_TOLD.search(body):
            orphans.append(header[:60])
    return (not orphans), f"orphan_stops={orphans}"


def _report(text):
    print("  --- STOP LIST ---", flush=True)
    for h in _STOP_HEADER_RE.findall(text):
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    print("  --- DEFECT DETECTORS ---", flush=True)
    results = {}
    for name, fn in (("BUG1_victims_were_event", detect_bug1_victims_copula),
                     ("BUG2_orphan_leadin_or_consequence",
                      detect_bug2_orphan_leadin)):
        try:
            ok, detail = fn(text)
        except Exception as e:
            ok, detail = False, f"detector error: {e}"
        results[name] = ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    allok = all(results.values())
    print(f"  [LOCAL-663] BOTH DEFECTS GONE = {allok}", flush=True)
    return results


def _store(location, text, n_stops, slug):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-663 {location.split(',')[0][:40]} {int(time.time())}"
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
                 f"LOCAL-663 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _run_one(location, stops, tour_type, slug):
    spend = _spend_so_far()
    print(f"\n[reserve-gate] spend_so_far=${spend if spend is not None else '?'} "
          f"+ reserve ${RESERVE_USD} vs cap ${HARD_CAP_USD}", flush=True)
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP {slug}: would exceed cap", flush=True)
        return None, 'SKIPPED_CAP', None
    print(f"=== generating: {location} ({stops} stops, {tour_type}) ===",
          flush=True)
    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            location, tour_type, f"/app/tours/LOCAL663_{slug}.txt", stops,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {e}", flush=True)
        return None, f'ERROR:{e}', None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None, 'NO_TEXT', None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    results = _report(text)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(location, text, delivered, slug)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL663_TOUR_ID_{slug}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL663_{slug}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return nid, 'DELIVERED', results


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

results = []
for _loc, _stops, _ttype, _slug in TOURS:
    _id, _outcome, _det = _run_one(_loc, _stops, _ttype, _slug)
    results.append((_slug, _id, _outcome, _det))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print("=== LOCAL-663 run complete ===", flush=True)
for _slug, _id, _outcome, _det in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"detectors={_det}", flush=True)
