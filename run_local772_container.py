#!/usr/bin/env python3
"""run_local772_container.py — LOCAL-772 isolated live check (D716 retired-model fix).

ONE fresh 2-stop tour through the REAL generation path to prove that with
TOUR_LLM_MODEL unset (as in the subscribed container) no runtime call sends the
retired gpt-3.5-turbo. Success bar from the ticket:

  * the log shows NO ``404`` and NO ``deprecated``
  * fact sheets N/N (every selected stop gets a sheet)
  * budget <= $0.30 (enforced by tests/live_run_meter.py, plus a reserve gate)
  * audio_tours row count unchanged (this run does NOT write — read-only count
    before and after)

Runs in its OWN container (local772-tg) on a spare port; never touches an
audioura-* container. No INSERT, no DELETE.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-772')
except Exception as _meter_err:
    print(f"[LOCAL-772] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped", flush=True)

import os
import re
import socket
import time

# Mirror the subscribed tour-generator env, EXCEPT leave TOUR_LLM_MODEL UNSET —
# that is the whole point: the retired-model fallback path must now resolve live.
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['DISABLE_STOP_POOL'] = '1'
os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.30')
os.environ['COST_HARD_LIMIT_USD'] = '0.30'
os.environ.pop('TOUR_LLM_MODEL', None)   # explicit: unset, as in the container

HARD_CAP_USD = 0.30
RESERVE_USD = 0.25        # start the tour only if spend + 0.25 <= cap
HOST = socket.gethostname()

LOCATION = 'Watertown City Hall, Watertown MA'
STOPS = 2
TOUR_TYPE = 'walking'

print("=== LOCAL-772 isolated live check (Watertown City Hall, 2 stops) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : TOUR_LLM_MODEL={os.environ.get('TOUR_LLM_MODEL', '(unset)')}  "
      f"NARRATION_MODEL={os.environ.get('NARRATION_MODEL')}  "
      f"TOUR_STORY_MODEL={os.environ.get('TOUR_STORY_MODEL')}  "
      f"HARD CAP ${HARD_CAP_USD}", flush=True)

# Sanity: the resolvers must not resolve to a retired model with env unset.
import llm_models as _m
from llm_fallback import RETIRED_MODELS
_checks = {
    'check_model()': _m.check_model(),
    'write_model(site_default=gpt-3.5-turbo)': _m.write_model(site_default='gpt-3.5-turbo'),
    'held_model(gpt-3.5-turbo, IS_RESTAURANT_MODEL)': _m.held_model('gpt-3.5-turbo', site_env='IS_RESTAURANT_MODEL'),
}
for _label, _val in _checks.items():
    print(f"[resolver] {_label} -> {_val}", flush=True)
    assert _val not in RETIRED_MODELS, f"{_label} resolved to RETIRED {_val}"
print("[resolver] all resolve to live models (env unset) OK", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402


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


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


before = _row_count()
print(f"[db] audio_tours row count BEFORE: {before}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

spend = _spend_so_far()
if spend is not None and (spend + RESERVE_USD) > HARD_CAP_USD:
    print(f"[reserve-gate] ABORT: spend ${spend:.4f} + reserve ${RESERVE_USD} "
          f"> cap ${HARD_CAP_USD}", flush=True)
    _sys.exit(2)

print(f"=== generating: {LOCATION} ({STOPS} stops, {TOUR_TYPE}) ===", flush=True)
t0 = time.time()
outcome = 'UNKNOWN'
text = None
try:
    text, _p, _c = generate_tour_text(
        LOCATION, TOUR_TYPE, '/tmp/LOCAL772_watertown.txt', STOPS,
        user_id=None)
    outcome = 'DELIVERED' if text else 'NO_TEXT'
except Exception as e:
    outcome = f'ERROR:{e}'
    print(f"RUN ERROR: {e}", flush=True)
elapsed = time.time() - t0

if text:
    headers = re.findall(r"(?mi)^Stop\s+\d+:\s*(.+)$", text)
    print(f"OUTCOME: DELIVERED {len(text)} chars, {len(headers)} stop headers, "
          f"wall {elapsed:.1f}s", flush=True)
    for h in headers:
        print(f"  STOP TITLE: {h.strip()[:70]}", flush=True)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tour_cost = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"  [cost] tour_total=${tour_cost:.4f}", flush=True)
    except Exception:
        pass
else:
    print(f"OUTCOME: {outcome} after {elapsed:.1f}s", flush=True)

after = _row_count()
print(f"[db] audio_tours row count AFTER: {after}", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_spend_so_far()}",
      flush=True)
print(f"[db] audio_tours DELTA: {None if (before is None or after is None) else after - before} "
      f"(expected 0 — this run does not write)", flush=True)
print("=== LOCAL-772 run complete ===", flush=True)
