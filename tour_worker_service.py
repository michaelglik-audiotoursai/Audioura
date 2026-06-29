"""
Tour Worker Service — Cloud Tasks target for tour generation.
==============================================================

This service does the FULL tour generation pipeline synchronously within
the Cloud Tasks HTTP request. CPU is allocated for the entire request duration
(no throttling), and the service scales 0→N based on task queue depth.

Called by: Cloud Tasks queue 'tour-generation'
Writes to: Cloud SQL job_status table (via DatabaseJobStore)
Stores:    Final tour ZIP in database (audio_tours table)

Design:
  - POST /run-job: receives job payload from Cloud Tasks, runs generation
  - No background threads — everything is synchronous within the request
  - Progress updates written to job_status for mobile polling
  - Cloud Tasks handles retries on failure
  - Idempotent: if job already completed, returns success without re-running
"""

import os
import sys
import json
import uuid
import zipfile
import shutil
import time
import requests
import traceback
import re
from datetime import datetime
from flask import Flask, request, jsonify

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)

# Inter-service URLs (env-var-driven for Cloud Run)
TOUR_GENERATOR_URL = os.getenv('TOUR_GENERATOR_URL', 'http://development-tour-generator-1:5000')
MODERNIZED_URL = os.getenv('MODERNIZED_URL', 'http://tour-generation-modernized-1:5021')
TRANSLATION_URL = os.getenv('TRANSLATION_URL', 'http://translation-service-1:5030')
TOUR_UPDATE_URL = os.getenv('TOUR_UPDATE_URL', 'http://development-tour-update-1:5001')
USER_API_URL = os.getenv('USER_API_URL', 'http://user-api-2:5000')
COORDINATES_URL = os.getenv('COORDINATES_URL', 'http://coordinates-fromai:5004')

TOURS_DIR = "/app/tours"

# Max poll iterations before failing (prevents infinite loops on hung sub-services)
MAX_POLL_ITERATIONS = 60  # 60 * 10s = 10 min for text gen; 60 * 5s = 5 min for TTS

# Cloud Tasks max retry attempts (must match queue config — env-driven to stay in sync)
MAX_TASK_ATTEMPTS = int(os.getenv('MAX_TASK_ATTEMPTS', '3'))

app = Flask(__name__)


# === Auth helpers (same pattern as orchestrator) ===

def _get_auth_headers(target_url):
    """Get authorization headers for service-to-service calls on Cloud Run."""
    if not target_url.startswith('https://'):
        return {}
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
    from urllib.parse import urlparse
    parsed = urlparse(url)
    audience = f"{parsed.scheme}://{parsed.netloc}"
    auth_headers = _get_auth_headers(audience)

    headers = kwargs.get('headers', {}) or {}
    headers.update(auth_headers)
    kwargs['headers'] = headers

    return requests.request(method, url, **kwargs)


# === Database helpers ===

def _get_db_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
    )


def update_job_status(job_id, status, progress='', error=None, **extra):
    """Write job progress to job_status table (readable by any instance).
    Uses COALESCE to handle NULL output_data safely (prevents NULL || jsonb = NULL)."""
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        output_data = json.dumps(extra, default=str) if extra else '{}'
        if error:
            cur.execute("""
                UPDATE job_status SET status=%s, progress=%s, error=%s,
                    output_data=COALESCE(output_data, '{}'::jsonb) || %s::jsonb,
                    updated_at=CURRENT_TIMESTAMP
                WHERE job_id=%s
            """, (status, progress, error, output_data, job_id))
        else:
            cur.execute("""
                UPDATE job_status SET status=%s, progress=%s,
                    output_data=COALESCE(output_data, '{}'::jsonb) || %s::jsonb,
                    updated_at=CURRENT_TIMESTAMP
                WHERE job_id=%s
            """, (status, progress, output_data, job_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"[JOB_STATUS] Failed to update job {job_id}: {e}")


# === Coordinates helper ===

def get_coordinates_direct(location):
    """Get coordinates from the coordinates service."""
    import urllib.parse
    try:
        encoded_location = urllib.parse.quote(location)
        url = f"{COORDINATES_URL}/coordinates/{encoded_location}"
        response = _authenticated_request("GET", url, timeout=60)
        if response.status_code == 200:
            data = response.json()
            if "coordinates" in data and len(data["coordinates"]) >= 2:
                return (data["coordinates"][0], data["coordinates"][1])
    except Exception as e:
        print(f"[COORDS] Error getting coordinates for {location}: {e}")
    return (0, 0)


# === Tour storage ===

def store_audio_tour(tour_name, request_string, zip_path, lat, lng, tour_content=None):
    """Store the audio tour ZIP in the database."""
    try:
        import psycopg2
        conn = _get_db_conn()
        cur = conn.cursor()

        with open(zip_path, "rb") as f:
            zip_data = f.read()
        print(f"[STORE] Read {len(zip_data)} bytes from {zip_path}")

        # Check if tour already exists
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name = %s AND request_string = %s",
            (tour_name, request_string)
        )
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE audio_tours
                SET audio_tour=%s, number_requested=number_requested+1, lat=%s, lng=%s, tour_content=%s
                WHERE id=%s
            """, (psycopg2.Binary(zip_data), lat, lng, tour_content, existing[0]))
            print(f"[STORE] Updated existing tour: {tour_name} (id={existing[0]})")
        else:
            cur.execute("""
                INSERT INTO audio_tours (tour_name, request_string, audio_tour, number_requested, lat, lng, tour_content, content_language)
                VALUES (%s, %s, %s, 1, %s, %s, %s, 'en')
            """, (tour_name, request_string, psycopg2.Binary(zip_data), lat, lng, tour_content))
            print(f"[STORE] Inserted new tour: {tour_name}")

        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[STORE] ERROR: {e}\n{traceback.format_exc()}")
        return False


def get_tour_id_from_db(tour_name, request_string):
    """Get the tour ID after storing."""
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM audio_tours WHERE tour_name=%s AND request_string=%s ORDER BY id DESC LIMIT 1",
            (tour_name, request_string)
        )
        result = cur.fetchone()
        cur.close()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        print(f"[DB] Error getting tour ID: {e}")
        return None


# === Main generation pipeline ===

def _read_job_status(job_id):
    """Read current job status from database (for idempotency check)."""
    try:
        conn = _get_db_conn()
        cur = conn.cursor()
        cur.execute("SELECT status FROM job_status WHERE job_id = %s", (job_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return {'status': row[0]} if row else None
    except Exception as e:
        print(f"[IDEMPOTENCY] Error reading job {job_id}: {e}")
        return None


def run_generation(job_id, location, tour_type, total_stops, user_id=None, request_string=None, language='en'):
    """
    Execute the full tour generation pipeline synchronously.
    Updates job_status table with progress throughout.
    Returns True on success, False on failure.
    
    IDEMPOTENT: If the job is already completed, returns True without re-running.
    This protects against Cloud Tasks lost-response retries.
    """
    # --- Idempotency guard (must-fix #1) ---
    existing = _read_job_status(job_id)
    if existing and existing.get('status') == 'completed':
        print(f"[WORKER] Job {job_id} already completed — skipping (idempotent)")
        return True

    print(f"\n==== WORKER: GENERATION STARTED {datetime.now().isoformat()} ====")
    print(f"  job_id={job_id}, location={location}, type={tour_type}, stops={total_stops}, lang={language}")

    update_job_status(job_id, 'processing', 'Starting tour generation pipeline...')

    try:
        # --- Step 1: Generate tour text ---
        update_job_status(job_id, 'processing', 'Step 1/5: Generating tour text...')
        generate_data = {"location": location, "tour_type": tour_type, "total_stops": total_stops}

        response = _authenticated_request("POST", f"{TOUR_GENERATOR_URL}/generate",
            headers={"Content-Type": "application/json"},
            json=generate_data, timeout=60)

        if response.status_code != 200:
            raise Exception(f"Tour generator returned {response.status_code}: {response.text[:500]}")

        job_data = response.json()
        gen_job_id = job_data["job_id"]
        print(f"[STEP1] Generator job: {gen_job_id}")

        # Poll for text generation completion (with max iteration cap)
        coordinates = None
        tour_file = None
        poll_count = 0
        while poll_count < MAX_POLL_ITERATIONS:
            poll_count += 1
            status_resp = _authenticated_request("GET", f"{TOUR_GENERATOR_URL}/status/{gen_job_id}", timeout=10)
            if status_resp.status_code != 200:
                raise Exception(f"Generator status check failed: {status_resp.text[:500]}")

            sdata = status_resp.json()
            if sdata["status"] == "completed":
                tour_file = sdata.get("output_file")
                coordinates = sdata.get("coordinates")
                break
            elif sdata["status"] == "error":
                raise Exception(f"Text generation error: {sdata.get('error', 'Unknown')}")
            else:
                progress = sdata.get('progress', 'Processing...')
                update_job_status(job_id, 'processing', f'Text generation: {progress}')
                time.sleep(10)
        else:
            raise Exception(f"Text generation timed out after {MAX_POLL_ITERATIONS} polls ({MAX_POLL_ITERATIONS * 10}s)")

        # --- Step 2: Modernized service (TTS + ZIP) ---
        update_job_status(job_id, 'processing', 'Step 2/5: Converting to audio...')
        tour_content = sdata.get("tour_content")
        modernized_data = {"tour_content": tour_content} if tour_content else {"tour_file": tour_file}

        mod_resp = _authenticated_request("POST", f"{MODERNIZED_URL}/process",
            headers={"Content-Type": "application/json"},
            json=modernized_data, timeout=60)

        if mod_resp.status_code != 200:
            raise Exception(f"Modernized service error: {mod_resp.text[:500]}")

        mod_job_id = mod_resp.json()["job_id"]

        # Poll modernized (with max iteration cap)
        poll_count = 0
        while poll_count < MAX_POLL_ITERATIONS:
            poll_count += 1
            mod_status = _authenticated_request("GET", f"{MODERNIZED_URL}/status/{mod_job_id}", timeout=10)
            if mod_status.status_code != 200:
                raise Exception(f"Modernized status check failed: {mod_status.text[:500]}")
            mdata = mod_status.json()
            if mdata["status"] == "completed":
                break
            elif mdata["status"] == "error":
                raise Exception(f"Audio generation error: {mdata.get('error', 'Unknown')}")
            else:
                update_job_status(job_id, 'processing', f'Audio: {mdata.get("progress", "Processing...")}')
                time.sleep(5)
        else:
            raise Exception(f"Audio generation timed out after {MAX_POLL_ITERATIONS} polls ({MAX_POLL_ITERATIONS * 5}s)")

        # --- Step 3: Get coordinates ---
        if not coordinates or not isinstance(coordinates, list) or len(coordinates) < 2:
            lat, lng = get_coordinates_direct(location)
            coordinates = [lat, lng]

        # --- Step 4: Download and save ZIP ---
        update_job_status(job_id, 'processing', 'Step 3/5: Downloading tour package...')
        dl_resp = _authenticated_request("GET", f"{MODERNIZED_URL}/download/{mod_job_id}", timeout=60)
        if dl_resp.status_code != 200:
            raise Exception(f"Download error: {dl_resp.text[:500]}")

        safe_location = re.sub(r'[^a-z0-9_]', '_', location.lower())[:50]
        zip_filename = f"{safe_location}_{tour_type}_{job_id[:8]}.zip"
        zip_path = os.path.join(TOURS_DIR, zip_filename)
        os.makedirs(TOURS_DIR, exist_ok=True)
        with open(zip_path, 'wb') as f:
            f.write(dl_resp.content)
        print(f"[STEP4] Saved ZIP: {zip_path} ({len(dl_resp.content)} bytes)")

        # --- Step 5: Verify stop count ---
        update_job_status(job_id, 'processing', 'Step 4/5: Verifying tour...')
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                audio_files = [n for n in zf.namelist() if re.fullmatch(r'audio_\d+\.mp3', n)]
            actual_stops = len(audio_files)
        except Exception:
            actual_stops = None

        if actual_stops == 0 or actual_stops is None:
            raise Exception(f"Tour ZIP has no audio files (expected {total_stops})")

        # --- Step 6: Store in database ---
        update_job_status(job_id, 'processing', 'Step 5/5: Storing tour...')
        tour_name = f"{location} - {tour_type} Tour"
        lat = coordinates[0] if coordinates and len(coordinates) >= 2 else None
        lng = coordinates[1] if coordinates and len(coordinates) >= 2 else None

        # Add tour_content.txt to ZIP if available
        if tour_content:
            try:
                with zipfile.ZipFile(zip_path, 'a') as zf:
                    zf.writestr('tour_content.txt', tour_content.encode('utf-8'))
            except Exception:
                pass

        store_success = store_audio_tour(tour_name, request_string or location, zip_path, lat, lng, tour_content)
        if not store_success:
            raise Exception("Failed to store tour in database")

        english_tour_id = get_tour_id_from_db(tour_name, request_string or location)
        final_tour_id = english_tour_id
        translation_failed = False

        # --- Step 7: Translate if non-English ---
        if language != 'en' and english_tour_id:
            update_job_status(job_id, 'processing', f'Translating to {language.upper()}...')
            try:
                tr_resp = _authenticated_request("POST", f"{TRANSLATION_URL}/translate-with-audio",
                    headers={"Content-Type": "application/json"},
                    json={"content_id": english_tour_id, "content_type": "tour", "languages": [language]},
                    timeout=120)
                if tr_resp.status_code == 200:
                    tr_data = tr_resp.json()
                    translated_id = tr_data.get('translated_tour_ids', {}).get(language)
                    if translated_id:
                        final_tour_id = translated_id
                        print(f"[TRANSLATE] Success: translated tour ID={translated_id}")
                    else:
                        translation_failed = True
                        print(f"[TRANSLATE] Warning: translation completed but no tour ID for {language}")
                else:
                    translation_failed = True
                    print(f"[TRANSLATE] Failed: {tr_resp.status_code} — {tr_resp.text[:200]}")
            except Exception as tr_err:
                translation_failed = True
                print(f"[TRANSLATE] Error (non-fatal): {tr_err}")

        # --- Step 8: Update tour_requests if tracked ---
        # Uses subquery because PostgreSQL UPDATE does not support ORDER BY/LIMIT directly
        if user_id:
            try:
                conn = _get_db_conn()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE tour_requests SET status='completed', finished_at=NOW()
                    WHERE id = (
                        SELECT id FROM tour_requests
                        WHERE secret_id=%s AND status IN ('started','processing')
                        ORDER BY started_at DESC LIMIT 1
                    )
                """, (user_id,))
                conn.commit()
                cur.close()
                conn.close()
            except Exception as e:
                print(f"[TOUR_REQ] Error updating: {e}")

        # --- Done ---
        completion_extras = {
            "final_tour_id": final_tour_id,
            "english_tour_id": english_tour_id,
            "output_zip": zip_filename,
            "coordinates": coordinates,
            "actual_stops": actual_stops,
            "expected_stops": total_stops,
            "language": language,
        }
        if translation_failed:
            completion_extras["translation_failed"] = True

        update_job_status(job_id, 'completed',
            f'Tour generation completed in {language.upper()}!',
            **completion_extras)

        # Clean up local ZIP (it's in the DB now)
        try:
            os.remove(zip_path)
        except Exception:
            pass

        print(f"==== WORKER: GENERATION COMPLETED {datetime.now().isoformat()} ====")
        return True

    except Exception as e:
        print(f"==== WORKER: GENERATION FAILED {datetime.now().isoformat()} ====")
        print(f"Error: {e}\n{traceback.format_exc()}")
        # Error status is written by the caller (run_job) based on retry count
        # We return the error message for the caller to decide
        raise


# === Flask routes ===

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy", "service": "tour-worker"})


@app.route('/run-job', methods=['POST'])
def run_job():
    """
    Cloud Tasks target endpoint.
    Receives job payload, runs the full generation synchronously,
    and returns 200 on success (or 500 on failure for Cloud Tasks retry).
    
    Retry-aware: only marks job as 'error' on the FINAL retry attempt.
    On earlier failures, keeps status as 'processing' so the mobile app
    continues polling while Cloud Tasks retries.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    job_id = data.get('job_id')
    location = data.get('location')
    tour_type = data.get('tour_type')
    total_stops = data.get('total_stops', 10)
    user_id = data.get('user_id')
    request_string = data.get('request_string')
    language = data.get('language', 'en')

    if not job_id or not location or not tour_type:
        return jsonify({"error": "job_id, location, and tour_type required"}), 400

    # Cloud Tasks sends retry count in headers (0-indexed)
    retry_count = int(request.headers.get('X-CloudTasks-TaskRetryCount', '0'))
    is_final_attempt = (retry_count >= MAX_TASK_ATTEMPTS - 1)

    print(f"[RUN-JOB] job_id={job_id}, retry={retry_count}/{MAX_TASK_ATTEMPTS}, final={is_final_attempt}")

    try:
        success = run_generation(job_id, location, tour_type, total_stops, user_id, request_string, language)
        if success:
            return jsonify({"status": "completed", "job_id": job_id}), 200
        else:
            # Should not reach here (run_generation raises on failure)
            return jsonify({"status": "error", "job_id": job_id}), 500
    except Exception as e:
        error_msg = str(e)
        if is_final_attempt:
            # Final attempt — mark the job as permanently failed
            update_job_status(job_id, 'error', error_msg, error=error_msg)
            print(f"[RUN-JOB] FINAL attempt failed for {job_id}: {error_msg}")
            
            # Rollback usage row so a failed tour doesn't permanently consume quota
            try:
                _rc = _get_db_conn()
                _rcur = _rc.cursor()
                _rcur.execute("DELETE FROM tour_requests WHERE tour_id = %s AND source = 'orchestrator'", (job_id,))
                _rc.commit()
                _rcur.close()
                _rc.close()
                print(f"[RUN-JOB] Rolled back usage row for permanently failed job {job_id}")
            except Exception as rb_err:
                print(f"[RUN-JOB] WARNING: usage rollback failed (non-fatal): {rb_err}")
        else:
            # Not final — keep status as 'processing' so app keeps polling while Tasks retries
            update_job_status(job_id, 'processing', f'Retrying after error: {error_msg[:200]}')
            print(f"[RUN-JOB] Attempt {retry_count+1}/{MAX_TASK_ATTEMPTS} failed for {job_id}, will retry: {error_msg[:200]}")

        # Return 500 so Cloud Tasks retries (unless it's the final attempt)
        return jsonify({"status": "error", "job_id": job_id, "retry": retry_count}), 500


if __name__ == '__main__':
    os.makedirs(TOURS_DIR, exist_ok=True)
    print(f"Starting Tour Worker Service: {datetime.now().isoformat()}")
    port = int(os.getenv('PORT', '5040'))
    app.run(host='0.0.0.0', port=port, debug=False)
