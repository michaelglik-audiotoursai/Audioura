#!/usr/bin/env python3
"""
Map Delivery Service - Serves map data and tours from PostgreSQL database
"""
import os
import sys
import json
import psycopg2
import math
import traceback
import base64
import zipfile
import tempfile
import re
import requests
# [LOCAL-573] text-sized /synthesize timeout (30 + 0.05*len, cap 180). Soft
# import so a missing module never breaks the caller.
try:
    from tts_timeout import synthesize_timeout
except Exception:  # noqa: BLE001
    def synthesize_timeout(text):
        n = len(text) if isinstance(text, str) else int(text or 0)
        return min(180.0, 30.0 + 0.05 * max(0, n))
from io import BytesIO
from datetime import datetime
import flask
from flask import Flask, request, jsonify, send_file as _send_file
from flask_cors import CORS
import inspect as _inspect

# [LOCAL-782] Redact secrets (X-Api-Key, Authorization, Cookie, tokens) before
# logging request headers. Shared module shipped in the image; inline fallback
# keeps the service safe even if the file is missing from a build.
try:
    from safe_headers import safe_headers
except Exception:  # pragma: no cover - image without the shared module
    def safe_headers(headers):
        _h = dict(headers) if headers is not None else {}
        _bad = ("token", "secret", "key", "x-goog-", "password", "auth", "cookie")
        return {k: ("…" + str(v)[-4:] if len(str(v)) > 4 else "…redacted")
                if any(m in k.lower() for m in _bad) else v for k, v in _h.items()}


def _compat_send_file(path_or_file, **kwargs):
    """Version-tolerant send_file wrapper.

    Flask <2.0 uses ``attachment_filename``; Flask >=2.0 renamed it to
    ``download_name``.  This helper accepts either and maps to whichever the
    installed Flask supports, so the same code runs on both.
    """
    sig = _inspect.signature(_send_file)
    params = sig.parameters

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

# R2 blob storage for tour delivery (Phase D)
_blob_storage = None
def _get_blob_storage():
    global _blob_storage
    if _blob_storage is None:
        blob_type = os.getenv('BLOB_STORAGE_TYPE', 'database')
        if blob_type == 'r2':
            from blobstorage import R2BlobStorage
            _blob_storage = R2BlobStorage()
        else:
            _blob_storage = None
    return _blob_storage

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\n==== MAP DELIVERY SERVICE STARTING: {datetime.now().isoformat()} ====")
sys.stdout.flush()

app = Flask(__name__)
CORS(app)

# Log all incoming requests
@app.before_request
def log_request():
    print(f"\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote Address: {request.remote_addr}")
    print(f"User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    print(f"Content Type: {request.headers.get('Content-Type', 'Unknown')}")
    print(f"Headers: {safe_headers(request.headers)}")
    sys.stdout.flush()

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
    )

_TRACK_COLUMN = None


def _has_track_column(cur):
    """True if audio_tours.track exists. Looked up once, then cached.

    Kept as a real catalog read rather than an assumption: this service is shared
    by Beta and Storied, so a wrong guess here is an outage for both.
    """
    global _TRACK_COLUMN
    if _TRACK_COLUMN is None:
        cur.execute("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'audio_tours' AND column_name = 'track'
        """)
        _TRACK_COLUMN = cur.fetchone() is not None
        print(f"audio_tours.track column present: {_TRACK_COLUMN}")
        sys.stdout.flush()
    return _TRACK_COLUMN


# [LOCAL-737 / D708] Valid deployment tracks. Beta, Storied and Subscribed are
# separate stacks sharing one GCloud Postgres. Subscribed is a first-class
# track; anything unknown normalises to 'beta'.
VALID_TRACKS = ('beta', 'storied', 'subscribed')


def normalize_track(value):
    """Resolve a raw track value to one of VALID_TRACKS, defaulting to 'beta'."""
    normalized = (value or 'beta').strip().lower()
    if normalized not in VALID_TRACKS:
        normalized = 'beta'
    return normalized


def _requested_track(req):
    """The explicit track filter from a request's ?track= query param, if any.

    Returns a normalised track ('beta'/'storied'/'subscribed') when the caller
    sent a non-empty ?track=, else None. None means "no track filter" so the
    historic behaviour (list every track's tours, each labelled with its own
    track) is preserved exactly for Beta and Storied, which never send it.
    A Subscribed app sends ?track=subscribed to list only its own tours (D708).
    """
    raw = (req.args.get('track') or '').strip()
    if not raw:
        return None
    return normalize_track(raw)


def calculate_distance(lat1, lng1, lat2, lng2):
    """Calculate distance between two points in kilometers"""
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lng = math.radians(lng2 - lng1)
    
    a = (math.sin(delta_lat / 2) * math.sin(delta_lat / 2) +
         math.cos(lat1_rad) * math.cos(lat2_rad) *
         math.sin(delta_lng / 2) * math.sin(delta_lng / 2))
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ─── [LOCAL-798] Token-based tour-name search ────────────────────────────────
#
# Michael, iPhone 84, 2026-10-28: a name search "Mui Ne seafood*" found nothing
# even though tour 466 "Seafood restaurants in Mui Ne, Vietnam - Tour" exists.
# The old WHERE matched the WHOLE query as one contiguous substring
# (`LOWER(tour_name) LIKE '%mui ne seafood%'`), so the words had to be adjacent
# and in that order. Fix: split into words and require EVERY word to appear in
# tour_name OR request_string (AND across words, any order), case- and diacritic-
# insensitive ("Mũi Né" == "Mui Ne"). unaccent() folds in SQL when present; else
# the ASCII words bound the candidate set and Python folds the rest.
import unicodedata as _unicodedata

_SEARCH_STOP_WORDS = frozenset({
    'a', 'an', 'the', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or',
    'near', 'by', 'with', 'from', 'tour', 'tours',
})


def _fold_text(s):
    """Lower-case and strip diacritics: "Mũi Né" → "mui ne"."""
    if not s:
        return ''
    decomposed = _unicodedata.normalize('NFKD', str(s))
    stripped = ''.join(ch for ch in decomposed
                       if not _unicodedata.combining(ch))
    return stripped.lower()


def _tokenize_search(pattern):
    """Split a search string into folded content words (drops a trailing '*',
    punctuation and stop-words). "Mui Ne seafood*" → ['mui','ne','seafood']."""
    folded = _fold_text((pattern or '').strip())
    raw = re.split(r'[^a-z0-9]+', folded)
    tokens, seen = [], set()
    for w in raw:
        if not w or w in _SEARCH_STOP_WORDS:
            continue
        if w not in seen:
            seen.add(w)
            tokens.append(w)
    return tokens


_HAS_UNACCENT = None


def _has_unaccent(cur):
    """True if Postgres unaccent() is callable here. Probed once + cached; a DB
    without the extension never 500s (we fold in Python instead)."""
    global _HAS_UNACCENT
    if _HAS_UNACCENT is None:
        try:
            cur.execute("SELECT unaccent('x')")
            cur.fetchone()
            _HAS_UNACCENT = True
        except Exception:
            try:
                cur.connection.rollback()
            except Exception:
                pass
            _HAS_UNACCENT = False
        print(f"unaccent() available: {_HAS_UNACCENT}")
        sys.stdout.flush()
    return _HAS_UNACCENT


def _is_ascii_token(tok):
    return all(ord(c) < 128 for c in tok)


def _token_where_sql(cur, tokens, name_col, req_col):
    """(sql_fragment, params) enforcing a token-AND search: every token in
    name_col OR req_col. unaccent() → fully accent-insensitive in SQL; else only
    ASCII tokens are constrained (superset) and diacritic tokens fall to Python.
    The fragment is a run of ' AND (...)' conditions, ready to splice after the
    existing WHERE."""
    frag, params = "", []
    use_unaccent = _has_unaccent(cur)
    for tok in tokens:
        like = f'%{tok}%'
        if use_unaccent:
            frag += (f" AND (unaccent(LOWER({name_col})) LIKE unaccent(%s) "
                     f"OR unaccent(LOWER({req_col})) LIKE unaccent(%s))")
            params += [like, like]
        elif _is_ascii_token(tok):
            frag += f" AND (LOWER({name_col}) LIKE %s OR LOWER({req_col}) LIKE %s)"
            params += [like, like]
    return frag, params


def _token_match_py(tokens, name, request_string):
    """Authoritative token-AND check in Python (used when unaccent() is absent):
    EVERY token must be a folded substring of name or request_string."""
    hay = _fold_text(name or '') + '\n' + _fold_text(request_string or '')
    return all(tok in hay for tok in tokens)


def _words_in_name(tokens, name):
    """How many search tokens appear in the folded tour_name (LOCAL-798 rank)."""
    folded = _fold_text(name or '')
    return sum(1 for tok in tokens if tok in folded)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    print("Health check requested")
    sys.stdout.flush()
    return jsonify({"status": "healthy", "service": "map_delivery", "req012": "active"})

@app.route('/version-test', methods=['GET'])
def version_test():
    """Simple version test endpoint"""
    import time
    return jsonify({
        "test": "REQ-012 working",
        "timestamp": int(time.time()),
        "version": "1.2.5.REQ012"
    })

@app.route('/tours-near/<lat>/<lng>', methods=['GET'])
def get_tours_near_location(lat, lng):
    """Get tours near a specific location (including custom tours)"""
    print(f"Getting tours near lat={lat}, lng={lng}")
    sys.stdout.flush()
    
    try:
        # Convert lat/lng to float
        lat = float(lat)
        lng = float(lng)
        radius_km = float(request.args.get('radius', 50))
        print(f"Search radius: {radius_km} km")
        sys.stdout.flush()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get original tours (exclude test tours and translations)
        # COALESCE so rows written before audio_tours.track existed read 'beta'
        # rather than NULL. The app must never have to guess which engine made a
        # tour -- guessing only works within one session and breaks for anything
        # generated before the Stable/Preview selector shipped (ClickUp wdvrdaxywb).
        # [LOCAL-737 / D708] Optional ?track= filter. When a Subscribed app asks
        # for track=subscribed it must see ONLY subscribed tours, exactly as Beta
        # and Storied are isolated. Beta/Storied apps send no ?track= and so keep
        # the historic behaviour (every track's tours, each labelled). The filter
        # is only meaningful when the column exists; a track-less DB has nothing
        # but Beta, so an explicit non-beta filter correctly matches nothing.
        _track_filter = _requested_track(request)
        _track_sql_expr = "COALESCE(track, 'beta')" if _has_track_column(cur) else "'beta'"
        _where_track = ""
        _track_params = []
        if _track_filter is not None:
            _where_track = " AND %s = %%s" % _track_sql_expr
            _track_params.append(_track_filter)
        cur.execute(("""
            -- The track column is selected only when it EXISTS. audio_tours.track
            -- is created by the Storied orchestrator's self-healing ALTER, so on a
            -- database that has never run it the column is absent -- and an
            -- unguarded reference would turn the whole tour list into a 500 for
            -- every user on both tracks. Degrading to 'beta' is correct anyway:
            -- no track column means nothing but Beta has ever written here.
            --
            -- The is_test / original_tour_id filters are STORIED-ONLY and are kept
            -- deliberately: main has never had them, and dropping them here would
            -- make Storied start listing translations and test tours.
            SELECT id, tour_name, request_string, lat, lng, number_requested,
                   %s AS track
            FROM audio_tours 
            WHERE lat IS NOT NULL AND lng IS NOT NULL
              AND (is_test IS NOT TRUE)
              AND original_tour_id IS NULL%s
        """ % (_track_sql_expr, _where_track)), _track_params)
        
        tours = cur.fetchall()
        nearby_tours = []
        
        for tour in tours:
            tour_id, tour_name, request_string, tour_lat, tour_lng, requests, track = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    nearby_tours.append({
                        'id': tour_id,
                        'name': tour_name,
                        'request_string': request_string,
                        'lat': tour_lat,
                        'lng': tour_lng,
                        'distance_km': round(distance, 2),
                        'popularity': requests,
                        'type': 'walking_tour',
                        'is_custom': False,
                        # 'beta' | 'storied' | 'subscribed'. Additive: older app
                        # builds ignore it. (LOCAL-737)
                        'track': track or 'beta'
                    })
        
        # Get custom tours
        cur.execute("""
            SELECT custom_tour_id, tour_name, request_string, lat, lng, number_requested, original_tour_id
            FROM custom_tours 
            WHERE lat IS NOT NULL AND lng IS NOT NULL
        """)
        
        custom_tours = cur.fetchall()
        
        for tour in custom_tours:
            custom_id, tour_name, request_string, tour_lat, tour_lng, requests, original_id = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    nearby_tours.append({
                        'id': custom_id,  # Use custom_tour_id as id
                        'name': tour_name,
                        'request_string': request_string,
                        'lat': tour_lat,
                        'lng': tour_lng,
                        'distance_km': round(distance, 2),
                        'popularity': requests,
                        'type': 'walking_tour',
                        'is_custom': True,
                        'original_tour_id': original_id
                    })
        
        nearby_tours.sort(key=lambda x: x['distance_km'])
        cur.close()
        conn.close()
        
        print(f"Found {len(nearby_tours)} tours within {radius_km} km")
        sys.stdout.flush()
        
        return jsonify({
            'tours': nearby_tours,
            'center_lat': lat,
            'center_lng': lng,
            'radius_km': radius_km,
            'count': len(nearby_tours)
        })
        
    except Exception as e:
        print(f"ERROR in get_tours_near_location: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500



@app.route('/tour/<download_id>/resolve', methods=['GET'])
def resolve_tour_id(download_id):
    """Resolve download ID to tour info (cloud-compatible version)"""
    try:
        if not download_id.isdigit():
            return jsonify({"status": "error", "error_code": "INVALID_DOWNLOAD_ID", "message": f"Download ID must be numeric"}), 400
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, tour_name, tour_blob_uri FROM audio_tours WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)", (int(download_id),))
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if not result:
            return jsonify({"status": "error", "error_code": "TOUR_NOT_FOUND", "message": f"Tour {download_id} not found"}), 404
        
        tour_id, tour_name, blob_uri = result
        return jsonify({
            "status": "success",
            "download_id": int(download_id),
            "tour_id": str(tour_id),
            "tour_name": tour_name,
            "editable": False,
            "has_audio": True
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download-tour/<tour_id>', methods=['GET'])
def download_tour(tour_id):
    """Download a tour zip file by ID with version checking"""
    version_param = request.args.get('v', '')
    force_download = request.args.get('force', 'false').lower() == 'true'
    print(f"Downloading tour ID: {tour_id} (version: {version_param}, force: {force_download})")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if it's a custom tour
        if str(tour_id).startswith('custom_'):
            cur.execute("""
                SELECT tour_name, audio_tour, request_string
                FROM custom_tours 
                WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
            """, (tour_id,))
            
            result = cur.fetchone()
            
            if result:
                tour_name, audio_tour_data, request_string = result
                cur.execute("""
                    UPDATE custom_tours 
                    SET number_requested = number_requested + 1 
                    WHERE custom_tour_id = %s
                """, (tour_id,))
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Custom tour not found'}), 404
        else:
            # Regular tour — dual-read: R2 if tour_blob_uri set, else BYTEA
            cur.execute("""
                SELECT tour_name, audio_tour, request_string, tour_blob_uri
                FROM audio_tours 
                WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)
            """, (int(tour_id),))
            
            result = cur.fetchone()
            
            if result:
                tour_name, audio_tour_data, request_string, tour_blob_uri = result
                
                # If R2 key is available and R2 is configured, read from R2
                if tour_blob_uri and _get_blob_storage():
                    try:
                        audio_tour_data = _get_blob_storage().download(tour_blob_uri)
                        print(f"Serving tour {tour_id} from R2: {tour_blob_uri}")
                    except Exception as r2_err:
                        print(f"R2 read failed for {tour_id}, falling back to BYTEA: {r2_err}")
                        if not audio_tour_data:
                            cur.close()
                            conn.close()
                            return jsonify({'error': 'Tour data unavailable'}), 500
                
                if not audio_tour_data:
                    cur.close()
                    conn.close()
                    return jsonify({'error': 'Tour data not found'}), 404
                
                cur.execute("""
                    UPDATE audio_tours 
                    SET number_requested = number_requested + 1 
                    WHERE id = %s
                """, (int(tour_id),))
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Tour not found'}), 404
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Version checking logic
        if version_param and not force_download:
            import time
            current_version = f"1.2.5.{int(time.time())}"
            if version_param == current_version:
                return '', 304  # Not Modified
        
        safe_name = request_string.replace(' ', '_').lower()
        filename = f"{safe_name}_tour.zip"
        
        print(f"Sending tour file: {filename}")
        sys.stdout.flush()
        
        response = send_file(
            BytesIO(audio_tour_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=filename
        )
        
        # Add version headers
        import time
        response.headers['X-Tour-Version'] = f"1.2.5.{int(time.time())}"
        response.headers['X-Last-Modified'] = datetime.now().isoformat()
        
        return response
        
    except Exception as e:
        print(f"ERROR in download_tour: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/search-tours', methods=['GET'])
def search_tours():
    """Search tours by query (enhanced to include custom tours)"""
    query = request.args.get('query', '').strip()
    print(f"Searching tours with query: '{query}'")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        all_tours = []
        
        if query:
            # [LOCAL-798] Token search for a MULTI-WORD query: each word must
            # appear in tour_name OR request_string (AND across words, any order),
            # case- and diacritic-insensitive. A single word keeps the historic
            # whole-string LIKE (so one-word searches are byte-for-byte unchanged).
            _tokens = _tokenize_search(query)
            _token_search = len(_tokens) >= 2
            _needs_py_filter = _token_search and not _has_unaccent(cur)

            # Search original tours
            # [LOCAL-737 / D708] Optional ?track= filter, same contract as
            # tours-near: a Subscribed app (track=subscribed) sees only its own
            # tours; Beta/Storied send no ?track= and behaviour is unchanged.
            # Guarded by column presence so a track-less DB never 500s.
            _track_filter = _requested_track(request)
            _where_track = ""
            _track_params = []
            if _track_filter is not None and _has_track_column(cur):
                _where_track = " AND COALESCE(track, 'beta') = %s"
                _track_params = [_track_filter]

            if _token_search:
                _name_frag, _name_params = _token_where_sql(
                    cur, _tokens, 'tour_name', 'request_string')
                _where_match = "(TRUE" + _name_frag + ")"
                _match_params = _name_params
            else:
                _where_match = ("(LOWER(tour_name) LIKE LOWER(%s) "
                                "OR LOWER(request_string) LIKE LOWER(%s))")
                _match_params = [f'%{query}%', f'%{query}%']

            cur.execute(("""
                SELECT id, tour_name, request_string, lat, lng, number_requested, created_at
                FROM audio_tours 
                WHERE """ + _where_match + """
                AND lat IS NOT NULL AND lng IS NOT NULL
                AND (is_test IS NOT TRUE)""" + _where_track + """
            """), _match_params + _track_params)
            
            tours = cur.fetchall()
            
            for tour in tours:
                tour_id, tour_name, request_string, tour_lat, tour_lng, requests, created_at = tour
                # [LOCAL-798] On a DB without unaccent() the SQL only bounded the
                # candidates by ASCII tokens; confirm the full folded token-AND.
                if _needs_py_filter and not _token_match_py(_tokens, tour_name, request_string):
                    continue
                _row = {
                    'id': tour_id,
                    'name': tour_name,
                    'request_string': request_string,
                    'lat': tour_lat,
                    'lng': tour_lng,
                    'distance_km': 0,  # Will be calculated if needed
                    'popularity': requests,
                    'type': 'walking_tour',
                    'is_custom': False
                }
                if _token_search:
                    _win = _words_in_name(_tokens, tour_name)
                    _row['_rank_all_in_name'] = 1 if _win == len(_tokens) else 0
                    _row['_rank_words_in_name'] = _win
                    _row['_rank_created_at'] = created_at
                all_tours.append(_row)
            
            # Search custom tours
            if _token_search:
                _cfrag, _cparams = _token_where_sql(
                    cur, _tokens, 'tour_name', 'request_string')
                _cwhere = "(TRUE" + _cfrag + ")"
            else:
                _cwhere = ("(LOWER(tour_name) LIKE LOWER(%s) "
                           "OR LOWER(request_string) LIKE LOWER(%s))")
                _cparams = [f'%{query}%', f'%{query}%']
            cur.execute(("""
                SELECT custom_tour_id, tour_name, request_string, lat, lng, number_requested, original_tour_id
                FROM custom_tours 
                WHERE """ + _cwhere + """
                AND lat IS NOT NULL AND lng IS NOT NULL
            """), _cparams)
            
            custom_tours = cur.fetchall()
            
            for tour in custom_tours:
                custom_id, tour_name, request_string, tour_lat, tour_lng, requests, original_id = tour
                if _needs_py_filter and not _token_match_py(_tokens, tour_name, request_string):
                    continue
                _row = {
                    'id': custom_id,
                    'name': tour_name,
                    'request_string': request_string,
                    'lat': tour_lat,
                    'lng': tour_lng,
                    'distance_km': 0,  # Will be calculated if needed
                    'popularity': requests,
                    'type': 'walking_tour',
                    'is_custom': True,
                    'original_tour_id': original_id
                }
                if _token_search:
                    _win = _words_in_name(_tokens, tour_name)
                    _row['_rank_all_in_name'] = 1 if _win == len(_tokens) else 0
                    _row['_rank_words_in_name'] = _win
                    _row['_rank_created_at'] = None  # custom_tours newest proxied by popularity/id
                all_tours.append(_row)

            # [LOCAL-798] Rank a multi-word name search: tours with ALL words in
            # the name first, then MORE words in the name, then newest, then
            # popularity. A single-word search keeps the historic popularity sort.
            if _token_search:
                def _created_key(x):
                    c = x.get('_rank_created_at')
                    try:
                        return c.timestamp() if hasattr(c, 'timestamp') else float(c or 0)
                    except Exception:
                        return 0.0
                all_tours.sort(key=lambda x: (
                    -x.get('_rank_all_in_name', 0),
                    -x.get('_rank_words_in_name', 0),
                    -_created_key(x),
                    -x['popularity']))
                for _r in all_tours:
                    _r.pop('_rank_all_in_name', None)
                    _r.pop('_rank_words_in_name', None)
                    _r.pop('_rank_created_at', None)
            else:
                # Sort by popularity (historic behaviour)
                all_tours.sort(key=lambda x: x['popularity'], reverse=True)
        
        cur.close()
        conn.close()
        
        print(f"Found {len(all_tours)} tours matching query")
        sys.stdout.flush()
        
        return jsonify({
            'tours': all_tours,
            'count': len(all_tours),
            'pattern': query
        })
        
    except Exception as e:
        print(f"ERROR in search_tours: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

# [LOCAL-793] Server-side geocoder fallback for the Home place search.
#
# The app's client geocoder asks Nominatim for several results and prefers a
# PLACE over a POI (so "Saigon Vietnam" no longer opens a Paris restaurant).
# When Nominatim returns NO place -- a typo like "Hi Chi Minh, Vietnam", or
# only far POIs -- the app calls THIS endpoint, which resolves the free text
# server-side where the paid key lives (never shipped in the app):
#
#   1. Serper Places (metered via serper_meter.serper_post, ~$0.001/query) when
#      a key is configured. Serper's index is typo-tolerant, so "Hi Chi Minh"
#      resolves to Ho Chi Minh City. We take the first result's coordinates.
#   2. Nominatim fallback (free) with a real User-Agent and a larger result set,
#      preferring a place class, when Serper is not configured or finds nothing.
#
# Response: {"lat": .., "lng": .., "name": ".."} on success, or 404 when the
# place cannot be resolved. Only ONE paid query per lookup (cap-friendly).
@app.route('/geocode', methods=['GET'])
def geocode_place():
    query = (request.args.get('q') or request.args.get('query') or '').strip()
    print(f"Geocoding place: '{query}'")
    sys.stdout.flush()
    if not query:
        return jsonify({'error': 'missing q'}), 400

    # 1. Serper Places (metered, typo-tolerant). Guarded + fail-open.
    try:
        result = _geocode_via_serper(query)
        if result is not None:
            return jsonify(result)
    except Exception as e:
        print(f"GEOCODE: serper path error: {e}")
        sys.stdout.flush()

    # 2. Nominatim fallback (free).
    try:
        result = _geocode_via_nominatim(query)
        if result is not None:
            return jsonify(result)
    except Exception as e:
        print(f"GEOCODE: nominatim path error: {e}")
        sys.stdout.flush()

    return jsonify({'error': 'not found', 'q': query}), 404


def _geocode_via_serper(query):
    """Resolve `query` to {lat,lng,name} via the metered Serper Places door, or
    None when no key is configured / nothing is found. One metered query."""
    try:
        from serper_meter import serper_post
    except Exception:
        return None
    key = os.environ.get('SERP_API_KEY') or os.environ.get('SERPER_API_KEY')
    if not key:
        return None
    status, body = serper_post(
        'https://google.serper.dev/places',
        {'q': query, 'num': 5},
        api_key=key,
    )
    if status != 200 or not body:
        return None
    try:
        data = json.loads(body.decode('utf-8', 'ignore'))
    except Exception:
        return None
    places = data.get('places') or []
    for p in places:
        lat = p.get('latitude')
        lng = p.get('longitude')
        if lat is None or lng is None:
            continue
        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            continue
        name = p.get('address') or p.get('title') or query
        print(f"GEOCODE: serper '{query}' -> {name} ({lat},{lng})")
        sys.stdout.flush()
        return {'lat': lat, 'lng': lng, 'name': name}
    return None


def _geocode_via_nominatim(query):
    """Resolve `query` to {lat,lng,name} via Nominatim, preferring a PLACE class
    over a POI. Server-side so a real User-Agent is used. None when nothing
    usable comes back."""
    url = (
        'https://nominatim.openstreetmap.org/search'
        '?q=' + requests.utils.quote(query) +
        '&format=json&limit=8&accept-language=en'
    )
    resp = requests.get(
        url,
        headers={
            'User-Agent': 'com.audioura.audiotours/1.0 (support@audioura.com)',
            'Accept-Language': 'en',
        },
        timeout=12,
    )
    if resp.status_code != 200:
        return None
    rows = resp.json()
    if not isinstance(rows, list) or not rows:
        return None
    _place_types = {
        'country', 'state', 'region', 'province', 'county', 'city', 'town',
        'municipality', 'village', 'hamlet', 'suburb', 'neighbourhood',
        'quarter', 'borough', 'district', 'locality',
    }

    def _is_place(r):
        klass = str(r.get('class') or r.get('category') or '').lower()
        typ = str(r.get('type') or '').lower()
        if klass == 'place' and typ in _place_types:
            return True
        if klass == 'boundary' and typ == 'administrative':
            return True
        return typ == 'administrative'

    def _importance(r):
        try:
            return float(r.get('importance') or 0.0)
        except (TypeError, ValueError):
            return 0.0

    places = [r for r in rows if _is_place(r)]
    pool = places if places else rows
    # [LOCAL-824 LEAD] Keep Nominatim's own relevance order among PLACE rows: sorting places by
    # 'importance' sent "Mui Ne" (ward Mũi Né, rank 1) to Meizhou, China (bigger, rank 2).
    # Importance only breaks ties when no place row came back.
    if not places:
        pool = sorted(pool, key=_importance, reverse=True)
    best = pool[0]
    try:
        lat = float(best['lat'])
        lng = float(best['lon'])
    except (KeyError, TypeError, ValueError):
        return None
    name = best.get('display_name') or query
    print(f"GEOCODE: nominatim '{query}' -> {name} ({lat},{lng})")
    sys.stdout.flush()
    return {'lat': lat, 'lng': lng, 'name': name}


@app.route('/tour/<int:tour_id>/version', methods=['GET'])
def get_tour_version(tour_id):
    """Get tour version information for update checking"""
    print(f"Getting version for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tour_name FROM audio_tours 
            WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)
        """, (int(tour_id),))
        
        result = cur.fetchone()
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': 'Tour not found'}), 404
        
        cur.close()
        conn.close()
        
        import time
        current_timestamp = int(time.time())
        version = f"1.2.5.{current_timestamp}"
        
        return jsonify({
            'tour_id': tour_id,
            'version': version,
            'last_modified': datetime.now().isoformat(),
            'has_updates': True
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_version: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tours/check-versions', methods=['POST'])
def check_multiple_versions():
    """Bulk version check for multiple tours"""
    data = request.json
    if not data or not isinstance(data, list):
        return jsonify({'error': 'Expected array of tour version checks'}), 400
    
    results = []
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        for item in data:
            tour_id = item.get('tour_id')
            local_version = item.get('local_version', '1.0.0')
            
            if not tour_id:
                continue
                
            cur.execute("""
                SELECT id FROM audio_tours 
                WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)
            """, (int(tour_id),))
            
            if cur.fetchone():
                import time
                server_version = f"1.2.5.{int(time.time())}"
                needs_update = server_version != local_version
                
                results.append({
                    'tour_id': tour_id,
                    'server_version': server_version,
                    'local_version': local_version,
                    'needs_update': needs_update
                })
        
        cur.close()
        conn.close()
        
        return jsonify(results)
        
    except Exception as e:
        print(f"ERROR in check_multiple_versions: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour-info/<int:tour_id>', methods=['GET'])
def get_tour_info(tour_id):
    """Get detailed information about a tour with version info"""
    print(f"Getting info for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT id, tour_name, request_string, lat, lng, number_requested
            FROM audio_tours 
            WHERE id = %s
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
            print(f"Tour {tour_id} not found")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        tour_id, tour_name, request_string, lat, lng, requests = result
        cur.close()
        conn.close()
        
        # Generate version based on current timestamp (simplified)
        import time
        current_timestamp = int(time.time())
        version = f"1.2.5.{current_timestamp}"
        
        return jsonify({
            'id': tour_id,
            'name': tour_name,
            'request_string': request_string,
            'lat': lat,
            'lng': lng,
            'downloads': requests,
            'has_audio': True,
            'version': version,
            'last_modified': datetime.now().isoformat(),
            'has_custom_edits': True,
            'download_url': f'/download-tour/{tour_id}?v={current_timestamp}',
            'api_version': '1.2.5.REQ012'
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_info: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

def ensure_custom_tours_table():
    """Ensure custom_tours table exists"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS custom_tours (
                id SERIAL PRIMARY KEY,
                custom_tour_id VARCHAR(255) UNIQUE NOT NULL,
                original_tour_id INTEGER REFERENCES audio_tours(id),
                user_id VARCHAR(255),
                tour_name VARCHAR(255) NOT NULL,
                request_string TEXT NOT NULL,
                audio_tour BYTEA,
                lat DOUBLE PRECISION,
                lng DOUBLE PRECISION,
                number_requested INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        cur.close()
        conn.close()
        print("Custom tours table ensured")
    except Exception as e:
        print(f"Error ensuring custom_tours table: {e}")

def extract_tour_stops(tour_id):
    """Extract stops from a tour's HTML content"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if it's a custom tour
    if str(tour_id).startswith('custom_'):
        cur.execute("""
            SELECT audio_tour, tour_name FROM custom_tours 
            WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
        """, (tour_id,))
    else:
        cur.execute("""
            SELECT audio_tour, tour_name, tour_blob_uri FROM audio_tours 
            WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)
        """, (tour_id,))
    
    result = cur.fetchone()
    if not result:
        cur.close()
        conn.close()
        return []
    
    audio_tour_data, tour_name, tour_blob_uri = result
    
    # R2 read if available
    if not audio_tour_data and tour_blob_uri and _get_blob_storage():
        try:
            audio_tour_data = _get_blob_storage().download(tour_blob_uri)
        except Exception as r2_err:
            print(f"R2 read failed for tour stops extraction: {r2_err}")
    
    if not audio_tour_data:
        cur.close()
        conn.close()
        return []
    
    cur.close()
    conn.close()
    
    stops = []
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "tour.zip")
            with open(zip_path, 'wb') as f:
                f.write(audio_tour_data)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # List all files in the zip
                file_list = zip_ref.namelist()
                
                # Find HTML file
                html_file = None
                for file in file_list:
                    if file.endswith('.html'):
                        html_file = file
                        break
                
                if not html_file:
                    return []
                
                html_content = zip_ref.read(html_file).decode('utf-8')
                
                # Extract tour stops from HTML
                # Look for audio files and their corresponding text
                audio_files = [f for f in file_list if f.endswith('.mp3')]
                
                for i, audio_file in enumerate(audio_files):
                    # Extract title from filename or HTML
                    title = os.path.splitext(os.path.basename(audio_file))[0]
                    title = title.replace('_', ' ').title()
                    
                    # Try to extract text content from HTML
                    text_pattern = rf'<p[^>]*>([^<]*{re.escape(title)}[^<]*)</p>'
                    text_match = re.search(text_pattern, html_content, re.IGNORECASE)
                    current_text = text_match.group(1) if text_match else f"Welcome to {title}"
                    
                    stops.append({
                        'stop_number': i + 1,
                        'title': title,
                        'current_text': current_text,
                        'audio_file': audio_file,
                        'audio_duration': 45,  # Default duration
                        'editable': True
                    })
    except Exception as e:
        print(f"Error extracting tour stops: {e}")
        # Return basic structure if extraction fails
        stops = [{
            'stop_number': 1,
            'title': 'Tour Stop 1',
            'current_text': 'Welcome to this tour location',
            'audio_file': 'audio_1.mp3',
            'audio_duration': 45,
            'editable': True
        }]
    
    return stops

@app.route('/tour/<tour_id>/edit-info', methods=['GET'])
def get_tour_edit_info(tour_id):
    """Get tour information for editing"""
    print(f"Getting edit info for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check if it's a custom tour or regular tour
        if str(tour_id).startswith('custom_'):
            cur.execute("""
                SELECT custom_tour_id, tour_name FROM custom_tours 
                WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
            """, (tour_id,))
        else:
            cur.execute("""
                SELECT id, tour_name FROM audio_tours 
                WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)
            """, (int(tour_id),))
        
        result = cur.fetchone()
        if not result:
            cur.close()
            conn.close()
            return jsonify({'error': 'Tour not found'}), 404
        
        tour_id_db, tour_name = result
        cur.close()
        conn.close()
        
        # Extract stops from tour
        stops = extract_tour_stops(tour_id)
        
        return jsonify({
            'tour_id': str(tour_id),
            'tour_name': tour_name,
            'stops': stops
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_edit_info: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour/<tour_id>/update-stop', methods=['POST'])
def update_tour_stop(tour_id):
    """Update a specific stop in a tour"""
    print(f"Updating stop for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        stop_number = data.get('stop_number')
        new_text = data.get('new_text')
        audio_file = data.get('audio_file')  # Base64 encoded
        audio_format = data.get('audio_format', 'mp3')
        
        if not stop_number:
            return jsonify({'error': 'stop_number is required'}), 400
        
        # Store the modification for later processing
        # In a full implementation, this would modify the tour ZIP file
        print(f"Stop {stop_number} update requested:")
        print(f"  New text: {new_text[:100] if new_text else 'None'}...")
        print(f"  Has custom audio: {bool(audio_file)}")
        
        # If new text provided, generate new audio using Polly TTS
        if new_text:
            try:
                # Call Polly TTS service
                tts_response = requests.post(
                    "http://polly-tts:5018/synthesize",
                    json={
                        "text": new_text,
                        "voice_id": "Joanna",
                        "output_format": "mp3"
                    },
                    timeout=synthesize_timeout(new_text)  # [LOCAL-573] text-sized
                )
                
                if tts_response.status_code == 200:
                    print(f"Generated new audio for stop {stop_number}")
                else:
                    print(f"TTS generation failed: {tts_response.text}")
            except Exception as tts_error:
                print(f"TTS service error: {tts_error}")
        
        return jsonify({
            'status': 'success',
            'message': f'Stop {stop_number} updated',
            'tour_id': tour_id,
            'stop_number': stop_number
        })
        
    except Exception as e:
        print(f"ERROR in update_tour_stop: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour/<tour_id>/create-custom', methods=['POST'])
def create_custom_tour(tour_id):
    """Create a custom version of a tour"""
    print(f"Creating custom tour from ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        data = request.json or {}
        custom_name = data.get('custom_name', f'Custom Tour {tour_id}')
        modifications = data.get('modifications', [])
        user_id = data.get('user_id', 'anonymous')
        
        # Ensure custom tours table exists
        ensure_custom_tours_table()
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get original tour
        if str(tour_id).startswith('custom_'):
            cur.execute("""
                SELECT tour_name, request_string, audio_tour, lat, lng, original_tour_id
                FROM custom_tours 
                WHERE custom_tour_id = %s AND audio_tour IS NOT NULL
            """, (tour_id,))
            result = cur.fetchone()
            if result:
                tour_name, request_string, audio_tour, lat, lng, original_id = result
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Original tour not found'}), 404
        else:
            cur.execute("""
                SELECT tour_name, request_string, audio_tour, lat, lng, tour_blob_uri
                FROM audio_tours 
                WHERE id = %s AND (audio_tour IS NOT NULL OR tour_blob_uri IS NOT NULL)
            """, (int(tour_id),))
            result = cur.fetchone()
            if result:
                tour_name, request_string, audio_tour, lat, lng, tour_blob_uri = result
                original_id = int(tour_id)
                # R2 read if BYTEA is null
                if not audio_tour and tour_blob_uri and _get_blob_storage():
                    try:
                        audio_tour = _get_blob_storage().download(tour_blob_uri)
                    except Exception as r2_err:
                        print(f"R2 read failed for create-custom: {r2_err}")
            else:
                cur.close()
                conn.close()
                return jsonify({'error': 'Original tour not found'}), 404
        
        # Generate unique custom tour ID
        import time
        timestamp = int(time.time())
        custom_tour_id = f"custom_{original_id}_{timestamp}"
        
        # Process modifications
        modified_audio_tour = audio_tour  # Start with original
        
        # Apply text modifications using TTS
        for mod in modifications:
            stop_number = mod.get('stop_number')
            new_text = mod.get('new_text')
            has_custom_audio = mod.get('has_custom_audio', False)
            
            if new_text and not has_custom_audio:
                try:
                    # Generate new audio using Polly TTS
                    tts_response = requests.post(
                        "http://polly-tts:5018/synthesize",
                        json={
                            "text": new_text,
                            "voice_id": "Joanna",
                            "output_format": "mp3"
                        },
                        timeout=synthesize_timeout(new_text)  # [LOCAL-573] text-sized
                    )
                    
                    if tts_response.status_code == 200:
                        print(f"Generated new audio for stop {stop_number}")
                        # In full implementation, would modify the ZIP file
                    else:
                        print(f"TTS generation failed for stop {stop_number}: {tts_response.text}")
                except Exception as tts_error:
                    print(f"TTS service error for stop {stop_number}: {tts_error}")
        
        # Insert custom tour
        cur.execute("""
            INSERT INTO custom_tours 
            (custom_tour_id, original_tour_id, user_id, tour_name, request_string, audio_tour, lat, lng)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (custom_tour_id, original_id, user_id, custom_name, request_string, modified_audio_tour, lat, lng))
        
        custom_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        return jsonify({
            'custom_tour_id': custom_tour_id,
            'download_url': f'/download-tour/{custom_tour_id}',
            'status': 'processing'
        })
        
    except Exception as e:
        print(f"ERROR in create_custom_tour: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Ensure custom tours table exists on startup
    ensure_custom_tours_table()
    
    print("Starting Map Delivery Service with Phase 2 Tour Editing...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location (includes custom)")
    print("  GET /search-tours?query=<text> - Search tours by text (includes custom)")
    print("  GET /download-tour/<tour_id> - Download tour zip file (supports custom)")
    print("  GET /tour-info/<tour_id> - Get tour information")
    print("  GET /tour/<tour_id>/edit-info - Get tour editing information")
    print("  POST /tour/<tour_id>/update-stop - Update a tour stop")
    print("  POST /tour/<tour_id>/create-custom - Create custom tour version")
    print("\nPhase 2 Tour Editing Features:")
    print("  - Tour structure extraction for editing")
    print("  - Individual stop content updates")
    print("  - Custom tour generation with modifications")
    print("  - Polly TTS integration for text changes")
    print("  - Enhanced tours-near with custom tour support")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5005')), debug=False)
