from flask import Flask, request, jsonify
import psycopg2
import json
from datetime import datetime
import os
import sys
import traceback

app = Flask(__name__)

# [LOCAL-595] Subscription-levels HTTP surface: /entitlements/* and
# /purchases/verify. Registered as a blueprint so the existing user-tracking
# routes are untouched.
try:
    from entitlements_api import entitlements_bp
    app.register_blueprint(entitlements_bp)
    print("[LOCAL-595] entitlements blueprint registered")
except Exception as _ent_err:  # pragma: no cover - import-time safety
    print(f"[LOCAL-595] WARNING: could not register entitlements blueprint: {_ent_err}")

# [LOCAL-690] Communities HTTP surface: /communities/* (create, page, join by
# code, episodes, feed import, map, mine, reminders). Pass purchases route
# through /purchases/verify (entitlements) which delegates to communities_api.
try:
    from communities_api import communities_bp
    app.register_blueprint(communities_bp)
    print("[LOCAL-690] communities blueprint registered")
except Exception as _com_err:  # pragma: no cover - import-time safety
    print(f"[LOCAL-690] WARNING: could not register communities blueprint: {_com_err}")

# [LOCAL-691] Legal-page acceptance capture: /document-acceptance (POST to
# record a version-stamped acceptance, GET to list a user's acceptances).
# Required + stored for selling a guide tour and creating a community.
try:
    from document_acceptance_api import document_acceptance_bp
    app.register_blueprint(document_acceptance_bp)
    print("[LOCAL-691] document_acceptance blueprint registered")
except Exception as _doc_err:  # pragma: no cover - import-time safety
    print(f"[LOCAL-691] WARNING: could not register document_acceptance blueprint: {_doc_err}")

def get_db():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "healthy"})

@app.route('/users', methods=['GET'])
def list_users():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT secret_id FROM users ORDER BY created_at DESC')
    users = cur.fetchall()
    user_list = [user[0] for user in users]
    cur.close()
    conn.close()
    return jsonify({"users": user_list})

@app.route('/user', methods=['POST'])
def add_user():
    data = request.json
    secret_id = data.get('secret_id')
    coordinates = data.get('coordinates', {})
    app_version = data.get('app_version', 'unknown')
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        INSERT INTO users (secret_id, app_version) 
        VALUES (%s, %s) 
        ON CONFLICT (secret_id) DO NOTHING
    ''', (secret_id, app_version))
    
    if coordinates:
        cur.execute('''
            INSERT INTO coordinates (secret_id, lat, lng) 
            VALUES (%s, %s, %s)
        ''', (secret_id, coordinates.get('lat'), coordinates.get('lng')))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/user/<secret_id>', methods=['PUT'])
def update_user(secret_id):
    data = request.json
    print(f"Updating user: {secret_id}, data: {data}")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Ensure user exists before adding related data
    cur.execute('''
        INSERT INTO users (secret_id, app_version) 
        VALUES (%s, %s) 
        ON CONFLICT (secret_id) DO NOTHING
    ''', (secret_id, data.get('app_version', 'unknown')))
    
    if 'coordinates' in data:
        cur.execute('''
            INSERT INTO coordinates (secret_id, lat, lng) 
            VALUES (%s, %s, %s)
        ''', (secret_id, data['coordinates'].get('lat'), data['coordinates'].get('lng')))
    
    if 'tour_request' in data:
        cur.execute('''
            INSERT INTO tour_requests (secret_id, tour_id, request_string, status, started_at) 
            VALUES (%s, %s, %s, %s, %s)
        ''', (secret_id, data['tour_request'].get('tour_id'), data['tour_request'].get('request_string'), 'started', datetime.now()))
    
    if 'tour_status_update' in data:
        tour_id = data['tour_status_update'].get('tour_id')
        status = data['tour_status_update'].get('status')
        finished_at = data['tour_status_update'].get('finished_at', datetime.now().isoformat())
        
        print(f"Updating tour status: tour_id={tour_id}, status={status}, finished_at={finished_at}")
        
        # First check if the tour exists and belongs to this user
        cur.execute('''
            SELECT id FROM tour_requests 
            WHERE secret_id = %s AND tour_id = %s
        ''', (secret_id, tour_id))
        
        tour = cur.fetchone()
        if tour:
            print(f"Tour found: {tour[0]}, proceeding with update")
            cur.execute('''
                UPDATE tour_requests 
                SET status = %s, finished_at = %s 
                WHERE secret_id = %s AND tour_id = %s
            ''', (status, finished_at, secret_id, tour_id))
            
            # Verify the update
            cur.execute('''
                SELECT id, status, finished_at FROM tour_requests 
                WHERE secret_id = %s AND tour_id = %s
            ''', (secret_id, tour_id))
            
            updated_tour = cur.fetchone()
            if updated_tour:
                print(f"Tour updated: id={updated_tour[0]}, status={updated_tour[1]}, finished_at={updated_tour[2]}")
            else:
                print(f"Tour update verification failed")
        else:
            print(f"Tour not found for user {secret_id}, tour_id={tour_id}")
    
    if 'map_request' in data:
        coords = data['map_request'].get('coordinates', {})
        cur.execute('''
            INSERT INTO map_requests (secret_id, lat, lng) 
            VALUES (%s, %s, %s)
        ''', (secret_id, coords.get('lat'), coords.get('lng')))
    
    if 'app_uninstalled' in data:
        cur.execute('''
            UPDATE users SET app_uninstalled = %s, updated_at = CURRENT_TIMESTAMP 
            WHERE secret_id = %s
        ''', (data['app_uninstalled'], secret_id))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/user/<secret_id>', methods=['DELETE'])
def delete_user(secret_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        UPDATE users 
        SET is_deleted = TRUE, updated_at = CURRENT_TIMESTAMP 
        WHERE secret_id = %s
    ''', (secret_id,))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'status': 'success'})

@app.route('/user/<secret_id>', methods=['GET'])
def get_user(secret_id):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT * FROM users WHERE secret_id = %s', (secret_id,))
    user = cur.fetchone()
    
    if not user:
        cur.close()
        conn.close()
        return jsonify({'error': 'User not found'}), 404
    
    cur.execute('SELECT id, lat, lng, created_at FROM coordinates WHERE secret_id = %s ORDER BY created_at', (secret_id,))
    coordinates = cur.fetchall()
    
    cur.execute('SELECT id, tour_id, request_string, status, created_at FROM tour_requests WHERE secret_id = %s ORDER BY created_at', (secret_id,))
    tours = cur.fetchall()
    
    cur.execute('SELECT id, lat, lng, created_at FROM map_requests WHERE secret_id = %s ORDER BY created_at', (secret_id,))
    maps = cur.fetchall()
    
    user_data = {
        'secret_id': user[0],
        'app_version': user[1],
        'is_deleted': user[2],
        'app_uninstalled': user[3],
        'created_at': user[4].isoformat() if user[4] else None,
        'updated_at': user[5].isoformat() if user[5] else None,
        'total_records': len(coordinates) + len(tours) + len(maps),
        'coordinates': [{
            'id': c[0],
            'lat': c[1],
            'lng': c[2],
            'timestamp': c[3].isoformat() if c[3] else None
        } for c in coordinates],
        'tours': [{
            'id': t[0],
            'tour_id': t[1],
            'request_string': t[2],
            'status': t[3],
            'timestamp': t[4].isoformat() if t[4] else None
        } for t in tours],
        'map_requests': [{
            'id': m[0],
            'lat': m[1],
            'lng': m[2],
            'timestamp': m[3].isoformat() if m[3] else None
        } for m in maps]
    }
    
    cur.close()
    conn.close()
    return jsonify(user_data)

# Add a special endpoint that uses the existing user endpoint
@app.route('/tour/<tour_id>/update', methods=['POST'])
def update_tour_via_user(tour_id):
    """Update tour status by finding the user and using the user endpoint."""
    try:
        data = request.json
        status = data.get('status', 'completed')
        
        print(f"Updating tour {tour_id} to status {status}")
        
        conn = get_db()
        cur = conn.cursor()
        
        # Find the user who owns this tour
        cur.execute("SELECT secret_id FROM tour_requests WHERE tour_id = %s", (tour_id,))
        result = cur.fetchone()
        
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': f'No tour found with ID {tour_id}'}), 404
        
        secret_id = result[0]
        print(f"Found tour owned by user {secret_id}")
        
        # Update the tour using the existing user endpoint logic
        finished_at = datetime.now().isoformat()
        
        cur.execute(
            "UPDATE tour_requests SET status = %s, finished_at = %s WHERE tour_id = %s",
            (status, finished_at, tour_id)
        )
        
        conn.commit()
        rows_affected = cur.rowcount
        
        # Verify the update
        cur.execute("SELECT id, status, finished_at FROM tour_requests WHERE tour_id = %s", (tour_id,))
        updated_tour = cur.fetchone()
        if updated_tour:
            print(f"Tour updated: id={updated_tour[0]}, status={updated_tour[1]}, finished_at={updated_tour[2]}")
        
        cur.close()
        conn.close()
        
        if rows_affected > 0:
            return jsonify({
                'status': 'success',
                'tour_id': tour_id,
                'user_id': secret_id,
                'rows_affected': rows_affected
            })
        else:
            return jsonify({'error': f'Failed to update tour with ID {tour_id}'}), 500
    
    except Exception as e:
        print(f"Error: {e}")
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# ---------------------------------------------------------------------------
# [LOCAL-785 / D723] POST /client-failure — the app's failure-reporting sink.
#
# The app's FailureReporter POSTs every failure it shows (error dialog/snackbar
# for a tour/download/save/translate/play/purchase), every uncaught Flutter /
# Dart error, and the known SILENT failures (post-download save/resolve, auto-
# play not starting), here. We store each one in failure_events via the SAME
# recorder the server uses, so an app failure sits beside the server failures in
# failure_report.py.
#
# Guards (abuse + size):
#   * body must be <= 8 KB (a client failure is small; anything larger is junk),
#   * per-user rate limit of 20/hour (in-memory sliding window keyed on the
#     reported user_id or the request IP) so a looping client cannot flood the
#     table; over the limit returns 429 and stores nothing,
#   * validation: JSON object required; surface/error_code/message are strings;
#     unknown fields are ignored; platform defaults to 'unknown'.
# The endpoint NEVER 500s on a malformed body — a bad report is a 400, and a
# storage hiccup is swallowed by the recorder (which falls back to stdout).
# ---------------------------------------------------------------------------
import time as _time
import threading as _threading
from collections import deque as _deque

try:
    import failure_log as _failure_log
except Exception:
    # The module ships beside app.py in the user-api image (COPY . .); in local
    # tests it lives at the repo root. Try the repo root as a fallback.
    try:
        _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)
        import failure_log as _failure_log
    except Exception as _fl_err:  # pragma: no cover - import-time safety
        _failure_log = None
        print(f"[LOCAL-785] WARNING: failure_log unavailable: {_fl_err}")

_CLIENT_FAILURE_MAX_BYTES = 8 * 1024
_CLIENT_FAILURE_RATE = 20              # max reports
_CLIENT_FAILURE_WINDOW_S = 3600        # per hour
_client_failure_hits = {}              # key -> deque[timestamps]
_client_failure_lock = _threading.Lock()


def _client_failure_rate_ok(key):
    """Sliding-window rate limit: True if this key may record another event now.
    In-memory and best-effort (per-process) — enough to stop a looping client;
    the real durable cap is the 8 KB body + the report's own de-duplication."""
    now = _time.time()
    with _client_failure_lock:
        dq = _client_failure_hits.get(key)
        if dq is None:
            dq = _deque()
            _client_failure_hits[key] = dq
        # Drop timestamps older than the window.
        cutoff = now - _CLIENT_FAILURE_WINDOW_S
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _CLIENT_FAILURE_RATE:
            return False
        dq.append(now)
        # Opportunistic cleanup so the dict cannot grow without bound.
        if len(_client_failure_hits) > 10000:
            for _k in [k for k, v in list(_client_failure_hits.items()) if not v]:
                _client_failure_hits.pop(_k, None)
        return True


def _as_str(value, cap):
    if value is None:
        return None
    try:
        s = str(value)
    except Exception:
        return None
    return s[:cap] if len(s) > cap else s


@app.route('/client-failure', methods=['POST'])
def client_failure():
    """Record one app-reported failure. See block comment above."""
    # 1. Size guard — reject an oversized body before parsing.
    raw = request.get_data(cache=False) or b''
    if len(raw) > _CLIENT_FAILURE_MAX_BYTES:
        return jsonify({'status': 'error', 'error': 'payload too large'}), 413

    # 2. Parse JSON defensively — a malformed body is a 400, never a 500.
    try:
        data = json.loads(raw.decode('utf-8')) if raw else None
    except Exception:
        data = None
    if not isinstance(data, dict):
        return jsonify({'status': 'error', 'error': 'invalid body'}), 400

    user_id = _as_str(data.get('user_id'), 255)
    rate_key = user_id or (request.headers.get('X-Forwarded-For', '')
                           or request.remote_addr or 'anon')

    # 3. Rate limit per user (or IP when anonymous).
    if not _client_failure_rate_ok(rate_key):
        return jsonify({'status': 'error', 'error': 'rate limited'}), 429

    # 4. Validate + normalise the fields we store. Unknown fields are ignored.
    platform = _as_str(data.get('platform'), 32) or 'unknown'
    surface = _as_str(data.get('surface'), 64)
    error_code = _as_str(data.get('error_code'), 128)
    message = _as_str(data.get('message'), 4000)
    exception_type = _as_str(data.get('exception_type'), 128)
    frames = _as_str(data.get('frames'), 4000)
    request_text = _as_str(data.get('request_text'), 4000)
    tour_id = _as_str(data.get('tour_id'), 64)
    app_version = _as_str(data.get('app_version'), 64)
    track = _as_str(data.get('track'), 32)
    http_status = data.get('http_status')
    try:
        http_status = int(http_status) if http_status is not None else None
    except (TypeError, ValueError):
        http_status = None

    # A report with nothing usable is a 400 (don't store empty noise).
    if not any([surface, error_code, message, exception_type]):
        return jsonify({'status': 'error', 'error': 'empty report'}), 400

    # 5. Store via the shared recorder (service='app', platform from the body).
    signature = None
    if _failure_log is not None:
        try:
            signature = _failure_log.record(
                service='app', surface=surface, error_code=error_code,
                message=message, exception_type=exception_type, frames=frames,
                http_status=http_status, user_id=user_id, app_version=app_version,
                platform=platform, track=track, request_text=request_text,
                tour_id=tour_id,
            )
        except Exception:
            signature = None

    return jsonify({'status': 'success', 'signature': signature}), 200


if __name__ == '__main__':
    print("Starting Flask app...")
    print("Routes defined:")
    for rule in app.url_map.iter_rules():
        print(f"{rule.endpoint}: {rule.rule}")
    app.run(host='0.0.0.0', port=5000, debug=True)