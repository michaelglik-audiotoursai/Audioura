"""
Tour ID Resolution Service - REQ-004 Implementation
Maps download IDs (numeric) to edit IDs (UUID) for cross-service compatibility.

LOCAL-50: Deterministic resolution via stored zip_filename column.
Filesystem scanning is a legacy fallback only, logs loudly, and refuses
to resolve ambiguous matches.
"""
import sys
sys.path.insert(0, '/app')  # Ensure storied modules are importable
try:
    from storied_version_constants import STORIED_SERVICE_VERSION
    SERVICE_VERSION = STORIED_SERVICE_VERSION
except ImportError:
    SERVICE_VERSION = "2.2.0.1"

import os
import json
import logging
import psycopg2
from pathlib import Path
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

from deeplink_resolution_endpoint import deeplink_bp
app.register_blueprint(deeplink_bp)

TOURS_DIR = "/app/tours"

# --- Failure recorder (LOCAL-785 / D723) ---
# tour-id-resolution records its 404 (tour/edit-id not found) and 5xx failures to
# failure_events. Guarded import; never raises; 1s DB timeout; stdout fallback.
try:
    import failure_log as _failure_log
except Exception:
    _failure_log = None


def _record_failure(**kw):
    if _failure_log is None:
        return None
    try:
        kw.setdefault("service", "tour-id-resolution")
        kw.setdefault("surface", "resolve")
        kw.setdefault("track", os.getenv("TOUR_TRACK"))
        return _failure_log.record(**kw)
    except Exception:
        return None


@app.errorhandler(Exception)
def _record_unhandled_exception(e):
    """[LOCAL-785] Record every unhandled exception then re-raise the SAME 500."""
    from werkzeug.exceptions import HTTPException as _HTTPException
    if isinstance(e, _HTTPException):
        return e
    try:
        _record_failure(surface="resolve", exc=e, http_status=500,
                        message=str(e), exception_type=type(e).__name__)
    except Exception:
        pass
    raise e


logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# [LOCAL-781] On Cloud Run the tour ZIPs live in Cloudflare R2, not on local
# disk — /app/tours is empty. Resolution must therefore check the ZIP's
# existence in the SAME blob layer map_delivery_service.py reads from, driven by
# the SAME BLOB_STORAGE_TYPE/R2_* env. When BLOB_STORAGE_TYPE is unset (the Mac
# stack) this returns None and the disk stays the source of truth — behaviour is
# exactly as before this task. Lazily constructed and cached, like map-delivery.
_blob_storage = None


def _get_blob_storage():
    """Return the R2 blob storage when BLOB_STORAGE_TYPE=r2, else None (disk mode).

    Mirrors map_delivery_service._get_blob_storage so both services agree on when
    the cloud object store is authoritative and when the local disk is.
    """
    global _blob_storage
    if _blob_storage is None:
        blob_type = os.getenv('BLOB_STORAGE_TYPE', 'database')
        if blob_type == 'r2':
            from blobstorage import R2BlobStorage
            _blob_storage = R2BlobStorage()
        else:
            _blob_storage = None
    return _blob_storage


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
    )


def _extract_uuid_from_zip_stem(stem):
    """Extract the trailing UUID segment from a ZIP filename stem.

    Convention: the UUID is the last underscore-separated part, at least
    8 alphanumeric characters (e.g. 'a1b2c3d4' from 'boston_common_walking_a1b2c3d4').
    """
    parts = stem.split('_')
    if len(parts) > 1:
        candidate = parts[-1]
        if len(candidate) >= 8 and candidate.replace('-', '').isalnum():
            return candidate
    return None


def _resolve_from_column(download_id, conn):
    """Primary path: look up zip_filename stored on the row.

    Returns a result dict or None if column is NULL/missing.

    [LOCAL-50] The deterministic edit id always comes from the stored
    zip_filename column, never from a filesystem guess.

    [LOCAL-781] The existence check is backend-aware:
      - Blob mode (BLOB_STORAGE_TYPE=r2, Cloud Run): the ZIP lives in R2, so
        existence is `blobstorage.exists(tour_blob_uri)`. /app/tours is empty and
        is never touched. stops_count/editability come from the DB row, not a ZIP
        read, so no object download is needed just to answer /resolve.
      - Disk mode (no BLOB env, the Mac stack): unchanged — the ZIP must be on
        local disk at TOURS_DIR/zip_filename.
    """
    blob = _get_blob_storage()

    cur = conn.cursor()
    if blob is not None:
        # Cloud: also fetch the R2 key (tour_blob_uri) and stops_count from the DB.
        cur.execute(
            "SELECT tour_name, zip_filename, tour_blob_uri, stops_count, "
            "COALESCE(octet_length(audio_tour), 0) "
            "FROM audio_tours WHERE id = %s",
            (int(download_id),)
        )
        result = cur.fetchone()
        cur.close()

        if not result:
            return None  # row does not exist

        tour_name, zip_filename, tour_blob_uri, stops_count, db_zip_bytes = result

        if not zip_filename:
            return None  # column not populated (legacy row) -> fallback

        # The R2 key normally comes from tour_blob_uri (map_delivery's read key).
        # If the row predates the blob migration, fall back to the conventional
        # key 'tours/<id>.zip' so an existing object is still found.
        blob_key = tour_blob_uri or f"tours/{int(download_id)}.zip"

        # [LOCAL-781 fix, 2026-10-26] Subscribed and Storied ZIPs live in the DB column
        # audio_tours.audio_tour (bytea) -- that is what map-delivery /download-tour
        # streams. Only some Beta rows are in R2. The tour is PRESENT when the DB
        # holds its ZIP, or when its R2 object exists; 404 only when neither.
        if db_zip_bytes and int(db_zip_bytes) > 0:
            blob_key = f"db:audio_tours.audio_tour#{int(download_id)}"
        elif not blob.exists(blob_key):
            logger.warning(
                "LOCAL-781: blob object missing for tour id=%s (key=%s, "
                "zip_filename=%s). Not falling back to a name scan.",
                download_id, blob_key, zip_filename
            )
            return None

        stem = Path(zip_filename).stem
        uuid_part = _extract_uuid_from_zip_stem(stem)

        return {
            'edit_tour_id': uuid_part or stem,
            'directory_name': stem,
            'full_path': blob_key,          # R2 key, not a disk path
            'resolution_method': 'column_blob',
            'blob_backed': True,
            'stops_count': int(stops_count) if stops_count else 0,
            # In blob mode editability is decided from the DB: a modern tour with
            # separate audio files has stops_count > 0 (same signal the old
            # ZIP-size heuristic approximated, but authoritative and free).
            'editable': bool(stops_count and int(stops_count) > 0),
        }

    # ---- Disk mode (unchanged pre-LOCAL-781 behaviour) ----
    cur.execute(
        "SELECT tour_name, zip_filename FROM audio_tours WHERE id = %s",
        (int(download_id),)
    )
    result = cur.fetchone()
    cur.close()

    if not result:
        return None  # row does not exist

    tour_name, zip_filename = result

    if not zip_filename:
        return None  # column not populated (legacy row)

    zip_path = Path(TOURS_DIR) / zip_filename
    if not zip_path.exists():
        logger.warning(
            "zip_filename column points to non-existent file: %s (tour id=%s)",
            zip_filename, download_id
        )
        return None

    stem = zip_path.stem
    uuid_part = _extract_uuid_from_zip_stem(stem)

    return {
        'edit_tour_id': uuid_part or stem,
        'directory_name': stem,
        'full_path': str(zip_path),
        'resolution_method': 'column',
        'blob_backed': False,
    }


def _resolve_from_filesystem(download_id, tour_name, tours_dir):
    """Legacy fallback: scan the filesystem for a matching ZIP.

    Logs a loud WARNING that this path was taken.
    Returns an error dict if ambiguous, a result dict if unique, or None if no match.
    """
    logger.warning(
        "LEGACY FALLBACK: Scanning filesystem for tour id=%s name='%s'. "
        "This tour has no zip_filename stored — run the backfill.",
        download_id, tour_name
    )

    tour_name_lower = tour_name.lower()

    # Generic keyword extraction (no hardcoded venue names)
    words = tour_name_lower.replace(',', ' ').replace('-', ' ').replace('_', ' ').split()
    keywords = [w for w in words if len(w) > 3][:3]

    if not keywords:
        logger.error("No usable keywords extracted from tour name '%s'", tour_name)
        return None

    tours_path = Path(tours_dir)
    matches = []

    for item in tours_path.iterdir():
        if item.is_file() and item.name.endswith('.zip'):
            item_name_lower = item.name.lower()
            if all(keyword in item_name_lower for keyword in keywords[:2]):
                uuid_part = _extract_uuid_from_zip_stem(item.stem)
                if uuid_part:
                    matches.append({
                        'edit_tour_id': uuid_part,
                        'directory_name': item.stem,
                        'full_path': str(item),
                        'resolution_method': 'filesystem_fallback',
                    })

    if len(matches) == 0:
        return None
    elif len(matches) == 1:
        logger.warning(
            "Filesystem fallback resolved tour id=%s to %s (single match)",
            download_id, matches[0]['full_path']
        )
        return matches[0]
    else:
        # Ambiguous — refuse to guess
        filenames = [m['directory_name'] for m in matches]
        logger.error(
            "AMBIGUOUS RESOLUTION: tour id=%s name='%s' matched %d ZIPs: %s. "
            "Refusing to guess. Populate zip_filename column to resolve.",
            download_id, tour_name, len(matches), filenames
        )
        return {
            'error': 'ambiguous',
            'message': f"Tour id={download_id} matches {len(matches)} ZIPs: {filenames}. "
                       f"Cannot resolve without stored zip_filename.",
            'matches': filenames,
        }



def _organiser_audio_resolution(download_id, tour_name, conn=None):
    """[LOCAL-759 LEAD] Resolution for an organiser-audio tour, or None.

    Such a tour has no ZIP on disk: map-delivery serves audio_tours.audio_tour and
    the phone fetches each stop's audio from the organiser's host. The phone only
    needs a stable folder id; it never edits these tours (LOCAL-755: 409
    organiser_audio_not_editable)."""
    own = conn is None
    try:
        if own:
            conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT source_kind, stops_count FROM audio_tours WHERE id = %s",
                    (int(download_id),))
        row = cur.fetchone()
        cur.close()
    except Exception as e:
        logger.warning("organiser-audio check failed for %s: %s", download_id, e)
        return None
    finally:
        if own and conn:
            try:
                conn.close()
            except Exception:
                pass
    if not row or (row[0] or '') != 'organiser_audio':
        return None
    out = {
        "status": "success",
        "download_id": int(download_id),
        "edit_tour_id": f"organiser{int(download_id)}",
        "tour_name": tour_name,
        "editable": False,
        "has_separate_audio_files": False,
        "download_url": f"/tour/{download_id}/download",
        "directory_name": f"organiser{int(download_id)}",
        "resolution_method": "organiser_audio",
    }
    if row[1]:
        out["stops_count"] = int(row[1])
    return out

def find_edit_tour_id(download_id):
    """Find UUID-based edit tour ID from numeric download ID.

    Resolution order:
    1. Read zip_filename column from audio_tours (deterministic).
    2. Filesystem scan fallback for legacy rows (logs loudly, refuses ambiguity).
    """
    conn = None
    try:
        conn = get_db_connection()

        # Primary: stored column
        result = _resolve_from_column(download_id, conn)
        if result:
            return result

        # [LOCAL-781] In blob mode the ZIP is in R2 and /app/tours is empty, so
        # the filesystem fallback can only ever scan an empty directory. Skip it:
        # if the column path did not resolve (missing object or NULL column), the
        # answer is a clean "not found" (404), NOT a misleading legacy name-scan
        # warning. The deterministic LOCAL-50 rule still governs the id.
        if _get_blob_storage() is not None:
            logger.warning(
                "LOCAL-781: blob-mode resolution did not find tour id=%s via the "
                "zip_filename column; returning not-found (no filesystem scan).",
                download_id
            )
            return None

        # Need tour_name for fallback
        cur = conn.cursor()
        cur.execute("SELECT tour_name FROM audio_tours WHERE id = %s", (int(download_id),))
        row = cur.fetchone()
        cur.close()

        if not row:
            return None

        tour_name = row[0]

        # Fallback: filesystem scan (disk/Mac mode only)
        return _resolve_from_filesystem(download_id, tour_name, TOURS_DIR)

    except Exception as e:
        logger.error("Error finding edit tour ID for %s: %s", download_id, e)
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def check_tour_editability(tour_path):
    """Check if tour ZIP file exists (simplified check)"""
    try:
        tour_file = Path(tour_path)
        # For ZIP files, just check if file exists and is reasonable size
        if tour_file.exists() and tour_file.is_file() and tour_file.suffix == '.zip':
            file_size = tour_file.stat().st_size
            # Consider editable if ZIP file is larger than 1MB (has content)
            return file_size > 1024 * 1024
        return False

    except Exception:
        return False


def count_mp3_files_from_zip(zip_path):
    """Count MP3 files in ZIP - only for modern tours with separate audio files"""
    try:
        import zipfile

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            # Count MP3 files (excluding system files)
            mp3_files = [f for f in zip_ref.namelist()
                        if f.endswith('.mp3') and not f.startswith('__MACOSX/')]
            return len(mp3_files)

    except Exception as e:
        logger.error("Error counting MP3 files from ZIP %s: %s", zip_path, e)
        return 0  # Return 0 if can't count - field will be omitted


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "tour_id_resolution",
        "version": SERVICE_VERSION,
        "mode": os.getenv("STORIED_MODE", "false")
    })


@app.route('/tour/<download_id>/resolve', methods=['GET'])
def resolve_tour_id(download_id):
    """REQ-004: Resolve download ID to edit-compatible tour ID"""
    try:
        # Validate download ID
        if not download_id.isdigit():
            return jsonify({
                "status": "error",
                "error_code": "INVALID_DOWNLOAD_ID",
                "message": f"Download ID '{download_id}' must be numeric",
                "download_id": download_id
            }), 400

        # Get tour info from database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tour_name FROM audio_tours WHERE id = %s", (int(download_id),))
        result = cur.fetchone()
        cur.close()
        conn.close()

        if not result:
            _record_failure(error_code="TOUR_NOT_FOUND", http_status=404,
                            message=f"Tour with download ID not found",
                            tour_id=download_id)
            return jsonify({
                "status": "error",
                "error_code": "TOUR_NOT_FOUND",
                "message": f"Tour with download ID '{download_id}' not found",
                "download_id": int(download_id)
            }), 404

        tour_name = result[0]

        # [LOCAL-759 LEAD] An organiser-audio tour (LOCAL-754B) lives only in
        # audio_tours.audio_tour (no ZIP in the tour store, no zip_filename), so the
        # filesystem fallback below must never run for it: it guessed by name and
        # matched other tours' ZIPs ("Salem Witch Trial" -> two Salem Witch Museum
        # ZIPs, 409 AMBIGUOUS, tour 750, 2026-10-24). Answer deterministically.
        organiser = _organiser_audio_resolution(download_id, tour_name)
        if organiser is not None:
            return jsonify(organiser)

        # Find corresponding edit tour ID
        edit_info = find_edit_tour_id(download_id)

        if not edit_info:
            _record_failure(error_code="EDIT_ID_NOT_FOUND", http_status=404,
                            message="No edit-compatible tour found for download ID",
                            tour_id=download_id)
            return jsonify({
                "status": "error",
                "error_code": "EDIT_ID_NOT_FOUND",
                "message": f"No edit-compatible tour found for download ID '{download_id}'",
                "download_id": int(download_id),
                "tour_name": tour_name
            }), 404

        # Check for ambiguity error from fallback
        if 'error' in edit_info and edit_info['error'] == 'ambiguous':
            return jsonify({
                "status": "error",
                "error_code": "AMBIGUOUS_RESOLUTION",
                "message": edit_info['message'],
                "download_id": int(download_id),
                "tour_name": tour_name,
                "candidate_zips": edit_info.get('matches', []),
            }), 409  # Conflict

        # Check editability.
        # [LOCAL-781] In blob mode the ZIP is in R2, not on disk, so editability
        # and stop count are taken from the DB row (carried on edit_info) rather
        # than by reading the object — no download just to answer /resolve. In
        # disk mode the behaviour is unchanged (inspect the ZIP on disk).
        if edit_info.get('blob_backed'):
            is_editable = bool(edit_info.get('editable'))
            response_data = {
                "status": "success",
                "download_id": int(download_id),
                "edit_tour_id": edit_info['edit_tour_id'],
                "tour_name": tour_name,
                "editable": is_editable,
                "has_separate_audio_files": is_editable,
                "download_url": f"/tour/{download_id}/download",
                "directory_name": edit_info['directory_name'],
                "resolution_method": edit_info.get('resolution_method', 'unknown'),
            }
            stops_count = edit_info.get('stops_count') or 0
            if stops_count > 0:
                response_data["stops_count"] = stops_count
            return jsonify(response_data)

        is_editable = check_tour_editability(edit_info['full_path'])

        # Build response
        response_data = {
            "status": "success",
            "download_id": int(download_id),
            "edit_tour_id": edit_info['edit_tour_id'],
            "tour_name": tour_name,
            "editable": is_editable,
            "has_separate_audio_files": is_editable,
            "download_url": f"/tour/{download_id}/download",
            "directory_name": edit_info['directory_name'],
            "resolution_method": edit_info.get('resolution_method', 'unknown'),
        }

        # Only add stops_count for modern tours with MP3 files
        stops_count = count_mp3_files_from_zip(edit_info['full_path'])
        if stops_count > 0:
            response_data["stops_count"] = stops_count

        return jsonify(response_data)

    except ValueError:
        return jsonify({
            "status": "error",
            "error_code": "INVALID_DOWNLOAD_ID",
            "message": f"Download ID '{download_id}' must be numeric",
            "download_id": download_id
        }), 400

    except Exception as e:
        _record_failure(error_code="INTERNAL_ERROR", http_status=500,
                        message=f"Failed to resolve tour ID: {str(e)}",
                        exception_type=type(e).__name__, exc=e,
                        tour_id=download_id)
        return jsonify({
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"Failed to resolve tour ID: {str(e)}",
            "download_id": download_id
        }), 500


@app.route('/tour/<download_id>/info', methods=['GET'])
def get_tour_info(download_id):
    """Get detailed tour information for mobile app"""
    try:
        # Get basic resolution first
        resolution_response = resolve_tour_id(download_id)

        if resolution_response[1] != 200:  # If resolution failed
            return resolution_response

        resolution_data = resolution_response[0].get_json()

        # Add additional info
        edit_info = find_edit_tour_id(download_id)
        if edit_info and 'error' not in edit_info:
            tour_dir = Path(edit_info['full_path'])

            # Count stops
            audio_files = list(tour_dir.glob("audio_*.mp3"))
            stop_count = len(audio_files)

            # Get file sizes
            total_size = sum(f.stat().st_size for f in tour_dir.rglob('*') if f.is_file())

            resolution_data.update({
                "stop_count": stop_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "last_modified": max(f.stat().st_mtime for f in tour_dir.rglob('*') if f.is_file())
            })

        return jsonify(resolution_data)

    except Exception as e:
        return jsonify({
            "status": "error",
            "error_code": "INFO_ERROR",
            "message": f"Failed to get tour info: {str(e)}",
            "download_id": download_id
        }), 500


if __name__ == '__main__':
    print(f"Starting Tour ID Resolution Service v{SERVICE_VERSION}")
    print(f"Tours directory: {TOURS_DIR}")
    app.run(host='0.0.0.0', port=5025, debug=False)
