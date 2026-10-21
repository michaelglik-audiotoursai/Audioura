#!/usr/bin/env python3
"""
Treats Service - Serves treats data from PostgreSQL database

[LOCAL-730 / D694, Privacy "Location and places"] Treats are chosen from the
PLACES IN THE USER'S TOURS, or a place the user typed on Home — never from the
phone's location. The app sends tour-stop coordinates here; this service never
receives, needs or stores a device id, user id or IP, and it logs only ROUNDED
coordinates (2 decimals, ~1.1 km) — enough to debug, not enough to track.

Endpoints:
  GET  /treats-near/<lat>/<lng>   — one point (kept for older app versions)
  POST /treats-near-places        — several points (<= 10); merged + de-duped
"""
import os
import sys
import json
import psycopg2
import math
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\n==== TREATS SERVICE STARTING: {datetime.now().isoformat()} ====")
sys.stdout.flush()

app = Flask(__name__)
CORS(app)

# The most points one /treats-near-places request may carry. A tour has a
# handful of stops; the cap keeps one request cheap and bounds the fan-out.
MAX_POINTS = 10

# How many treats a single response returns (unchanged behaviour for GET).
RESULT_LIMIT = 5


def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
    )


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


def round_coord(value):
    """Round a coordinate to 2 decimals (~1.1 km) for logging only. The
    Privacy promise: we log rounded coordinates or none — never the exact
    position the app sent."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _treats_near_point(cur, lat, lng):
    """Return the RESULT_LIMIT treats nearest to (lat, lng).

    Pulls every treat once and ranks by distance (the table is tiny). Each
    treat dict carries its treat id so callers can merge/de-duplicate across
    several points. Binary images are left on the row here and base64-encoded
    once, after merging, by the caller.
    """
    cur.execute(
        """
        SELECT id, ad_name, ad_text, lat, lng, link_to_vendor, ad_image,
               distance_in_feet
        FROM treats
        ORDER BY id DESC
        """
    )
    rows = cur.fetchall()
    with_coords = []
    without_coords = []
    for row in rows:
        (treat_id, ad_name, ad_text, treat_lat, treat_lng,
         link_to_vendor, ad_image, distance_in_feet) = row
        treat = {
            'id': treat_id,
            'name': ad_name,
            'description': ad_text,
            'lat': treat_lat,
            'lng': treat_lng,
            'link_to_vendor': link_to_vendor,
            'ad_image': ad_image,
            'distance_in_feet': distance_in_feet,
        }
        if treat_lat and treat_lng:
            if distance_in_feet and distance_in_feet > 0:
                treat['distance_km'] = round(distance_in_feet * 0.0003048, 2)
            else:
                treat['distance_km'] = round(
                    calculate_distance(lat, lng, treat_lat, treat_lng), 2)
            with_coords.append(treat)
        else:
            without_coords.append(treat)

    with_coords.sort(key=lambda t: t['distance_km'])
    return (with_coords + without_coords)[:RESULT_LIMIT]


def merge_treats(treat_lists):
    """Merge several per-point treat lists into one, de-duplicating by treat id
    (keeping the SMALLEST distance_km seen for each), sorted nearest-first, and
    capped at RESULT_LIMIT. Treats without an id fall back to name+vendor as the
    de-dup key; treats without a distance sort to the end."""
    merged = {}
    for treats in treat_lists:
        for treat in treats:
            key = treat.get('id')
            if key is None:
                key = (treat.get('name'), treat.get('link_to_vendor'))
            existing = merged.get(key)
            if existing is None:
                merged[key] = treat
            else:
                # keep the nearer copy of the same treat
                new_d = treat.get('distance_km')
                old_d = existing.get('distance_km')
                if new_d is not None and (old_d is None or new_d < old_d):
                    merged[key] = treat

    result = list(merged.values())
    result.sort(key=lambda t: t.get('distance_km', float('inf')))
    return result[:RESULT_LIMIT]


def encode_images(treats):
    """Base64-encode each treat's binary image in place (dropping the raw
    bytes). Mutates and returns the same list."""
    import base64
    for treat in treats:
        img = treat.pop('ad_image', None)
        treat['image_base64'] = (
            base64.b64encode(img).decode('utf-8') if img else None)
    return treats


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    print("Health check requested")
    sys.stdout.flush()
    return jsonify({"status": "healthy", "service": "treats"})


@app.route('/treats-near/<float:lat>/<float:lng>', methods=['GET'])
@app.route('/treats-near/<lat>/<lng>', methods=['GET'])
def get_treats_near_location(lat, lng):
    """Get treats near a single location (kept for older app versions)."""
    try:
        lat = float(lat)
        lng = float(lng)
    except ValueError:
        return jsonify({'error': 'Invalid coordinates'}), 400

    # Log only ROUNDED coordinates (2 decimals) — never the exact position.
    print(f"Getting treats near lat~={round_coord(lat)}, lng~={round_coord(lng)}")
    sys.stdout.flush()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        result_treats = _treats_near_point(cur, lat, lng)
        cur.close()
        conn.close()

        print(f"Found {len(result_treats)} treats")
        sys.stdout.flush()

        encode_images(result_treats)

        return jsonify({
            'treats': result_treats,
            'center_lat': lat,
            'center_lng': lng,
            'count': len(result_treats),
        })
    except Exception as e:
        print(f"ERROR in get_treats_near_location: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500


@app.route('/treats-near-places', methods=['POST'])
def get_treats_near_places():
    """[LOCAL-730] Get treats near SEVERAL places in one request.

    Body: {"points": [{"lat": <float>, "lng": <float>}, ...]}  (1..MAX_POINTS)
    The points are the stops of the user's tour (or a place typed on Home) —
    never the phone's GPS. Results for every point are merged and de-duplicated
    by treat id, nearest-first, capped at RESULT_LIMIT. No device/user/IP is
    read or stored; only rounded coordinates are logged.
    """
    body = request.get_json(silent=True) or {}
    raw_points = body.get('points')
    if not isinstance(raw_points, list) or not raw_points:
        return jsonify({'error': 'points must be a non-empty list'}), 400
    if len(raw_points) > MAX_POINTS:
        return jsonify({'error': f'at most {MAX_POINTS} points allowed'}), 400

    points = []
    for p in raw_points:
        if not isinstance(p, dict):
            return jsonify({'error': 'each point must be an object'}), 400
        try:
            points.append((float(p['lat']), float(p['lng'])))
        except (KeyError, TypeError, ValueError):
            return jsonify({'error': 'each point needs numeric lat and lng'}), 400

    rounded = [f"({round_coord(la)},{round_coord(ln)})" for la, ln in points]
    print(f"Getting treats near {len(points)} places: {', '.join(rounded)}")
    sys.stdout.flush()

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        per_point = [_treats_near_point(cur, la, ln) for la, ln in points]
        cur.close()
        conn.close()

        result_treats = merge_treats(per_point)
        print(f"Found {len(result_treats)} treats across {len(points)} places")
        sys.stdout.flush()

        encode_images(result_treats)

        return jsonify({
            'treats': result_treats,
            'count': len(result_treats),
            'points': len(points),
        })
    except Exception as e:
        print(f"ERROR in get_treats_near_places: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("Starting Treats Service...")
    print("Endpoints:")
    print("  GET  /health - Health check")
    print("  GET  /treats-near/<lat>/<lng> - Get treats near one location")
    print("  POST /treats-near-places - Get treats near several tour places")
    sys.stdout.flush()

    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5006')), debug=False)
