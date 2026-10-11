#!/usr/bin/env python3
"""run_local674_container.py — LOCAL-674 live A/B (ONE arm per ISOLATED container).

The research-only harness picked serper_plus as the winner on evidence at the
lowest $. This proves it END-TO-END on a FRESH full walking tour through the real
generation path, one arm per container, both launched at the same moment:

    docker run --rm --name local674-gemini      -e ARM=gemini      ...
    docker run --rm --name local674-serper_plus  -e ARM=serper_plus ...

The ONLY difference between the two arms is the WALKING tour research backend:

    ARM=gemini      → WALKING_RESEARCH unset (default): walking stays on grounded
                      Gemini, one request per stop — today's behaviour / baseline.
    ARM=serper_plus → WALKING_RESEARCH=serper_plus: Wikipedia-first + better
                      Serper pages + news-where-relevant + one extractor.

Everything else is held EQUAL and matches the shared stack: CHEAP_ARM_CATEGORIES=
museum (so the museum cheap-arm envs do NOT bleed into this walking tour),
FAST_PIPELINE=1, cache+pool OFF (fresh). Narration is the production walking
default (gpt-4.1) in BOTH arms, so the measured difference is RESEARCH only.

ONE paid tour per container. HARD CAP $0.70 per arm, enforced by
tests/live_run_meter.py + a reserve gate. The delivered SPOKEN tour is stored as
ONE additive is_test row (critique.sh / detectors read it). is_test rows are the
ONLY rows written. No DELETE. Reports stops, Gemini grounding requests, $ (r5)
and seconds; the LEAD/this harness then runs critique.sh and detectors on the id.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-674')
except Exception as _meter_err:
    print(f"[LOCAL-674] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped", flush=True)

import re
import socket
import time

ARM = _os.environ.get('ARM', 'gemini').strip()

# ── held-equal settings (match the shared stack) ──────────────────────────────
_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'   # FRESH
_os.environ['DISABLE_STOP_POOL'] = '1'    # FRESH
_os.environ.setdefault('FAST_PIPELINE', '1')
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EDITOR', '1')
# Keep the museum cheap-arm envs from bleeding into this walking tour; walking is
# NOT in the list, so RESEARCH_BACKEND/NARRATION_MODEL do not apply to it.
_os.environ.setdefault('CHEAP_ARM_CATEGORIES', 'museum')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.70')
_os.environ['COST_HARD_LIMIT_USD'] = '0.70'

# ── the ONE varying knob ──────────────────────────────────────────────────────
if ARM == 'serper_plus':
    _os.environ['WALKING_RESEARCH'] = 'serper_plus'
elif ARM == 'gemini_per_venue':
    _os.environ['WALKING_RESEARCH'] = 'gemini_per_venue'
else:
    ARM = 'gemini'
    _os.environ.pop('WALKING_RESEARCH', None)   # default: unchanged Gemini

HARD_CAP_USD = 0.70
RESERVE_USD = 0.50
HOST = socket.gethostname()

REQUEST = ('Walking tour in Boston dedicated to Massachusetts politics and '
           'historic civic buildings, Boston, MA')
STOPS = 5
SLUG = f'BOSTONWALK_{ARM.upper()}'

print(f"=== LOCAL-674 live A/B — ARM={ARM} (ONE paid walking tour) ===", flush=True)
print(f"host: {HOST}  request: {REQUEST!r}  stops: {STOPS}", flush=True)
print(f"WALKING_RESEARCH={_os.environ.get('WALKING_RESEARCH', '(unset=gemini)')}  "
      f"CHEAP_ARM_CATEGORIES={_os.environ.get('CHEAP_ARM_CATEGORIES')}  "
      f"cache_off pool_off  cap ${HARD_CAP_USD}", flush=True)

import story_leads as _sl  # noqa: E402
from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")


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


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host=%s",
                (HOST,))
    return float(v) if v is not None else None


def _store(text, delivered):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-674 {ARM} Boston walking {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO audio_tours
                     (tour_name, request_string, number_requested, tour_content,
                      stops_count, creator_type, storied_mode, is_test, track,
                      tour_kind, description)
                   VALUES (%s,%s,%s,%s,%s,'Test',true,true,'beta','full',%s)
                   RETURNING id""",
                (name, REQUEST, STOPS, text, delivered,
                 f"LOCAL-674 live A/B arm={ARM} (walking research)"))
            nid = cur.fetchone()[0]
        conn.close(); return nid
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def main():
    print(f"[db] is_test rows BEFORE: "
          f"{_scalar('SELECT count(*) FROM audio_tours WHERE is_test=true')}",
          flush=True)
    print(f"[db] spend for host {HOST} BEFORE: ${_spend_so_far()}", flush=True)

    spend = _spend_so_far()
    if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
        print(f"[reserve-gate] SKIP: spend ${spend} + ${RESERVE_USD} > cap "
              f"${HARD_CAP_USD}", flush=True)
        return
    try:
        _sl.reset_grounding_requests()
    except Exception:
        pass
    print(f"  research_backend()={_sl.research_backend()}  "
          f"walking_research_backend()={_sl.walking_research_backend()!r}  "
          f"pv_selected={_sl.walking_gemini_per_venue_selected()}", flush=True)

    t0 = time.time()
    try:
        text, _p, _c = generate_tour_text(
            REQUEST, 'walking', f"/app/tours/LOCAL674_{SLUG}.txt", STOPS,
            user_id=None)
    except Exception as e:
        print(f"RUN ERROR: {e}", flush=True)
        return
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in _STOP_HEADER_RE.findall(text):
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    try:
        greq = _sl.get_grounding_requests(); gq = _sl.get_grounding_queries()
        print(f"  [GROUNDING] Gemini grounding requests this tour: {greq} "
              f"(queries {gq})", flush=True)
    except Exception:
        pass
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        _tot = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"  [cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(text, delivered)
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL674_TOUR_ID_{ARM}={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL674_{SLUG}_delivered.txt", 'w',
                  encoding='utf-8') as df:
            df.write(text)
    except Exception:
        pass
    print(f"[db] spend for host {HOST} AFTER: ${_spend_so_far()}", flush=True)
    print(f"=== LOCAL-674 arm={ARM} complete ===", flush=True)


if __name__ == '__main__':
    main()
