#!/usr/bin/env python3
"""
Amenities Near Service — runtime navigation amenities (LOCAL-337).

Returns the nearest amenity of a given kind (drinking water, toilets) to a
coordinate, plus a landmark hint drawn from OSM data. The app uses this to
speak a sentence like:

    "Water — there's a public fountain 200 metres ahead, just past the church."

This is a RUNTIME service — it does not modify tour narration (D250).

Three distinguishable response states:
  - found:             amenity located, distance + optional landmark
  - none_found:       searched successfully, nothing within radius
  - service_unavailable: Overpass failed/throttled (D162 — never report
                         a failed lookup as "no water nearby")

Museum tours are excluded at the endpoint — GPS is useless indoors and
there is nothing to route to. The exclusion checks the tour name in the
database so it cannot be bypassed by omitting context.
"""
import math
import os
import sys
import threading
import time

import psycopg2
import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# Configure unbuffered logging
sys.stdout.reconfigure(line_buffering=True)
print(f"\n==== AMENITIES NEAR SERVICE STARTING ====")
sys.stdout.flush()

app = Flask(__name__)
CORS(app)

# ──── Configuration ──────────────────────────────────────────────────────────

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_HEADERS = {
    "User-Agent": "Audioura/2.2 (amenities-near; contact: support@audioura.com)",
}
# Overpass usage policy: respectful rate — 1 request per 2 seconds minimum
OVERPASS_MIN_INTERVAL = 2.0
OVERPASS_TIMEOUT = 10  # seconds

# Search radius for amenities (metres)
AMENITY_SEARCH_RADIUS = 1000
# Search radius for landmark hint around an amenity (metres)
LANDMARK_SEARCH_RADIUS = 150

# Valid amenity kinds
VALID_KINDS = {"drinking_water", "toilets"}

# Rate-limit state (shared across threads)
_overpass_lock = threading.Lock()
_overpass_last_request_time = 0.0


# ──── Database ───────────────────────────────────────────────────────────────

def get_db_connection():
    """Get database connection (matches treats_service.py conventions)."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432')
    )


def is_museum_tour(tour_id):
    """Check if a tour is a museum tour by its name.

    Museum tours contain 'museum' (case-insensitive) in tour_name.
    Returns True if museum, False if not, None if tour_id not found.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT tour_name FROM audio_tours WHERE id = %s", (tour_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row is None:
            return None
        return "museum" in row[0].lower()
    except Exception:
        # DB failure — cannot verify, so we allow the lookup to proceed
        # (failing safe = allowing a search, not blocking a thirsty person)
        return False


# ──── Haversine ──────────────────────────────────────────────────────────────

def haversine_metres(lat1, lng1, lat2, lng2):
    """Distance in metres between two WGS84 points."""
    R = 6371000  # Earth radius in metres
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ──── Overpass queries ───────────────────────────────────────────────────────

def _overpass_query(query_str):
    """Execute an Overpass query with rate-limiting.

    Returns parsed JSON on success.
    Raises RuntimeError on 429, timeout, or connection failure.
    """
    global _overpass_last_request_time

    with _overpass_lock:
        now = time.time()
        elapsed = now - _overpass_last_request_time
        if elapsed < OVERPASS_MIN_INTERVAL:
            time.sleep(OVERPASS_MIN_INTERVAL - elapsed)
        _overpass_last_request_time = time.time()

    try:
        resp = requests.post(
            OVERPASS_URL,
            data={"data": query_str},
            headers=OVERPASS_HEADERS,
            timeout=OVERPASS_TIMEOUT,
        )
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        raise RuntimeError(f"Overpass connection failed: {e}")

    if resp.status_code == 429:
        raise RuntimeError("Overpass rate limited (429)")
    if resp.status_code != 200:
        raise RuntimeError(f"Overpass HTTP {resp.status_code}")

    return resp.json()


def find_nearest_amenity(lat, lng, kind):
    """Find nearest amenity of given kind within AMENITY_SEARCH_RADIUS.

    Returns dict with keys: lat, lng, name, distance_m
    Returns None if nothing found.
    Raises RuntimeError if Overpass is unavailable.
    """
    query = f"""
    [out:json][timeout:10];
    node["amenity"="{kind}"](around:{AMENITY_SEARCH_RADIUS},{lat},{lng});
    out body;
    """
    data = _overpass_query(query)
    elements = data.get("elements", [])
    if not elements:
        return None

    # Find the closest one
    best = None
    best_dist = float("inf")
    for el in elements:
        el_lat = el.get("lat")
        el_lng = el.get("lon")
        if el_lat is None or el_lng is None:
            continue
        dist = haversine_metres(lat, lng, el_lat, el_lng)
        if dist < best_dist:
            best_dist = dist
            best = el

    if best is None:
        return None

    tags = best.get("tags", {})
    name = tags.get("name") or tags.get("description") or kind.replace("_", " ")

    return {
        "lat": best["lat"],
        "lng": best["lon"],
        "name": name,
        "distance_m": round(best_dist),
        "osm_id": best.get("id"),
    }


def find_landmark_near(lat, lng):
    """Find the nearest named feature near a point (for the landmark hint).

    Queries for named nodes/ways within LANDMARK_SEARCH_RADIUS that are
    likely useful landmarks: places of worship, monuments, shops, cafés,
    squares, etc.

    Returns a name string or None.
    Raises RuntimeError if Overpass is unavailable.
    """
    query = f"""
    [out:json][timeout:10];
    (
      node["name"](around:{LANDMARK_SEARCH_RADIUS},{lat},{lng});
      way["name"](around:{LANDMARK_SEARCH_RADIUS},{lat},{lng});
    );
    out body;
    """
    data = _overpass_query(query)
    elements = data.get("elements", [])
    if not elements:
        return None

    # Prefer features that make good spoken landmarks
    # Priority: place_of_worship > monument > historic > shop/cafe > any named
    priority_tags = [
        "place_of_worship", "monument", "memorial", "castle",
        "church", "chapel", "mosque", "synagogue",
    ]

    best = None
    best_dist = float("inf")
    best_priority = 999

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue

        # Skip the amenity itself if it has a name matching what we're querying
        amenity_type = tags.get("amenity", "")
        if amenity_type in VALID_KINDS:
            continue

        el_lat = el.get("lat")
        el_lng = el.get("lon")
        if el_lat is None or el_lng is None:
            # Ways have center lat/lng in 'center' if requested, but we
            # didn't request center — skip ways without coordinates
            continue

        dist = haversine_metres(lat, lng, el_lat, el_lng)

        # Determine priority
        priority = 999
        for i, ptag in enumerate(priority_tags):
            if ptag in tags.get("amenity", "") or ptag in tags.get("historic", "") or ptag in tags.get("building", ""):
                priority = i
                break

        # Prefer higher priority; within same priority, prefer closer
        if priority < best_priority or (priority == best_priority and dist < best_dist):
            best = name
            best_dist = dist
            best_priority = priority

    # Fallback: if no priority match, take the closest named feature
    if best is None:
        closest_name = None
        closest_dist = float("inf")
        for el in elements:
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            el_lat = el.get("lat")
            el_lng = el.get("lon")
            if el_lat is None or el_lng is None:
                continue
            if tags.get("amenity", "") in VALID_KINDS:
                continue
            dist = haversine_metres(lat, lng, el_lat, el_lng)
            if dist < closest_dist:
                closest_dist = dist
                closest_name = name
        best = closest_name

    return best


# ──── Endpoints ──────────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "amenities-near"})


@app.route('/amenities-near/<float:lat>/<float:lng>', methods=['GET'])
@app.route('/amenities-near/<lat>/<lng>', methods=['GET'])
def get_amenities_near(lat, lng):
    """Get nearest amenity of a given kind.

    Query params:
      - kind: amenity type (drinking_water, toilets). Required.
      - tour_id: active tour ID (for museum exclusion). Optional but
                 recommended — if provided and tour is museum, returns 403.

    Response states:
      - 200 with status="found": amenity located
      - 200 with status="none_found": searched, nothing within radius
      - 503 with status="service_unavailable": could not search (D162)
      - 400: invalid parameters
      - 403: museum tour (amenities not available indoors)
    """
    # Parse coordinates
    try:
        lat = float(lat)
        lng = float(lng)
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid coordinates"}), 400

    # Validate kind
    kind = request.args.get("kind")
    if not kind:
        return jsonify({"error": "Missing required parameter: kind"}), 400
    if kind not in VALID_KINDS:
        return jsonify({
            "error": f"Invalid kind: {kind}",
            "valid_kinds": sorted(VALID_KINDS),
        }), 400

    # Museum exclusion (D250 + Michael's explicit instruction)
    tour_id = request.args.get("tour_id")
    if tour_id:
        try:
            tour_id_int = int(tour_id)
        except ValueError:
            return jsonify({"error": "Invalid tour_id"}), 400
        museum = is_museum_tour(tour_id_int)
        if museum is True:
            return jsonify({
                "status": "excluded",
                "reason": "museum_tour",
                "message": "Amenity lookup not available for museum tours (indoor, no GPS)",
            }), 403

    print(f"[AMENITIES-NEAR] Searching kind={kind} near {lat},{lng}")
    sys.stdout.flush()

    # Find nearest amenity
    try:
        amenity = find_nearest_amenity(lat, lng, kind)
    except RuntimeError as e:
        # D162: failed lookup ≠ "no water nearby"
        print(f"[AMENITIES-NEAR] Overpass failed: {e}")
        sys.stdout.flush()
        return jsonify({
            "status": "service_unavailable",
            "message": "I can't check right now",
            "error_detail": str(e),
        }), 503

    if amenity is None:
        return jsonify({
            "status": "none_found",
            "message": "I can't find water nearby" if kind == "drinking_water"
                       else "I can't find toilets nearby",
            "search_radius_m": AMENITY_SEARCH_RADIUS,
            "center_lat": lat,
            "center_lng": lng,
        }), 200

    # Find landmark hint near the amenity
    landmark_hint = None
    try:
        landmark_hint = find_landmark_near(amenity["lat"], amenity["lng"])
    except RuntimeError as e:
        # Landmark lookup failed — still return the amenity without hint
        print(f"[AMENITIES-NEAR] Landmark lookup failed: {e}")
        sys.stdout.flush()

    return jsonify({
        "status": "found",
        "amenity": {
            "kind": kind,
            "name": amenity["name"],
            "lat": amenity["lat"],
            "lng": amenity["lng"],
            "distance_m": amenity["distance_m"],
            "landmark_hint": landmark_hint,
        },
        "center_lat": lat,
        "center_lng": lng,
    }), 200


if __name__ == '__main__':
    print("Starting Amenities Near Service...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /amenities-near/<lat>/<lng>?kind=drinking_water|toilets[&tour_id=N]")
    sys.stdout.flush()

    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5009')), debug=False)
