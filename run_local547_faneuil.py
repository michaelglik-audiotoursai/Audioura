#!/usr/bin/env python3
"""LOCAL-524 — Prove the whole path with Igor's actual case, through the SERVICE.

Igor is the reason this exists (D562): he wanted to set up MFA Boston exhibits by
hand and could not — "we think it is us who knows better." This is his case, end
to end: a real MFA visit, a handful of stops he chose, entered by hand, generating
a tour of EXACTLY those stops — and run through the SERVICE (POST
/generate-complete-tour), not generate_tour_text directly, so it lands in
`audio_tours` WITH AUDIO. That combination — user-chosen stops + service path +
audio in the DB — has never been verified.

HOW "ENTERED BY HAND" IS EXPRESSED
----------------------------------
The service has no "explicit stops" parameter. A user names the stops they chose
inside the `location` text, and generate_tour_text.named_waypoints() (D536) lifts
each one out with _WAYPOINT_RE and marks it user_explicit=True — inserted at the
FRONT of the POI list so later phases cannot trim it, and protected from PHASE 3C
/ GEO-CHECK. The phrasing "with a stop at X, a stop at Y, and a stop at Z" captures
all three (verified: named_waypoints returns all three on the sanitized string).
That IS "entered by hand": the person types the works they picked, and the tour is
of EXACTLY those works.

WHY THE ORCHESTRATOR 'location' FIELD CARRIES THE STOPS
-------------------------------------------------------
orchestrate_tour_async forwards only {location, tour_type, total_stops[, user_id]}
to the tour-generator (tour_orchestrator_service.py:659), and generate_tour_text
runs named_waypoints() on `location`. So the hand-picked stops must live in the
`location` string — that is where the waypoint parser reads them.

WHY tour_type='contained' (museum), NOT 'walking'
-------------------------------------------------
A prior LOCAL-524 attempt sent these same stops on the WALKING path. Walking
geo-resolves each named work to a nearby venue and the facility path replaces them
with building parts, so the delivered stops came back "Grand staircase / Display
vitrines / Period rooms" — the named works were gone (that failure is what this
rewrite fixes). With a museum request naming a single venue ("Museum of Fine Arts"
→ tour_category='museum' via S15/CLASSIFY-FIX), PHASE 3C is skipped (all stops are
inside one building) and the user-explicit works are preserved as the stops.

SANITIZATION: sanitize_input() strips apostrophes/quotes and truncates to 200
chars (tour_orchestrator_service.py:155). This location is 153 chars with no
apostrophes — safe (verified).

WHY THIS EXACT PHRASING (comma after "Boston", waypoints joined by "and a stop at"
with NO commas between them): the museum path derives a Wikidata city hint by
splitting `location` on commas and taking the SECOND segment
(generate_tour_text.py:6311, parts[1]). A comma right after "Boston" makes that
segment exactly "Boston" — a clean city hint. Joining the three waypoints with
"and a stop at" (instead of comma-separating them) keeps any later text out of that
second segment. With city hint "Boston", resolve_venue('Museum of Fine Arts,
Boston', 'Boston') returns Q49133 (verified). Comma-separating the waypoints
instead pollutes the city hint to "Boston with a stop at the Sargent Murals", every
city-qualified Wikidata search misses, the venue resolves to None, and the whole
museum run clean-fails "unresolvable" (verified repeatedly). This is a
request-phrasing choice on the caller side; it does NOT touch product code.
named_waypoints() still lifts all three stops from this phrasing (verified).

It does NOT modify any product code. It seeds a dedicated test user (never a real
user) on the free plan, drives the running Docker service over HTTP, then reads
back the production `audiotours` DB the service writes to (LOCAL-302: the service
writes where ITS OWN DATABASE_URL points — production — regardless of this
process's env).
"""
import io
import json
import os
import re
import sys
import time
import unicodedata
import zipfile
from datetime import datetime

import requests

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
ORCH = os.environ.get("ORCH_URL", "http://localhost:5002")
# Host-side connection to the SAME postgres the service uses (5433 -> container 5432).
DB = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5433"),
    "dbname": os.environ.get("DB_NAME", "audiotours"),
    "user": os.environ.get("DB_USER", "admin"),
    "password": os.environ.get("DB_PASSWORD", "password123"),
}
TEST_USER = "ITEST-LOCAL547-FANEUIL"   # dedicated id; never a real user
BASELINE_USD = 0.244                # D565, n=3, ±13%

# Igor's actual case (D562): he visits the MFA and picks the works he wants to hear
# about, entering them by hand. These three are real, iconic MFA works:
#   - the Sargent Murals (John Singer Sargent's rotunda murals)
#   - the Liberty Bowl by Paul Revere (the Sons of Liberty Bowl, 1768)
#   - Watson and the Shark by Copley (John Singleton Copley, 1778)
# Each is named INSIDE the location string with "a stop at ..." so named_waypoints()
# lifts it as a user-explicit stop (verified: all three extract on the sanitized
# string). The tour must be of EXACTLY these three.
#
# WHY NOT "the Japanese Temple Room" (a first, faithful pick): the product-code
# venue-class detector (LOCAL-485) matches the word "Temple" as a WORSHIP/CIVIC
# place class and flips the whole tour museum → walking (VENUE-CLASS GUARD), which
# then delivers building parts and discards the named works. That is a real
# classifier false-positive on a gallery-inside-a-museum, but it is NOT this task's
# subject and must not be patched into product code just to make a test pass. Igor's
# case is "hand-picked MFA works"; three works with no worship/civic/facility
# trigger word prove exactly that path. (venue_class verified None for this string.)
STOPS = [
    "Quincy Market",
    "the Samuel Adams statue",
    "the Boston Massacre site",
]
LOCATION = (
    "Faneuil Hall Marketplace, Boston MA, with a stop at Quincy Market "
    "and a stop at the Samuel Adams statue "
    "and a stop at the Boston Massacre site"
)
REQUEST_STRING = LOCATION
# 'contained' is the museum/exhibition tour type: single venue, PHASE 3C skipped,
# user-explicit works preserved as the stops.
TOUR_TYPE = "walking"
TOTAL_STOPS = len(STOPS)


def _pg():
    import psycopg2
    return psycopg2.connect(**DB)


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def _norm(s):
    """Accent- and punctuation-insensitive normalization for name matching."""
    n = unicodedata.normalize("NFKD", (s or "").lower())
    n = "".join(c for c in n if not unicodedata.combining(c))
    n = re.sub(r"[^\w\s]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


# --------------------------------------------------------------------------- #
# Step 0 — seed the test user (free plan, 10/day) and clear prior usage
# --------------------------------------------------------------------------- #
def seed_user():
    conn = _pg()
    cur = conn.cursor()
    # free plan already exists (10/day, tour_max_poi 30). Just ensure the user maps to it.
    cur.execute(
        "INSERT INTO users (secret_id, plan) VALUES (%s, 'free') "
        "ON CONFLICT (secret_id) DO UPDATE SET plan = EXCLUDED.plan",
        (TEST_USER,),
    )
    # Clear today's orchestrator usage so the quota gate lets us through.
    cur.execute(
        "DELETE FROM tour_requests WHERE secret_id = %s AND source = 'orchestrator'",
        (TEST_USER,),
    )
    conn.commit()
    cur.close()
    conn.close()
    log(f"Seeded test user {TEST_USER} on free plan; cleared prior orchestrator usage.")


def bust_cache():
    """Delete this request's tour_cache row so the run is a TRUE fresh generation.

    The tour-generator caches by _cache_key(location, tour_type, stop-bucket) in the
    tour_cache table. Without busting, a second run of the same location returns the
    cached tour unchanged. The acceptance suite busts the cache exactly this way
    (run_local95_acceptance.py:bust_tour_cache). Cache-table cleanup only.
    """
    try:
        from tour_cache_layer1 import _cache_key, _legacy_cache_key
    except Exception as e:
        log(f"(could not import cache key fns: {e}; skipping bust)")
        return
    keys = {
        _cache_key(LOCATION, TOUR_TYPE, TOTAL_STOPS),
        _legacy_cache_key(LOCATION, TOUR_TYPE, TOTAL_STOPS),
    }
    conn = _pg()
    cur = conn.cursor()
    deleted = 0
    for k in keys:
        cur.execute("DELETE FROM tour_cache WHERE cache_key = %s", (k,))
        deleted += cur.rowcount
    # Also clear any row whose stored location matches (defensive, covers bucket drift).
    cur.execute("DELETE FROM tour_cache WHERE location ILIKE %s", ("%Sargent Murals%",))
    deleted += cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    log(f"Busted tour_cache: {deleted} row(s) removed — this run is a fresh generation.")


def clear_prior_test_tours():
    """Remove prior LOCAL-524 test rows from audio_tours.

    store_audio_tour keys on lower(tour_name) via uq_audio_tours_original_name: if a
    row with the same name exists it UPDATEs number_requested and keeps the OLD
    content instead of storing the fresh tour. These rows are this task's own test
    artifacts (the MFA request string is unmistakable), never real user tours, so
    clearing them lets each fresh run store and be verified. Scoped tightly to our
    exact request.
    """
    conn = _pg()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM audio_tours WHERE request_string ILIKE %s OR tour_name ILIKE %s",
        ("%Sargent Murals%", "%Sargent Murals%"),
    )
    n = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    log(f"Cleared {n} prior LOCAL-524 test row(s) from audio_tours.")


# --------------------------------------------------------------------------- #
# Step 1 — POST to the SERVICE and poll to completion
# --------------------------------------------------------------------------- #
def run_service():
    payload = {
        "location": LOCATION,
        "tour_type": TOUR_TYPE,
        "total_stops": TOTAL_STOPS,
        "user_id": TEST_USER,
        "request_string": REQUEST_STRING,
        "language": "en",
    }
    log(f"POST {ORCH}/generate-complete-tour")
    log(f"  location   : {LOCATION}")
    log(f"  tour_type  : {TOUR_TYPE}")
    log(f"  stops      : {TOTAL_STOPS}  {STOPS}")
    t0 = time.time()
    r = requests.post(f"{ORCH}/generate-complete-tour", json=payload, timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"FAIL: service returned {r.status_code}: {r.text[:500]}")
    body = r.json()
    job_id = body.get("job_id")
    if not job_id:
        raise SystemExit(f"FAIL: no job_id in response: {body}")
    log(f"  job_id     : {job_id}")

    # Poll /status until completed or error.
    last_progress = None
    deadline = t0 + 900  # 15 min ceiling
    status_data = {}
    while time.time() < deadline:
        time.sleep(8)
        try:
            s = requests.get(f"{ORCH}/status/{job_id}", timeout=30)
        except requests.RequestException as e:
            log(f"  (status poll transient error: {e})")
            continue
        if s.status_code != 200:
            log(f"  (status {s.status_code})")
            continue
        status_data = s.json()
        st = status_data.get("status")
        prog = status_data.get("progress", "")
        if prog != last_progress:
            log(f"  status={st}  {prog}")
            last_progress = prog
        if st == "completed":
            elapsed = time.time() - t0
            log(f"COMPLETED in {elapsed:.1f}s")
            return job_id, elapsed, status_data
        if st == "error":
            raise SystemExit(f"FAIL: service error: {status_data.get('error')}")
    raise SystemExit("FAIL: timed out waiting for completion")


# --------------------------------------------------------------------------- #
# Step 2 — verify the tour landed in audio_tours WITH audio
# --------------------------------------------------------------------------- #
def verify_audio_tours(job_id, status_data):
    """Find the row this run created and confirm real audio bytes + audio_N.mp3."""
    tour_id = status_data.get("final_tour_id")
    conn = _pg()
    cur = conn.cursor()

    row = None
    if tour_id:
        cur.execute(
            "SELECT id, tour_name, stops_count, zip_filename, "
            "octet_length(audio_tour), length(tour_content) "
            "FROM audio_tours WHERE id = %s",
            (tour_id,),
        )
        row = cur.fetchone()
    if row is None:
        # Fall back to newest matching row created in the last few minutes.
        cur.execute(
            "SELECT id, tour_name, stops_count, zip_filename, "
            "octet_length(audio_tour), length(tour_content) "
            "FROM audio_tours "
            "WHERE request_string ILIKE %s AND created_at > NOW() - INTERVAL '20 minutes' "
            "ORDER BY id DESC LIMIT 1",
            ("%Sargent Murals%",),
        )
        row = cur.fetchone()
    if row is None:
        cur.close(); conn.close()
        raise SystemExit("FAIL: no audio_tours row found for this run")

    tid, tour_name, stops_count, zip_filename, audio_bytes, content_len = row
    log("audio_tours row:")
    log(f"  id           : {tid}")
    log(f"  tour_name    : {tour_name}")
    log(f"  stops_count  : {stops_count}")
    log(f"  zip_filename : {zip_filename}")
    log(f"  audio_tour   : {audio_bytes} bytes (BYTEA)")
    log(f"  tour_content : {content_len} chars")

    if not audio_bytes or audio_bytes < 1000:
        cur.close(); conn.close()
        raise SystemExit(f"FAIL: audio_tour BYTEA missing/too small ({audio_bytes})")

    # Pull the ZIP bytes and inspect for audio_N.mp3 and tour_content.txt.
    cur.execute("SELECT audio_tour FROM audio_tours WHERE id = %s", (tid,))
    blob = cur.fetchone()[0]
    cur.close(); conn.close()

    zip_bytes = bytes(blob)
    audio_members, content_text, names = [], None, []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            names = z.namelist()
            audio_members = [n for n in names if re.fullmatch(r"audio_\d+\.mp3", os.path.basename(n))]
            for n in names:
                if os.path.basename(n) == "tour_content.txt":
                    content_text = z.read(n).decode("utf-8", errors="ignore")
        log(f"  ZIP members  : {sorted(os.path.basename(n) for n in names)}")
        log(f"  audio_N.mp3  : {len(audio_members)} -> {sorted(os.path.basename(n) for n in audio_members)}")
    except zipfile.BadZipFile:
        raise SystemExit("FAIL: audio_tour BYTEA is not a valid ZIP")

    if len(audio_members) < 1:
        raise SystemExit("FAIL: no audio_N.mp3 files in the stored ZIP")

    # If tour_content.txt was not in the ZIP, fall back to the DB column.
    if not content_text:
        conn = _pg(); cur = conn.cursor()
        cur.execute("SELECT tour_content FROM audio_tours WHERE id = %s", (tid,))
        content_text = (cur.fetchone() or [None])[0]
        cur.close(); conn.close()

    return {
        "tour_id": tid,
        "tour_name": tour_name,
        "stops_count": stops_count,
        "zip_filename": zip_filename,
        "audio_bytes": audio_bytes,
        "audio_members": sorted(os.path.basename(n) for n in audio_members),
        "content_text": content_text,
    }


# --------------------------------------------------------------------------- #
# Step 3 — score with tour_quality.score_tour
# --------------------------------------------------------------------------- #
def score(content_text):
    from tour_quality import score_tour
    result = score_tour(content_text, requested_stops=TOTAL_STOPS)
    log("tour_quality.score_tour:")
    log(f"  clean        : {result['clean']}")
    log(f"  metrics      : {result['metrics']}")
    log(f"  defects      : {result['defects'] or '(none)'}")
    return result


def stops_present(content_text):
    """Return the delivered stop headers, in order."""
    stop_lines = re.findall(r"^Stop \d+:\s*(.+)$", content_text or "", re.M)
    log(f"delivered stop headers ({len(stop_lines)}):")
    for i, s in enumerate(stop_lines, 1):
        log(f"    {i}. {s.strip()}")
    return [s.strip() for s in stop_lines]


def stops_match(delivered_headers):
    """Confirm the delivered stops ARE Igor's hand-picked stops.

    Unlike a keyword-anywhere check, this matches each chosen stop to a DELIVERED
    STOP HEADER (the works are the stops, not merely mentioned in prose). A chosen
    stop is 'present' when a distinctive token from it appears in some header.
    """
    # A distinctive anchor token for each chosen stop (accent-insensitive).
    # [2026-09-24, LEAD] These anchors were left as the MFA works when this file was
    # derived from run_local547_igor_e2e.py -- only STOPS and LOCATION were changed.
    # The Faneuil run therefore reported PARTIAL/FAIL while delivering all three
    # requested stops correctly. A stale assertion reading as a product failure is
    # exactly the trap the pinned corpus counts set last night.
    anchors = {
        "Quincy Market": ["quincy"],
        "the Samuel Adams statue": ["samuel adams", "adams"],
        "the Boston Massacre site": ["boston massacre", "massacre"],
    }
    norm_headers = [_norm(h) for h in delivered_headers]
    matched, matched_to = {}, {}
    for stop, keys in anchors.items():
        hit_idx = None
        for i, h in enumerate(norm_headers):
            if any(_norm(k) in h for k in keys):
                hit_idx = i
                break
        matched[stop] = hit_idx is not None
        matched_to[stop] = (hit_idx + 1) if hit_idx is not None else None
    log("user-chosen stop -> delivered as a STOP header?")
    for stop, ok in matched.items():
        where = f"Stop {matched_to[stop]}" if ok else "—"
        log(f"    [{'YES' if ok else 'NO '}] {stop}  ({where})")
    return matched, matched_to


def order_is_sensible(matched_to):
    """A sensible order: each chosen stop maps to a distinct header and the mapping
    is monotonic (no two chosen stops collapse to one header)."""
    positions = [p for p in matched_to.values() if p is not None]
    distinct = len(set(positions)) == len(positions)
    return distinct and len(positions) == len(matched_to)


# --------------------------------------------------------------------------- #
# Step 4 — cost from cost_ledger, keyed on job_id
# --------------------------------------------------------------------------- #
def cost_for_job(orch_job_id, tour_id):
    """Sum our_cost_usd for this run.

    The orchestrator generates a job_id, but the cost_ledger rows (spine_generate,
    tour_generate) are keyed on the TOUR-GENERATOR's internal job_id. The bridge is
    stop_metrics: store_audio_tour backfills stop_metrics.tour_id, and those rows
    carry the text-gen job_id. So: final_tour_id -> stop_metrics.job_id ->
    cost_ledger.job_id. (TTS runs inside the polly container without a ledger row in
    this deployment, exactly as SUBMISSION_LOCAL-323 recorded — so text+spine is the
    measured cost.)
    """
    conn = _pg()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT job_id FROM stop_metrics WHERE tour_id = %s AND job_id IS NOT NULL",
        (tour_id,),
    )
    text_job_ids = [r[0] for r in cur.fetchall()]
    job_ids = list({orch_job_id, *text_job_ids})
    log(f"cost job_ids: orchestrator={orch_job_id} text-gen={text_job_ids}")

    cur.execute(
        "SELECT operation_type, our_cost_usd, cache_hit, job_id FROM cost_ledger "
        "WHERE job_id = ANY(%s) ORDER BY created_at",
        (job_ids,),
    )
    rows = cur.fetchall()
    cur.close(); conn.close()
    total = sum(float(c) for _, c, _, _ in rows)
    log("cost_ledger (this run):")
    for op, c, hit, jid in rows:
        log(f"    {op:24s} ${float(c):.6f}{'  (cache hit)' if hit else ''}")
    log(f"  TOTAL measured our_cost_usd : ${total:.4f}   (baseline ${BASELINE_USD:.3f}, "
        f"TTS not ledgered in this container per D323)")
    return total, rows


# --------------------------------------------------------------------------- #
def main():
    print("=" * 74)
    print("  LOCAL-524 — Igor's MFA case (hand-entered stops), through the SERVICE")
    print("=" * 74)
    seed_user()
    bust_cache()
    clear_prior_test_tours()
    job_id, elapsed, status_data = run_service()
    verified = verify_audio_tours(job_id, status_data)
    delivered = stops_present(verified["content_text"])
    matched, matched_to = stops_match(delivered)
    order_ok = order_is_sensible(matched_to)
    log(f"order sensible (distinct 1:1 mapping): {order_ok}")
    scored = score(verified["content_text"])
    total_cost, cost_rows = cost_for_job(job_id, verified["tour_id"])

    summary = {
        "job_id": job_id,
        "wall_time_s": round(elapsed, 1),
        "tour_id": verified["tour_id"],
        "tour_name": verified["tour_name"],
        "location": LOCATION,
        "tour_type": TOUR_TYPE,
        "stops_requested": TOTAL_STOPS,
        "stops_count_db": verified["stops_count"],
        "stops_delivered_headers": delivered,
        "user_chosen_stops": STOPS,
        "stops_match": matched,
        "stops_match_to_header": matched_to,
        "all_chosen_stops_present": all(matched.values()),
        "order_sensible": order_ok,
        "audio_bytes": verified["audio_bytes"],
        "audio_members": verified["audio_members"],
        "zip_filename": verified["zip_filename"],
        "score_clean": scored["clean"],
        "score_metrics": scored["metrics"],
        "score_defects": scored["defects"],
        "cost_usd": round(total_cost, 4),
        "cost_baseline_usd": BASELINE_USD,
        "cost_rows": [{"op": op, "usd": float(c), "cache_hit": hit, "job_id": jid}
                      for op, c, hit, jid in cost_rows],
    }
    out = os.path.join(PROJECT_ROOT, "local524_igor_mfa_result.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=2)
    log(f"Wrote {out}")

    # Verdict
    print("=" * 74)
    checks = {
        "landed in audio_tours with audio (BYTEA + audio_N.mp3)":
            verified["audio_bytes"] > 1000 and len(verified["audio_members"]) >= 1,
        "delivered stop count == requested":
            len(delivered) == TOTAL_STOPS,
        "tour is of EXACTLY the stops Igor hand-entered (each is a delivered stop)":
            all(matched.values()),
        "stops in a sensible order (distinct 1:1 mapping)":
            order_ok,
        "no scoring defects (clean)":
            scored["clean"] and not scored["defects"],
        "cost recorded (>0) in cost_ledger":
            total_cost > 0,
    }
    for k, v in checks.items():
        print(f"  [{'PASS' if v else 'FAIL'}] {k}")
    print("=" * 74)
    print("VERDICT:", "PASS" if all(checks.values()) else "PARTIAL/FAIL")
    print("=" * 74)
    return all(checks.values())


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
