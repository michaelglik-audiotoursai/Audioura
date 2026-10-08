#!/usr/bin/env python3
"""run_local626_container.py — LOCAL-626 live acceptance (ISOLATED container).

Runs AT MOST TWO FRESH 3-stop museum tours through the REAL generation path with
the LOCAL-626 branch code in the image, metered + HARD-CAPPED at $1.20 COMBINED
(all providers, via tests/live_run_meter.py):

    1. The Courtauld Gallery, London, United Kingdom   (3 stops; cache AND pool OFF)
    2. Museo del Prado, Madrid, Spain                  (3 stops; fresh, never generated)

HARD CAP, ENFORCED (not merely reported): before STARTING each tour the harness
reads the meter's combined spend; once it is at/over $1.20 the next tour is NOT
started. During a tour the LiveRunMeter grounding-cap guard raises the instant
combined spend reaches $1.20, so a single tour cannot overrun the budget either.

Every delivered tour is stored as an additive is_test row in ``audio_tours``
(creator_type='Test', is_test=true) so ``critique.sh <id> 3`` scores the SAME
spoken text. The is_test rows are the ONLY rows written. No DELETE.

Usage (inside the isolated container):
    python3 run_local626_container.py
"""
# [LOCAL-613] Meter + cap this isolated run (install BEFORE importing generators).
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

CAP_USD = 1.20

import live_run_meter as _lrm  # noqa: E402
# Build the meter ourselves (not auto_meter) so we can read combined_spend_usd()
# BETWEEN tours and refuse to start a new tour once we are at/over the cap.
_METER = _lrm.LiveRunMeter("LOCAL-626", cap_usd=CAP_USD, install_cap=True)

import os  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
import atexit  # noqa: E402

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tours (no cache HIT)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool OFF (item requirement)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = str(CAP_USD)
os.environ['TEST_GEMINI_MAX_USD'] = str(CAP_USD)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STORY_PREFS', '1')

# At most two tours; Courtauld first (the ticket venue), then one other famous
# never-generated museum (Prado).
VENUES = [
    ("The Courtauld Gallery, London, United Kingdom", 3, 'COURTAULD'),
    ("Museo del Prado, Madrid, Spain", 3, 'PRADO'),
]

print("=== LOCAL-626 isolated live run (<=2 FRESH museums, 3 stops each) ===",
      flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP (combined): "
      f"${CAP_USD:.2f}   cache=OFF pool=OFF", flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import generate_tour_text as _gtt  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


def _conn():
    import psycopg2
    dburl = os.environ.get('DATABASE_URL')
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'development-postgres-2-1'),
        port=os.environ.get('DB_PORT', '5432'),
        dbname=os.environ.get('DB_NAME', 'audiotours'),
        user=os.environ.get('DB_USER', 'admin'),
        password=os.environ.get('DB_PASSWORD', 'password123'))


def _row_count(where=""):
    try:
        conn = _conn()
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audio_tours" + (" " + where if where else ""))
            n = cur.fetchone()[0]
        conn.close()
        return n
    except Exception as e:
        print(f"  [db] row count failed: {e}", flush=True)
        return None


# ── item checks on the delivered SPOKEN text ─────────────────────────────────
def _item_report(text, venue_first):
    out = []
    # Item 1: no stop whose title IS the venue itself.
    stop_titles = re.findall(r"(?mi)^Stop\s+\d+\s*[:\-]\s*(.+?)\s*$", text)
    venue_stop = [t for t in stop_titles
                  if t.strip().lower().rstrip('.').endswith(venue_first.lower())
                  and len(t.split()) <= 3]
    out.append(("item1 venue-as-stop", venue_stop))
    out.append(("item1 stop titles", stop_titles))
    # Item 3: no second-person recruitment copy.
    recruit = re.findall(r"(?i)you'll learn|forge a career|study in the heart of|"
                         r"world-renowned (?:programmes|specialists)", text)
    out.append(("item3 recruitment copy", recruit))
    # Item 5: no 'this ... panel' on a non-picture object; no obvious date clash
    panel = re.findall(r"(?i)this\s+\w+\s+panel\b", text)
    out.append(("item5 object-type bleed", panel))
    # Admission/hours line (item 2 already shipped; report what is spoken)
    hours = re.findall(r"(?mi)^.*\bopen\b.*$", text)[:1]
    adm = re.findall(r"(?mi)^.*\badmission\b.*$|.*\bStandard admission\b.*", text)[:1]
    out.append(("hours line", hours))
    out.append(("admission line", adm))
    return out


def _store_tour(location, text, n_stops, slug):
    try:
        conn = _conn()
        conn.autocommit = True
        name = f"LOCAL-626 {location.split(',')[0]} {int(time.time())}"
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
                 f"LOCAL-626 live fresh ({slug})"))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True)
        return None


def _run_one(location, stops, out_file, slug):
    venue_first = location.split(',')[0].replace('The ', '').split()[0]
    print(f"\n=== generating: {location} ({stops} stops) ===", flush=True)
    t0 = time.time()
    try:
        text, _out_path, _coords = generate_tour_text(
            location, 'museum', out_file, stops, user_id=None)
    except Exception as e:
        print(f"RUN ERROR for {location}: {type(e).__name__}: {e}", flush=True)
        return None
    elapsed = time.time() - t0
    if not text:
        print(f"OUTCOME: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None
    delivered = _tc.count_delivered_stops(text)
    print(f"OUTCOME: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    print(f"[LOCAL-626 item checks on spoken text] — {location}", flush=True)
    for label, hits in _item_report(text, venue_first):
        if label in ("item1 stop titles", "hours line", "admission line"):
            print(f"  {label}: {hits}", flush=True)
        else:
            status = "CLEAN" if not hits else f"FOUND {hits}"
            print(f"  {label}: {status}", flush=True)
    try:
        _c = dict(_gtt._LAST_GENERATION_COST or {})
        _tot = float(_c.get('tour_total_cost', _c.get('total_cost', 0.0)) or 0.0)
        print(f"[cost] tour_total=${_tot:.4f}", flush=True)
    except Exception:
        pass
    new_id = _store_tour(location, text, delivered, slug)
    if new_id:
        print(f"STORED audio_tours id = {new_id}  (is_test=true)", flush=True)
        print(f"LOCAL626_TOUR_ID={new_id}", flush=True)
    return new_id


# Record ONE ledger row + print the meter summary at process exit even if the cap
# stops us mid-run.
def _finalize():
    if not _METER._recorded:
        try:
            _METER.add_generation(_gtt)
        except Exception:
            pass
        try:
            _METER.record()
        finally:
            print(_METER.summary(), flush=True)
            _METER.uninstall()
atexit.register(_finalize)


_before = _row_count()
_before_test = _row_count("WHERE is_test=true")
print(f"[db] audio_tours row count BEFORE: total={_before} is_test={_before_test}",
      flush=True)

ids = []
for location, stops, slug in VENUES:
    spend = _METER.combined_spend_usd()
    print(f"\n[CAP] combined spend so far ${spend:.4f} / cap ${CAP_USD:.2f}",
          flush=True)
    if spend >= CAP_USD:
        print(f"[CAP] HARD CAP REACHED (${spend:.4f} >= ${CAP_USD:.2f}) — NOT "
              f"starting '{location}'. Stopping.", flush=True)
        break
    tid = _run_one(location, stops, f"/app/tours/LOCAL626_{slug}.txt", slug)
    # fold this tour's measured spend into the meter before deciding on the next
    try:
        _METER.add_generation(_gtt)
    except Exception:
        pass
    if tid:
        ids.append(tid)

_after = _row_count()
_after_test = _row_count("WHERE is_test=true")
print(f"\n[db] audio_tours row count AFTER:  total={_after} is_test={_after_test}",
      flush=True)
print(f"[db] rows added: total +{(_after or 0) - (_before or 0)}  "
      f"is_test +{(_after_test or 0) - (_before_test or 0)}", flush=True)
print(f"[CAP] final combined spend ${_METER.combined_spend_usd():.4f} / "
      f"cap ${CAP_USD:.2f}  cap_hit={_METER.capped}", flush=True)
print("=== LOCAL-626 run complete ===", flush=True)
print(f"LOCAL626_TOUR_IDS={','.join(str(i) for i in ids)}", flush=True)
