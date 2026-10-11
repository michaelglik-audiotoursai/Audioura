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
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, send_file, make_response

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\n==== MAP DELIVERY SERVICE STARTING: {datetime.now().isoformat()} ====")
sys.stdout.flush()

app = Flask(__name__)

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
@app.route('/tour-by-code/<code>', methods=['GET'])
def get_tour_by_code(code):
    """[ST-2] Resolve a share code into ONE tour, shaped exactly like a /tours-near entry.

    Why this exists: the home list is built from /tours-near, which is LOCATION based.
    Kostya's teammates enter his code at home, nowhere near the trailhead, so proximity
    will never surface that tour. This is the second way in.

    Why the shape is IDENTICAL and not merely similar: the app drops this straight into
    the list it already renders, so pick -> download -> translate keep working UNCHANGED.
    Note `original_tour_id` in particular -- that is the chain the app follows to offer
    a translation, and it is why a share must reference a real audio_tours row (ST-1)
    rather than the detached text copy the table used to hold.

    Public, by Michael's ruling 2026-09-24: "Everything in Audioura must be public. It is
    just some of the tours are paid and most are free." Payment is a property of a tour,
    not of how it was found, so resolution carries no auth.
    """
    print(f"Resolving share code: {code}")
    sys.stdout.flush()
    try:
        code = (code or '').strip()
        if not code or len(code) > 16:
            return jsonify({'error': 'invalid code'}), 404

        conn = get_db_connection()
        cur = conn.cursor()

        # ST-1 put the reference here. Legacy rows predate it and hold NULL; they
        # resolve through their stored text and cannot be surfaced as a map entry, so
        # they are a clean 404 rather than a half-populated row.
        cur.execute("SELECT audio_tour_id FROM shared_tours WHERE tour_id = %s", (code,))
        row = cur.fetchone()
        if not row or not row[0]:
            cur.close()
            conn.close()
            return jsonify({'error': 'tour not found'}), 404

        cur.execute(f"""
            SELECT t.id, t.tour_name, t.request_string, t.lat, t.lng,
                   t.number_requested, t.language, t.original_tour_id,
                   v.max_version_no, v.last_replaced_at, t.created_at,
                   {_source_version_select(cur)} AS source_version,
                   sv.max_version_no AS source_max_version_no,
                   {_ratings_select(cur)}
            FROM audio_tours t
            LEFT JOIN (
                SELECT tour_id,
                       MAX(version_no)  AS max_version_no,
                       MAX(replaced_at) AS last_replaced_at
                FROM audio_tour_versions
                WHERE tour_id = %s
                GROUP BY tour_id
            ) v ON v.tour_id = t.id
            LEFT JOIN (
                SELECT tour_id, MAX(version_no) AS max_version_no
                FROM audio_tour_versions
                GROUP BY tour_id
            ) sv ON sv.tour_id = t.original_tour_id
            {_ratings_join(cur)}
            WHERE t.id = %s
        """, (row[0], row[0]))
        t = cur.fetchone()
        cur.close()
        conn.close()
        if not t:
            return jsonify({'error': 'tour not found'}), 404

        (tour_id, tour_name, request_string, tour_lat, tour_lng, requests,
         language, original_id, max_vn, last_replaced, created_at,
         source_version, source_max_vn, rating_count, rating_values) = t
        # [LOCAL-666] A share code can point at a translation row (original_tour_id
        # set, e.g. Russian 615 of 557) as well as an original. For a translation we
        # report the SOURCE tour's version (its pinned source_version, else the
        # source's live version) with the translation's own created_at as the
        # "updated" date — so the Russian copy of v10 says v10, not v1 (the number
        # LOCAL-657 produced by joining on the translation's never-replaced own id).
        # Originals are unchanged.
        version, updated_at = _resolved_version_fields(
            original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
        rating = compute_rating(rating_values)
        # Same keys as a /tours-near element. distance_km is None, not 0: the listener
        # is not near it, and 0 would sort it to the top under false pretences.
        return jsonify({
            'tours': [{
                'id': tour_id,
                'name': tour_name,
                'request_string': request_string,
                'lat': tour_lat,
                'lng': tour_lng,
                'distance_km': None,
                'popularity': requests,
                'type': 'walking_tour',
                'language': language or 'en',
                'original_tour_id': original_id,
                'via_share_code': code,
                'version': version,
                'updated_at': updated_at,
                'rating_score': rating['score'],
                'rating_count': rating['count'],
                'rating_label': rating['label'],
            }],
            'count': 1,
        })
    except Exception as e:
        print(f"[ST-2] tour-by-code failed for {code!r}: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        return jsonify({'error': 'tour not found'}), 404


@app.route('/tours-near/<lat>/<lng>', methods=['OPTIONS'])
@app.route('/download-tour/<int:tour_id>', methods=['OPTIONS'])
@app.route('/tour-info/<int:tour_id>', methods=['OPTIONS'])
@app.route('/search-tours', methods=['OPTIONS'])
def handle_options(*args, **kwargs):
    response = make_response()
    return add_cors_headers(response)

# Log all incoming requests
@app.before_request
def log_request():
    print(f"\n==== INCOMING REQUEST: {datetime.now().isoformat()} ====")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Remote Address: {request.remote_addr}")
    print(f"User Agent: {request.headers.get('User-Agent', 'Unknown')}")
    print(f"Content Type: {request.headers.get('Content-Type', 'Unknown')}")
    print(f"Headers: {dict(request.headers)}")
    sys.stdout.flush()

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host="postgres-2",
        database="audiotours", 
        user="admin",
        password="password123"
    )

def _version_fields(max_version_no, last_replaced_at, created_at):
    """[LOCAL-657] Derive the (version, updated_at) pair the app shows next to Downloads.

    version = COALESCE(MAX(version_no), 0) + 1 for the tour's own id. A tour that
    has never been replaced has no audio_tour_versions rows (max is NULL) and is
    therefore version 1. Each replacement archives the OLD version_no (1,2,3,…),
    so N archived rows mean the live row is version N+1.

    updated_at = the newest replaced_at if the tour has ever been replaced, else
    the row's created_at. Returned as an ISO date string (YYYY-MM-DD), or None if
    no timestamp is available at all. The app only renders this when version >= 2.
    """
    version = (max_version_no or 0) + 1
    stamp = last_replaced_at or created_at
    updated_at = None
    if stamp is not None:
        try:
            updated_at = stamp.date().isoformat()
        except AttributeError:
            # Already a date, or a string — fall back to str() of its date part.
            updated_at = str(stamp)[:10]
    return version, updated_at


def _iso_date(stamp):
    """Format a timestamp/date (or ISO string) as YYYY-MM-DD, or None."""
    if stamp is None:
        return None
    try:
        return stamp.date().isoformat()
    except AttributeError:
        return str(stamp)[:10]


def _resolved_version_fields(original_tour_id, source_version,
                             source_max_version_no, own_max_version_no,
                             own_last_replaced_at, created_at):
    """[LOCAL-666] Version + updated_at for a row that may be an ORIGINAL or a TRANSLATION.

    A translation row (original_tour_id set) is never replaced in place, so joining
    audio_tour_versions on its OWN id always yields v1 (the LOCAL-657 bug for
    translations). Instead a translation reports:
      * version    = its pinned source_version (snapshot taken at translation time),
                     falling back to the SOURCE tour's live version
                     (COALESCE(MAX(version_no),0)+1 over the source id) when
                     source_version is NULL (pre-666 rows, or source_version column
                     absent → passed as None here).
      * updated_at = the translation row's OWN created_at — the day this translated
                     copy was produced — NOT the source's replaced_at.

    An ORIGINAL row (original_tour_id is None) is unchanged from LOCAL-657: version
    from its own archive rows, updated_at = newest replaced_at else created_at.
    """
    if original_tour_id is None:
        return _version_fields(own_max_version_no, own_last_replaced_at, created_at)
    # Translation row.
    if source_version is not None:
        version = int(source_version)
    else:
        version = (source_max_version_no or 0) + 1
    return version, _iso_date(created_at)


# [LOCAL-666] Cache the one-time schema probe for the optional source_version column
# so each request does not re-query information_schema. None until first checked.
_HAS_SOURCE_VERSION = None


def _has_source_version_column(cur):
    """True if audio_tours.source_version exists. Probed once per process and cached.
    When absent (older schema), the SELECTs below omit the column and translations
    fall back to the SOURCE tour's live version — the ticket's 'column absent → falls
    back' requirement."""
    global _HAS_SOURCE_VERSION
    if _HAS_SOURCE_VERSION is None:
        try:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'source_version'
            """)
            _HAS_SOURCE_VERSION = cur.fetchone() is not None
        except Exception:
            _HAS_SOURCE_VERSION = False
    return _HAS_SOURCE_VERSION


def _source_version_select(cur):
    """SQL fragment selecting source_version (or a NULL literal on an older schema)."""
    return "t.source_version" if _has_source_version_column(cur) else "NULL::integer"


# ─── Tour rating (LOCAL-670) ──────────────────────────────────────────────────
# The per-TOUR 1..10 rating is OWNED by the orchestrator's tour_rating_service
# (POST/GET /tour/<id>/rating). map-delivery only READS it so the home list and
# tour dialogs can show the badge and the home filter can pass min_rating. The
# score rule below is a deliberate, self-contained copy of that service's rule
# (D647) — this directory deploys as its own image and cannot import the root
# module. Keep the two in lock-step; they are both unit-tested against the brief.
#
#   0 ratings   → 7.5, label "New"
#   1..3        → average of (7.5 + the real ratings), 1 dp (half-up)
#   >= 4        → median of the real ratings only, 1 dp (half-up)
RATING_DEFAULT_SCORE = 7.5
RATING_MEDIAN_SWITCH_COUNT = 4


def _rating_round_1dp(value):
    """One decimal place, half-up (8.25 → 8.3), without importing Decimal cost
    per row: do the half-up by hand on a scaled integer."""
    return math.floor(value * 10 + 0.5) / 10.0


def _rating_median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return (float(s[mid - 1]) + float(s[mid])) / 2.0


def compute_rating(ratings):
    """{score, count, label} from a list of REAL ratings (may be empty).

    Identical rule to tour_rating_service.compute_score (LOCAL-670 / D647)."""
    ratings = [int(r) for r in (ratings or []) if r is not None]
    count = len(ratings)
    if count == 0:
        return {"score": RATING_DEFAULT_SCORE, "count": 0, "label": "New"}
    if count < RATING_MEDIAN_SWITCH_COUNT:
        blended = [RATING_DEFAULT_SCORE] + [float(r) for r in ratings]
        score = _rating_round_1dp(sum(blended) / len(blended))
    else:
        score = _rating_round_1dp(_rating_median(ratings))
    label = f"{count} rating" if count == 1 else f"{count} ratings"
    return {"score": score, "count": count, "label": label}


# One grouped pass over tour_ratings — NOT one query per tour. Keyed on the
# ORIGINAL tour id, so a translation (original_tour_id set) inherits its source
# tour's ratings when the caller joins on COALESCE(t.original_tour_id, t.id).
_RATINGS_AGG_SUBQUERY = """
    LEFT JOIN (
        SELECT tour_id,
               COUNT(*)            AS rating_count,
               ARRAY_AGG(rating)   AS rating_values
        FROM tour_ratings
        GROUP BY tour_id
    ) r ON r.tour_id = COALESCE(t.original_tour_id, t.id)
"""

_HAS_TOUR_RATINGS = None


def _has_tour_ratings_table(cur):
    """True if the tour_ratings table exists. Probed once per process and cached.
    When absent (schema predates LOCAL-670) every tour reads as 0 ratings → the
    default 7.5 "New" — never a 500."""
    global _HAS_TOUR_RATINGS
    if _HAS_TOUR_RATINGS is None:
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'tour_ratings'
            """)
            _HAS_TOUR_RATINGS = cur.fetchone() is not None
        except Exception:
            _HAS_TOUR_RATINGS = False
    return _HAS_TOUR_RATINGS


def _parse_min_rating(args):
    """Parse the optional ?min_rating=<float> query param. Returns a float or
    None (absent/blank/invalid → no filter)."""
    raw = (args.get('min_rating') or '').strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _ratings_select(cur):
    """SQL fragment selecting (rating_count, rating_values) or NULL literals on
    an older schema with no tour_ratings table."""
    if _has_tour_ratings_table(cur):
        return "r.rating_count, r.rating_values"
    return "NULL::bigint AS rating_count, NULL::smallint[] AS rating_values"


def _ratings_join(cur):
    """The grouped LEFT JOIN over tour_ratings, or empty string on older schema."""
    return _RATINGS_AGG_SUBQUERY if _has_tour_ratings_table(cur) else ""


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

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    print("Health check requested")
    sys.stdout.flush()
    return jsonify({"status": "healthy", "service": "map_delivery"})

@app.route('/tours-near/<lat>/<lng>', methods=['GET'])
def get_tours_near_location(lat, lng):
    """Get tours near a specific location - all languages for map display"""
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
        
        # Get only English/original tours for map display (no translations)
        # Exclude test-generated tours (is_test flag set by test-mode generation)
        # [LOCAL-657] LEFT JOIN one grouped pass over audio_tour_versions (not a
        # query per tour) to carry each tour's version + last-replaced timestamp.
        # [LOCAL-666] source_version + a source-id aggregate are selected too so the
        # shared _resolved_version_fields helper works uniformly; this list is
        # originals-only (original_tour_id IS NULL) so they are inert here, but keep
        # the shape identical to the other endpoints that DO surface translations.
        # [LOCAL-670] Optional server-side rating filter (home page: Any/7+/8+/9+).
        min_rating = _parse_min_rating(request.args)

        cur.execute(f"""
            SELECT t.id, t.tour_name, t.request_string, t.lat, t.lng,
                   t.number_requested, t.content_language, t.original_tour_id,
                   v.max_version_no, v.last_replaced_at, t.created_at,
                   {_source_version_select(cur)} AS source_version,
                   sv.max_version_no AS source_max_version_no,
                   {_ratings_select(cur)}
            FROM audio_tours t
            LEFT JOIN (
                SELECT tour_id,
                       MAX(version_no)  AS max_version_no,
                       MAX(replaced_at) AS last_replaced_at
                FROM audio_tour_versions
                GROUP BY tour_id
            ) v ON v.tour_id = t.id
            LEFT JOIN (
                SELECT tour_id, MAX(version_no) AS max_version_no
                FROM audio_tour_versions
                GROUP BY tour_id
            ) sv ON sv.tour_id = t.original_tour_id
            {_ratings_join(cur)}
            WHERE t.lat IS NOT NULL AND t.lng IS NOT NULL
            AND (t.content_language = 'en' OR t.content_language IS NULL)
            AND t.original_tour_id IS NULL
            AND (t.is_test IS NOT TRUE)
        """)
        
        tours = cur.fetchall()
        tours_list = []
        
        for tour in tours:
            (tour_id, tour_name, request_string, tour_lat, tour_lng, requests,
             language, original_id, max_vn, last_replaced, created_at,
             source_version, source_max_vn, rating_count, rating_values) = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    version, updated_at = _resolved_version_fields(
                        original_id, source_version, source_max_vn,
                        max_vn, last_replaced, created_at)
                    rating = compute_rating(rating_values)
                    # Server-side min_rating filter: skip tours below the bar.
                    if min_rating is not None and rating['score'] < min_rating:
                        continue
                    tour_data = {
                        'id': tour_id,
                        'name': tour_name,
                        'request_string': request_string,
                        'lat': tour_lat,
                        'lng': tour_lng,
                        'distance_km': round(distance, 2),
                        'popularity': requests,
                        'type': 'walking_tour',
                        'language': language or 'en',
                        'original_tour_id': original_id,
                        'version': version,
                        'updated_at': updated_at,
                        'rating_score': rating['score'],
                        'rating_count': rating['count'],
                        'rating_label': rating['label'],
                    }
                    tours_list.append(tour_data)
        
        # Sort tours by distance
        tours_list.sort(key=lambda x: x['distance_km'])
        
        cur.close()
        conn.close()
        
        print(f"Found {len(tours_list)} tours within {radius_km} km")
        sys.stdout.flush()
        
        return jsonify({
            'tours': tours_list,
            'center_lat': lat,
            'center_lng': lng,
            'radius_km': radius_km,
            'total_count': len(tours_list)
        })
        
    except Exception as e:
        print(f"ERROR in get_tours_near_location: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/download-tour/<int:tour_id>', methods=['GET'])
def download_tour(tour_id):
    """Download a tour zip file by ID with multi-language support"""
    languages = request.args.get('languages', 'en').split('|')
    user_id = request.args.get('user_id', 'anonymous')
    print(f"Downloading tour ID: {tour_id}, languages: {languages}, user: {user_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            SELECT tour_name, audio_tour, request_string
            FROM audio_tours 
            WHERE id = %s AND audio_tour IS NOT NULL
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
            print(f"Tour {tour_id} not found")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        tour_name, audio_tour_data, request_string = result
        
        cur.execute("""
            UPDATE audio_tours 
            SET number_requested = number_requested + 1 
            WHERE id = %s
        """, (tour_id,))
        
        conn.commit()
        cur.close()
        conn.close()
        
        safe_name = request_string.encode('ascii', 'ignore').decode('ascii').replace(' ', '_').lower()
        if not safe_name:  # If all characters were non-ASCII
            safe_name = f"tour_{tour_id}"
        filename = f"{safe_name}_tour.zip"
        
        print(f"Sending tour file: {filename}")
        sys.stdout.flush()
        
        # Use streaming response for large files
        from flask import Response
        
        def generate():
            # Stream the file in chunks
            chunk_size = 8192  # 8KB chunks
            data = BytesIO(audio_tour_data)
            while True:
                chunk = data.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        
        return Response(
            generate(),
            mimetype='application/zip',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(audio_tour_data)),
                'Content-Type': 'application/zip'
            }
        )
        
    except Exception as e:
        print(f"ERROR in download_tour: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/tour-info/<int:tour_id>', methods=['GET'])
def get_tour_info(tour_id):
    """Get detailed information about a tour"""
    print(f"Getting info for tour ID: {tour_id}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # [LOCAL-666] Carry version + updated_at here too (the ticket lists /tour-info),
        # using the same rule as the list endpoints: a translation reports its SOURCE
        # version (pinned source_version, else the source's live version) with its own
        # created_at as the updated date; an original is unchanged from LOCAL-657.
        cur.execute(f"""
            SELECT t.id, t.tour_name, t.request_string, t.lat, t.lng,
                   t.number_requested, t.content_language, t.original_tour_id,
                   v.max_version_no, v.last_replaced_at, t.created_at,
                   {_source_version_select(cur)} AS source_version,
                   sv.max_version_no AS source_max_version_no,
                   {_ratings_select(cur)}
            FROM audio_tours t
            LEFT JOIN (
                SELECT tour_id, MAX(version_no) AS max_version_no, MAX(replaced_at) AS last_replaced_at
                FROM audio_tour_versions GROUP BY tour_id
            ) v ON v.tour_id = t.id
            LEFT JOIN (
                SELECT tour_id, MAX(version_no) AS max_version_no
                FROM audio_tour_versions GROUP BY tour_id
            ) sv ON sv.tour_id = t.original_tour_id
            {_ratings_join(cur)}
            WHERE t.id = %s
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
            print(f"Tour {tour_id} not found")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        (tour_id, tour_name, request_string, lat, lng, requests, language, original_id,
         max_vn, last_replaced, created_at, source_version, source_max_vn,
         rating_count, rating_values) = result
        cur.close()
        conn.close()
        
        is_translation = original_id is not None and (language and language != 'en')
        version, updated_at = _resolved_version_fields(
            original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
        rating = compute_rating(rating_values)
        
        return jsonify({
            'id': tour_id,
            'name': tour_name,
            'request_string': request_string,
            'lat': lat,
            'lng': lng,
            'downloads': requests,
            'has_audio': True,
            'language': language or 'en',
            'is_translation': is_translation,
            'parent_tour_id': original_id,
            'version': version,
            'updated_at': updated_at,
            'rating_score': rating['score'],
            'rating_count': rating['count'],
            'rating_label': rating['label'],
        })
        
    except Exception as e:
        print(f"ERROR in get_tour_info: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

@app.route('/search-tours', methods=['GET'])
def search_tours():
    """Search tours by pattern"""
    pattern = request.args.get('pattern', '')
    lat = float(request.args.get('lat', 0))
    lng = float(request.args.get('lng', 0))
    
    print(f"Searching tours with pattern: '{pattern}' near lat={lat}, lng={lng}")
    sys.stdout.flush()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Use ILIKE for case-insensitive pattern matching
        # Convert regex pattern back to SQL LIKE pattern
        sql_pattern = pattern.replace('.*', '%')
        # [LOCAL-670] Optional server-side rating filter.
        min_rating = _parse_min_rating(request.args)
        
        # [LOCAL-657, LEAD] Search results open the same tour dialogs, so they carry
        # the version label fields too (one grouped LEFT JOIN, as in /tours-near).
        # [LOCAL-666] Search surfaces translations (no original_tour_id IS NULL filter),
        # so a translation must show its SOURCE version, not v1. Join the versions
        # aggregate on the source id as well and resolve via _resolved_version_fields.
        # [LOCAL-670] Rating aggregate joined on COALESCE(original_tour_id, id) so a
        # translation inherits its source tour's rating too.
        cur.execute(f"""
            SELECT t.id, t.tour_name, t.request_string, t.lat, t.lng, t.number_requested,
                   t.content_language, t.original_tour_id,
                   v.max_version_no, v.last_replaced_at, t.created_at,
                   {_source_version_select(cur)} AS source_version,
                   sv.max_version_no AS source_max_version_no,
                   {_ratings_select(cur)}
            FROM audio_tours t
            LEFT JOIN (
                SELECT tour_id, MAX(version_no) AS max_version_no, MAX(replaced_at) AS last_replaced_at
                FROM audio_tour_versions GROUP BY tour_id
            ) v ON v.tour_id = t.id
            LEFT JOIN (
                SELECT tour_id, MAX(version_no) AS max_version_no
                FROM audio_tour_versions GROUP BY tour_id
            ) sv ON sv.tour_id = t.original_tour_id
            {_ratings_join(cur)}
            WHERE (t.tour_name ILIKE %s OR t.request_string ILIKE %s)
            AND t.lat IS NOT NULL AND t.lng IS NOT NULL
            AND (t.is_test IS NOT TRUE)
            ORDER BY t.number_requested DESC
            LIMIT 50
        """, (f'%{sql_pattern}%', f'%{sql_pattern}%'))
        
        tours = cur.fetchall()
        search_results = []
        
        for tour in tours:
            (tour_id, tour_name, request_string, tour_lat, tour_lng, requests, language, original_id,
             max_vn, last_replaced, created_at, source_version, source_max_vn,
             rating_count, rating_values) = tour
            version, updated_at = _resolved_version_fields(
                original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
            rating = compute_rating(rating_values)
            # Server-side min_rating filter.
            if min_rating is not None and rating['score'] < min_rating:
                continue
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                is_translation = original_id is not None and (language and language != 'en')
                
                search_results.append({
                    'id': tour_id,
                    'name': tour_name,
                    'request_string': request_string,
                    'lat': tour_lat,
                    'lng': tour_lng,
                    'distance_km': round(distance, 2),
                    'popularity': requests,
                    'type': 'walking_tour',
                    'language': language or 'en',
                    'is_translation': is_translation,
                    'parent_tour_id': original_id,
                    'version': version,
                    'updated_at': updated_at,
                    'rating_score': rating['score'],
                    'rating_count': rating['count'],
                    'rating_label': rating['label'],
                })
        
        # Sort by popularity first, then by distance
        search_results.sort(key=lambda x: (-x['popularity'], x['distance_km']))
        
        cur.close()
        conn.close()
        
        print(f"Found {len(search_results)} tours matching pattern '{pattern}'")
        sys.stdout.flush()
        
        return jsonify({
            'tours': search_results,
            'pattern': pattern,
            'count': len(search_results)
        })
        
    except Exception as e:
        print(f"ERROR in search_tours: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("Starting Map Delivery Service...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location")
    print("  GET /download-tour/<tour_id> - Download tour zip file")
    print("  GET /tour-info/<tour_id> - Get tour information")
    print("  GET /search-tours?pattern=<pattern>&lat=<lat>&lng=<lng> - Search tours by pattern")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=5005, debug=True)
