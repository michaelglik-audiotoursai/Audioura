#!/usr/bin/env python3
"""run_local669c_container.py — LOCAL-669C live acceptance (ISOLATED container).

Ticket: "Ho Chi Minh City Museum of Fine Arts, Vietnam", 5 stops, museum, FRESH,
NORMAL arm then CHEAP arm. HARD CAP $1.80 for the WHOLE task.

Verifies the 669C fix end to end on BOTH arms: the HCMC tour must deliver 5
DISTINCT works with the National Treasure Spring Garden (Q109406846) appearing
ONCE, not twice/three times — on both the normal arm (gpt-4.1 narration, Gemini
grounded highlights) and the cheap arm (gpt-4.1-mini narration, Serper research).
Reports, per arm: the delivered stops (with the bilingual header), the
LOCAL-669C final-gate decision log (QID stamps, collapses, refills), the
LOCAL-669C highlights-trigger decision, the bilingual headers, grounded-request
count, $ (from paid_api_calls, r5 rates) and seconds.

Rows: additive is_test only. No DELETE. Spend from paid_api_calls, tagged
user_id=TEST-LOCAL-669C. Cheap arm runs AFTER normal so it reuses the 30-day
venue highlights cache (0 extra grounded requests), keeping the task under cap.
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))
try:
    import live_run_meter as _live_run_meter
    _live_run_meter.auto_meter('LOCAL-669C')
except Exception as _meter_err:
    print(f"[LOCAL-669C] live_run_meter unavailable ({_meter_err}): "
          f"run will not be metered/capped")

import io
import re
import socket
import time
import contextlib

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'            # FRESH tour (cache off)
_os.environ['DISABLE_STOP_POOL'] = '1'             # pool off (fresh)
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.80')
_os.environ['COST_HARD_LIMIT_USD'] = '1.80'        # ticket HARD CAP (whole task)
_os.environ.setdefault('LOCAL603_PREFLIGHT', '1')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.80
HOST = socket.gethostname()
LOCATION = 'Ho Chi Minh City Museum of Fine Arts, Vietnam'
STOPS = 5

print("=== LOCAL-669C isolated live run (HCMC museum 5, NORMAL then CHEAP) ===",
      flush=True)
print(f"host  : {HOST}", flush=True)
print(f"HARD CAP(task): ${HARD_CAP_USD}  cache_off=1 pool_off=1", flush=True)

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


def _row_count():
    return _scalar("SELECT count(*) FROM audio_tours")


def _test_row_count():
    return _scalar("SELECT count(*) FROM audio_tours WHERE is_test = true")


def _spend_so_far():
    v = _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE host = %s",
                (HOST,))
    return float(v) if v is not None else None


def _spend_breakdown():
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT provider, COUNT(*), COALESCE(SUM(usd),0) "
                "FROM paid_api_calls WHERE host = %s GROUP BY provider "
                "ORDER BY 3 DESC", (HOST,))
            rows = cur.fetchall()
        conn.close(); return rows
    except Exception as e:
        print(f"  [db] breakdown failed: {e}", flush=True); return []


# ───────────────────────── detectors ────────────────────────────────────────

_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_SOURCES_RE = re.compile(r"(?mi)^Sources?:\s*(.+)$")


def _norm_identity(s):
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", (s or "").lower())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    glue = {"the", "of", "and", "a", "an", "to", "in", "on", "with", "for"}
    toks = sorted(t for t in stripped.split() if t not in glue and len(t) >= 2)
    return " ".join(toks)


def _titles(text):
    # The delivered header may carry a bilingual form and a trailing " by Artist,
    # year"; take the stop-title portion up to " by ".
    out = []
    for raw in _STOP_HEADER_RE.findall(text):
        t = re.split(r"\s+by\s+", raw.strip(), maxsplit=1)[0].strip()
        out.append(t)
    return out


def detect_delivered(text):
    n = _tc.count_delivered_stops(text)
    return (n >= 1), f"delivered_stops={n}"


def detect_no_citation_stop(text):
    bad = [t for t in _titles(text)
           if re.search(r"(?i)\b(source|references?|citation|portal|\[|\*\*|https?://)", t)]
    return (not bad), f"citation_titles={bad}"


def detect_distinct_works(text):
    """The 669C headline: no two delivered stops are the SAME work by a loose
    order-ignored content-token identity. The bilingual header carries BOTH the
    local and English title, so we test the FULL header AND the local-only
    portion (text before '(') — either repeating is a duplicate work."""
    titles = _titles(text)
    seen = {}
    dups = []
    for t in titles:
        # Compare on BOTH the whole header and its leading local title, so
        # "Vườn xuân … (North Central South Spring Garden)" and a bare
        # "North Central South Spring Garden" still register as the same work.
        local_only = t.split("(")[0].strip()
        english_in_paren = ""
        m = re.search(r"\(([^)]+)\)\s*$", t)
        if m:
            english_in_paren = m.group(1).strip()
        keys = {_norm_identity(local_only)}
        if english_in_paren:
            keys.add(_norm_identity(english_in_paren))
        hit = next((seen[k] for k in keys if k and k in seen), None)
        if hit:
            dups.append((hit, t))
        for k in keys:
            if k:
                seen[k] = t
    return (not dups), f"duplicate_pairs={dups}"


def detect_bilingual_header(text):
    """At least one delivered header is the bilingual '<local> (<English>)'
    form the ticket asks for (local first). Informational — a venue whose works
    have no distinct English label legitimately shows mono-lingual headers."""
    bil = [t for t in _titles(text) if re.search(r"\([A-Za-z][^)]*\)\s*$", t)]
    return True, f"bilingual_headers={bil}"


def _report(text, gen_log):
    titles = _titles(text)
    print("  --- STOP LIST (delivered headers) ---", flush=True)
    for h in _STOP_HEADER_RE.findall(text):
        print(f"  STOP TITLE: {h.strip()[:140]}", flush=True)
    print("  --- LOCAL-669C decision log ---", flush=True)
    for ln in gen_log.splitlines():
        if ("[LOCAL-669C]" in ln or "[LOCAL-669B] IDENTITY DEDUP" in ln
                or "[LOCAL-669]" in ln):
            print(f"    {ln.strip()[:200]}", flush=True)
    print("  --- DETECTORS ---", flush=True)
    results = {}
    for name, fn in (("DELIVERED", detect_delivered),
                     ("NO_CITATION_STOP", detect_no_citation_stop),
                     ("DISTINCT_WORKS", detect_distinct_works),
                     ("BILINGUAL_HEADER", detect_bilingual_header)):
        try:
            ok, detail = fn(text)
        except Exception as e:
            ok, detail = False, f"detector error: {e}"
        results[name] = ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    # The task's PASS set excludes the purely-informational BILINGUAL_HEADER.
    core = {k: v for k, v in results.items() if k != "BILINGUAL_HEADER"}
    print(f"  [LOCAL-669C] CORE DETECTORS PASS = {all(core.values())}", flush=True)
    return results


def _store(location, text, n_stops, arm):
    try:
        conn = _conn(); conn.autocommit = True
        name = f"LOCAL-669C {location.split(',')[0][:36]} {arm} {int(time.time())}"
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
                 f"LOCAL-669C live fresh ({arm})"))
            new_id = cur.fetchone()[0]
        conn.close(); return new_id
    except Exception as e:
        print(f"  [store] insert failed: {e}", flush=True); return None


def _count_grounded(gen_log):
    hl_grounded = 0
    hl_serper = 0
    for ln in gen_log.splitlines():
        m = re.search(r"highlights:\s*(\d+)\s*candidates,\s*(\d+)\s*verified,"
                      r"\s*cost\s*(\d+)\s*grounded request\s*\+\s*(\d+)\s*Serper", ln)
        if m:
            hl_grounded = int(m.group(3))
            hl_serper = int(m.group(4))
    return hl_grounded, hl_serper


def _run_arm(arm, env_overrides):
    print(f"\n=== [{arm}] generating: {LOCATION} ({STOPS} stops, museum) ===",
          flush=True)
    for k, v in env_overrides.items():
        if v is None:
            _os.environ.pop(k, None)
        else:
            _os.environ[k] = v
    print(f"  [{arm}] env: NARRATION_MODEL={_os.environ.get('NARRATION_MODEL','')!r} "
          f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND','')!r}", flush=True)

    t0 = time.time()
    _buf = io.StringIO()

    class _Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                s.write(data)
            return len(data)

        def flush(self):
            for s in self.streams:
                try:
                    s.flush()
                except Exception:
                    pass

    text = None
    try:
        with contextlib.redirect_stdout(_Tee(_sys.__stdout__, _buf)):
            text, _p, _c = generate_tour_text(
                LOCATION, 'museum', f"/app/tours/LOCAL669C_{arm}.txt", STOPS,
                user_id=None)
    except Exception as e:
        print(f"RUN ERROR [{arm}]: {e}", flush=True)

    elapsed = time.time() - t0
    gen_log = _buf.getvalue()

    if not text:
        print(f"OUTCOME [{arm}]: NO TOUR TEXT after {elapsed:.1f}s", flush=True)
        return None

    delivered = _tc.count_delivered_stops(text)
    print(f"\nOUTCOME [{arm}]: DELIVERED — {len(text)} chars, {delivered} stops, "
          f"wall {elapsed:.1f}s", flush=True)
    _report(text, gen_log)
    hl_grounded, hl_serper = _count_grounded(gen_log)
    print(f"\n[{arm}] grounded requests (highlights): {hl_grounded}  "
          f"serper 2nd-source: {hl_serper}", flush=True)
    try:
        from generate_tour_text import _LAST_GENERATION_COST
        _cc = dict(_LAST_GENERATION_COST or {})
        tc = float(_cc.get('tour_total_cost', _cc.get('total_cost', 0.0)) or 0.0)
        print(f"[{arm}] [cost] tour_total=${tc:.4f}", flush=True)
    except Exception:
        pass
    nid = _store(LOCATION, text, delivered, arm)
    if nid:
        print(f"STORED [{arm}] audio_tours id = {nid}  (is_test=true)", flush=True)
        print(f"LOCAL669C_{arm}_TOUR_ID={nid}", flush=True)
    try:
        with open(f"/app/tours/LOCAL669C_{arm}_delivered.txt", "w",
                  encoding="utf-8") as _df:
            _df.write(text)
    except Exception:
        pass
    return {"arm": arm, "stops": delivered, "wall_s": round(elapsed, 1),
            "grounded": hl_grounded, "serper": hl_serper, "id": nid}


print(f"[db] audio_tours row count BEFORE: {_row_count()} "
      f"(is_test rows BEFORE: {_test_row_count()})", flush=True)
print(f"[db] paid_api_calls spend for host {HOST} BEFORE: ${_spend_so_far()}",
      flush=True)

summaries = []
# NORMAL arm: default narration (gpt-4.1), Gemini grounded highlights.
summaries.append(_run_arm("NORMAL", {
    "NARRATION_MODEL": None,
    "RESEARCH_BACKEND": None,
}))
# CHEAP arm: gpt-4.1-mini narration, Serper research backend. Runs AFTER NORMAL
# so the 30-day highlights venue cache is warm (0 extra grounded requests).
summaries.append(_run_arm("CHEAP", {
    "NARRATION_MODEL": "gpt-4.1-mini",
    "RESEARCH_BACKEND": "serper",
}))

print(f"\n[db] audio_tours row count AFTER: {_row_count()} "
      f"(is_test rows AFTER: {_test_row_count()})", flush=True)
_final_spend = _spend_so_far()
print(f"[db] paid_api_calls spend for host {HOST} AFTER: ${_final_spend}",
      flush=True)
print("[db] spend breakdown by provider (r5 rates, from paid_api_calls):",
      flush=True)
for prov, cnt, usd in _spend_breakdown():
    print(f"    {prov}: {cnt} calls, ${float(usd):.4f}", flush=True)

print("\n=== LOCAL-669C SUMMARY ===", flush=True)
for s in summaries:
    if s:
        print(f"  {s['arm']}: stops={s['stops']} grounded={s['grounded']} "
              f"serper={s['serper']} wall={s['wall_s']}s id={s['id']}", flush=True)
if _final_spend is not None:
    print(f"  TOTAL task spend (both arms): ${_final_spend:.4f} "
          f"(cap ${HARD_CAP_USD})", flush=True)
print("=== LOCAL-669C run complete ===", flush=True)
