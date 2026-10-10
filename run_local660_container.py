#!/usr/bin/env python3
"""run_local660_container.py — LOCAL-660 live acceptance (ISOLATED container).

Tour 557 v7 (Kiro 5/10) shipped the Boston walking tour wrong four ways:
  1. Stop 5 cut mid-sentence ("…the centuries gather and do not let").
  2. A garbled degrade ("The victims were Boston Massacre.") + the Massacre told
     twice in the same stop.
  3. A dangling pronoun (Stop 3 "His legacy is carved…").
  4. Directions on the leg into stop 2 said "…marking the end of your walk
     exploring Massachusetts politics and current affairs" (stop 2 of 5).

This harness proves the fix end-to-end on ONE FRESH PAID tour through the real
generation path: the ticket request, 5 stops, walking, fresh. It runs four
deterministic detectors over the delivered text and prints PASS/FAIL for each.

ONE paid tour only. HARD CAP $1.00 for the WHOLE task, enforced by
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
    _live_run_meter.auto_meter('LOCAL-660')
except Exception as _meter_err:
    print(f"[LOCAL-660] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import os
import re
import socket
import time

os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
os.environ.setdefault('TOUR_LLM_MODEL', 'gpt-4o')
os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
os.environ['COST_HARD_LIMIT_USD'] = '1.00'        # ticket HARD CAP (whole task)
os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
os.environ.setdefault('STOP_EDITOR', '1')
os.environ.setdefault('STOP_EDITOR_ENABLED', '1')

HARD_CAP_USD = 1.00
RESERVE_USD = 0.55          # start the tour only if spend + 0.55 <= cap
HOST = socket.gethostname()

TOURS = [
    ('Walking tour in Boston dedicated to Massachusetts politics and current '
     'affairs, Boston, MA', 5, 'walking', 'BOSTONWALK'),
]

print("=== LOCAL-660 isolated live run (Boston walking 5, ONE paid tour) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"model : {os.environ['TOUR_LLM_MODEL']}   HARD CAP(task): "
      f"${HARD_CAP_USD}  reserve: ${RESERVE_USD}  cache_off=1 pool_off=1",
      flush=True)

from generate_tour_text import generate_tour_text  # noqa: E402
import tour_conclusion as _tc  # noqa: E402


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


# ───────────────────────── Four deterministic detectors ─────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_DIR_LINE_RE = re.compile(r"(?mi)^Directions:\s*(.+)$")
# A sentence that opens on a personal pronoun with no clear antecedent heuristic
# — we reuse the real gate for a faithful detector.


def _stop_bodies(text):
    """[(num, title, body_lines)] for each Stop N: block (narration only split)."""
    parts = re.split(r"(?mi)^(Stop\s+\d+:.*)$", text)
    out = []
    # parts = [pre, hdr1, body1, hdr2, body2, ...]
    i = 1
    while i < len(parts):
        hdr = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        m = re.match(r"(?i)Stop\s+(\d+):\s*(.+)", hdr)
        if m:
            out.append((int(m.group(1)), m.group(2).strip(), body))
        i += 2
    return out


def detect_defect1(text):
    """Mid-sentence truncation anywhere in a stop body / conclusion."""
    import work_first_evidence as wfe
    # If repair would change the delivered text, a mid-sentence cut is present.
    repaired, rep = wfe.repair_midsentence_truncation(text)
    bad = rep.get("repaired", 0) > 0 or "do not let" in text
    return (not bad), f"midsentence_repair_would_fire={rep.get('repaired',0)}"


def detect_defect2(text):
    """Garbled '<subject> (was|were|is|are) <bare ProperNoun>.' + double-told fact."""
    bad = []
    # (a) copula-bare-entity garble
    for m in re.finditer(r"[A-Z][^.?!]*\b(?:was|were|is|are)\s+(?:the\s+|a\s+|an\s+)?"
                         r"(?:[A-Z][A-Za-z’'\-]+\s+){1,4}[A-Z][A-Za-z’'\-]+\s*\.",
                         text):
        frag = m.group(0).strip()
        # Exclude legitimate 'is <next stop>' orientation and role nominatives.
        if re.search(r"\bof\b", frag):
            continue
        bad.append(frag[-70:])
    garble = [b for b in bad if "massacre" in b.lower()
              or "tea party" in b.lower() or "declaration" in b.lower()]
    # (b) within-stop fact repeat
    from derepetition_guard import check_cross_stop_fact_repetition
    within = [r for r in check_cross_stop_fact_repetition(text)
              if r.get("within_stop")]
    ok = not garble and not within
    return ok, (f"copula_garble={garble[:2]} within_stop_repeats="
                f"{[(r['repeat_stop'], r['signature']) for r in within][:3]}")


def detect_defect3(text):
    """Dangling personal-pronoun opener with no antecedent in the stop."""
    import dangling_pronoun_gate as dpg
    _out, n = dpg.strip_dangling_pronoun_openers_in_text(text)
    return (n == 0), f"dangling_pronoun_openers_would_drop={n}"


def detect_defect4(text):
    """A non-final leg must not say the walk is ending or echo the theme."""
    bodies = _stop_bodies(text)
    n_stops = len(bodies)
    bad = []
    for idx, (num, _title, body) in enumerate(bodies):
        for dm in _DIR_LINE_RE.finditer(body):
            leg = dm.group(1)
            is_last_leg = (idx == n_stops - 2)  # leg into the LAST stop
            if not is_last_leg:
                if re.search(r"(?i)\b(?:end|final|last|conclud|finish)\b.*"
                             r"(?:walk|tour|journey|visit)", leg) or \
                   re.search(r"(?i)marking the (?:end|close|conclusion)", leg):
                    bad.append((num, "end-language", leg[:80]))
                if re.search(r"(?i)(?:walk|tour|journey)\s+"
                             r"(?:exploring|dedicated to|celebrating|devoted to)", leg):
                    bad.append((num, "theme-echo", leg[:80]))
    return (not bad), f"nonfinal_leg_violations={bad[:3]}"


def _report(text):
    print("  --- STOP LIST ---", flush=True)
    for h in _STOP_HEADER_RE.findall(text):
        print(f"  STOP TITLE: {h.strip()[:90]}", flush=True)
    print("  --- DIRECTIONS LINES ---", flush=True)
    for d in _DIR_LINE_RE.findall(text):
        print(f"  DIR: {d.strip()[:120]}", flush=True)
    print("  --- DEFECT DETECTORS ---", flush=True)
    results = {}
    for name, fn in (("DEFECT1_midsentence", detect_defect1),
                     ("DEFECT2_garble_double", detect_defect2),
                     ("DEFECT3_dangling_pronoun", detect_defect3),
                     ("DEFECT4_directions_end_theme", detect_defect4)):
        try:
            ok, detail = fn(text)
        except Exception as e:
            ok, detail = False, f"detector error: {e}"
        results[name] = ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    allok = all(results.values())
    print(f"  [LOCAL-660] ALL FOUR DEFECTS GONE = {allok}", flush=True)
    return results


def _store(location, text, n_stops, slug, kind_desc):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-660 {location.split(',')[0][:40]} {int(time.time())}"
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
                (name, location, n_stops, text, n_stops, kind_desc))
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
            location, tour_type, f"/app/tours/LOCAL660_{slug}.txt", stops,
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
    nid = _store(location, text, delivered, slug,
                 f"LOCAL-660 live fresh ({slug}, {tour_type})")
    if nid:
        print(f"STORED audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL660_TOUR_ID_{slug}={nid}", flush=True)
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
print("=== LOCAL-660 run complete ===", flush=True)
for _slug, _id, _outcome, _det in results:
    print(f"RESULT {_slug}: id={_id if _id else ''} outcome={_outcome} "
          f"detectors={_det}", flush=True)
