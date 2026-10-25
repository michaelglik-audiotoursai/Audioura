import os
import sys
import json
import uuid
import zipfile
import shutil
import time
import signal
import threading
import requests
import traceback
import re
import math
import logging
from datetime import datetime, timedelta
import flask
from flask import Flask, request, jsonify, send_file as _send_file, make_response
import inspect as _inspect

_orch_logger = logging.getLogger("tour_orchestrator_service")


# [LOCAL-737 / D708] The deployment `track` is per-DEPLOYMENT (Beta, Storied and
# Subscribed are separate Cloud Run services that SHARE one GCloud Postgres).
# Each always writes its own value so (name, creator, track) stays unique per
# track and the same-name collision class (bug 432) cannot return between tracks.
# Subscribed is now a first-class track alongside Beta and Storied. Any missing
# or unknown value still normalises to 'beta' (D687 addendum, LOCAL-727 note).
VALID_TRACKS = ('beta', 'storied', 'subscribed')


def normalize_track(value):
    """Resolve a raw track value to one of VALID_TRACKS, defaulting to 'beta'.

    Accepts None, empty/whitespace, or any case. Anything outside VALID_TRACKS
    (including missing/unknown) means 'beta', matching the long-standing default.
    """
    normalized = (value or 'beta').strip().lower()
    if normalized not in VALID_TRACKS:
        normalized = 'beta'
    return normalized


def _compat_send_file(path_or_file, **kwargs):
    """Version-tolerant send_file wrapper.

    Flask <2.0 uses ``attachment_filename``; Flask >=2.0 renamed it to
    ``download_name``.  This helper accepts either and maps to whichever the
    installed Flask supports, so the same code runs on both.
    """
    sig = _inspect.signature(_send_file)
    params = sig.parameters

    # Normalise: caller may pass either name
    download_name = kwargs.pop("download_name", None)
    attachment_filename = kwargs.pop("attachment_filename", None)
    name = download_name or attachment_filename

    if name:
        if "download_name" in params:
            kwargs["download_name"] = name
        else:
            kwargs["attachment_filename"] = name

    return _send_file(path_or_file, **kwargs)


send_file = _compat_send_file

# [GCS-KS1] Env kill switch for user-chosen stops (D591). Default OFF: unless
# USER_STOPS_ENABLED=true, a request's user-chosen stops are neutralized right at
# this HTTP boundary so the tour is generated the normal way. Local Docker sets
# the flag true (docker-compose-beta-local.yml et al.) so the Mac Mini keeps the
# feature. See user_stops_flag.py for the contract.
from user_stops_flag import neutralize_if_disabled as _neutralize_user_stops

# ARCHITECTURAL NOTE: Directory Cleanup Policy
# - ZIP files are the PRIMARY storage format in database
# - Directories are TEMPORARY for processing/extraction only
# - After successful ZIP storage in database, directories are cleaned up
# - This prevents storage bloat and maintains clean architecture
# - Tour resolution service handles ZIP files, not directories

# Inter-service URLs (env-var-driven for Cloud Run, defaults for local Docker)
TOUR_GENERATOR_URL = os.getenv('TOUR_GENERATOR_URL', 'http://development-tour-generator-1:5000')
MODERNIZED_URL = os.getenv('MODERNIZED_URL', 'http://tour-generation-modernized-1:5021')
TRANSLATION_URL = os.getenv('TRANSLATION_URL', 'http://translation-service-1:5030')
TOUR_UPDATE_URL = os.getenv('TOUR_UPDATE_URL', 'http://development-tour-update-1:5001')
USER_API_URL = os.getenv('USER_API_URL', 'http://user-api-2:5000')
COORDINATES_URL = os.getenv('COORDINATES_URL', 'http://coordinates-fromai:5004')

# [GCS-C1, 2026-10-16] A tour with no usable coordinates is INVISIBLE: tours-near
# filters on lat/lng, so the row can never be found by any listener while the app
# is told generation succeeded. Two silent holes produced exactly that, both
# proven on live Preview job 36b13113 (ClickUp wdvrdaz109):
#
#   1. The guard was `len(coordinates) < 2`, and the modernized service returns
#      [None, None] -- a list of length 2. It PASSED, the fallback never ran, and
#      the row was stored with NULL lat/lng:
#        19:13:02  Coordinates from modernized service: [None, None]
#      with no "No coordinates received" line after it. That absence is the bug.
#   2. Every failure branch of get_coordinates_direct() returns (0, 0), written
#      to the DB verbatim. 0,0 is in the Gulf of Guinea -- absent from tours-near
#      anywhere a human is, and misplotted if opened. The coordinates service it
#      calls has returned 500 on every request since it was built against
#      openai<1.0.0, so (0, 0) was the only thing it could ever produce.
#
# "Is it a 2-element list" is the wrong question. The question is whether we hold
# two real, finite numbers. 0,0 is rejected deliberately: it is the old sentinel,
# it is in the ocean, and no tour of ours is there.
def _usable_coordinates(c):
    """True only for a pair of finite, non-null, in-range, non-(0,0) numbers."""
    if not isinstance(c, (list, tuple)) or len(c) < 2:
        return False
    lat, lng = c[0], c[1]
    for v in (lat, lng):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return False
        if not math.isfinite(v):
            return False
    if lat == 0 and lng == 0:
        return False
    return -90 <= lat <= 90 and -180 <= lng <= 180


# Cloud Tasks configuration (Part B architecture)
# When GENERATION_MODE=cloud_tasks, the orchestrator enqueues to Cloud Tasks instead of threading.
# When GENERATION_MODE=thread (default), uses the original daemon-thread approach (local Docker).
GENERATION_MODE = os.getenv('GENERATION_MODE', 'thread')  # 'thread' or 'cloud_tasks'
CLOUD_TASKS_QUEUE = os.getenv('CLOUD_TASKS_QUEUE', 'tour-generation')
CLOUD_TASKS_LOCATION = os.getenv('CLOUD_TASKS_LOCATION', 'us-central1')
GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID', 'audiotours-migration')
TOUR_WORKER_URL = os.getenv('TOUR_WORKER_URL', 'https://tour-worker-60899077572.us-central1.run.app')
# Service account for Cloud Tasks OIDC auth to the worker
WORKER_SERVICE_ACCOUNT = os.getenv('WORKER_SERVICE_ACCOUNT', '')

# Job store mode: 'memory' for local Docker, 'database' for Cloud Run (multi-instance safe)
JOB_STORE_MODE = os.getenv('JOB_STORE_MODE', 'memory')


def _get_auth_headers(target_url):
    """Get authorization headers for service-to-service calls on Cloud Run.
    On local Docker, returns empty dict (no auth needed).
    On Cloud Run, fetches an identity token from the metadata server."""
    if not target_url.startswith('https://'):
        return {}  # Local Docker — no auth needed
    try:
        metadata_url = f"http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity?audience={target_url}"
        resp = requests.get(metadata_url, headers={"Metadata-Flavor": "Google"}, timeout=5)
        if resp.status_code == 200:
            return {"Authorization": f"Bearer {resp.text}"}
    except Exception as e:
        print(f"[AUTH] Failed to get identity token for {target_url}: {e}")
    return {}


def _authenticated_request(method, url, **kwargs):
    """Wrapper for requests that adds identity token for Cloud Run service-to-service calls."""
    # Extract base URL for audience (scheme + netloc)
    from urllib.parse import urlparse
    parsed = urlparse(url)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    auth_headers = _get_auth_headers(audience)
    
    headers = kwargs.get('headers', {}) or {}
    headers.update(auth_headers)
    kwargs['headers'] = headers
    
    return requests.request(method, url, **kwargs)


def _cancel_generation_job(text_job_id, reason=""):
    """[LOCAL-622] Ask the generator to stop a job the orchestrator is giving up on.

    Best-effort and non-raising: the orchestrator is already about to fail the
    request, so a failed cancel must not mask the original give-up. Flipping the
    generator's cooperative cancel flag (POST /cancel/<job_id>) stops it before
    the next spend-incurring step, so no further money is spent on a tour nobody
    will receive (D635).
    """
    if not text_job_id:
        return
    try:
        print(f"[LOCAL-622] Asking generator to stop job {text_job_id} ({reason})")
        resp = _authenticated_request(
            "POST", f"{TOUR_GENERATOR_URL}/cancel/{text_job_id}", timeout=15)
        print(f"[LOCAL-622] Cancel request returned {resp.status_code}: {resp.text[:200]}")
    except Exception as _cancel_err:
        print(f"[LOCAL-622] Cancel request failed (non-fatal): {_cancel_err}")


# Configure unbuffered logging
import sys
sys.stdout.reconfigure(line_buffering=True)

app = Flask(__name__)

# --- Wallet API Blueprint (LOCAL-68 / LOCAL-154) ---
# The Dart client calls GET /wallet/<id>, GET /wallet/<id>/transactions,
# GET /plans/available, POST /wallet/<id>/topup on this service (port 5002).
# Without this registration all wallet screens show "connection error" and
# the topup flow silently fails.
#
# Failure is logged at ERROR, not printed. A swallowed ImportError is how
# corpus mining silently degraded for two days (see D31).
try:
    from wallet_api import wallet_bp
    app.register_blueprint(wallet_bp)
    print("[ORCHESTRATOR] Wallet API blueprint registered (LOCAL-68)")
except ImportError as _wallet_err:
    import logging as _wallet_logging
    _wallet_logging.getLogger("tour_orchestrator_service").error(
        f"[LOCAL-154] Wallet API NOT registered — wallet screens will fail: {_wallet_err}"
    )
    print(f"[ORCHESTRATOR] ERROR: wallet API unavailable: {_wallet_err}")

# --- Swipe Preference Routes (LOCAL-107 / LOCAL-154) ---
# The Dart client posts to /user/<id>/stop-feedback on this service (port
# 5002). Without this registration every swipe 404s and LOCAL-105's offline
# queue retries ten times and discards it.
#
# Failure is logged at ERROR, not printed (D31, LOCAL-146).
try:
    from swipe_preference_service import register_preference_routes
    register_preference_routes(app)
    print("[ORCHESTRATOR] Preference routes registered (LOCAL-107)")
except ImportError as _pref_err:
    import logging as _pref_logging
    _pref_logging.getLogger("tour_orchestrator_service").error(
        f"[LOCAL-154] Preference routes NOT registered — every swipe will 404: {_pref_err}"
    )
    print(f"[ORCHESTRATOR] ERROR: preference routes unavailable: {_pref_err}")

# --- Tour Rating Routes (LOCAL-670) ---
# The Dart client posts to /tour/<id>/rating and reads GET /tour/<id>/rating on
# this service (port 5002). Per-TOUR 1..10 rating, alongside the per-STOP thumbs
# already handled by swipe_preference_service. Without this registration the
# rating badge shows nothing and "Rate this tour" 404s.
#
# Failure is logged at ERROR, not printed (D31, LOCAL-146).
try:
    from tour_rating_service import register_rating_routes
    register_rating_routes(app)
    print("[ORCHESTRATOR] Tour rating routes registered (LOCAL-670)")
except ImportError as _rating_err:
    import logging as _rating_logging
    _rating_logging.getLogger("tour_orchestrator_service").error(
        f"[LOCAL-670] Tour rating routes NOT registered — rating will 404: {_rating_err}"
    )
    print(f"[ORCHESTRATOR] ERROR: tour rating routes unavailable: {_rating_err}")

# [LOCAL-672] Verified reviews: text reviews with a moderation queue, one curator
# reply, "helpful" votes, the rating distribution, and the moderation queue
# visible to LEAD. All endpoints live on the orchestrator alongside the ratings
# so the app talks to one service for every per-tour judgement. Registered
# defensively so a missing module logs at ERROR and 404s the review endpoints
# only — it never takes the orchestrator down or affects ratings.
try:
    from tour_reviews_service import register_review_routes
    register_review_routes(app)
    print("[ORCHESTRATOR] Tour review routes registered (LOCAL-672)")
except ImportError as _review_err:
    import logging as _review_logging
    _review_logging.getLogger("tour_orchestrator_service").error(
        f"[LOCAL-672] Tour review routes NOT registered — reviews will 404: {_review_err}"
    )
    print(f"[ORCHESTRATOR] ERROR: tour review routes unavailable: {_review_err}")

# --- Tour Pricing / Unlock Routes (LOCAL-677) ---
# Curator paid tours: a Curator (plans.can_sell) sets/clears a price tier on
# their own tour (POST /tour/<id>/price), buyers read the price and their
# unlock/preview state, and the curator reads a Sales (unlock) count. The buy
# flow itself verifies through the existing /purchases/verify path (user-api),
# which writes tour_unlocks; these endpoints are the pricing + gating surface.
# Registered defensively — a missing module 404s only the pricing endpoints and
# never takes the orchestrator (or ratings/reviews) down.
try:
    from tour_pricing_service import register_pricing_routes
    register_pricing_routes(app)
    print("[ORCHESTRATOR] Tour pricing routes registered (LOCAL-677)")
except ImportError as _pricing_err:
    import logging as _pricing_logging
    _pricing_logging.getLogger("tour_orchestrator_service").error(
        f"[LOCAL-677] Tour pricing routes NOT registered — pricing will 404: {_pricing_err}"
    )
    print(f"[ORCHESTRATOR] ERROR: tour pricing routes unavailable: {_pricing_err}")

# --- Community Tour Routes (LOCAL-701, D663 §3) ---
# A tour generated FOR a community: tag it with community_id + visibility
# (members | public), read a community's tour list for its page, and read one
# tour's community tag. Charging is unchanged — the generate pipeline already
# charges the requesting user (the organiser). Registered defensively: a missing
# module 404s only the community-tour endpoints and never takes the orchestrator
# (or pricing/ratings/reviews) down.
try:
    from community_tours_service import register_community_tour_routes
    register_community_tour_routes(app)
    print("[ORCHESTRATOR] Community tour routes registered (LOCAL-701)")
except ImportError as _community_err:
    import logging as _community_logging
    _community_logging.getLogger("tour_orchestrator_service").error(
        f"[LOCAL-701] Community tour routes NOT registered — community tagging will 404: {_community_err}"
    )
    print(f"[ORCHESTRATOR] ERROR: community tour routes unavailable: {_community_err}")

# --- Recovery Code / Profile Portability Routes (LOCAL-695) ---
# Anonymous recovery code: the listener saves a code after their first purchase
# (POST /recovery-code/generate), and on a NEW phone restores their Listen page
# with it (POST /recovery-code/restore) — the new device is linked to the
# profile and the old one unlinked (consolidation tables), paid tours get a
# restore grant so they re-download without paying again, attempts are rate-
# limited and logged, and >2 restores in 30 days is refused. Hosted here because
# the orchestrator already owns account deletion and can import the repo-root
# consolidation module. Registered defensively — a missing module 404s only the
# recovery endpoints and never takes the orchestrator down.
try:
    from recovery_code_service import register_recovery_routes
    register_recovery_routes(app)
    print("[ORCHESTRATOR] Recovery code routes registered (LOCAL-695)")
except ImportError as _recovery_err:
    import logging as _recovery_logging
    _recovery_logging.getLogger("tour_orchestrator_service").error(
        f"[LOCAL-695] Recovery code routes NOT registered — recovery/restore will 404: {_recovery_err}"
    )
    print(f"[ORCHESTRATOR] ERROR: recovery code routes unavailable: {_recovery_err}")

# CORS headers for web platform support
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

@app.after_request
def after_request(response):
    return add_cors_headers(response)

# Handle preflight OPTIONS requests
@app.route('/health', methods=['OPTIONS'])
@app.route('/generate-complete-tour', methods=['OPTIONS'])
@app.route('/status/<job_id>', methods=['OPTIONS'])
@app.route('/download/<job_id>', methods=['OPTIONS'])
@app.route('/serve/<job_id>', methods=['OPTIONS'])
@app.route('/jobs', methods=['OPTIONS'])
@app.route('/wallet/<user_id>', methods=['OPTIONS'])
@app.route('/wallet/<user_id>/transactions', methods=['OPTIONS'])
@app.route('/wallet/<user_id>/topup', methods=['OPTIONS'])
@app.route('/plans/available', methods=['OPTIONS'])
def handle_options(*args, **kwargs):
    response = make_response()
    return add_cors_headers(response)

def sanitize_input(input_text):
    """Sanitize user input for security and filesystem safety"""
    if not input_text or not isinstance(input_text, str):
        return ""
    
    # Remove control characters and null bytes
    sanitized = re.sub(r'[\x00-\x1F\x7F]', '', input_text)
    
    # Replace filesystem-dangerous characters with underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', sanitized)
    
    # Remove script injection characters
    sanitized = re.sub(r'[<>"\']', '', sanitized)
    
    # Normalize whitespace
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    # Limit length to prevent issues
    if len(sanitized) > 200:
        sanitized = sanitized[:200].strip()
    
    return sanitized


# [LOCAL-525] Ceiling on user-chosen stops — mirrors the total_stops 1..50 range.
_MAX_USER_STOPS = 50


def validate_stops(raw):
    """Validate and sanitize a user-supplied ``stops`` list (LOCAL-525).

    Promotes the engine's forced_stops path (LOCAL-357) to a product input at the
    orchestrator boundary. Each name is run through ``sanitize_input`` for the same
    filesystem/injection safety every other user string gets.

    Contract:
      * ``None`` / missing → ``(None, None)``. Normal generation, unchanged.
      * Non-empty list of non-empty strings → ``(clean_list, None)``, order kept.
      * Anything else → ``(None, error_message)``. Rejected, never silently ignored.

    Returns:
        tuple(clean_stops_or_None, error_message_or_None)
    """
    if raw is None:
        return None, None

    if not isinstance(raw, list):
        return None, (
            "'stops' must be a list of stop names (strings). "
            f"Received {type(raw).__name__}."
        )

    if len(raw) == 0:
        return None, (
            "'stops' was provided but is empty. Omit 'stops' for automatic stop "
            "selection, or provide at least one stop name."
        )

    if len(raw) > _MAX_USER_STOPS:
        return None, (
            f"'stops' has {len(raw)} entries; the maximum is {_MAX_USER_STOPS}."
        )

    clean = []
    for i, item in enumerate(raw):
        if not isinstance(item, str):
            return None, (
                f"'stops' entry #{i + 1} must be a string, got {type(item).__name__}."
            )
        name = sanitize_input(item)
        if not name:
            return None, (
                f"'stops' entry #{i + 1} is blank after sanitization. Every stop "
                "name must contain usable text."
            )
        clean.append(name)

    return clean, None
# Log all incoming requests
@app.before_request
def log_request_info():
    print(f"\n==== REQUEST RECEIVED: {datetime.now().isoformat()} ====")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote address: {request.remote_addr}")
    print(f"User agent: {request.headers.get('User-Agent', 'Unknown')}")


# Global variables
TOURS_DIR = "/app/tours"  # Docker volume mount point
ACTIVE_JOBS = {}  # Track running jobs
_ACTIVE_GENERATION_THREADS = []  # Track in-flight generation threads for graceful shutdown
_SHUTTING_DOWN = False  # Signal that shutdown is in progress


def _graceful_shutdown(signum, frame):
    """Handle SIGTERM (Cloud Run shutdown signal) by waiting for in-flight generations."""
    global _SHUTTING_DOWN
    _SHUTTING_DOWN = True
    active = [t for t in _ACTIVE_GENERATION_THREADS if t.is_alive()]
    if active:
        print(f"[SHUTDOWN] SIGTERM received. Waiting for {len(active)} in-flight generation(s) to complete (max 240s)...")
        for t in active:
            t.join(timeout=240)  # Below Cloud Run's 300s grace period to allow clean exit
        still_active = [t for t in active if t.is_alive()]
        if still_active:
            print(f"[SHUTDOWN] WARNING: {len(still_active)} generation(s) did not finish in time.")
        else:
            print(f"[SHUTDOWN] All in-flight generations completed cleanly.")
    else:
        print(f"[SHUTDOWN] SIGTERM received. No in-flight generations. Exiting cleanly.")
    sys.exit(0)


signal.signal(signal.SIGTERM, _graceful_shutdown)


def _enqueue_cloud_task(job_id, location, tour_type, total_stops, user_id, request_string,
                        language, stops=None):
    """Enqueue a tour generation task to Cloud Tasks.
    The task will HTTP-push to tour-worker's /run-job endpoint."""
    try:
        from google.cloud import tasks_v2
        from google.protobuf import timestamp_pb2
        import datetime as dt

        client = tasks_v2.CloudTasksClient()
        parent = client.queue_path(GCP_PROJECT_ID, CLOUD_TASKS_LOCATION, CLOUD_TASKS_QUEUE)

        payload = json.dumps({
            "job_id": job_id,
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops,
            "user_id": user_id,
            "request_string": request_string,
            "language": language,
            # [LOCAL-547, 2026-09-24] Carry the listener's chosen stops onto the CLOUD
            # path too. This function did not take them, so `stops` reached the local
            # thread worker (which passes them to orchestrate_tour_async) and was
            # silently dropped the moment Cloud Tasks was the transport. The feature
            # would therefore have worked on the Mac Mini and failed in production --
            # the worst shape of bug, because local testing proves nothing about it.
            # Omitted entirely when absent, so the worker's payload is unchanged for
            # ordinary requests.
            **({"stops": stops} if stops else {})
        })

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{TOUR_WORKER_URL}/run-job",
                "headers": {"Content-Type": "application/json"},
                "body": payload.encode(),
            }
        }

        # Add OIDC token for authenticated worker access
        if WORKER_SERVICE_ACCOUNT:
            task["http_request"]["oidc_token"] = {
                "service_account_email": WORKER_SERVICE_ACCOUNT,
                "audience": TOUR_WORKER_URL,
            }

        # Set dispatch deadline (max time for the task to complete)
        task["dispatch_deadline"] = {"seconds": 900}  # 15 min

        response = client.create_task(request={"parent": parent, "task": task})
        print(f"[CLOUD_TASKS] Enqueued task for job {job_id}: {response.name}")
        return True
    except Exception as e:
        print(f"[CLOUD_TASKS] ERROR enqueuing task for job {job_id}: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False


def _create_job_in_db(job_id, location, tour_type, total_stops, user_id, request_string, language):
    """Create a job row in job_status table (for database-backed job tracking)."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        output_data = json.dumps({
            "user_id": user_id,
            "request_string": request_string,
            "language": language,
        })
        cur.execute("""
            INSERT INTO job_status (job_id, service_name, status, progress, location, tour_type, total_stops, output_data)
            VALUES (%s, 'tour-orchestrator', 'queued', 'Job queued for processing', %s, %s, %s, %s)
            ON CONFLICT (job_id) DO NOTHING
        """, (job_id, location, tour_type, total_stops, output_data))
        conn.commit()
        cur.close()
        conn.close()
        print(f"[JOB_DB] Created job row for {job_id}")
        return True
    except Exception as e:
        print(f"[JOB_DB] ERROR creating job row for {job_id}: {e}")
        return False


def _read_job_from_db(job_id):
    """Read a job from job_status table (for /status endpoint in database mode)."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT job_id, status, progress, location, tour_type, total_stops, output_data, error, created_at
            FROM job_status WHERE job_id = %s
        """, (job_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        result = {
            "job_id": row[0],
            "status": row[1],
            "progress": row[2],
            "location": row[3],
            "tour_type": row[4],
            "total_stops": row[5],
            "error": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
        }
        # Merge output_data fields
        if row[6]:
            extra = row[6] if isinstance(row[6], dict) else json.loads(row[6])
            result.update(extra)
        return result
    except Exception as e:
        print(f"[JOB_DB] ERROR reading job {job_id}: {e}")
        return None

def ensure_tours_directory():
    """Ensure the tours directory exists."""
    if not os.path.exists(TOURS_DIR):
        os.makedirs(TOURS_DIR)
        print(f"Created tours directory: {TOURS_DIR}")
    else:
        print(f"Tours directory exists: {TOURS_DIR}")

def log_job_update(job_id, status, progress):
    """Update and log the status of a job."""
    if job_id in ACTIVE_JOBS:
        ACTIVE_JOBS[job_id]["status"] = status
        ACTIVE_JOBS[job_id]["progress"] = progress
        print(f"JOB UPDATE [{job_id}]: Status={status}, Progress={progress}")
    else:
        print(f"WARNING: Attempted to update non-existent job: {job_id}")


def _set_tour_request_status(job_id, status):
    """[LOCAL-595B defect 2] Flip the orchestrator's tour_requests row (keyed on
    tour_id = job_id) to 'completed' or 'failed'. L2/Tester period caps count
    only 'completed' rows, so a 'failed'/'started' row never spends a daily or
    monthly allowance. Best-effort; failure is logged, not raised."""
    try:
        import psycopg2 as _pg
        _conn = _pg.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        _cur = _conn.cursor()
        _cur.execute("""
            UPDATE tour_requests SET status = %s, finished_at = NOW()
            WHERE tour_id = %s AND source = 'orchestrator'
        """, (status, job_id))
        _conn.commit()
        _cur.close()
        _conn.close()
        print(f"[QUOTA] tour_requests[{job_id}] status -> {status}")
    except Exception as _e:
        print(f"[QUOTA] WARNING: could not set tour_requests status={status} for {job_id}: {_e}")


def _release_generation_reservation(user_id, job_id, reason):
    """[LOCAL-595B defect 2/3] Give back the L3 fresh_used / L4 ops_used unit
    reserved at request time, because the reserved generation did not result in
    a fresh paid delivery (reason='failed' or reason='cache_hit'). Best-effort."""
    if not user_id:
        return
    try:
        from entitlements import release_operation
        release_operation(user_id, 'generate')
        print(f"[QUOTA] released generation reservation for {user_id} (job={job_id}, reason={reason})")
    except Exception as _e:
        print(f"[QUOTA] WARNING: could not release reservation for {user_id} (job={job_id}): {_e}")


# [LOCAL-606] The columns captured in a version snapshot. Centralised so the
# ensure-table DDL, the snapshot INSERT in store_audio_tour and the restore
# helper (restore_tour_version.py) all agree on the exact set.
AUDIO_TOUR_VERSION_COLUMNS = (
    "tour_content", "zip_filename", "stops_count", "lat", "lng",
)


def _ensure_versioning_objects(cur):
    """[LOCAL-606] Self-healing DDL for the replace-on-change rule (D622).

    Mirrors the self-healing pattern already used in store_audio_tour for
    audio_tour/lat/number_requested/track/tour_kind: additive, idempotent, and
    safe to run on any Postgres (Cloud SQL, Mac Mini local dev, a fresh checkout,
    or a throwaway test schema) regardless of whether a migration SQL file has
    been applied yet.

    Creates:
      * audio_tours.translation_stale BOOLEAN DEFAULT FALSE — a translation row
        (original_tour_id = some id) is flipped TRUE when its original is
        replaced, so the next translation request regenerates it. Never deletes
        the stale translation.
      * audio_tour_versions — the additive, append-only archive of every
        superseded original-row content. Each replacement inserts the OLD values
        here first, so every replacement is reversible via restore_tour_version.py.
    """
    # Additive stale flag on audio_tours.
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'audio_tours' AND column_name = 'translation_stale'
    """)
    if cur.fetchone() is None:
        print("[LOCAL-606] Adding audio_tours.translation_stale column...")
        cur.execute(
            "ALTER TABLE audio_tours "
            "ADD COLUMN translation_stale BOOLEAN NOT NULL DEFAULT FALSE"
        )

    # Append-only version archive. version_no is per-tour (1,2,3,…). The row
    # keeps the OLD content/zip/stops/lat/lng that was replaced, plus when and by
    # which job. No FK to audio_tours.id on purpose: the archive must survive
    # even if a tour row is later removed by some other process, and tests clone
    # tables individually. The (tour_id, version_no) pair is unique.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audio_tour_versions (
            id SERIAL PRIMARY KEY,
            tour_id INTEGER NOT NULL,
            version_no INTEGER NOT NULL,
            tour_content TEXT,
            zip_filename VARCHAR(512),
            stops_count INTEGER,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            replaced_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            replaced_by_job VARCHAR(128),
            CONSTRAINT uq_audio_tour_versions_tour_version UNIQUE (tour_id, version_no)
        )
    """)


def _rename_superseded_zip(old_zip_filename, version_no):
    """[LOCAL-606] Rename a replaced tour's ZIP on disk to ``<name>.v<N>.zip`` so
    it is kept, never deleted, and every replacement stays reversible.

    Returns the archived basename (what was written to audio_tour_versions), or
    the original basename unchanged if the file could not be found on disk (the
    DB row still records what the name was). Best-effort on the filesystem; the
    DB transaction is the source of truth.
    """
    if not old_zip_filename:
        return old_zip_filename
    base = os.path.basename(old_zip_filename)
    # Strip a trailing .zip (case-insensitive) and append .v<N>.zip.
    stem = base[:-4] if base.lower().endswith(".zip") else base
    archived = f"{stem}.v{version_no}.zip"
    try:
        src = os.path.join(TOURS_DIR, base)
        dst = os.path.join(TOURS_DIR, archived)
        if os.path.exists(src) and not os.path.exists(dst):
            os.rename(src, dst)
            print(f"[LOCAL-606] Renamed superseded ZIP {base} -> {archived}")
        elif not os.path.exists(src):
            print(f"[LOCAL-606] Superseded ZIP {base} not on disk; "
                  f"recording archived name {archived} in version row only")
    except Exception as _e:
        print(f"[LOCAL-606] WARNING: could not rename superseded ZIP "
              f"{base} -> {archived}: {_e}")
    return archived


def _pool_db_url():
    """Build a postgresql:// URL from this service's DB env vars.

    tour_orchestrator_service connects via discrete DB_HOST/DB_NAME/… env vars,
    but the stop-pool modules (stop_pool_store, stop_pool_sources) take a
    connection URL. Compose one from the same env the INSERT uses, so provenance
    is recorded against the SAME database the tour row was written to.
    """
    host = os.getenv('DB_HOST', 'postgres-2')
    name = os.getenv('DB_NAME', 'audiotours')
    user = os.getenv('DB_USER', 'admin')
    pwd = os.getenv('DB_PASSWORD', 'password123')
    port = os.getenv('DB_PORT', '5432')
    return f"postgresql://{user}:{pwd}@{host}:{port}/{name}"


def _record_pool_provenance(audio_tour_id, location, request_string, tour_name,
                            tour_type, tour_content, is_test):
    """[LOCAL-766 / D713] Link the pooled stops this tour delivered to its id.

    Called after the audio_tours row exists (new-insert and replacement paths),
    where the id, creator, location and tour_type are known. The stop pool store
    runs INSIDE generate_tour_text BEFORE this row exists, so provenance cannot be
    recorded there; here is the one point with both the pooled stops (parsed from
    tour_content) and the tour id. Best-effort and strictly non-fatal: a failure
    must never fail a tour that is already stored. Test rows are recorded too —
    the live test proves the rule end-to-end on is_test rows — but a NULL/empty
    content simply records nothing.
    """
    try:
        if not tour_content or not audio_tour_id:
            return
        import stop_pool_sources as provenance
        _loc = location or request_string or tour_name or ""
        # tour_type passed through from the serving path; fall back to the
        # tour_name's "- <Category> Tour" suffix so the pool_key matches the row
        # the pool stored under (the store keys on tour_type.lower()).
        _ttype = tour_type
        if not _ttype:
            _ttype = provenance._tour_type_from_tour(tour_name, tour_content)
        n = provenance.record_pool_sources(
            _pool_db_url(), _loc, _ttype or "", int(audio_tour_id), tour_content)
        print(f"  [LOCAL-766] provenance: linked {n} pooled stop(s) to tour "
              f"{audio_tour_id} (type={_ttype!r}, is_test={is_test})")
    except Exception as _prov_err:
        print(f"  [LOCAL-766] provenance record skipped (non-fatal): {_prov_err}")


def store_audio_tour(tour_name, request_string, zip_path, lat, lng, tour_content=None, stops_count=None, is_test=None, tour_kind=None, job_id=None, user_id=None, track=None, tour_type=None, location=None):
    """Store the audio tour in the database with original tour content.

    [LOCAL-727 / bug 432] ``track`` is the deployment track that produced this
    tour ('beta', 'storied' or 'subscribed'). It is part of the existing-tour
    lookup key (alongside creator and name) so tours with the same name and
    creator but different tracks never collapse into one row on the shared
    GCloud DB. When None it falls back to the ``TOUR_TRACK`` env var; any other
    value is normalised to 'beta' (LOCAL-737).

    Returns:
        dict with keys:
            success (bool): True if stored or already existed.
            existing_tour_id (int|None): If the tour already exists, its ID.
            action (str): 'inserted', 'updated', 'already_exists', or 'error'.
            error (str|None): Error message on failure.
        Legacy callers can still treat the return value as truthy/falsy via __bool__
        but the richer dict carries the distinction between "stored OK" and
        "already exists" that LOCAL-156 needs.
    """
    print(f"\n==== STORING AUDIO TOUR IN DATABASE: {datetime.now().isoformat()} ====")
    print(f"Tour name: {tour_name}")
    print(f"Request string: {request_string}")
    print(f"ZIP path: {zip_path}")
    print(f"Coordinates: lat={lat}, lng={lng}")
    print(f"Tour content length: {len(tour_content) if tour_content else 0} characters")

    def _result(success, action, existing_tour_id=None, error=None, version_no=None,
                replaced_version_no=None):
        """Build a result dict that also supports bool() for backward compat.

        [LOCAL-717 / D677 §2] version_no is the version of the CURRENT row after
        this call (1 = fresh insert, N = Nth content). [LOCAL-718 / D678]
        replaced_version_no is the version number ARCHIVED when a creator
        re-generates their own same-name tour (None otherwise). The app reads
        version_no + action == 'replaced'.
        """
        return {"success": success, "action": action,
                "existing_tour_id": existing_tour_id, "error": error,
                "version_no": version_no,
                "replaced_version_no": replaced_version_no,
                "__bool__": success}
    
    try:
        import psycopg2
        # Connect to the database
        print(f"Connecting to database...")
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        print(f"Connected to database")
        
        # Check if audio_tours table exists
        print(f"Checking if audio_tours table exists...")
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'audio_tours'
            )
        """)
        table_exists = cur.fetchone()[0]
        print(f"Table exists: {table_exists}")
        
        if not table_exists:
            # Create table if it doesn't exist
            print(f"Creating audio_tours table...")
            cur.execute("""
                CREATE TABLE audio_tours (
                    id SERIAL PRIMARY KEY,
                    tour_name VARCHAR(255) NOT NULL,
                    request_string TEXT NOT NULL,
                    audio_tour BYTEA,
                    number_requested INTEGER NOT NULL DEFAULT 0,
                    lat DOUBLE PRECISION,
                    lng DOUBLE PRECISION
                )
            """)
            print("Created audio_tours table")
            conn.commit()
            has_audio_tour = True
            has_lat = True
            has_number_requested = True
        else:
            try:
                # Check if audio_tour column exists
                print(f"Checking if audio_tour column exists...")
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'audio_tours' AND column_name = 'audio_tour'
                """)
                has_audio_tour = cur.fetchone() is not None
                print(f"audio_tour column exists: {has_audio_tour}")
                
                # Check if lat/lng columns exist
                print(f"Checking if lat column exists...")
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'audio_tours' AND column_name = 'lat'
                """)
                has_lat = cur.fetchone() is not None
                print(f"lat column exists: {has_lat}")
                
                # Check if number_requested column exists
                print(f"Checking if number_requested column exists...")
                cur.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'audio_tours' AND column_name = 'number_requested'
                """)
                has_number_requested = cur.fetchone() is not None
                print(f"number_requested column exists: {has_number_requested}")
                
                # Add missing columns if needed
                if not has_audio_tour:
                    print(f"Adding audio_tour column...")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN audio_tour BYTEA")
                    print("Added audio_tour column")
                
                if not has_lat:
                    print(f"Adding lat/lng columns...")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN lat DOUBLE PRECISION")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN lng DOUBLE PRECISION")
                    print("Added lat/lng columns")
                
                if not has_number_requested:
                    print(f"Adding number_requested column...")
                    cur.execute("ALTER TABLE audio_tours ADD COLUMN number_requested INTEGER NOT NULL DEFAULT 0")
                    print("Added number_requested column")
                
                conn.commit()
                print(f"Table structure updated")
            except Exception as e:
                print(f"Error checking table structure: {e}")
                print(f"Traceback: {traceback.format_exc()}")
                conn.rollback()
        
        # Check if tour_content column exists
        print(f"Checking if tour_content column exists...")
        cur.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'audio_tours' AND column_name = 'tour_content'
        """)
        has_tour_content = cur.fetchone() is not None
        print(f"tour_content column exists: {has_tour_content}")

        # Track B: self-healing add, same pattern as audio_tour/lat/number_requested
        # above — guarantees this INSERT works on any Postgres (Cloud SQL, Mac
        # Mini local dev, a fresh checkout) regardless of whether migration/sql/007
        # has been run against it yet.
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'audio_tours' AND column_name = 'track'
        """)
        has_track = cur.fetchone() is not None
        if not has_track:
            print(f"Adding track column...")
            cur.execute("ALTER TABLE audio_tours ADD COLUMN track VARCHAR(16) NOT NULL DEFAULT 'beta'")
            conn.commit()
            print("Added track column")

        # [LOCAL-582] tour_kind: 'full' (default — a normal multi-stop tour) or
        # 'overview' (rung 3 — one sourced orientation stop from the venue's own
        # site when works could not be verified). Additive, self-healing column so
        # this INSERT works on any Postgres whether or not the migration SQL has run.
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'audio_tours' AND column_name = 'tour_kind'
        """)
        has_tour_kind = cur.fetchone() is not None
        if not has_tour_kind:
            print(f"Adding tour_kind column...")
            cur.execute("ALTER TABLE audio_tours ADD COLUMN tour_kind VARCHAR(16) NOT NULL DEFAULT 'full'")
            conn.commit()
            has_tour_kind = True
            print("Added tour_kind column")
        _tour_kind_value = (tour_kind or 'full').strip().lower()
        if _tour_kind_value not in ('full', 'overview'):
            _tour_kind_value = 'full'

        # [LOCAL-718 / D678] creator_user_id records WHO created the tour. Set at
        # INSERT from the request's user_id; the existing-tour lookup is scoped by
        # it so a tour is only ever versioned by its OWN creator. Self-healing,
        # additive column so this works on any Postgres whether or not migration
        # 041 has run. NULL creator = "unknown creator" (existing/backfilled rows).
        cur.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'audio_tours' AND column_name = 'creator_user_id'
        """)
        has_creator_user_id = cur.fetchone() is not None
        if not has_creator_user_id:
            print(f"Adding creator_user_id column...")
            cur.execute("ALTER TABLE audio_tours ADD COLUMN creator_user_id TEXT")
            conn.commit()
            has_creator_user_id = True
            print("Added creator_user_id column")
        # Normalise: treat empty/whitespace user_id as NULL (unknown creator).
        _creator_user_id = (user_id or '').strip() or None

        # [LOCAL-727 / bug 432] Resolve the deployment track BEFORE the
        # existing-tour lookup so the lookup can be scoped by it. `track` is
        # per-DEPLOYMENT, not per-request: Beta and Storied are separate Cloud
        # Run services that each always write their own value (TRACK_B_STORIED_
        # VS_BETA.md), but they SHARE the GCloud DB. The explicit `track=`
        # argument (passed by the serving path) wins; otherwise fall back to the
        # TOUR_TRACK env var, exactly as the INSERT path has always done. Any
        # value other than a known track ('beta'/'storied'/'subscribed') is
        # normalised to 'beta' (LOCAL-737).
        _track = normalize_track(track if track is not None else os.getenv('TOUR_TRACK', 'beta'))

        # [LOCAL-606] Make sure the versioning archive + stale flag exist before
        # we may need them in the existing-row branch. Self-healing, additive.
        _ensure_versioning_objects(cur)
        conn.commit()

        # [LOCAL-727] Self-heal the `track` column here too (same additive,
        # idempotent pattern as the Track-B block above) so the track-scoped
        # lookup below works on any Postgres whether or not migration 007/043 has
        # run against it. Existing/backfilled rows default to 'beta'.
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'audio_tours' AND column_name = 'track'
        """)
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE audio_tours ADD COLUMN track VARCHAR(16) NOT NULL DEFAULT 'beta'")
            conn.commit()

        # [LOCAL-156] Check if tour already exists using the SAME logic as the unique index:
        # lower(tour_name) WHERE original_tour_id IS NULL.
        # Previously this checked (tour_name, request_string) with case-sensitive match,
        # which diverged from the partial unique index uq_audio_tours_original_name.
        # [LOCAL-606] Also pull the stored content/zip/stops/lat/lng so the
        # existing-row branch can decide: replace (text differs) vs increment
        # (byte-identical cache hit).
        # [LOCAL-718 / D678] Scoped by creator_user_id: a tour belongs to its
        # creator. A DIFFERENT creator (or a NULL request creator) never matches
        # and falls through to the INSERT path = a NEW, separate tour.
        # [LOCAL-727 / bug 432] NOW ALSO scoped by `track`. On the shared GCloud
        # DB a Beta tour and a Storied tour can hold the SAME name under the SAME
        # (non-NULL) creator; without the track in the key the second track's
        # store matched the first track's row and REPLACED it, mixing columns and
        # making the first track's tour vanish while reporting success. With
        # `AND track = %s` a different track always falls through to INSERT and
        # gets its own row. FOR UPDATE takes a row lock so two concurrent stores
        # of the SAME (name, creator, track) serialise on the existing row
        # instead of racing to replace it and mixing columns; same-track
        # identical requests (the versioning case) are then handled one at a time.
        print(f"Checking if tour already exists (case-insensitive, creator- and track-scoped, matching index)...")
        cur.execute(
            "SELECT id, tour_content, zip_filename, stops_count, lat, lng "
            "FROM audio_tours "
            "WHERE lower(tour_name) = lower(%s) AND creator_user_id = %s "
            "AND track = %s AND original_tour_id IS NULL "
            "FOR UPDATE",
            (tour_name, _creator_user_id, _track)
        )
        existing_tour = cur.fetchone()
        print(f"Existing tour (creator+track-scoped check, creator={_creator_user_id!r}, "
              f"track={_track!r}): {existing_tour[0] if existing_tour else None}")

        # [LEAD 2026-10-07] A TEST request must never touch a real tour. The LOCAL-611
        # canary's McMullen run (is_test) replaced Michael's tour 399 via the LOCAL-606
        # replace-on-change branch and nulled its coordinates. When the request is a
        # test and the matching row is real (is_test IS NOT TRUE), store the test under
        # its own name instead of replacing/incrementing the real one.
        if existing_tour and is_test:
            cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (existing_tour[0],))
            _ex_is_test = (cur.fetchone() or [None])[0]
            if _ex_is_test is not True:
                tour_name = f"{tour_name} [TEST {(job_id or 'x')[:8]}]"
                print(f"[LEAD] test request matched REAL tour id={existing_tour[0]} — storing as separate test row {tour_name!r}")
                existing_tour = None

        # [LOCAL-50] persist zip_filename for deterministic resolution
        zip_filename = os.path.basename(zip_path)

        # [LOCAL-606 / D622] Existing-row branch: a fresh/newly-assembled delivery
        # whose text DIFFERS from the stored row REPLACES the row's content, ZIP
        # and stops_count (and sets lat/lng if they are NULL). The old version is
        # archived first and the old ZIP is renamed <name>.v<N>.zip — never
        # deleted — so the replacement is reversible. A byte-identical cache hit
        # keeps the pre-606 behaviour: just increment number_requested.
        # Share code (shared_tours) and the tour id are untouched, so curator
        # links keep working and point at the improved tour.
        if existing_tour:
            (existing_id, old_content, old_zip, old_stops,
             old_lat, old_lng) = existing_tour

            # Normalise for the byte-identical comparison. Treat NULL stored
            # content as "no content yet" → always a replacement so a row that
            # predates tour_content gets healed.
            _new_text = tour_content if tour_content is not None else ""
            _old_text = old_content if old_content is not None else None
            text_identical = (_old_text is not None and _old_text == _new_text)

            if text_identical:
                print(f"[LOCAL-156] Tour already exists (id={existing_id}) and text is "
                      f"byte-identical. Incrementing number_requested; no replacement.")
                cur.execute(
                    "UPDATE audio_tours SET number_requested = number_requested + 1 WHERE id = %s",
                    (existing_id,)
                )
                # [LOCAL-717 / D677 §2] The current version of an unchanged row is
                # the number of archived versions + 1 (no new version is created).
                cur.execute(
                    "SELECT COALESCE(MAX(version_no), 0) + 1 "
                    "FROM audio_tour_versions WHERE tour_id = %s",
                    (existing_id,)
                )
                _current_version = cur.fetchone()[0]
                conn.commit()
                cur.close()
                conn.close()
                print(f"==== AUDIO TOUR ALREADY EXISTS — REUSING id={existing_id} "
                      f"(version {_current_version}) ====")
                return _result(success=True, action="already_exists",
                               existing_tour_id=existing_id,
                               version_no=_current_version)

            # --- Replacement path (text differs or stored content was NULL) ---
            print(f"[LOCAL-606] Tour id={existing_id} regenerated with DIFFERENT text "
                  f"(old_len={len(_old_text) if _old_text is not None else 'NULL'}, "
                  f"new_len={len(_new_text)}). Replacing stored content; archiving old version.")

            # Read the new ZIP as binary data for the row update.
            print(f"Reading ZIP file: {zip_path}")
            print(f"File exists: {os.path.exists(zip_path)}")
            print(f"File size: {os.path.getsize(zip_path) if os.path.exists(zip_path) else 'N/A'}")
            with open(zip_path, "rb") as f:
                zip_data = f.read()
            print(f"Read {len(zip_data)} bytes from ZIP file")

            _job_id = job_id or os.getenv('CURRENT_JOB_ID') or request_string

            try:
                # Single transaction: version insert + row update + stale flag.
                # Next version number for this tour.
                cur.execute(
                    "SELECT COALESCE(MAX(version_no), 0) + 1 "
                    "FROM audio_tour_versions WHERE tour_id = %s",
                    (existing_id,)
                )
                next_version = cur.fetchone()[0]

                # Rename the superseded ZIP on disk to <name>.v<N>.zip and record
                # the archived name in the version row (best-effort on disk; the
                # DB row is authoritative).
                archived_zip = _rename_superseded_zip(old_zip, next_version)

                # Archive the OLD content first — reversibility invariant.
                cur.execute(
                    """
                    INSERT INTO audio_tour_versions
                        (tour_id, version_no, tour_content, zip_filename,
                         stops_count, lat, lng, replaced_by_job)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (existing_id, next_version, old_content, archived_zip,
                     old_stops, old_lat, old_lng, str(_job_id)[:128])
                )

                # Replace the row's content/zip/stops_count; set lat/lng only if
                # they were NULL (D622: "sets lat/lng if they are NULL"). Keep
                # id, tour_name, share code, original_tour_id unchanged, and bump
                # number_requested like any served delivery.
                cur.execute(
                    """
                    UPDATE audio_tours
                    SET tour_content = %s,
                        audio_tour = %s,
                        zip_filename = %s,
                        stops_count = %s,
                        lat = COALESCE(lat, %s),
                        lng = COALESCE(lng, %s),
                        number_requested = number_requested + 1
                    WHERE id = %s
                    """,
                    (tour_content, psycopg2.Binary(zip_data), zip_filename,
                     stops_count, lat, lng, existing_id)
                )

                # [LOCAL-685] New content → the evaluated score is stale; clear it so
                # the background scorer (tour_editor_score.py --backfill) re-scores.
                # SAVEPOINT: a schema without the column must not abort the replace.
                cur.execute("SAVEPOINT clear_editor_score")
                try:
                    cur.execute("UPDATE audio_tours SET editor_score = NULL WHERE id = %s",
                                (existing_id,))
                    cur.execute("RELEASE SAVEPOINT clear_editor_score")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT clear_editor_score")

                # [LOCAL-724 item 4] The tour's TEXT just changed, so its old
                # content rating is stale. Re-rate it now, in this same
                # transaction, before the replacement commits — so the edited
                # tour is never listed under a rating earned by its previous
                # text. rate_tour_row clears/overwrites content_rating,
                # review_status, content_rated_at; it never raises and never
                # commits. If it cannot rate (model error / old schema), the row
                # keeps its prior rating and the launchd backfill re-rates later.
                try:
                    import tour_content_rating
                    _redetail = tour_content_rating.rate_tour_row(
                        cur, existing_id, tour_name, tour_content, stops_count)
                    if _redetail is None:
                        # Could not re-rate synchronously: do NOT keep showing the
                        # tour under its stale rating. Hold it (clear + pending)
                        # until the backfill re-rates it.
                        tour_content_rating.clear_rating(cur, existing_id)
                except Exception as _rerate_err:
                    print(f"[LOCAL-724] re-rate skipped for tour {existing_id}: "
                          f"{_rerate_err}")

                # Flag translations (original_tour_id = this id) stale so the next
                # translation request regenerates them. Never deleted.
                cur.execute(
                    "UPDATE audio_tours SET translation_stale = TRUE "
                    "WHERE original_tour_id = %s",
                    (existing_id,)
                )
                stale_count = cur.rowcount

                conn.commit()
                print(f"[LOCAL-606] Replaced tour id={existing_id} content "
                      f"(version {next_version} archived, old ZIP -> {archived_zip}, "
                      f"{stale_count} translation(s) flagged stale).")
                cur.close()
                conn.close()
                print(f"==== AUDIO TOUR CONTENT REPLACED — id={existing_id} ====")
                # [LOCAL-766 / D713] Record which pooled stops this (replaced)
                # tour delivered, so the delivery rule can protect them if this
                # tour is community/priced. After the row is committed/closed;
                # non-fatal.
                _record_pool_provenance(existing_id, location, request_string,
                                        tour_name, tour_type, tour_content, is_test)
                # [LOCAL-717] live row is version next_version + 1; [LOCAL-718] the
                # archived (old) content is version next_version.
                return _result(success=True, action="replaced",
                               existing_tour_id=existing_id,
                               version_no=next_version + 1,
                               replaced_version_no=next_version)
            except Exception as _replace_err:
                conn.rollback()
                print(f"[LOCAL-606] ERROR during replacement of id={existing_id}: {_replace_err}")
                print(f"Traceback: {traceback.format_exc()}")
                cur.close()
                conn.close()
                return _result(success=False, action="error", existing_tour_id=existing_id,
                               error=str(_replace_err))

        # Read the ZIP file as binary data (new-insert path)
        print(f"Reading ZIP file: {zip_path}")
        print(f"File exists: {os.path.exists(zip_path)}")
        print(f"File size: {os.path.getsize(zip_path) if os.path.exists(zip_path) else 'N/A'}")
        with open(zip_path, "rb") as f:
            zip_data = f.read()
        print(f"Read {len(zip_data)} bytes from ZIP file")

        # Insert new tour (existing_tour case already returned above)
        print(f"Inserting new tour...")
        # LOCAL-103: is_test from request param takes precedence; env var is fallback
        if is_test is not None:
            _is_test_mode = is_test
        else:
            _is_test_mode = os.getenv('TOUR_TEST_MODE', 'false').lower() == 'true'
        # Track B: which deployment produced this row — 'beta' (default, current
        # production) or 'storied' (the comparison track). Set per-deployment via
        # env var, NOT per-request — Beta and Storied are separate Cloud Run
        # services (TRACK_B_STORIED_VS_BETA.md), each always writing their own
        # value. Distinct from storied_mode above, which is Track A's story-
        # pipeline quality flag and can vary per-request within either track.
        # [LOCAL-727] `_track` was already resolved (track= arg or TOUR_TRACK env)
        # and normalised BEFORE the existing-tour lookup so the lookup is
        # track-scoped. Reuse that exact value here — the INSERT must store the
        # SAME track the lookup keyed on, or the row could be found under one
        # track and written under another.
        if has_audio_tour and has_lat and has_number_requested and has_tour_content:
            cur.execute(
                """
                INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng,
                    tour_content, content_language, storied_mode, stops_count, zip_filename, is_test, track, tour_kind,
                    creator_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (tour_name, request_string, psycopg2.Binary(zip_data), 1, lat, lng, tour_content, 'en',
                 os.getenv('STORIED_MODE', 'false').lower() == 'true', stops_count, zip_filename, _is_test_mode, _track,
                 _tour_kind_value, _creator_user_id)
            )
        elif has_audio_tour and has_lat and has_number_requested:
            cur.execute(
                """
                INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng, zip_filename, is_test, track, creator_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (tour_name, request_string, psycopg2.Binary(zip_data), 1, lat, lng, zip_filename, _is_test_mode, _track, _creator_user_id)
            )
        else:
            # Fallback if columns don't exist
            cur.execute(
                """
                INSERT INTO audio_tours (tour_name, request_string, is_test, track, creator_user_id)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (tour_name, request_string, _is_test_mode, _track, _creator_user_id)
            )
        # [LOCAL-711 / D673] Capture the new tour's id so short_title can be
        # filled after commit. RETURNING id is additive — every branch now
        # returns the row id; a failure to read it must never fail the store.
        try:
            _new_tour_id = cur.fetchone()[0]
        except Exception:
            _new_tour_id = None
        print(f"Inserted new tour: {tour_name} (zip={zip_filename}, is_test={_is_test_mode})")

        # [LOCAL-724 items 1 & 2] Rate this new ORIGINAL tour BEFORE the row is
        # committed, i.e. before it can appear in /tours-near. The rater runs
        # here in the serving path (not the Mac Mini launchd tick), so it also
        # works on GCloud; the OpenAI key is read from the environment and never
        # written. Synchronous and in THIS transaction so the row is never
        # listable unrated. Non-blocking by design: rate_tour_row never raises.
        # [LOCAL-724B defect 2] If it CANNOT rate (short text, model error, no
        # key, old schema) we no longer commit the row unrated (unrated reads as
        # general and would list); instead we HOLD it (clear_rating -> NULL +
        # review_status 'pending'), exactly as the edit path does, so it is not
        # listable until the launchd backfill rates it. Test rows are skipped,
        # exactly like the launchd backfill (is_test IS NOT TRUE).
        if _new_tour_id is not None and not _is_test_mode:
            try:
                import tour_content_rating
                _ndetail = tour_content_rating.rate_tour_row(
                    cur, _new_tour_id, tour_name, tour_content, stops_count)
                if _ndetail is None:
                    # [LOCAL-724B defect 2] The rater could not rate this new
                    # ORIGINAL (no OpenAI key, model error, or a schema without
                    # the 027 columns). The approved policy is "nothing lists
                    # before it is rated": an unrated row reads as general in the
                    # listing layer and would be shown. HOLD it instead — exactly
                    # as the edit/replace path does — by clearing to NULL +
                    # review_status 'pending', so it is NOT listable until the
                    # launchd backfill rates it (and, if general, un-holds it).
                    # Short text (< 200 chars) also lands here: held, backfill
                    # decides. clear_rating never raises and never commits, so a
                    # schema without the columns simply leaves the row as-is.
                    tour_content_rating.clear_rating(cur, _new_tour_id)
            except Exception as _rate_err:
                # Defensive: the import or call must never fail the store.
                print(f"[LOCAL-724] content rating skipped for tour "
                      f"{_new_tour_id}: {_rate_err}")

        # Commit the transaction (the rating, if any, commits atomically with the
        # row — so the tour is rated the instant it becomes listable).
        print(f"Committing transaction...")
        conn.commit()
        print(f"Transaction committed")

        # [LOCAL-711 / D673] Write the server short_title for this new ORIGINAL
        # tour. One cheap LLM call (gpt-4o-mini class), AFTER the tour is already
        # committed, and strictly non-blocking: any failure is logged and the
        # column stays NULL (the app falls back to its own shortTourTitle()).
        # Skipped for test rows and when the id could not be read.
        if _new_tour_id is not None and not _is_test_mode:
            try:
                from tour_short_title import make_short_title_only, _tour_type_from_name
                _stype = _tour_type_from_name(tour_name)
                _short = make_short_title_only(tour_name, request_string, _stype)
                if _short:
                    cur.execute(
                        "UPDATE audio_tours SET short_title = %s WHERE id = %s",
                        (_short, _new_tour_id))
                    conn.commit()
                    print(f"[LOCAL-711] short_title for tour {_new_tour_id}: {_short!r}")
                else:
                    print(f"[LOCAL-711] short_title left NULL for tour {_new_tour_id} "
                          f"(generation returned nothing)")
            except Exception as _st_err:
                # Never let the short_title step affect the stored tour.
                try:
                    conn.rollback()
                except Exception:
                    pass
                print(f"[LOCAL-711] short_title step skipped for tour {_new_tour_id}: {_st_err}")
        
        # Close cursor and connection
        print(f"Closing database connection...")
        cur.close()
        conn.close()
        print(f"Database connection closed")
        
        print(f"==== AUDIO TOUR STORED SUCCESSFULLY ====")
        # [LOCAL-766 / D713] Record which pooled stops this new tour delivered,
        # so the delivery rule can protect them when this tour is community or
        # priced (now or later). After commit + close; strictly non-fatal.
        _record_pool_provenance(_new_tour_id, location, request_string, tour_name,
                                tour_type, tour_content, is_test)
        # [LOCAL-717 / D677 §2] A brand-new tour is version 1.
        return _result(success=True, action="inserted", version_no=1)
        
    except Exception as e:
        print(f"ERROR storing audio tour: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return _result(success=False, action="error", error=str(e))


def link_stop_metrics_to_tour(tour_id, job_id):
    """LOCAL-128: Set tour_id on stop_metrics rows that were written before the tour existed.

    The evaluator in generate_tour_text_service writes stop_metrics with job_id
    but cannot set tour_id (the tour row doesn't exist yet). After store_audio_tour
    creates the tour row, this function backfills the link.

    Returns the number of rows updated, or -1 on error.
    """
    import psycopg2
    try:
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        cur.execute(
            "UPDATE stop_metrics SET tour_id = %s WHERE job_id = %s AND tour_id IS NULL",
            (tour_id, job_id)
        )
        updated = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        return updated
    except Exception as e:
        print(f"[LOCAL-128] link_stop_metrics_to_tour failed: {e}")
        return -1


def orchestrate_tour_async(job_id, location, tour_type, total_stops, user_id=None, request_string=None, language='en', persona=None, is_test=None, stops=None, mode=None):
    """Orchestrate the complete tour generation pipeline asynchronously."""
    print(f"\n==== ORCHESTRATE_TOUR_ASYNC STARTED: {datetime.now().isoformat()} ====")
    print(f"Parameters:")
    print(f"  job_id: {job_id}")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  total_stops: {total_stops}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")
    print(f"  language: {language}")
    print(f"  persona: {persona}")
    # [LOCAL-595B defect 3] Set true if the tour is served from cache / stop pool.
    # Used at the completed transition to decide whether the reserved pack unit
    # stands (fresh delivery) or was already released (cache hit).
    _was_cache_hit = False
    try:
        ACTIVE_JOBS[job_id]["status"] = "processing"
        ACTIVE_JOBS[job_id]["progress"] = "Starting complete tour generation pipeline..."
        
        # Step 1: Generate tour text first, then process with modernized service
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 1/5: Generating tour text...")
        generate_data = {
            "location": location,
            "tour_type": tour_type,
            "total_stops": total_stops
        }
        # [S81] Forward user_id so downstream tour-generator can perform persona lookup
        if user_id:
            generate_data["user_id"] = user_id
        # [S81] Forward persona for direct-pass cases (skips DB lookup in tour-generator)
        if persona:
            generate_data["persona"] = persona
        # [LOCAL-525] Forward user-chosen stops (validated at the orchestrator
        # boundary). The tour-generator re-validates and passes them to the engine
        # as forced_stops. Absent → omitted → normal generation, unchanged.
        if stops:
            generate_data["stops"] = stops
        # [LOCAL-597] Forward the generation mode. 'by_reference' makes the
        # generator reuse already-researched stops only (zero grounding, zero
        # SERP). Absent/None → normal generation.
        if mode:
            generate_data["mode"] = mode
        
        print(f"Calling tour text generator API: {datetime.now().isoformat()}")
        print(f"Request data: {generate_data}")
        response = _authenticated_request("POST", f"{TOUR_GENERATOR_URL}/generate",
            headers={"Content-Type": "application/json"},
            json=generate_data,
            timeout=60
        )
        
        print(f"Tour generator API response: {response.status_code}")
        print(f"Response content: {response.text[:1000]}")
        if response.status_code != 200:
            raise Exception(f"Error generating tour: {response.text}")
        
        job_data = response.json()
        job_id_1 = job_data["job_id"]
        ACTIVE_JOBS[job_id]["text_job_id"] = job_id_1
        print(f"Tour text generator job ID: {job_id_1}")
        
        # Wait for text generation to complete
        ACTIVE_JOBS[job_id]["progress"] = "Waiting for tour text generation..."
        coordinates = None
        poll_count = 0
        tour_file = None
        _consecutive_poll_failures_1 = 0
        # [LOCAL-547, 2026-09-23] Was 6, commented "~1 minute of unreachable generator".
        # The arithmetic never matched the comment -- each failure costs a 30s timeout
        # plus a 10s sleep, so 6 failures is ~4 minutes, not 1 -- and more importantly
        # the thing being measured is NOT reachability. The status endpoint is trivial;
        # what makes it time out is the generator's own event loop being saturated by
        # the generation it is being asked about. Busy is not dead.
        #
        # Measured tonight on a REAL request: Museum of Fine Arts, Boston (145 canonical
        # titles, 689,968 chars of corpus) starved the status endpoint for 200s+ and the
        # orchestrator killed a job the generator was still successfully working on --
        # the tour text was being written while the caller was told it had failed. Any
        # large museum hits this, so it is a production defect and not a test artifact.
        #
        # Raised to cover observed generation time. The loop is still bounded: the
        # absolute ceiling below stops it hanging forever if the generator really is
        # dead, which is what the original guard was for.
        _MAX_CONSECUTIVE_POLL_FAILURES = 30
        # [LOCAL-622] Progress-based polling. D635: a fixed 20-minute wall killed a
        # tour the generator FINISHED — it had merely spent 663.4s stuck in
        # external_lookups (now budget-capped), and the orchestrator counted that
        # against an absolute clock. The orchestrator must never abandon a LIVE
        # generation. We now give up ONLY when the generator has reported no new
        # progress for 5 minutes (a true stall), and keep a 40-minute absolute cap
        # as the last-resort backstop against a wedged process. Any observed
        # progress — a changed progress string or a newer updated_at — resets the
        # stall clock, so a slow-but-advancing tour runs to completion.
        _POLL_STALL_LIMIT = timedelta(minutes=5)      # no-progress give-up
        _POLL_ABSOLUTE_CAP = timedelta(minutes=40)    # hard backstop
        _poll_started_at = datetime.now()
        _last_progress_marker = None                  # (progress_str, updated_at)
        _last_progress_at = datetime.now()
        _POLL_TIMEOUT = 30  # seconds; status endpoint is trivial, this measures event-loop busy-ness
        _poll_failure_start_1 = None
        while True:
            poll_count += 1
            _now = datetime.now()
            _stalled_for = _now - _last_progress_at
            _ran_for = _now - _poll_started_at
            # Give up only on a real stall, or at the absolute backstop. On
            # either, tell the generator job to STOP so no further spend happens
            # on a tour nobody will receive (D635).
            if _stalled_for > _POLL_STALL_LIMIT or _ran_for > _POLL_ABSOLUTE_CAP:
                _reason = ("no progress for "
                           f"{_stalled_for.total_seconds() / 60:.1f} min"
                           if _stalled_for > _POLL_STALL_LIMIT
                           else f"absolute {_POLL_ABSOLUTE_CAP.total_seconds() / 60:.0f}-minute cap")
                _cancel_generation_job(job_id_1, reason=_reason)
                raise Exception(
                    f"Text-generation abandoned after {poll_count} polls — {_reason}. "
                    f"The generator job was asked to stop. (ran "
                    f"{_ran_for.total_seconds() / 60:.1f} min, last progress "
                    f"{_stalled_for.total_seconds() / 60:.1f} min ago.)"
                )
            print(f"Checking tour text generator status: {datetime.now().isoformat()} (Poll #{poll_count})")
            try:
                status_response = _authenticated_request("GET", f"{TOUR_GENERATOR_URL}/status/{job_id_1}", timeout=_POLL_TIMEOUT)
            except (requests.Timeout, requests.ConnectionError) as poll_err:
                _consecutive_poll_failures_1 += 1
                if _poll_failure_start_1 is None:
                    _poll_failure_start_1 = datetime.now()
                print(
                    f"[POLL-RESILIENCE] Text-gen status poll #{poll_count} failed "
                    f"({type(poll_err).__name__}), consecutive failures: "
                    f"{_consecutive_poll_failures_1}/{_MAX_CONSECUTIVE_POLL_FAILURES}"
                )
                if _consecutive_poll_failures_1 >= _MAX_CONSECUTIVE_POLL_FAILURES:
                    elapsed = (datetime.now() - _poll_failure_start_1).total_seconds()
                    raise Exception(
                        f"Text-generation status polling failed: "
                        f"{_consecutive_poll_failures_1} consecutive poll failures "
                        f"over {elapsed:.0f}s. Last error: {poll_err}"
                    )
                time.sleep(10)
                continue
            # Successful network round-trip — reset consecutive failure counter
            _consecutive_poll_failures_1 = 0
            _poll_failure_start_1 = None
            print(f"Status response: {status_response.status_code}")
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                print(f"Status data: {status_data}")
                
                if status_data["status"] == "completed":
                    tour_file = status_data.get("output_file")
                    if "coordinates" in status_data:
                        coordinates = status_data["coordinates"]
                        print(f"Received coordinates from tour generator: {coordinates}")
                    print(f"Tour text generation completed: {datetime.now().isoformat()}")
                    break
                elif status_data["status"] == "error":
                    error_msg = f"Error in tour text generation: {status_data.get('error', 'Unknown error')}"
                    print(f"ERROR: {error_msg}")
                    # [LOCAL-580] Pass the generator's structured failure through to the app's /status
                    # poll (LOCAL-581 reads message > error and shows suggestion as a button). Without
                    # this the app only ever saw the prefixed string above, and no suggestion.
                    for _k in ("error_code", "message", "suggestion"):
                        if status_data.get(_k) is not None:
                            ACTIVE_JOBS[job_id][_k] = status_data[_k]
                    raise Exception(error_msg)
                else:
                    progress = status_data.get('progress', 'Processing...')
                    print(f"Tour text generation in progress: {progress}")
                    ACTIVE_JOBS[job_id]["progress"] = f"Text generation: {progress}"
                    # [LOCAL-622] Advancing progress resets the stall clock. We
                    # treat EITHER a changed progress string OR a newer updated_at
                    # as "the generator is alive and working". updated_at is the
                    # stronger signal (DB-backed store) but may be absent, so the
                    # progress-string change is the always-available fallback.
                    _marker = (progress, status_data.get('updated_at'), status_data.get('heartbeat_at'))  # heartbeat: worker thread alive (LEAD 2026-10-08)
                    if _marker != _last_progress_marker:
                        _last_progress_marker = _marker
                        _last_progress_at = datetime.now()
                    time.sleep(10)
            else:
                error_msg = f"Error checking text generation status: {status_response.text}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
        
        # Step 1.5: Process with modernized service
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 1.5/5: Processing with modernized service...")
        if not tour_file:
            raise Exception("No tour file received from text generator")
        
        # Prefer tour_content (HTTP-based, Cloud Run compatible) over tour_file (volume-based)
        tour_content = status_data.get("tour_content")
        # [LOCAL-582] Carry the generator's tour_kind ('full' | 'overview') through
        # to the DB row. An overview is a legitimate delivery (rung 3), labelled
        # honestly rather than stored as a normal tour.
        ACTIVE_JOBS[job_id]["tour_kind"] = status_data.get("tour_kind", "full") or "full"
        if tour_content:
            modernized_data = {"tour_content": tour_content}
            print(f"Using tour_content for modernized service ({len(tour_content)} chars)")
        else:
            modernized_data = {"tour_file": tour_file}
            print(f"Using tour_file for modernized service: {tour_file}")
        
        # [LOCAL-323] Forward user_id and job_id for TTS cost attribution
        if user_id:
            modernized_data["user_id"] = user_id
        modernized_data["job_id"] = job_id

        print(f"Calling MODERNIZED service: {datetime.now().isoformat()}")
        modernized_response = _authenticated_request("POST", f"{MODERNIZED_URL}/process",
            headers={"Content-Type": "application/json"},
            json=modernized_data,
            timeout=60
        )
        
        if modernized_response.status_code != 200:
            raise Exception(f"Error calling modernized service: {modernized_response.text}")
        
        modernized_job_data = modernized_response.json()
        modernized_job_id = modernized_job_data["job_id"]
        print(f"Modernized service job ID: {modernized_job_id}")
        
        # Wait for modernized processing to complete
        ACTIVE_JOBS[job_id]["progress"] = "Waiting for modernized processing..."
        _consecutive_poll_failures_2 = 0
        _poll_failure_start_2 = None
        while True:
            try:
                modernized_status_response = _authenticated_request("GET", f"{MODERNIZED_URL}/status/{modernized_job_id}", timeout=_POLL_TIMEOUT)
            except (requests.Timeout, requests.ConnectionError) as poll_err:
                _consecutive_poll_failures_2 += 1
                if _poll_failure_start_2 is None:
                    _poll_failure_start_2 = datetime.now()
                print(
                    f"[POLL-RESILIENCE] Modernized status poll failed "
                    f"({type(poll_err).__name__}), consecutive failures: "
                    f"{_consecutive_poll_failures_2}/{_MAX_CONSECUTIVE_POLL_FAILURES}"
                )
                if _consecutive_poll_failures_2 >= _MAX_CONSECUTIVE_POLL_FAILURES:
                    elapsed = (datetime.now() - _poll_failure_start_2).total_seconds()
                    raise Exception(
                        f"Modernized-service status polling failed: "
                        f"{_consecutive_poll_failures_2} consecutive poll failures "
                        f"over {elapsed:.0f}s. Last error: {poll_err}"
                    )
                time.sleep(5)
                continue
            # Successful network round-trip — reset consecutive failure counter
            _consecutive_poll_failures_2 = 0
            _poll_failure_start_2 = None
            
            if modernized_status_response.status_code == 200:
                modernized_status_data = modernized_status_response.json()
                
                if modernized_status_data["status"] == "completed":
                    print(f"Modernized processing completed: {datetime.now().isoformat()}")
                    break
                elif modernized_status_data["status"] == "error":
                    error_msg = f"Error in modernized processing: {modernized_status_data.get('error', 'Unknown error')}"
                    print(f"ERROR: {error_msg}")
                    raise Exception(error_msg)
                else:
                    progress = modernized_status_data.get('progress', 'Processing...')
                    print(f"Modernized processing in progress: {progress}")
                    ACTIVE_JOBS[job_id]["progress"] = f"Modernized processing: {progress}"
                    time.sleep(5)
            else:
                error_msg = f"Error checking modernized processing status: {modernized_status_response.text}"
                print(f"ERROR: {error_msg}")
                raise Exception(error_msg)
        
        # Step 1.5: Get coordinates if not provided by modernized service
        print("\n==== COORDINATES CHECK IN ORCHESTRATE_TOUR_ASYNC ====")
        print(f"Coordinates from modernized service: {coordinates}")
        if not _usable_coordinates(coordinates):
            print(f"No USABLE coordinates from modernized service ({coordinates!r}) — "
                  f"resolving for: {location}")

            # [GCS-C1] Real geocoder FIRST. geocode_stops asks Nominatim
            # (OpenStreetMap): free, no API key, stdlib-only, already a dependency
            # of the generator. It exists because model-recalled coordinates were
            # measured 1.0-2.4 km wrong (Yury's BETA-4), so using the LLM service
            # as the safety net meant the net was made of the material it was
            # built to replace. Nominatim's 1 req/sec policy is enforced inside
            # geocode_stops; one call per tour is nowhere near it.
            coords = None
            try:
                from geocode_stops import geocode as _geocode_place
                coords = _geocode_place(location)
                print(f"[GCS-C1] Nominatim for {location!r}: {coords}")
            except Exception as _geo_err:
                print(f"[GCS-C1] Nominatim unavailable ({_geo_err}) — falling through")

            # Legacy HTTP coordinates service, kept only as a second chance while
            # it still exists. It returns (0, 0) on every failure, which
            # _usable_coordinates rejects below.
            if not _usable_coordinates(coords):
                print(f"Calling get_coordinates_direct for: {location}")
                coords = get_coordinates_direct(location)
                print(f"Result from get_coordinates_direct: {coords}")

            if _usable_coordinates(coords):
                coordinates = [coords[0], coords[1]]
                print(f"Using coordinates: {coordinates}")
            else:
                # [GCS-C1] NEVER store 0,0. NULL is honest: tours-near skips the
                # row either way, but 0,0 also plots a marker in the ocean and
                # looks like real data to everything downstream. Logged at ERROR
                # with the job id so an unreachable tour is findable in the logs
                # instead of vanishing quietly.
                coordinates = None
                print(f"ERROR: [GCS-C1] No usable coordinates for {location!r} "
                      f"(job {job_id}) — storing NULL lat/lng. This tour will NOT "
                      f"appear in tours-near until its coordinates are set.")
        
        # Step 2: Download complete modernized tour ZIP
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 2/5: Downloading complete modernized tour...")
        safe_location = location.replace(' ', '_').replace(',', '').replace(':', '').replace('/', '_').replace('\\', '_').lower()
        
        print(f"Downloading complete tour from MODERNIZED service: {datetime.now().isoformat()}")
        download_response = _authenticated_request("GET", f"{MODERNIZED_URL}/download/{modernized_job_id}", timeout=60)
        print(f"Download response: {download_response.status_code}")
        
        if download_response.status_code == 200:
            print(f"Received complete modernized tour: {len(download_response.content)} bytes")
        else:
            error_msg = f"Error downloading modernized tour: {download_response.text}"
            print(f"ERROR: {error_msg}")
            raise Exception(error_msg)
        
        # Step 3: Save modernized tour ZIP with separate MP3/TXT files
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 3/5: Processing modernized tour ZIP...")
        print(f"MODERNIZED service returned complete tour with separate MP3/TXT files")
        
        zip_filename = f"{safe_location}_{tour_type}_{job_id[:8]}.zip"
        zip_path = os.path.join(TOURS_DIR, zip_filename)
        print(f"Saving modernized tour to: {zip_path}")
        with open(zip_path, 'wb') as f:
            f.write(download_response.content)
        ACTIVE_JOBS[job_id]["output_zip"] = zip_filename
        print(f"Modernized tour saved: {len(download_response.content)} bytes")
        print(f"File exists: {os.path.exists(zip_path)}")
        
        # Step 4: Extract modernized tour ZIP
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 4/5: Extracting modernized tour package...")
        extract_dir = f"{safe_location}_{tour_type}_{job_id[:8]}"
        extract_path = os.path.join(TOURS_DIR, extract_dir)
        print(f"Extracting ZIP file to: {extract_path}")
        os.makedirs(extract_path, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            print(f"ZIP file extracted successfully")
            print(f"Extracted files: {os.listdir(extract_path)}")
        except Exception as e:
            error_msg = f"Error extracting ZIP file: {e}"
            print(f"ERROR: {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")
            raise Exception(error_msg)
        
        ACTIVE_JOBS[job_id]["extract_dir"] = extract_dir
        
        # COUNT ASSERTION: ZIP must have exactly total_stops audio files
        expected_stops = ACTIVE_JOBS[job_id].get("total_stops")
        audio_files_in_zip = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                audio_files_in_zip = [
                    n for n in zip_ref.namelist()
                    if re.fullmatch(r'audio_\d+\.mp3', n)
                ]
            actual_stops = len(audio_files_in_zip)
        except Exception as count_err:
            print(f"WARNING: Could not verify stop count in ZIP: {count_err}")
            actual_stops = None
        
        print(f"STOP COUNT VERIFICATION: expected={expected_stops}, actual={actual_stops}, files={sorted(audio_files_in_zip)}")
        ACTIVE_JOBS[job_id]["expected_stops"] = expected_stops
        ACTIVE_JOBS[job_id]["actual_stops"] = actual_stops
        
        if actual_stops == 0 or actual_stops is None:
            error_msg = (
                f"Tour generation produced no audio files. "
                f"Expected {expected_stops} stops, got {actual_stops}. Job {job_id}."
            )
            print(f"ERROR: {error_msg}")
            ACTIVE_JOBS[job_id]["status"] = "error"
            ACTIVE_JOBS[job_id]["error"] = error_msg
            # [LOCAL-595B defect 2] No tour was delivered — mark 'failed' and give
            # back the reserved pack unit so the listener's allowance is intact.
            _set_tour_request_status(job_id, 'failed')
            _release_generation_reservation(user_id, job_id, reason='no_audio_files')
            try:
                os.remove(zip_path)
            except Exception:
                pass
            return  # Do not store in database, do not trigger translation
        elif actual_stops is not None and actual_stops != expected_stops:
            warning_msg = (
                f"STOP COUNT MISMATCH: requested {expected_stops} stops, "
                f"delivered {actual_stops}. Job {job_id}."
            )
            print(f"ERROR: {warning_msg}")
            ACTIVE_JOBS[job_id]["stop_count_warning"] = warning_msg
        
        # Step 5: Store in database with original tour content
        log_job_update(job_id, ACTIVE_JOBS[job_id]["status"], "Step 5/5: Storing modernized tour in database...")
        
        # Derive tour_name from the generated content's title (uses effective category, not raw tour_type)
        # Parse the " - <X> Tour" suffix from the content's first line, fall back to raw tour_type
        _effective_tour_suffix = f"{tour_type} Tour"
        if tour_content_raw := ACTIVE_JOBS[job_id].get("tour_content", ""):
            _first_line = tour_content_raw.split('\n')[0] if tour_content_raw else ""
            if ' - ' in _first_line and _first_line.endswith(' Tour'):
                _effective_tour_suffix = _first_line.rsplit(' - ', 1)[-1]
        elif tour_file:
            # Read first line from tour file to get effective category
            _tf_path = os.path.join(TOURS_DIR, tour_file)
            if os.path.exists(_tf_path):
                try:
                    with open(_tf_path, 'r', encoding='utf-8') as _tf:
                        _first_line = _tf.readline().strip()
                    if ' - ' in _first_line and _first_line.endswith(' Tour'):
                        _effective_tour_suffix = _first_line.rsplit(' - ', 1)[-1]
                except Exception:
                    pass
        tour_name = f"{location} - {_effective_tour_suffix}"
        print(f"Tour name (from effective category): {tour_name}")
        
        # Extract coordinates
        lat = None
        lng = None
        # [GCS-C1] Same check as the guard above, for the same reason: [None, None]
        # satisfies `len(...) >= 2` and would set lat/lng to None here even if the
        # guard had been fixed in isolation.
        if _usable_coordinates(coordinates):
            lat = coordinates[0]
            lng = coordinates[1]
        
        # Resolve tour_content: prefer HTTP response (already captured at line 612),
        # fall back to reading from shared-volume file if HTTP didn't provide it.
        # FIX (LOCAL-49): Previously this unconditionally reset tour_content = None,
        # discarding the HTTP-received content and relying solely on a file read that
        # fails when the text generator's file isn't visible to the orchestrator.
        if not tour_content:
            # HTTP response didn't include tour_content — try file read
            if tour_file:
                tour_file_path = os.path.join(TOURS_DIR, tour_file)
                if os.path.exists(tour_file_path):
                    try:
                        with open(tour_file_path, 'r', encoding='utf-8') as f:
                            tour_content = f.read()
                        print(f"Successfully read tour content from file: {len(tour_content)} characters")
                    except Exception as read_error:
                        print(f"Warning: Could not read tour content from {tour_file_path}: {read_error}")
                else:
                    print(f"Warning: Tour file not found: {tour_file_path}")
            else:
                print(f"Warning: No tour file available for content extraction")
        else:
            print(f"Using tour_content from HTTP response: {len(tour_content)} characters")
        
        # Add tour_content.txt to the ZIP file for redundancy (regardless of source)
        if tour_content:
            try:
                with zipfile.ZipFile(zip_path, 'a') as zipf:
                    zipf.writestr('tour_content.txt', tour_content.encode('utf-8'))
                print(f"Added tour_content.txt to ZIP file")
            except Exception as zip_error:
                print(f"Warning: Could not add tour_content.txt to ZIP: {zip_error}")
        
        # [LOCAL-306] Score the final tour before delivery.
        # Gates NOTHING — a catastrophic score still delivers unchanged.
        # No LLM calls, no network. Pure rule-based scoring.
        _score_row_id = None
        _tour_score = None
        _per_stop_data = None
        if tour_content:
            try:
                from tour_scoring_service import score_tour_text, ensure_tour_scores_table
                ensure_tour_scores_table()
                _n_req = int(total_stops) if total_stops else (ACTIVE_JOBS[job_id].get("actual_stops") or 0)
                _tour_score, _score_row_id, _scoring_ms = score_tour_text(
                    tour_content,
                    n_requested=_n_req,
                    tour_id=None,  # backfilled after store_audio_tour
                    tour_name=tour_name,
                )
                # Extract per-stop data for guardrails diagnosis
                if _tour_score:
                    _per_stop_data = [
                        {"classification": sa.classification}
                        for sa in _tour_score.stops
                    ]
            except Exception as scoring_err:
                # Scoring failure MUST NOT block delivery (LOCAL-306 rule)
                print(f"[SCORING] Non-fatal error during in-flight scoring: {scoring_err}")
                traceback.print_exc()

        # [LOCAL-307] Quality guardrails: diagnose shortfalls, decide retry or message.
        # When QUALITY_GUARDRAILS_ENABLED=false (default): logs what it WOULD do,
        # takes no action. When enabled: retries PIPELINE_LOST once, messages UNAVAILABLE.
        _guardrail_user_message = None
        _is_retry = ACTIVE_JOBS[job_id].get("_guardrail_retry", False)
        if _tour_score and _per_stop_data:
            try:
                from quality_guardrails import (
                    evaluate_tour, format_guardrail_log, select_better_tour
                )
                _guardrail_decision = evaluate_tour(_tour_score, _per_stop_data, is_retry=_is_retry)
                print(format_guardrail_log(_guardrail_decision))

                if _guardrail_decision.action == 'message' and _guardrail_decision.user_message:
                    # Attach the message to the job for the client to read
                    _guardrail_user_message = _guardrail_decision.user_message
                    ACTIVE_JOBS[job_id]["quality_message"] = _guardrail_user_message
                    print(f"[GUARDRAILS] User message attached: {_guardrail_user_message}")

                elif _guardrail_decision.action == 'disabled_would_message' and _guardrail_decision.user_message:
                    # Log what would happen; attach nothing
                    ACTIVE_JOBS[job_id]["_guardrail_would_message"] = _guardrail_decision.user_message

                # Note: 'retry' action is NOT implemented as an actual re-generation
                # call here because it would require re-invoking the full pipeline
                # (text generation + TTS + ZIP packaging). The retry mechanism is
                # designed to be triggered by setting _guardrail_retry=True on the
                # job and re-invoking orchestrate_tour_async. This is gated OFF
                # by default and documented as the intended trigger point.
                # When enabled, the orchestrator would:
                #   1. Save original tour_content and score
                #   2. Re-invoke text generation
                #   3. Score the retry
                #   4. select_better_tour() → deliver the winner
                # This is the mechanism; activation requires QUALITY_GUARDRAILS_ENABLED=true.

                if _guardrail_decision.action in ('disabled_would_retry', 'retry'):
                    ACTIVE_JOBS[job_id]["_guardrail_retry_candidate"] = True
                    ACTIVE_JOBS[job_id]["_guardrail_original_score"] = _guardrail_decision.diagnosis.score

            except Exception as guardrail_err:
                # Guardrail failure MUST NOT block delivery
                print(f"[GUARDRAILS] Non-fatal error: {guardrail_err}")
                traceback.print_exc()

        # [LOCAL-312] Update per-user quality index (private, for review solicitation).
        # This runs for generated tours only (not edits). The user_id here is secret_id.
        if _tour_score and user_id:
            try:
                from user_quality_index import update_user_index, ensure_user_quality_index_table
                ensure_user_quality_index_table()
                update_user_index(user_id, _tour_score.total_score)
            except Exception as idx_err:
                # Index update must NOT block delivery
                print(f"[USER_INDEX] Non-fatal error: {idx_err}")

        # Store in database with tour content
        # [LOCAL-727] Pass the deployment track explicitly so the store's
        # track-scoped lookup and the post-store re-read key on the same value.
        # store_audio_tour also falls back to TOUR_TRACK when track is None, so
        # this is belt-and-braces; resolving it here keeps the two call paths in
        # lockstep and makes the chosen track visible at the call site.
        _store_track = normalize_track(os.getenv('TOUR_TRACK', 'beta'))
        store_result = store_audio_tour(tour_name, request_string or location, zip_path, lat, lng, tour_content, stops_count=ACTIVE_JOBS[job_id].get("actual_stops"), is_test=is_test, tour_kind=ACTIVE_JOBS[job_id].get("tour_kind"), job_id=job_id, user_id=user_id, track=_store_track, tour_type=tour_type, location=location)
        
        # [LOCAL-156] store_audio_tour now returns a dict:
        #   {"success": bool, "action": str, "existing_tour_id": int|None, "error": str|None}
        # [LOCAL-718] + "replaced_version_no": int|None (set only on action='replaced').
        store_success = store_result["success"] if isinstance(store_result, dict) else store_result
        store_action = store_result.get("action", "unknown") if isinstance(store_result, dict) else ("inserted" if store_result else "error")
        store_existing_id = store_result.get("existing_tour_id") if isinstance(store_result, dict) else None
        store_error = store_result.get("error") if isinstance(store_result, dict) else None
        # [LOCAL-717 / D677 §2] Version of the CURRENT row after this store. The
        # app shows "Updated your tour '<title>' — now version N" when a
        # regeneration REPLACED an existing tour (action 'replaced', N >= 2).
        store_version_no = store_result.get("version_no") if isinstance(store_result, dict) else None
        store_replaced = (store_action == "replaced")
        store_replaced_version_no = store_result.get("replaced_version_no") if isinstance(store_result, dict) else None
        
        if not store_success:
            # [LOCAL-156] FAIL CLOSED: storage failed — do NOT report completed.
            # Issue a compensating credit if the user was already charged.
            print(f"[LOCAL-156] STORAGE FAILED: {store_error}")
            print(f"[LOCAL-156] Job {job_id} will NOT report completed — billing must not diverge from delivery (D14).")
            
            # Issue compensating service_credit to reverse the charge
            if user_id:
                try:
                    from wallet_ledger import record_movement, get_balance_cents
                    from entitlements import _get_subscription_tier
                    _refund_tier = _get_subscription_tier(user_id)
                    if _refund_tier == 'ppu':
                        # Find the charge for this job and reverse it
                        _refund_idem_key = f"service_credit:store_failed:{user_id}:{job_id}"
                        _charge_idem_key = f"charge:{user_id}:{job_id}"
                        import psycopg2 as _pg2_refund
                        _refund_conn = _pg2_refund.connect(
                            host=os.getenv('DB_HOST', 'postgres-2'),
                            database=os.getenv('DB_NAME', 'audiotours'),
                            user=os.getenv('DB_USER', 'admin'),
                            password=os.getenv('DB_PASSWORD', 'password123'),
                            port=os.getenv('DB_PORT', '5432')
                        )
                        _refund_cur = _refund_conn.cursor()
                        _refund_cur.execute(
                            "SELECT amount_cents FROM wallet_ledger WHERE idempotency_key = %s",
                            (_charge_idem_key,)
                        )
                        _charge_row = _refund_cur.fetchone()
                        _refund_cur.close()
                        _refund_conn.close()
                        
                        if _charge_row and _charge_row[0] < 0:
                            # Reverse the charge with a positive credit
                            _credit_cents = abs(_charge_row[0])
                            from decimal import Decimal as _Dec
                            _credit_usd = _Dec(_credit_cents) / _Dec(100)
                            _row, _bal = record_movement(
                                user_id=user_id,
                                movement_type="service_credit",
                                amount_cents=_credit_cents,
                                idempotency_key=_refund_idem_key,
                                description=f"Refund: tour storage failed — {tour_name[:100]}",
                                reference_id=job_id,
                            )
                            print(f"[LOCAL-156] SERVICE_CREDIT issued: +{_credit_cents}¢ | "
                                  f"balance={_bal}¢ | user={user_id} | job={job_id}")
                        else:
                            print(f"[LOCAL-156] No charge found to reverse for job={job_id}")
                except Exception as _refund_err:
                    # Refund failure is logged but does not change the job status —
                    # the job is already failed. Manual reconciliation needed.
                    print(f"[LOCAL-156] ERROR: Could not issue service_credit: {_refund_err}")
            
            ACTIVE_JOBS[job_id]["status"] = "error"
            ACTIVE_JOBS[job_id]["error"] = (
                f"Tour storage failed: {store_error}. "
                f"A compensating credit has been issued if applicable."
            )
            ACTIVE_JOBS[job_id]["error_type"] = "store_failed"
            # [LOCAL-595B defect 2] Delivery did NOT happen — mark the row 'failed'
            # (so it never counts toward L2/Tester caps) and release the reserved
            # L3/L4 pack unit. The listener keeps their allowance.
            _set_tour_request_status(job_id, 'failed')
            _release_generation_reservation(user_id, job_id, reason='store_failed')
            print(f"Keeping extraction directory due to database storage failure: {extract_path}")
            return  # Do NOT fall through to "completed"
        
        # Tour stored (or already existed). Determine the english_tour_id.
        if store_action == "already_exists" and store_existing_id:
            english_tour_id = store_existing_id
            print(f"[LOCAL-172] Reusing existing tour id={english_tour_id} (no new storage needed)")
            # [LOCAL-172 / D47] Tour reuse charges the same as a fresh generation.
            # Michael's reasoning (same as D45 for translations):
            #   1. Price predictability — user should not wonder why the same
            #      request sometimes costs nothing.
            #   2. Cost sharing — the first requester should not pay for everyone.
            # The charge already happened upstream in generate_tour_text_service.py.
            # Previously LOCAL-156 issued a service_credit refund here; D47 removes it.
            # Free-tier users are never charged (entitlements gate + _our_cost check
            # in generate_tour_text_service.py skip the charge block entirely).
            print(f"[LOCAL-172] Charge retained for reuse (D47) | user={user_id} | job={job_id}")
            # [LOCAL-595B defect 3] A cache hit / stop-pool reuse is NOT a fresh
            # tour (the spec prices L3 as "5 FRESH tours"): it cost ~$0, so RELEASE
            # the L3 fresh_used / L4 ops_used unit reserved at request time. The
            # tour_requests row still flips to 'completed' below, so it STILL
            # counts toward the L2/Tester daily & monthly volume caps. This D47
            # wallet charge and the LOCAL-595 pack allowance are independent.
            _was_cache_hit = True
            _release_generation_reservation(user_id, job_id, reason='cache_hit')
        else:
            print(f"Tour stored successfully with coordinates: lat={lat}, lng={lng}")

            # [LOCAL-718 / D678] On the 'replaced' path store_audio_tour already
            # returns the authoritative row id — use it directly. For a fresh
            # INSERT we must re-read, and the read MUST be creator-scoped: two
            # creators may now hold the same name, so an unscoped
            # "ORDER BY id DESC LIMIT 1" could return the OTHER creator's tour.
            # [LOCAL-727 / bug 432] The re-read MUST ALSO be track-scoped: with
            # the track now part of the store's key, a Beta and a Storied row can
            # share the same name+creator, so an unscoped re-read could pick the
            # OTHER track's row for this job's english_tour_id. Resolve the same
            # track the store used (TOUR_TRACK env, normalised) and add it to the
            # predicate.
            english_tour_id = store_existing_id if store_action == "replaced" else None
            if english_tour_id is None:
                try:
                    import psycopg2
                    _creator_lookup = (user_id or '').strip() or None
                    _track_lookup = normalize_track(os.getenv('TOUR_TRACK', 'beta'))
                    conn = psycopg2.connect(
                        host=os.getenv('DB_HOST', 'postgres-2'),
                        database=os.getenv('DB_NAME', 'audiotours'),
                        user=os.getenv('DB_USER', 'admin'),
                        password=os.getenv('DB_PASSWORD', 'password123'),
                        port=os.getenv('DB_PORT', '5432')
                    )
                    cur = conn.cursor()
                    # creator_user_id = %s with a NULL param matches no row, so a
                    # NULL-creator insert falls to the IS NULL branch below.
                    if _creator_lookup is not None:
                        cur.execute(
                            "SELECT id FROM audio_tours "
                            "WHERE lower(tour_name) = lower(%s) AND creator_user_id = %s "
                            "AND track = %s AND original_tour_id IS NULL "
                            "ORDER BY id DESC LIMIT 1",
                            (tour_name, _creator_lookup, _track_lookup)
                        )
                    else:
                        cur.execute(
                            "SELECT id FROM audio_tours "
                            "WHERE lower(tour_name) = lower(%s) AND creator_user_id IS NULL "
                            "AND track = %s AND original_tour_id IS NULL "
                            "ORDER BY id DESC LIMIT 1",
                            (tour_name, _track_lookup)
                        )
                    result = cur.fetchone()
                    if result:
                        english_tour_id = result[0]
                        print(f"English tour ID: {english_tour_id}")
                    cur.close()
                    conn.close()
                except Exception as db_error:
                    print(f"Warning: Could not get tour ID from database: {db_error}")

        # [LOCAL-717 / D677 §2] Record the version of the delivered tour and
        # whether this generation REPLACED an existing tour, so the app can say
        # "Updated your tour '<title>' — now version N" instead of announcing a
        # brand-new tour. version_no comes straight from store_audio_tour
        # (1 = fresh insert, N = Nth content). 'replaced' is the signal the app
        # keys on; a plain insert (version 1) is a new tour, not an update.
        if store_version_no is not None:
            ACTIVE_JOBS[job_id]["version_no"] = store_version_no
        ACTIVE_JOBS[job_id]["replaced"] = bool(store_replaced)
        # Carry a short title for the app's message (the tour name the user sees).
        ACTIVE_JOBS[job_id]["tour_title"] = tour_name

        # LOCAL-128: Link stop_metrics to this tour via tour_id.
        # The text generator wrote stop_metrics with job_id = job_id_1
        # but could not set tour_id (the tour didn't exist yet).
        # Now that store_audio_tour has created the row, backfill it.
        if english_tour_id and job_id_1:
            _sm_updated = link_stop_metrics_to_tour(english_tour_id, job_id_1)
            if _sm_updated > 0:
                print(f"[LOCAL-128] Linked {_sm_updated} stop_metrics rows to tour_id={english_tour_id} (job_id={job_id_1})")
            elif _sm_updated == 0:
                print(f"[LOCAL-128] No stop_metrics rows found for job_id={job_id_1} (i-con may not have run)")
            else:
                print(f"[LOCAL-128] stop_metrics tour_id update failed (non-fatal)")

        # [LOCAL-306] Backfill tour_id on the score row now that we know it.
        if english_tour_id and _score_row_id:
            try:
                from tour_scoring_service import update_tour_id_on_score
                update_tour_id_on_score(_score_row_id, english_tour_id)
            except Exception as _bf_err:
                print(f"[SCORING] Non-fatal: could not backfill tour_id on score: {_bf_err}")

        # [LOCAL-701 / D663 §3] If this tour was generated FOR a community, TAG
        # it now (community_id + visibility). The organiser was already charged
        # by the normal generate path (this user_id's plan allowance). Tagging is
        # best-effort and non-fatal: a tagging failure must never fail an
        # already-delivered tour — worst case the tour is an ordinary tour the
        # organiser can re-tag. Only the OWNER of the community may tag (enforced
        # by tag_community_tour's owner check), and a members-only tour is the
        # safe default.
        _community_id_job = ACTIVE_JOBS.get(job_id, {}).get("community_id")
        if english_tour_id and _community_id_job:
            try:
                import psycopg2 as _pg2_ct
                import community_tours_service as _cts
                _ct_conn = _pg2_ct.connect(
                    host=os.getenv('DB_HOST', 'postgres-2'),
                    database=os.getenv('DB_NAME', 'audiotours'),
                    user=os.getenv('DB_USER', 'admin'),
                    password=os.getenv('DB_PASSWORD', 'password123'),
                    port=os.getenv('DB_PORT', '5432'),
                )
                try:
                    _ct_cur = _ct_conn.cursor()
                    _tagged = _cts.tag_community_tour(
                        _ct_cur, english_tour_id, _community_id_job,
                        visibility=ACTIVE_JOBS.get(job_id, {}).get(
                            "community_visibility", 'members'),
                        owner_user_id=user_id,
                    )
                    _ct_conn.commit()
                    print(f"[LOCAL-701] Tagged tour {english_tour_id} to community "
                          f"{_community_id_job} (tagged={_tagged}, "
                          f"visibility={ACTIVE_JOBS.get(job_id, {}).get('community_visibility')})")
                except _cts.CommunityTourError as _ct_err:
                    _ct_conn.rollback()
                    print(f"[LOCAL-701] Community tag refused for tour "
                          f"{english_tour_id}: {_ct_err.code} — {_ct_err.message}")
                finally:
                    _ct_cur.close()
                    _ct_conn.close()
            except Exception as _ct_outer:
                print(f"[LOCAL-701] Non-fatal: community tagging failed for tour "
                      f"{english_tour_id}: {_ct_outer}")

        if language != 'en':
            pass  # translation block below handles non-English
        
        # If non-English language requested, translate the tour
        if language != 'en' and english_tour_id:
            print(f"\n==== TRANSLATING TOUR TO {language.upper()} ====")
            try:
                translation_data = {
                    "content_id": english_tour_id,
                    "content_type": "tour",
                    "languages": [language],
                    # [LOCAL-578] Forward attribution so the translation service writes its
                    # cost_ledger rows (translation_generate + per-stop tts_generate) under
                    # the same job_id/user_id used for the English generation and the
                    # translation wallet charge below.
                    "job_id": job_id,
                    "user_id": user_id,
                }
                
                print(f"Calling translation service with data: {translation_data}")
                translation_response = _authenticated_request("POST", f"{TRANSLATION_URL}/translate-with-audio",
                    headers={"Content-Type": "application/json"},
                    json=translation_data,
                    timeout=120
                )
                
                if translation_response.status_code == 200:
                    translation_result = translation_response.json()
                    # [LOCAL-60] Extract translated_tour_ids for backward compat
                    _translations = translation_result.get('translations', {})
                    _lang_result = _translations.get(language, {})
                    translated_tour_id = _lang_result.get('id')
                    _translation_cache_hit = _lang_result.get('cache_hit', False)
                    
                    # Backward compat: older response format
                    if not translated_tour_id:
                        translated_tour_id = translation_result.get('translated_tour_ids', {}).get(language)
                    
                    if translated_tour_id:
                        print(f"Translation successful! Translated tour ID: {translated_tour_id} (cache_hit={_translation_cache_hit})")
                        ACTIVE_JOBS[job_id]["translated_tour_id"] = translated_tour_id
                        ACTIVE_JOBS[job_id]["final_tour_id"] = translated_tour_id
                        
                        # [LOCAL-60] Meter translation cost to cost_ledger
                        # [LOCAL-169] Charge wallet for BOTH fresh and cached translations (D45)
                        try:
                            from cost_meter import record_operation
                            from cost_rates import CACHE_HIT_COST_USD, translation_cost, DEPLOYED_TRANSLATION_PASSES

                            # Always compute fresh translation cost for charging
                            _source_chars = len(tour_content) if tour_content else 16000
                            _total_translation_cost = translation_cost(_source_chars, passes=DEPLOYED_TRANSLATION_PASSES)

                            if _translation_cache_hit:
                                # cost_ledger: record TRUE cost ($0.00) — our accounting
                                record_operation(
                                    operation_type="translation_cache_hit",
                                    our_cost_usd=CACHE_HIT_COST_USD,
                                    cache_hit=True,
                                    user_id=user_id,
                                    job_id=job_id,
                                    breakdown={"translate": 0.0, "tts": 0.0},
                                )
                            else:
                                # cost_ledger: record real cost
                                record_operation(
                                    operation_type="translation_generate",
                                    our_cost_usd=_total_translation_cost,
                                    cache_hit=False,
                                    user_id=user_id,
                                    job_id=job_id,
                                    breakdown={
                                        "translate_and_tts": _total_translation_cost,
                                        "source_chars": _source_chars,
                                        "translation_passes": DEPLOYED_TRANSLATION_PASSES,
                                    },
                                )
                        except Exception as _meter_err:
                            print(f"[LOCAL-60] Translation cost metering failed (non-fatal): {_meter_err}")

                        # [LOCAL-169] Charge the user's wallet (D45: cache hit charges same as fresh)
                        # This is a billing control — separate try, FAILS CLOSED for fresh,
                        # non-fatal for cache hits (translation already served).
                        if user_id:
                            try:
                                from pricing import compute_user_charge as _compute_charge
                                from wallet_ledger import charge as _wallet_charge, record_unlimited_cost as _record_unlimited
                                from entitlements import _get_subscription_tier
                                from cost_rates import translation_cost as _tc, DEPLOYED_TRANSLATION_PASSES as _dtp

                                _user_tier = _get_subscription_tier(user_id)
                                _source_chars_w = len(tour_content) if tour_content else 16000
                                _fresh_cost = _tc(_source_chars_w, passes=_dtp)

                                _op_type = "translation_cache_hit" if _translation_cache_hit else "translation_generate"
                                _charge_result = _compute_charge(
                                    our_cost_usd=CACHE_HIT_COST_USD if _translation_cache_hit else _fresh_cost,
                                    cache_hit=_translation_cache_hit,
                                    operation_type=_op_type,
                                    description=f"Translation to {language}",
                                    fresh_cost_usd=_fresh_cost if _translation_cache_hit else None,
                                )

                                if _user_tier == 'ppu' and _charge_result['user_charge_cents'] > 0:
                                    _charge_idem_key = f"charge:{user_id}:{job_id}:translation"
                                    _row_id, _new_bal, _was_stopped = _wallet_charge(
                                        user_id=user_id,
                                        charge_usd=_charge_result['user_charge_usd'],
                                        idempotency_key=_charge_idem_key,
                                        description=f"Translation to {language} — ${_charge_result['user_charge_usd']:.2f}",
                                        job_id=job_id,
                                    )
                                    print(f"[LOCAL-169] PPU translation charged: ${_charge_result['user_charge_usd']:.2f} | "
                                          f"cache_hit={_translation_cache_hit} | balance={_new_bal}¢ | user={user_id}")

                                elif _user_tier == 'unlimited':
                                    from decimal import Decimal as _Dec
                                    _record_unlimited(user_id, _Dec(str(_fresh_cost)))
                                    print(f"[LOCAL-169] Unlimited translation cost recorded: ${_fresh_cost:.6f} | user={user_id}")

                            except Exception as _charge_err:
                                print(f"[LOCAL-169] Translation wallet charge failed: {_charge_err}")
                    else:
                        print(f"Warning: Translation completed but no tour ID returned")
                        ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id
                else:
                    print(f"Translation failed: {translation_response.status_code} - {translation_response.text}")
                    ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id
                    
            except Exception as translation_error:
                print(f"Translation error: {translation_error}")
                ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id
        else:
            ACTIVE_JOBS[job_id]["final_tour_id"] = english_tour_id or "unknown"
        
        # Update tour_requests status to completed
        if user_id and 'tour_id' in ACTIVE_JOBS[job_id]:
            tour_id = ACTIVE_JOBS[job_id]['tour_id']
            print(f"Updating tour_requests status for tour_id: {tour_id}")
            try:
                update_data = {
                    'tour_id': tour_id,
                    'status': 'completed',
                    'finished_at': datetime.now().isoformat()
                }
                update_response = _authenticated_request("POST", f"{TOUR_UPDATE_URL}/update",
                    headers={"Content-Type": "application/json"},
                    json=update_data,
                    timeout=10
                )
                if update_response.status_code == 200:
                    print(f"Successfully updated tour_requests status for {tour_id}")
                else:
                    print(f"Failed to update tour_requests status: {update_response.text}")
            except Exception as update_error:
                print(f"Error updating tour_requests status: {update_error}")
        else:
            print(f"No tour_id available for tour_requests update (user_id: {user_id})")
        
        # Clean up extraction directory after successful database storage
        # ZIP file is now the primary storage, directory is no longer needed
        if os.path.exists(extract_path):
            try:
                print(f"Cleaning up extraction directory: {extract_path}")
                shutil.rmtree(extract_path)
                print(f"Successfully cleaned up directory: {extract_dir}")
                print(f"Storage optimization: Directory removed, ZIP file remains as primary storage")
            except Exception as cleanup_error:
                print(f"Warning: Could not clean up extraction directory: {cleanup_error}")
                print(f"Directory will remain: {extract_path}")
        else:
            print(f"Extraction directory not found for cleanup: {extract_path}")
        
        # [S82] Auto-call POST /tour/share after successful generation (Storied mode only)
        storied_mode = os.getenv('STORIED_MODE', 'false').lower() == 'true'
        if storied_mode and tour_content:
            try:
                share_payload = {
                    "location": location,
                    "tour_type": tour_type,
                    "total_stops": total_stops,
                    "tour_content": tour_content,
                }
                if user_id:
                    share_payload["user_id"] = user_id
                share_url = f"{TOUR_GENERATOR_URL}/tour/share"
                print(f"[S82][SHARE] Auto-sharing tour to {share_url}")
                _share_resp = _authenticated_request("POST", share_url,
                    headers={"Content-Type": "application/json"},
                    json=share_payload,
                    timeout=15
                )
                print(f"[S82][SHARE] Response: {_share_resp.status_code} — {_share_resp.text[:200]}")
                _share_data = _share_resp.json()
                ACTIVE_JOBS[job_id]["share_id"] = _share_data.get('share_id', '')
                ACTIVE_JOBS[job_id]["share_url"] = _share_data.get('share_url', '')
            except Exception as share_err:
                print(f"SHARE_STORE_WARN: {share_err}")

        # Complete
        final_message = f"Tour generation completed in {language.upper()}!"
        if language != 'en' and 'translated_tour_id' in ACTIVE_JOBS[job_id]:
            final_message += f" Translated tour ID: {ACTIVE_JOBS[job_id]['translated_tour_id']}"
        
        # [LOCAL-595B defect 2] Delivery succeeded — flip the orchestrator's
        # tour_requests row to 'completed' so it counts toward L2/Tester volume
        # caps. For a FRESH tour the reserved L3/L4 pack unit stands (it is the
        # real consumption); for a cache hit it was already released above, so we
        # do NOT release again.
        _set_tour_request_status(job_id, 'completed')
        if _was_cache_hit:
            print(f"[QUOTA] job={job_id} delivered from cache/pool — pack unit already released, tour still counts for volume caps")

        log_job_update(job_id, "completed", final_message)
        ACTIVE_JOBS[job_id]["netlify_ready"] = True
        ACTIVE_JOBS[job_id]["language"] = language
        # [LOCAL-718 / D678] Surface the archived version number when a creator
        # re-generated their OWN same-name tour (action='replaced'). LOCAL-717's
        # "Updated your tour — now version N" reads this. It is set ONLY on a true
        # same-creator replace; an insert / cache-hit / cross-creator new tour
        # leaves it None, which the app reads as "an ordinary new tour" (D678 §6).
        ACTIVE_JOBS[job_id]["replaced_version_no"] = store_replaced_version_no
        if coordinates:
            ACTIVE_JOBS[job_id]["coordinates"] = coordinates
        
        print(f"==== ORCHESTRATE_TOUR_ASYNC COMPLETED: {datetime.now().isoformat()} ====")
        
    except Exception as e:
        print(f"\n==== EXCEPTION IN ORCHESTRATE_TOUR_ASYNC: {datetime.now().isoformat()} ====")
        print(f"Exception: {e}")
        print(f"Exception type: {type(e).__name__}")
        print(f"Traceback: {traceback.format_exc()}")
        ACTIVE_JOBS[job_id]["status"] = "error"
        ACTIVE_JOBS[job_id]["error"] = str(e)
        
        # [LOCAL-595B defect 2] A failed generation must not consume the device's
        # allowance. Mark the orchestrator's tour_requests row 'failed' (L2/Tester
        # caps count only 'completed' rows) and release the reserved L3/L4 pack
        # unit (fresh_used / ops_used). We mark 'failed' rather than DELETE so the
        # attempt stays auditable; completed-only counting makes the effect the
        # same as the old rollback, and the pack unit is now correctly returned.
        _set_tour_request_status(job_id, 'failed')
        _release_generation_reservation(user_id, job_id, reason='exception')

def track_user_tour(user_id, tour_id, request_string):
    """Track a user's tour request in the user tracking service."""
    print(f"\n==== TRACKING USER TOUR: {datetime.now().isoformat()} ====")
    print(f"User ID: {user_id}")
    print(f"Tour ID: {tour_id}")
    print(f"Request string: {request_string}")
    
    try:
        # Prepare data for the user tracking service
        payload = {
            "tour_request": {
                "tour_id": tour_id,
                "request_string": request_string
            }
        }
        
        # Call the user tracking service
        print(f"Calling user tracking API for user {user_id}")
        print(f"Payload: {payload}")
        
        response = _authenticated_request("PUT", f"{USER_API_URL}/user/{user_id}",
            json=payload,
            timeout=10
        )
        
        print(f"User tracking response: {response.status_code} - {response.text}")
        
        if response.status_code != 200:
            print(f"ERROR: Failed to track user tour: {response.text}")
            return False
        
        print(f"SUCCESS: User tour tracked successfully")
        return True
    except Exception as e:
        print(f"ERROR: Exception tracking user tour: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

def get_coordinates_direct(location):
    # Get coordinates directly from the coordinates-fromai service
    import requests
    import urllib.parse
    
    print(f"\n==== DIRECT COORDINATES REQUEST FOR: {location} ====")
    print(f"Time: {datetime.now().isoformat()}")
    
    try:
        # URL-encode the location
        encoded_location = urllib.parse.quote(location)
        
        # Make the request to the coordinates-fromai service (internal port 5004)
        url = f"{COORDINATES_URL}/coordinates/{encoded_location}"
        print(f"Requesting URL: {url}")
        
        _auth = _get_auth_headers(COORDINATES_URL); response = requests.get(url, headers=_auth, timeout=60)
        
        print(f"Response status code: {response.status_code}")
        print(f"Response time: {datetime.now().isoformat()}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {data}")
            
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                lat, lng = data["coordinates"]
                print(f"Received coordinates: lat={lat}, lng={lng}")
                return (lat, lng)
            else:
                print(f"Invalid response format: {data}")
                print(f"ERROR: Invalid response format from coordinates service")
                return (0, 0)  # Return 0,0 as fallback
        else:
            print(f"Error response: {response.text}")
            print(f"ERROR: Failed to get coordinates from service: {response.status_code}")
            return (0, 0)  # Return 0,0 as fallback
    except Exception as e:
        print(f"ERROR: Exception while getting coordinates from coordinates-fromai service: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return (0, 0)  # Return 0,0 as fallback


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with cost ceiling stats."""
    try:
        from cost_ceiling_monitor import get_ceiling_stats
        _ceiling_stats = get_ceiling_stats()
    except ImportError as _ceil_err:
        _orch_logger.error(f"[LOCAL-146] MISSING: cost_ceiling_monitor (get_ceiling_stats) — ceiling stats unavailable in health endpoint: {_ceil_err}")
        _ceiling_stats = {}
    return jsonify({
        "status": "healthy",
        "service": "tour_orchestrator",
        "cost_ceiling": _ceiling_stats,
    })

@app.route('/generate-complete-tour', methods=['POST'])
def generate_complete_tour():
    """Generate a complete tour from text to audio to web."""
    print(f"\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")
    sys.stdout.flush()
    print(f"Request method: {request.method}")
    print(f"Request headers: {dict(request.headers)}")
    print(f"Request data: {request.get_data(as_text=True)}")
    print(f"Request JSON: {request.json if request.is_json else None}")
    
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400
    
    data = request.json
    print(f"Received request data: {data}")
    
    location = sanitize_input(data.get('location'))
    tour_type = sanitize_input(data.get('tour_type'))
    total_stops = data.get('total_stops', 10)
    user_id = sanitize_input(data.get('user_id'))
    request_string = sanitize_input(data.get('request_string'))
    language = data.get('language', 'en')  # Default to English
    # [LOCAL-701 / D663 §3] Optional "generate FOR a community" fields. When the
    # organiser picks "For: my community <name>" on the Generate tab, the app
    # sends the community id and the chosen visibility. The tour is generated by
    # the normal pipeline and CHARGED to this user (the organiser) exactly as any
    # tour; after it is stored we TAG it onto the community (community_id +
    # community_visibility). Absent → an ordinary public tour, unchanged.
    _community_id = data.get('community_id')
    try:
        _community_id = int(_community_id) if _community_id not in (None, '') else None
    except (TypeError, ValueError):
        _community_id = None
    # [LOCAL-752 B / D706] Did the app send an EXPLICIT visibility choice? When it
    # did (members/public from Generate), honour it. When it did NOT, the default
    # depends on the community: for a LISTED community a new tour defaults to
    # PUBLIC (D706 — findable on the map/search with the badge, download still
    # gated on membership); a PRIVATE community keeps members-only. Resolved via
    # community_tours_service.default_visibility_for_community so the rule lives in
    # one place. Best-effort: any read failure falls back to members-only.
    _explicit_visibility = data.get('community_visibility') or data.get('visibility')
    _community_visibility = 'members'
    if _community_id is not None:
        _explicit = (_explicit_visibility
                     if (_explicit_visibility is not None
                         and str(_explicit_visibility).strip().lower()
                         in ('members', 'public'))
                     else None)
        try:
            import psycopg2 as _pg2_vis
            import community_tours_service as _cts_vis
            _vis_conn = _pg2_vis.connect(
                host=os.getenv('DB_HOST', 'postgres-2'),
                database=os.getenv('DB_NAME', 'audiotours'),
                user=os.getenv('DB_USER', 'admin'),
                password=os.getenv('DB_PASSWORD', 'password123'),
                port=os.getenv('DB_PORT', '5432'),
            )
            try:
                _vis_cur = _vis_conn.cursor()
                _community_visibility = _cts_vis.default_visibility_for_community(
                    _vis_cur, _community_id, _explicit)
            finally:
                _vis_conn.close()
        except Exception as _vis_err:  # noqa: BLE001
            print(f"[LOCAL-752] default visibility resolve failed for community "
                  f"{_community_id}: {_vis_err}; using {_community_visibility!r}")
            # Keep any explicit choice if we had one; else members-only.
            if _explicit in ('members', 'public'):
                _community_visibility = _explicit
    persona = sanitize_input(data.get('persona'))  # [S81] Direct-pass persona (optional)

    # [LOCAL-525] Optional user-chosen stops. Validated/sanitized here; forwarded
    # to the tour-generator as 'stops' and ultimately to the engine's forced_stops
    # path. Malformed → 400 with a clear message. Absent → normal generation.
    # [LOCAL-547, 2026-09-24] Accept the field the MOBILE APP actually sends.
    # LOCAL-525 gave the service a `stops` list; LOCAL-523 gave the app its stop
    # editor. They were built against different names and never integrated:
    #     app  ->  tourData['user_stops'] = stopTitlesForGeneration(_userStops)
    #     here ->  data.get('stops')
    # so a listener could build their stop list, press Generate, and the names
    # never left the phone. Nothing server-side referenced `user_stops` at all --
    # it appeared only in user_stops_validate.py and its unit test.
    #
    # Worse, `stops` is already taken on the app side for the stop COUNT
    # ("'stops': _stopCountController.text"), so simply renaming in the app would
    # collide. Accepting both here is the compatible fix and needs no new build,
    # which matters because the install on Michael's phone is already made.
    _raw_stops = data.get('stops')
    _stops_field_present = 'stops' if _raw_stops is not None else None
    if _raw_stops is None:
        _raw_stops = data.get('user_stops')
        if _raw_stops is not None:
            _stops_field_present = 'user_stops'
    # [GCS-KS1] Kill switch (D591). When USER_STOPS_ENABLED is not 'true', the
    # user-chosen stops are dropped here — the request then behaves exactly as if
    # the app had sent no stops at all, and validate_stops(None) yields (None, None)
    # so the normal automatic selection runs. Logged once, with the count, when a
    # field was actually present, so we can see whether any installed app still
    # sends it. When the flag is on, _raw_stops passes through unchanged.
    _raw_stops = _neutralize_user_stops(
        _raw_stops, request_id=user_id, field=_stops_field_present)
    stops, _stops_error = validate_stops(_raw_stops)
    
    # [LOCAL-103] Accept is_test from request — gated by server-side allow-flag
    # Trust boundary: is_test is only honored when the server is already in test mode
    # (TOUR_TEST_MODE=true) OR when explicitly opted in (TOUR_TEST_MODE_ALLOW_REQUEST=true).
    # On a production deployment neither env var is set, so a malicious caller cannot
    # mark tours as test to hide them from tours-near.
    _is_test_raw = data.get('is_test')
    _server_test_mode = os.getenv('TOUR_TEST_MODE', 'false').lower() == 'true'
    _allow_request_flag = os.getenv('TOUR_TEST_MODE_ALLOW_REQUEST', 'false').lower() == 'true'
    if _is_test_raw and (_server_test_mode or _allow_request_flag):
        is_test_override = True
    else:
        is_test_override = None  # None means "use server env default"
    
    # [S81] Resolve persona: stored-preference-wins (downstream tour-generator handles DB lookup)
    # Log the resolved persona on every /generate request
    print(f"PERSONA_RESOLVED: {persona or 'none'}")
    
    print(f"Extracted parameters:")
    print(f"  location: {location}")
    print(f"  tour_type: {tour_type}")
    print(f"  total_stops: {total_stops}")
    print(f"  user_id: {user_id}")
    print(f"  request_string: {request_string}")
    print(f"  language: {language}")
    print(f"  persona: {persona}")
    print(f"  is_test: {is_test_override} (raw={_is_test_raw}, server_mode={_server_test_mode}, allow_request={_allow_request_flag})")
    
    # Validate language parameter
    supported_languages = ['en', 'ru', 'es', 'fr', 'de', 'zh', 'ko']
    if language not in supported_languages:
        return jsonify({"error": f"Unsupported language: {language}. Supported: {supported_languages}"}), 400

    # [LOCAL-525] Reject malformed user-chosen stops with a clear message.
    if _stops_error is not None:
        return jsonify({"error": _stops_error}), 400
    
    # [LOCAL-474] location is required; tour_type is NOT.
    # An absent/empty tour_type means "classify it" — the downstream category
    # classifier in generate_tour_text.py infers the category from the request
    # text (exactly as it does for a wrong-but-nonempty type). The app sends
    # tour_type='' whenever it recognises no category keyword (e.g. restaurant
    # tours, which have no parser branch), and that request must be honoured,
    # not rejected. See tour_request_parser.dart:111 and D538–D556.
    if not location:
        return jsonify({"error": "location is required"}), 400
    if not tour_type:
        print(f"[LOCAL-474] Empty tour_type — deferring category to downstream classifier")
    
    # Reject new requests during graceful shutdown
    if _SHUTTING_DOWN:
        response = jsonify({"error": "Service is shutting down. Please retry in a few seconds."})
        response.headers['Retry-After'] = '5'
        return response, 503
    
    try:
        total_stops = int(total_stops)
        if total_stops < 1 or total_stops > 50:
            return jsonify({"error": "total_stops must be between 1 and 50"}), 400
    except ValueError:
        return jsonify({"error": "total_stops must be a valid integer"}), 400

    # [LOCAL-525] A user-chosen stop list dictates the tour size. The engine sets
    # total_stops = len(forced_stops), so meter/clamp against the list length, not
    # the (possibly default) total_stops the client happened to send.
    if stops is not None:
        total_stops = len(stops)
    
    # Entitlements check: verify user hasn't exceeded their plan limits. FAIL-CLOSED.
    # Reject missing/anonymous user_id (matches news path — consistent policy).
    if not user_id or user_id.strip() == '':
        print(f"[QUOTA] Missing/anonymous user_id — denying tour (fail-closed)")
        return jsonify({
            "allowed": False, "error": "auth_required",
            "message": "A valid user id is required to generate tours."
        }), 401

    # [LOCAL-595] Subscription-levels enforcement is the authoritative gate.
    # check_operation reads the device's level from device_entitlement (install
    # default L1) and the per-level numbers from the plans table, and returns an
    # allow (with clamped_stops) or a structured LOCAL-580 refusal.
    try:
        from entitlements import check_operation
        quota = check_operation(user_id, 'generate', requested_stops=total_stops)
    except Exception as quota_err:
        print(f"[QUOTA] Operation check failed — denying (fail-closed): {quota_err}")
        return jsonify({
            "allowed": False, "error": "quota_check_failed",
            "error_code": "generation_failed",
            "message": "Could not verify your tour quota. Please try again."
        }), 503

    if not quota['allowed']:
        print(f"[QUOTA] Denied tour for {user_id}: {quota}")
        return jsonify(quota), 429
    # Clamp stops to the level maximum (max_stops column).
    total_stops = quota['clamped_stops']
    # [LOCAL-597] Generation mode from the levels check. L2 free tours come back
    # allowed with mode='by_reference' — the orchestrator forwards it so the
    # generator reuses already-researched stops only (zero grounding, zero SERP).
    generation_mode = quota.get('mode')
    print(f"[QUOTA] Allowed for {user_id}: level={quota.get('level')}, "
          f"stops_clamped={total_stops}, mode={generation_mode}")

    # [LOCAL-525] A user-chosen stop list is a promise: "generate EXACTLY these
    # stops." If the plan would clamp the count below the list length, silently
    # dropping stops is exactly the "not reliably honoured" failure that motivated
    # this feature. Reject with a clear, actionable message instead.
    if stops is not None and len(stops) > total_stops:
        print(f"[QUOTA] Stops list ({len(stops)}) exceeds plan max ({total_stops}) — rejecting")
        return jsonify({
            "allowed": False,
            "error": "stops_exceed_plan",
            "message": (
                f"You provided {len(stops)} stops, but your plan allows at most "
                f"{total_stops}. Remove some stops or upgrade your plan."
            ),
            "provided_stops": len(stops),
            "max_stops": total_stops,
            "upgrade": True,
        }), 429

    # Generate job ID FIRST (needed for usage recording)
    job_id = str(uuid.uuid4())
    print(f"Generated job ID: {job_id}")
    sys.stdout.flush()

    # Record usage immediately, keyed on job_id so we can rollback on failure.
    # source='orchestrator' distinguishes from tracking-service rows (avoids double-counting).
    _usage_row_id = None
    try:
        import psycopg2 as _pg
        _conn = _pg.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        _cur = _conn.cursor()
        _cur.execute("""
            INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
            VALUES (%s, %s, 'started', NOW(), 'orchestrator')
            RETURNING id
        """, (user_id, job_id))
        _usage_row_id = _cur.fetchone()[0]
        _conn.commit()
        _cur.close()
        _conn.close()
        print(f"[QUOTA] Usage recorded for {user_id} (row_id={_usage_row_id}, job_id={job_id})")
    except Exception as usage_err:
        # Non-fatal: usage recording failure shouldn't block generation
        print(f"[QUOTA] WARNING: Failed to record usage (non-fatal): {usage_err}")

    # [LOCAL-595 / LOCAL-595B defect 2] RESERVE the device's pack allowance for
    # L3/L4 (fresh_used / ops_used) BEFORE generation. The reservation is the
    # concurrency guard: two parallel requests cannot both pass a limit of 1.
    # It is RELEASED later (orchestrate_tour_async) if the generation fails
    # (defect 2) or is served from cache / the stop pool at ~$0 (defect 3); it
    # stands only for a successful FRESH delivery. Period levels (L2/Tester)
    # count from COMPLETED tour_requests rows, so they neither reserve nor
    # release here. Best-effort; never blocks.
    try:
        from entitlements import reserve_operation
        reserve_operation(user_id, 'generate')
    except Exception as _reserve_err:
        print(f"[QUOTA] WARNING: Failed to reserve pack allowance (non-fatal): {_reserve_err}")
    
    # Initialize job tracking
    ACTIVE_JOBS[job_id] = {
        "status": "queued",
        "progress": "Job queued for processing",
        "location": location,
        "tour_type": tour_type,
        "total_stops": total_stops,
        "user_id": user_id,
        "request_string": request_string,
        "language": language,
        "persona": persona,  # [S81] Pass persona for downstream generation
        "is_test": is_test_override,  # [LOCAL-103] Track test flag
        "stops": stops,  # [LOCAL-525] User-chosen stops (None → normal generation)
        "mode": generation_mode,  # [LOCAL-597] 'by_reference' for L2 free tours, else None
        "community_id": _community_id,  # [LOCAL-701] generate FOR a community (None = ordinary)
        "community_visibility": _community_visibility,  # [LOCAL-701] 'members' | 'public'
        "created_at": datetime.now().isoformat()
    }
    
    # Track user request immediately
    print(f"Checking user tracking condition - user_id: '{user_id}', request_string: '{request_string}'")
    if user_id and request_string:
        try:
            tour_id = f"tour_{job_id[:8]}"
            print(f"Tracking user tour immediately - User: {user_id}, Tour: {tour_id}")
            track_user_tour(user_id, tour_id, request_string)
            ACTIVE_JOBS[job_id]["tour_id"] = tour_id
            print(f"User tour tracking completed successfully")
        except Exception as e:
            print(f"ERROR: Failed to track user tour: {e}")
            print(f"Traceback: {traceback.format_exc()}")
    else:
        print(f"User tracking skipped - user_id empty: {not user_id}, request_string empty: {not request_string}")
    
    # === GENERATION MODE DISPATCH ===
    # [LOCAL-525] The Cloud Tasks enqueue path (_create_job_in_db /
    # _enqueue_cloud_task / tour-worker) does not yet carry the user's stop list.
    # Rather than silently drop it — the exact "not reliably honoured" failure this
    # feature fixes — a request WITH stops runs in thread mode, which forwards them
    # end-to-end. Requests without stops keep the configured mode unchanged.
    _use_cloud_tasks = (GENERATION_MODE == 'cloud_tasks') and (stops is None)
    if GENERATION_MODE == 'cloud_tasks' and stops is not None:
        print(f"[LOCAL-525] Stops provided — using thread mode so the stop list is honoured (job {job_id})")
    if _use_cloud_tasks:
        # Part B: Enqueue to Cloud Tasks — worker does generation synchronously
        # Job state lives in Cloud SQL (job_status table), readable by any instance
        _create_job_in_db(job_id, location, tour_type, total_stops, user_id, request_string, language)
        enqueued = _enqueue_cloud_task(job_id, location, tour_type, total_stops, user_id,
                                       request_string, language, stops)
        if not enqueued:
            # Fallback: if Cloud Tasks enqueue fails, fall back to thread
            print(f"[CLOUD_TASKS] Enqueue failed, falling back to thread mode for job {job_id}")
            thread = threading.Thread(
                target=orchestrate_tour_async,
                args=(job_id, location, tour_type, total_stops, user_id, request_string, language, persona, is_test_override, stops, generation_mode)
            )
            thread.daemon = True
            thread.start()
            _ACTIVE_GENERATION_THREADS.append(thread)
            _ACTIVE_GENERATION_THREADS[:] = [t for t in _ACTIVE_GENERATION_THREADS if t.is_alive()]
    else:
        # Legacy mode: background daemon thread (local Docker / single-instance)
        print(f"Starting orchestration in background thread")
        sys.stdout.flush()
        thread = threading.Thread(
            target=orchestrate_tour_async,
            args=(job_id, location, tour_type, total_stops, user_id, request_string, language, persona, is_test_override, stops, generation_mode)
        )
        thread.daemon = True
        thread.start()
        _ACTIVE_GENERATION_THREADS.append(thread)
        # Clean up completed threads from tracking list
        _ACTIVE_GENERATION_THREADS[:] = [t for t in _ACTIVE_GENERATION_THREADS if t.is_alive()]
    
    print(f"Returning response: job_id={job_id}, status=queued, language={language}, mode={GENERATION_MODE}")
    sys.stdout.flush()
    return jsonify({"job_id": job_id, "status": "queued", "language": language})

@app.route('/status/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get job status. Reads from in-memory dict (thread mode) or database (cloud_tasks mode)."""
    print(f"\n==== STATUS REQUEST: {datetime.now().isoformat()} ====")
    print(f"Job ID: {job_id}")
    
    # Try in-memory first (covers thread mode and recently-created cloud_tasks jobs)
    if job_id in ACTIVE_JOBS:
        job = ACTIVE_JOBS[job_id]
        response = {
            "job_id": job_id,
            "status": job["status"],
            "progress": job.get("progress", ""),
            "location": job.get("location", ""),
            "tour_type": job.get("tour_type", ""),
            "total_stops": job.get("total_stops", 0),
            "created_at": job.get("created_at", "")
        }
        
        if job["status"] == "completed":
            if "output_zip" in job:
                response["output_zip"] = job["output_zip"]
            if "extract_dir" in job:
                response["extract_dir"] = job["extract_dir"]
            response["netlify_ready"] = job.get("netlify_ready", True)
            if "coordinates" in job:
                response["coordinates"] = job["coordinates"]
            if "final_tour_id" in job:
                response["final_tour_id"] = job["final_tour_id"]
            # [LOCAL-718 / D678] int (version archived on a same-creator replace)
            # or null (ordinary new tour / insert / cache hit). Always present on
            # a completed job so LOCAL-717 can read it without a KeyError.
            response["replaced_version_no"] = job.get("replaced_version_no")
            if "translated_tour_id" in job:
                response["translated_tour_id"] = job["translated_tour_id"]
            # [LOCAL-717 / D677 §2] Version of the delivered tour and whether this
            # generation replaced an existing one, so the app says "Updated your
            # tour '<title>' — now version N" rather than announcing a new tour.
            if "version_no" in job:
                response["version_no"] = job["version_no"]
            if "replaced" in job:
                response["replaced"] = job["replaced"]
            if "tour_title" in job:
                response["tour_title"] = job["tour_title"]
            if "expected_stops" in job:
                response["expected_stops"] = job["expected_stops"]
            if "actual_stops" in job:
                response["actual_stops"] = job["actual_stops"]
            if "stop_count_warning" in job:
                response["stop_count_warning"] = job["stop_count_warning"]
            # [LOCAL-307] Surface quality guardrail message to the client.
            # This is the honest user-facing message explaining why a tour is
            # shorter or thinner than requested (UNAVAILABLE diagnosis).
            if "quality_message" in job:
                response["quality_message"] = job["quality_message"]
            if "share_id" in job:
                response["share_id"] = job["share_id"]
                response["share_url"] = job.get("share_url", "")
        elif job["status"] == "error":
            response["error"] = job.get("error", "Unknown error")
        
        print(f"Returning status (memory): {response}")
        return jsonify(response)
    
    # If not in memory, check database (cloud_tasks mode — worker writes status to DB)
    if GENERATION_MODE == 'cloud_tasks' or JOB_STORE_MODE == 'database':
        db_job = _read_job_from_db(job_id)
        if db_job:
            response = {
                "job_id": db_job["job_id"],
                "status": db_job["status"],
                "progress": db_job.get("progress", ""),
                "location": db_job.get("location", ""),
                "tour_type": db_job.get("tour_type", ""),
                "total_stops": db_job.get("total_stops", 0),
                "created_at": db_job.get("created_at", "")
            }
            if db_job["status"] == "completed":
                response["netlify_ready"] = True
                if "final_tour_id" in db_job:
                    response["final_tour_id"] = db_job["final_tour_id"]
                if "english_tour_id" in db_job:
                    response["english_tour_id"] = db_job["english_tour_id"]
                # [LOCAL-717 / D677 §2] Same version fields as the memory path,
                # for cloud_tasks/database mode (merged from output_data).
                if "version_no" in db_job:
                    response["version_no"] = db_job["version_no"]
                if "replaced" in db_job:
                    response["replaced"] = db_job["replaced"]
                if "tour_title" in db_job:
                    response["tour_title"] = db_job["tour_title"]
                # [LOCAL-718 / D678] Mirror the memory branch: present (int|null)
                # on a completed job. In database mode the worker writes it into
                # output_data; if absent (older worker), default to null.
                response["replaced_version_no"] = db_job.get("replaced_version_no")
                if "coordinates" in db_job:
                    response["coordinates"] = db_job["coordinates"]
                if "output_zip" in db_job:
                    response["output_zip"] = db_job["output_zip"]
                if "actual_stops" in db_job:
                    response["actual_stops"] = db_job["actual_stops"]
                if "expected_stops" in db_job:
                    response["expected_stops"] = db_job["expected_stops"]
            elif db_job["status"] == "error":
                response["error"] = db_job.get("error", "Unknown error")
            
            print(f"Returning status (database): {response}")
            return jsonify(response)
    
    print(f"Job not found: {job_id}")
    return jsonify({"error": "Job not found"}), 404


@app.route('/tour-status', methods=['POST'])
def update_tour_status():
    """K1: REST endpoint for mobile app to update tour request status.
    Replaces the client-side raw SQL direct DB update.
    
    Request body:
        {
            "tour_id": "tour_19e73f4059d",    (required)
            "status": "completed|failed|started",  (required)
            "job_id": "uuid"                  (optional, for correlation)
        }
    Response:
        {"status": "success", "tour_id": "...", "rows_affected": 1}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "JSON body required"}), 400
        
        tour_id = data.get('tour_id')
        new_status = data.get('status')
        
        if not tour_id or not new_status:
            return jsonify({"status": "error", "message": "tour_id and status are required"}), 400
        
        # Validate status value
        allowed_statuses = ('started', 'completed', 'failed', 'processing')
        if new_status not in allowed_statuses:
            return jsonify({"status": "error", "message": f"status must be one of: {allowed_statuses}"}), 400
        
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        
        if new_status == 'completed':
            cur.execute(
                "UPDATE tour_requests SET status = %s, finished_at = NOW() WHERE tour_id = %s",
                (new_status, tour_id)
            )
        else:
            cur.execute(
                "UPDATE tour_requests SET status = %s WHERE tour_id = %s",
                (new_status, tour_id)
            )
        
        rows_affected = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        
        print(f"[TOUR-STATUS] Updated tour_id={tour_id} to status={new_status}, rows={rows_affected}")
        return jsonify({"status": "success", "tour_id": tour_id, "rows_affected": rows_affected})
    
    except Exception as e:
        print(f"[TOUR-STATUS] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download/<job_id>', methods=['GET'])
def download_tour(job_id):
    """Download the complete tour package."""
    print(f"\n==== DOWNLOAD REQUEST: {datetime.now().isoformat()} ====")
    print(f"Job ID: {job_id}")
    
    # First try to find in active jobs (for recently generated tours)
    if job_id in ACTIVE_JOBS:
        job = ACTIVE_JOBS[job_id]
        if job["status"] != "completed":
            print(f"Job not completed: {job_id}")
            return jsonify({"error": "Job not completed"}), 400
        
        zip_path = os.path.join(TOURS_DIR, job["output_zip"])
        if os.path.exists(zip_path):
            # Sanitize filename by removing newlines and other problematic characters
            safe_filename = job["output_zip"].replace('\n', '_').replace('\r', '_').replace('/', '_').replace('\\', '_').replace(':', '_').replace('*', '_').replace('?', '_').replace('"', '_').replace('<', '_').replace('>', '_').replace('|', '_')
            
            print(f"Sending file from active jobs: {zip_path}")
            return send_file(zip_path, as_attachment=True, attachment_filename=safe_filename)
    
    # Try to find in database (for translated tours or older tours)
    try:
        tour_id = int(job_id)
        print(f"Looking for tour ID {tour_id} in database")
        
        import psycopg2
        import io
        
        # Connect to database
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()
        
        # Get tour from database
        cur.execute(
            "SELECT tour_name, audio_tour FROM audio_tours WHERE id = %s",
            (tour_id,)
        )
        result = cur.fetchone()
        
        if result:
            tour_name, zip_data = result
            print(f"Found tour in database: {tour_name}")
            print(f"ZIP data size: {len(zip_data)} bytes")
            
            # Create a safe filename
            safe_filename = f"tour_{tour_id}.zip"
            
            # Create BytesIO object from the binary data
            zip_buffer = io.BytesIO(zip_data)
            zip_buffer.seek(0)
            
            print(f"Sending tour from database: {safe_filename}")
            
            # Close database connection
            cur.close()
            conn.close()
            
            return send_file(
                zip_buffer,
                as_attachment=True,
                attachment_filename=safe_filename,
                mimetype='application/zip'
            )
        else:
            print(f"Tour ID {tour_id} not found in database")
            cur.close()
            conn.close()
            return jsonify({"error": "Tour not found"}), 404
            
    except ValueError:
        # job_id is not a number, only check active jobs
        print(f"Job ID is not numeric: {job_id}")
        return jsonify({"error": "Job not found"}), 404
    except Exception as e:
        print(f"Database error: {e}")
        return jsonify({"error": "Database error"}), 500

@app.route('/serve/<job_id>', methods=['GET'])
def serve_tour_info(job_id):
    """Get information about serving the tour."""
    print(f"\n==== SERVE REQUEST: {datetime.now().isoformat()} ====")
    print(f"Job ID: {job_id}")
    
    if job_id not in ACTIVE_JOBS:
        print(f"Job not found: {job_id}")
        return jsonify({"error": "Job not found"}), 404
    
    job = ACTIVE_JOBS[job_id]
    if job["status"] != "completed":
        print(f"Job not completed: {job_id}")
        return jsonify({"error": "Job not completed"}), 400
    
    extract_path = os.path.join(TOURS_DIR, job["extract_dir"])
    if not os.path.exists(extract_path):
        print(f"Tour directory not found: {extract_path}")
        return jsonify({"error": "Tour directory not found"}), 404
    
    response = {
        "job_id": job_id,
        "extract_dir": job["extract_dir"],
        "local_path": extract_path,
        "instructions": [
            "1. Download the ZIP file using /download/{job_id}",
            "2. Extract the ZIP file to your desired location",
            "3. Serve the extracted directory with any web server",
            "4. Or deploy the directory directly to Netlify"
        ],
        "netlify_ready": True
    }
    
    # Add coordinates if available
    if "coordinates" in job:
        response["coordinates"] = job["coordinates"]
    
    print(f"Returning serve info: {response}")
    return jsonify(response)

@app.route('/jobs', methods=['GET'])
def list_jobs():
    """List all orchestration jobs."""
    print(f"\n==== LIST JOBS REQUEST: {datetime.now().isoformat()} ====")
    
    jobs = []
    for job_id, job_data in ACTIVE_JOBS.items():
        job_info = {
            "job_id": job_id,
            "status": job_data["status"],
            "location": job_data["location"],
            "tour_type": job_data["tour_type"],
            "total_stops": job_data["total_stops"],
            "created_at": job_data["created_at"],
            "progress": job_data.get("progress", "")
        }
        
        # Add coordinates if available
        if "coordinates" in job_data:
            job_info["coordinates"] = job_data["coordinates"]
        
        jobs.append(job_info)
    
    print(f"Returning {len(jobs)} jobs")
    return jsonify({"jobs": jobs})


# === ACCOUNT DELETION (Apple/Google Store requirement) ===
@app.route('/delete-account/<secret_id>', methods=['DELETE'])
def delete_account(secret_id):
    """Full erasure of all personal data for a user. Idempotent.
    Required by Apple App Store and Google Play Store policies.
    Deletes from ALL tables keyed on secret_id/device_id, children before parents.

    [LOCAL-695] Consolidation-aware: once profiles span multiple devices under one
    consolidated_user_id (recovery-code portability), deletion must wipe EVERY
    linked device, not just the one that made the request (June design note). We
    resolve the full set of device ids (and the profile id) behind this secret_id
    first, then delete device-keyed rows for ALL of them. A single-device user
    resolves to a one-element set, so the previous behaviour is unchanged."""
    print(f"\n==== DELETE ACCOUNT REQUEST: {datetime.now().isoformat()} ====")
    print(f"secret_id: {secret_id}")
    
    if not secret_id or secret_id.strip() == '':
        return jsonify({"error": "secret_id required"}), 400
    
    conn = None
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv('DB_HOST', 'postgres-2'),
            database=os.getenv('DB_NAME', 'audiotours'),
            user=os.getenv('DB_USER', 'admin'),
            password=os.getenv('DB_PASSWORD', 'password123'),
            port=os.getenv('DB_PORT', '5432')
        )
        cur = conn.cursor()

        # [LOCAL-695] Resolve the consolidated identity: every device id linked to
        # this secret_id's profile (primary + every merged device, linked OR
        # unlinked), plus the profile id itself and secret_id. Falls back to
        # {secret_id} if the consolidation module/tables are absent, so deletion
        # never fails to remove the current device.
        try:
            from recovery_code_service import linked_device_ids_for_deletion
            identity_ids = sorted(linked_device_ids_for_deletion(cur, secret_id))
        except Exception as _rc_err:  # noqa: BLE001
            print(f"[DELETE-ACCOUNT] consolidation resolve fell back ({_rc_err}); single-device delete")
            identity_ids = [secret_id]
        # The profile id (if any) is included in identity_ids; the device ids are
        # every entry. Both sets are used below.
        print(f"[DELETE-ACCOUNT] consolidated identity spans {len(identity_ids)} id(s): {identity_ids}")

        # Everything in one transaction — fail-closed (all or nothing)
        tables_deleted = []
        
        # --- Children of article_requests (must go first due to FK) ---
        cur.execute("DELETE FROM news_audios WHERE article_id IN (SELECT article_id FROM article_requests WHERE secret_id = ANY(%s))", (identity_ids,))
        tables_deleted.append(('news_audios', cur.rowcount))
        
        # --- Credential/encryption tables (keyed on device_id or consolidated_user_id) ---
        # Delete by device_id in the identity set OR consolidated_user_id in the set.
        cur.execute("DELETE FROM user_subscription_credentials WHERE device_id = ANY(%s) OR consolidated_user_id = ANY(%s)", (identity_ids, identity_ids))
        tables_deleted.append(('user_subscription_credentials', cur.rowcount))
        
        cur.execute("DELETE FROM dh_aes_keys WHERE device_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('dh_aes_keys', cur.rowcount))
        
        cur.execute("DELETE FROM dh_server_keys WHERE device_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('dh_server_keys', cur.rowcount))
        
        cur.execute("DELETE FROM device_encryption_keys WHERE device_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('device_encryption_keys', cur.rowcount))

        # --- Recovery-code + restore ledgers (LOCAL-695) ---
        # Delete by consolidated_user_id in the identity set, and by requesting
        # device for the per-device attempt ledger. Only runs when the tables
        # exist (a DB that predates migration 033 skips them cleanly).
        cur.execute("SELECT to_regclass('recovery_codes')")
        if cur.fetchone()[0] is not None:
            cur.execute("DELETE FROM recovery_codes WHERE consolidated_user_id = ANY(%s)", (identity_ids,))
            tables_deleted.append(('recovery_codes', cur.rowcount))
        cur.execute("SELECT to_regclass('profile_restores')")
        if cur.fetchone()[0] is not None:
            cur.execute("DELETE FROM profile_restores WHERE consolidated_user_id = ANY(%s) OR new_device_id = ANY(%s) OR unlinked_device_id = ANY(%s)", (identity_ids, identity_ids, identity_ids))
            tables_deleted.append(('profile_restores', cur.rowcount))
        cur.execute("SELECT to_regclass('restore_attempts')")
        if cur.fetchone()[0] is not None:
            cur.execute("DELETE FROM restore_attempts WHERE device_id = ANY(%s)", (identity_ids,))
            tables_deleted.append(('restore_attempts', cur.rowcount))

        # --- Consolidation tables ---
        cur.execute("DELETE FROM device_consolidation_history WHERE consolidated_user_id = ANY(%s) OR merged_device_id = ANY(%s)", (identity_ids, identity_ids))
        tables_deleted.append(('device_consolidation_history', cur.rowcount))
        
        cur.execute("DELETE FROM user_consolidation_map WHERE consolidated_user_id = ANY(%s) OR primary_device_id = ANY(%s)", (identity_ids, identity_ids))
        tables_deleted.append(('user_consolidation_map', cur.rowcount))
        
        # --- Tables with FK to users (children, must go before users) ---
        cur.execute("DELETE FROM coordinates WHERE secret_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('coordinates', cur.rowcount))
        
        cur.execute("DELETE FROM map_requests WHERE secret_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('map_requests', cur.rowcount))
        
        cur.execute("DELETE FROM tour_requests WHERE secret_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('tour_requests', cur.rowcount))
        
        cur.execute("DELETE FROM article_requests WHERE secret_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('article_requests', cur.rowcount))
        
        # --- Parent: users table (last — all FK children already removed) ---
        cur.execute("DELETE FROM users WHERE secret_id = ANY(%s)", (identity_ids,))
        tables_deleted.append(('users', cur.rowcount))
        
        conn.commit()
        cur.close()
        
        total_rows = sum(count for _, count in tables_deleted)
        print(f"[DELETE-ACCOUNT] Deleted {total_rows} total rows for {secret_id} ({len(identity_ids)} linked id(s))")
        for table, count in tables_deleted:
            if count > 0:
                print(f"  {table}: {count} rows")
        
        return jsonify({"deleted": True, "rows_removed": total_rows, "linked_ids": len(identity_ids)})
    
    except Exception as e:
        print(f"[DELETE-ACCOUNT] ERROR: {e}")
        if conn:
            conn.rollback()
        return jsonify({"error": "deletion_failed", "message": "Could not delete account. Please try again."}), 500
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == '__main__':
    # Ensure tours directory exists
    ensure_tours_directory()
    
    print(f"Starting Modified Tour Orchestrator Service: {datetime.now().isoformat()}")
    print(f"Tours directory: {TOURS_DIR}")
    print(f"Pipeline: Complete tour generation orchestration with database storage")

    # [LOCAL-596] Guarded hourly L2 seat-maintenance job.
    # The orchestrator already runs background work as daemon threads
    # (GENERATION_MODE=thread); there is no launchd autonomy_tick.sh in this tree
    # (that tick is a task-file dispatcher, not a general cron). So the hourly
    # seat job (evict idle L2 >=7d, expire offers >72h, offer free seats to the
    # queue head) is wired here as a guarded daemon thread. It is OFF by default
    # and only starts when L2_SEAT_JOB_ENABLED=true, so existing deployments are
    # unaffected until explicitly opted in. The same job is runnable standalone
    # (python3 l2_seat_job.py) for manual use or a future launchd/cron entry.
    if os.getenv('L2_SEAT_JOB_ENABLED', 'false').lower() == 'true':
        try:
            import l2_seat_job
            _seat_job_thread = threading.Thread(
                target=l2_seat_job.run_forever,
                kwargs={'quiet': False},
                name='l2-seat-job',
                daemon=True,
            )
            _seat_job_thread.start()
            print("[LOCAL-596] L2 seat-maintenance job thread started "
                  f"(interval={os.getenv('L2_SEAT_JOB_INTERVAL_SECONDS', '3600')}s)")
        except Exception as _seat_job_err:  # pragma: no cover - startup safety
            print(f"[LOCAL-596] WARNING: could not start L2 seat job thread: {_seat_job_err}")
    else:
        print("[LOCAL-596] L2 seat-maintenance job disabled "
              "(set L2_SEAT_JOB_ENABLED=true to enable)")

    # Run Flask app
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5002')), debug=False)