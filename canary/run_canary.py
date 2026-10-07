#!/usr/bin/env python3
"""canary/run_canary.py — LOCAL-611 live canary runner.

Runs the KNOWN set (5 venues that have passed before) PLUS 3 never-seen venues
drawn from the Wikidata pool, every run, through the LIVE local orchestrator
(port 5002), as a dedicated canary device CANARY-LEAD at level 'admin'.

Michael's constraints:
  * 2 stops each, EN — "so it is cheap make only 2 stops" — EXCEPT one rotating
    known venue at 5 stops, because multi-stop defects (fill-to-N, cross-stop
    dedupe, conclusion recap) cannot show with only 2 stops.
  * Canary tours stored with is_test = TRUE and lat/lng NULL so they never
    appear in anyone's app. is_test is set by the orchestrator when the payload
    carries is_test:true AND the server runs with TOUR_TEST_MODE_ALLOW_REQUEST=true;
    the orchestrator always computes coordinates, so the RUNNER nulls lat/lng on
    the rows it created (live services used, NOT modified).
  * Budget guard: stop the run if cumulative cost passes $CANARY_MAX_USD ($3).

Per tour it records: success/failure, error code/message, stops delivered vs
requested, coordinates present, URL-in-audio check, the "check the website"
count, wall time, and the cost breakdown (from cost_ledger via cost_meter).

Reporting (canary/report.py): appends a run block to .continuous_dev/CANARY.md,
writes a '*** CANARY FAIL ***' line to ALERTS.md for any failure, and shows the
pass-rate history over the last 10 runs.

Usage:
    python3 canary/run_canary.py              # full live run (cap $3)
    python3 canary/run_canary.py --dry-run    # no HTTP; print the plan
"""

from __future__ import annotations

import io
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, PROJECT_ROOT)

import picker as pk  # noqa: E402
import venue_pool as vp  # noqa: E402
import report as rpt  # noqa: E402

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
ORCH = os.environ.get("ORCH_URL", "http://localhost:5002")
CANARY_USER = os.environ.get("CANARY_USER", "CANARY-LEAD")
CANARY_LEVEL = os.environ.get("CANARY_LEVEL", "admin")
CANARY_MAX_USD = float(os.environ.get("CANARY_MAX_USD", "3.0"))
POLL_INTERVAL_S = float(os.environ.get("CANARY_POLL_INTERVAL", "8"))
POLL_DEADLINE_S = float(os.environ.get("CANARY_POLL_DEADLINE", "900"))  # 15 min / tour
LANG = "en"

# Host-side DB (same postgres the service uses; 5433 -> container 5432).
DB = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5433"),
    "dbname": os.environ.get("DB_NAME", "audiotours"),
    "user": os.environ.get("DB_USER", "admin"),
    "password": os.environ.get("DB_PASSWORD", "password123"),
}

# The known-good set (D625). Configurable via canary/known_venues.json or env.
DEFAULT_KNOWN_VENUES = [
    {"location": "Phu Quoc, Vietnam", "tour_type": ""},
    {"location": "Fruitlands Museum, Harvard, MA", "tour_type": "museum"},
    {"location": "McMullen Museum of Art, Boston College, Boston, MA", "tour_type": "museum"},
    {"location": "MassArt Art Museum, Boston, MA", "tour_type": "museum"},
    {"location": "Freedom Trail, Boston, MA", "tour_type": "walking"},
]
KNOWN_STOPS = int(os.environ.get("CANARY_KNOWN_STOPS", "2"))
NEW_STOPS = int(os.environ.get("CANARY_NEW_STOPS", "2"))
MULTISTOP_STOPS = int(os.environ.get("CANARY_MULTISTOP_STOPS", "5"))

# URL / "check the website" detection in delivered audio text.
_URL_RE = re.compile(r"https?://|www\.|\b\w+\.(?:com|org|net|edu|gov)\b", re.I)
_CHECK_SITE_RE = re.compile(r"check (?:the|their|its|our) (?:official )?website", re.I)


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #
def _pg():
    import psycopg2
    return psycopg2.connect(**DB)


def seed_canary_device() -> None:
    """Ensure CANARY-LEAD exists at level 'admin' and clear prior usage so the
    quota gate always lets the canary through."""
    conn = _pg()
    cur = conn.cursor()
    # users row (plan free is fine; the authoritative gate is device_entitlement).
    try:
        cur.execute(
            "INSERT INTO users (secret_id, plan) VALUES (%s, 'free') "
            "ON CONFLICT (secret_id) DO NOTHING",
            (CANARY_USER,),
        )
    except Exception as e:
        log(f"(users seed note: {e})")
        conn.rollback()
        cur = conn.cursor()
    # device_entitlement at admin (hidden level with the highest limits).
    cur.execute(
        "INSERT INTO device_entitlement (user_id, level) VALUES (%s, %s) "
        "ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level",
        (CANARY_USER, CANARY_LEVEL),
    )
    # Clear today's orchestrator usage.
    try:
        cur.execute(
            "DELETE FROM tour_requests WHERE secret_id = %s AND source = 'orchestrator'",
            (CANARY_USER,),
        )
    except Exception as e:
        log(f"(usage clear note: {e})")
    conn.commit()
    cur.close()
    conn.close()
    log(f"Seeded canary device {CANARY_USER} at level {CANARY_LEVEL}; cleared prior usage.")


def count_audio_tours() -> int:
    conn = _pg()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    n = cur.fetchone()[0]
    cur.close()
    conn.close()
    return n


def fetch_tour_row(final_tour_id, request_string):
    """Return (id, is_test, lat, lng, audio_bytes, tour_content) for the created
    row, by id when available, else newest matching request within 25 min."""
    conn = _pg()
    cur = conn.cursor()
    row = None
    if final_tour_id:
        cur.execute(
            "SELECT id, is_test, lat, lng, octet_length(audio_tour), tour_content "
            "FROM audio_tours WHERE id = %s",
            (final_tour_id,),
        )
        row = cur.fetchone()
    if row is None and request_string:
        cur.execute(
            "SELECT id, is_test, lat, lng, octet_length(audio_tour), tour_content "
            "FROM audio_tours WHERE request_string ILIKE %s "
            "AND created_at > NOW() - INTERVAL '25 minutes' "
            "ORDER BY id DESC LIMIT 1",
            (f"%{request_string[:40]}%",),
        )
        row = cur.fetchone()
    cur.close()
    conn.close()
    return row


def null_coords_for(tour_id: int) -> bool:
    """Set lat/lng NULL on the given audio_tours row (keeps it off the map)."""
    conn = _pg()
    cur = conn.cursor()
    cur.execute("UPDATE audio_tours SET lat = NULL, lng = NULL WHERE id = %s", (tour_id,))
    affected = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return affected > 0


# --------------------------------------------------------------------------- #
# Cost (ledger via cost_meter)
# --------------------------------------------------------------------------- #
def job_cost(job_id: str) -> dict:
    """Return {'total': float, 'breakdown': {...}, 'rows': int} for a job_id.

    Reads cost_ledger via cost_meter.get_operation_cost. LOCAL-609 fields are
    not merged on this base, so we aggregate our_cost_usd and the per-row
    breakdown dicts directly. Never raises — cost is best-effort evidence.
    """
    total = 0.0
    agg: dict = {}
    nrows = 0
    try:
        from cost_meter import get_operation_cost
        rows = get_operation_cost(job_id) or []
        for r in rows:
            nrows += 1
            total += float(r.get("our_cost_usd") or 0.0)
            bd = r.get("breakdown") or {}
            if isinstance(bd, dict):
                for k, v in bd.items():
                    try:
                        agg[k] = agg.get(k, 0.0) + float(v)
                    except (TypeError, ValueError):
                        continue
    except Exception as e:
        log(f"(cost lookup failed for {job_id}: {e})")
    return {"total": round(total, 6), "breakdown": agg, "rows": nrows}


# --------------------------------------------------------------------------- #
# Audio inspection
# --------------------------------------------------------------------------- #
def inspect_audio_text(tour_id: int) -> dict:
    """Pull the stored ZIP (or tour_content) and compute URL / check-site counts
    and the delivered audio-file count."""
    result = {"audio_files": 0, "url_hits": 0, "check_site_count": 0, "text_chars": 0}
    conn = _pg()
    cur = conn.cursor()
    cur.execute("SELECT audio_tour, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
    r = cur.fetchone()
    cur.close()
    conn.close()
    if not r:
        return result
    blob, content = r
    text = ""
    if blob:
        try:
            with zipfile.ZipFile(io.BytesIO(bytes(blob))) as z:
                names = z.namelist()
                result["audio_files"] = sum(
                    1 for n in names if re.fullmatch(r"audio_\d+\.mp3", os.path.basename(n))
                )
                for n in names:
                    if os.path.basename(n).endswith(".txt"):
                        try:
                            text += z.read(n).decode("utf-8", errors="ignore") + "\n"
                        except Exception:
                            pass
        except zipfile.BadZipFile:
            pass
    if not text and content:
        text = content
    result["text_chars"] = len(text)
    result["url_hits"] = len(_URL_RE.findall(text))
    result["check_site_count"] = len(_CHECK_SITE_RE.findall(text))
    return result


# --------------------------------------------------------------------------- #
# Orchestrator HTTP
# --------------------------------------------------------------------------- #
def submit_tour(location, tour_type, total_stops, request_string=None):
    """POST /generate-complete-tour. Returns job_id. Raises on non-200/no job."""
    import requests
    payload = {
        "location": location,
        "tour_type": tour_type,
        "total_stops": total_stops,
        "user_id": CANARY_USER,
        "request_string": request_string or location,
        "language": LANG,
        "is_test": True,  # honored iff server has TOUR_TEST_MODE_ALLOW_REQUEST=true
    }
    r = requests.post(f"{ORCH}/generate-complete-tour", json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"submit HTTP {r.status_code}: {r.text[:300]}")
    body = r.json()
    job_id = body.get("job_id")
    if not job_id:
        raise RuntimeError(f"no job_id in response: {body}")
    return job_id


def poll_tour(job_id, deadline_s=POLL_DEADLINE_S, interval_s=POLL_INTERVAL_S):
    """Poll /status/<job_id> until completed/error/timeout. Returns status dict."""
    import requests
    t0 = time.time()
    last = None
    while time.time() - t0 < deadline_s:
        time.sleep(interval_s)
        try:
            s = requests.get(f"{ORCH}/status/{job_id}", timeout=30)
        except requests.RequestException as e:
            log(f"  (poll transient error: {e})")
            continue
        if s.status_code != 200:
            continue
        data = s.json()
        st = data.get("status")
        prog = data.get("progress", "")
        if prog != last:
            log(f"  status={st}  {prog}")
            last = prog
        if st in ("completed", "error"):
            return data
    return {"status": "timeout", "error": "poll deadline exceeded"}


# --------------------------------------------------------------------------- #
# One tour
# --------------------------------------------------------------------------- #
def run_one_tour(name, location, tour_type, total_stops, *, submit=submit_tour, poll=poll_tour):
    """Submit, poll, inspect, null-coords. Returns a result dict for the report."""
    res = {
        "name": name,
        "location": location,
        "tour_type": tour_type or "(classify)",
        "requested_stops": total_stops,
        "success": False,
        "error_code": "",
        "error_message": "",
        "delivered_stops": None,
        "coordinates_present": None,
        "is_test": None,
        "url_in_audio": None,
        "check_site_count": None,
        "wall_s": None,
        "cost": {"total": 0.0, "breakdown": {}, "rows": 0},
        "job_id": None,
        "tour_id": None,
    }
    t0 = time.time()
    try:
        job_id = submit(location, tour_type, total_stops, location)
    except Exception as e:
        res["error_code"] = "submit_failed"
        res["error_message"] = str(e)[:300]
        res["wall_s"] = round(time.time() - t0, 1)
        return res
    res["job_id"] = job_id
    log(f"  job_id={job_id}")

    status = poll(job_id)
    res["wall_s"] = round(time.time() - t0, 1)
    res["cost"] = job_cost(job_id)

    st = status.get("status")
    if st != "completed":
        res["error_code"] = st or "unknown"
        res["error_message"] = str(status.get("error", ""))[:300]
        return res

    # Completed. Collect delivery metrics.
    res["delivered_stops"] = status.get("actual_stops")
    coords = status.get("coordinates")
    res["coordinates_present"] = bool(coords and isinstance(coords, (list, tuple))
                                      and len(coords) >= 2 and (coords[0] or coords[1]))
    final_tour_id = status.get("final_tour_id")

    row = fetch_tour_row(final_tour_id, location)
    if row:
        tid, is_test, lat, lng, audio_bytes, _content = row
        res["tour_id"] = tid
        res["is_test"] = bool(is_test)
        # Inspect audio text for URL / check-site counts.
        info = inspect_audio_text(tid)
        if res["delivered_stops"] is None:
            res["delivered_stops"] = info["audio_files"]
        res["url_in_audio"] = info["url_hits"] > 0
        res["check_site_count"] = info["check_site_count"]
        # NULL the coordinates so the canary tour never shows on the map.
        try:
            null_coords_for(tid)
        except Exception as e:
            log(f"  (null coords failed for {tid}: {e})")
        # Success criterion: completed, delivered >=1 stop, real audio bytes.
        res["success"] = bool(audio_bytes and audio_bytes > 1000
                              and (res["delivered_stops"] or 0) >= 1)
        if not res["success"]:
            res["error_code"] = "empty_or_no_audio"
            res["error_message"] = (
                f"audio_bytes={audio_bytes}, delivered={res['delivered_stops']}"
            )
    else:
        res["error_code"] = "row_not_found"
        res["error_message"] = "completed but no audio_tours row located"
    return res


# --------------------------------------------------------------------------- #
# Plan builder
# --------------------------------------------------------------------------- #
def load_known_venues():
    """Known-good set. Override file canary/known_venues.json wins if present."""
    override = os.path.join(HERE, "known_venues.json")
    if os.path.exists(override):
        import json
        try:
            with open(override, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list) and data:
                return data
        except Exception as e:
            log(f"(known_venues.json ignored: {e})")
    return list(DEFAULT_KNOWN_VENUES)


def build_plan(run_index, pool, tried, *, seed=None):
    """Assemble the ordered list of tour specs: 5 known + 3 new.

    Exactly one *known* venue (rotated by run_index) runs at MULTISTOP_STOPS;
    the rest at the cheap 2-stop count. New venues run at NEW_STOPS (2).
    """
    known = load_known_venues()
    multistop_idx = run_index % len(known) if known else 0
    plan = []
    for i, kv in enumerate(known):
        stops = MULTISTOP_STOPS if i == multistop_idx else KNOWN_STOPS
        plan.append({
            "name": f"known[{i}]{' *multistop*' if i == multistop_idx else ''}",
            "location": kv["location"],
            "tour_type": kv.get("tour_type", ""),
            "total_stops": stops,
            "group": "known",
        })
    new_sel = pk.pick_new_venues(pool, tried, run_index=run_index, seed=seed, n=3)
    for j, sel in enumerate(new_sel):
        plan.append({
            "name": f"new[{j}:{sel['stratum']}{(':'+sel['subkind']) if sel.get('subkind') else ''}]",
            "location": sel["location"],
            "tour_type": sel.get("tour_type", ""),
            "total_stops": NEW_STOPS,
            "group": "new",
            "selection": sel,
        })
    return plan, new_sel


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="LOCAL-611 live canary runner.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Build the plan and print it; no HTTP, no DB writes.")
    ap.add_argument("--seed", type=int, default=None, help="Deterministic picker seed.")
    args = ap.parse_args(argv)

    # Determine run index from the existing CANARY.md history (0-based count).
    run_index = rpt.run_count(rpt.CANARY_MD)

    # Load the venue pool (built weekly; must exist for the live run).
    pool = vp.load_pool()
    tried = pk.load_tried()
    if not pool and not args.dry_run:
        log("WARNING: venue pool is empty. Run: python3 canary/venue_pool.py")

    plan, new_sel = build_plan(run_index, pool, tried, seed=args.seed)

    log(f"=== CANARY run #{run_index + 1} — {len(plan)} tours "
        f"(cap ${CANARY_MAX_USD:.2f}) ===")
    for spec in plan:
        log(f"  {spec['name']:<28} {spec['total_stops']}st  {spec['location']}")

    if args.dry_run:
        log("DRY RUN — not submitting.")
        return 0

    seed_canary_device()
    count_before = count_audio_tours()
    log(f"audio_tours BEFORE: {count_before}")

    results = []
    cumulative = 0.0
    budget_stopped = False
    for spec in plan:
        if cumulative >= CANARY_MAX_USD:
            log(f"*** BUDGET STOP *** cumulative ${cumulative:.4f} >= cap "
                f"${CANARY_MAX_USD:.2f}; skipping remaining tours.")
            budget_stopped = True
            break
        log(f"--- {spec['name']}: {spec['location']} ({spec['total_stops']} stops) ---")
        res = run_one_tour(spec["name"], spec["location"], spec["tour_type"],
                           spec["total_stops"])
        res["group"] = spec["group"]
        results.append(res)
        cumulative += res["cost"]["total"]
        log(f"  -> success={res['success']} stops={res['delivered_stops']}/"
            f"{res['requested_stops']} cost=${res['cost']['total']:.4f} "
            f"cum=${cumulative:.4f} wall={res['wall_s']}s")

    # Record the 3 new venues as tried (so they never repeat), even on partial
    # runs — a venue we SUBMITTED has been tried regardless of outcome.
    submitted_keys = {r.get("job_id") for r in results}
    tried_now = [s for s in new_sel
                 if any(rr.get("location") == s["location"] for rr in results)]
    if tried_now:
        pk.record_tried(tried_now)

    count_after = count_audio_tours()
    log(f"audio_tours AFTER: {count_after}  (delta +{count_after - count_before})")

    # Report.
    summary = {
        "run_index": run_index,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "code_sha": rpt.git_sha(),
        "cap_usd": CANARY_MAX_USD,
        "total_cost": round(cumulative, 6),
        "budget_stopped": budget_stopped,
        "count_before": count_before,
        "count_after": count_after,
        "results": results,
        "pool_meta": vp.load_meta(),
    }
    rpt.append_canary_report(summary)
    n_fail = sum(1 for r in results if not r["success"])
    if n_fail or budget_stopped:
        rpt.write_alert(summary)

    history = rpt.pass_rate_history(rpt.CANARY_MD, last=10)
    log(f"Pass-rate history (last 10 runs): {history}")
    log(f"=== CANARY run #{run_index + 1} complete: "
        f"{len(results) - n_fail}/{len(results)} passed, cost ${cumulative:.4f} ===")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
