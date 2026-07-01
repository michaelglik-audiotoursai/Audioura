"""
Sharing Endpoints — POST /tour/share and GET /tour/<tour_id>
==============================================================
Flask blueprint for tour sharing functionality.

Task [S49]: POST /tour/share — generate share ID, store tour, return URL.
Task [S50]: GET /tour/<tour_id> — retrieve shared tour by ID (public).
"""
import os
import logging

from flask import Blueprint, request, jsonify

from tour_sharing import (
    generate_shareable_tour_id,
    store_shared_tour,
    get_shared_tour,
    build_share_url,
)

logger = logging.getLogger(__name__)

sharing_bp = Blueprint('sharing', __name__)

# Database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:admin@localhost:5432/audiotours')

# Base URL for share links
BASE_URL = os.getenv('BASE_URL', 'https://audioura.io')

# API key for authentication
API_KEY = os.getenv('GATEWAY_API_KEY', '')


def _require_api_key():
    """Check X-API-Key header. Returns error response or None."""
    import hmac
    if not API_KEY:
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


@sharing_bp.route('/tour/share', methods=['POST'])
def share_tour():
    """Generate a shareable tour link.

    Body: {"location": "...", "tour_type": "...", "total_stops": N, "tour_text": "..."}
    Returns: 200 {"share_id": "abc12345", "share_url": "https://audioura.io/tour/abc12345"}
    Idempotent: same inputs always return same share_id without re-storing.
    Requires API key.
    """
    err = _require_api_key()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    location = data.get('location')
    tour_type = data.get('tour_type')
    total_stops = data.get('total_stops')
    tour_text = data.get('tour_text')

    if not all([location, tour_type, total_stops, tour_text]):
        return jsonify({"error": "location, tour_type, total_stops, and tour_text are required"}), 400

    try:
        total_stops = int(total_stops)
    except (ValueError, TypeError):
        return jsonify({"error": "total_stops must be an integer"}), 400

    # Generate deterministic share ID
    share_id = generate_shareable_tour_id(location, tour_type, total_stops)

    # Check if already stored (idempotent)
    existing = get_shared_tour(share_id, DATABASE_URL)
    if existing:
        share_url = build_share_url(share_id, BASE_URL)
        logger.info(f"Tour share already exists: {share_id}")
        return jsonify({"share_id": share_id, "share_url": share_url}), 200

    # Store the shared tour
    success = store_shared_tour(
        tour_id=share_id,
        tour_text=tour_text,
        location=location,
        tour_type=tour_type,
        total_stops=total_stops,
        db_url=DATABASE_URL,
    )

    if not success:
        return jsonify({"error": "Failed to store shared tour"}), 500

    share_url = build_share_url(share_id, BASE_URL)
    logger.info(f"Tour shared: {share_id} → {share_url}")
    return jsonify({"share_id": share_id, "share_url": share_url}), 200


@sharing_bp.route('/tour/<tour_id>', methods=['GET'])
def get_tour(tour_id):
    """Retrieve a shared tour by ID.

    Public endpoint — no API key required.
    Increments share_count on each retrieval.
    Returns: 200 {tour_text, location, tour_type, total_stops, share_count}
             or 404 {"error": "tour not found"}.
    """
    tour = get_shared_tour(tour_id, DATABASE_URL)
    if not tour:
        return jsonify({"error": "tour not found"}), 404

    # Increment share_count
    _increment_share_count(tour_id)

    # Return tour data with updated count
    return jsonify({
        "tour_text": tour["tour_text"],
        "location": tour["location"],
        "tour_type": tour["tour_type"],
        "total_stops": tour["total_stops"],
        "share_count": tour["share_count"] + 1,  # reflect the increment
    }), 200


def _increment_share_count(tour_id: str) -> None:
    """Increment the share_count for a tour. Best-effort, no error propagation."""
    import psycopg2
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE shared_tours SET share_count = share_count + 1 WHERE tour_id = %s",
                (tour_id,),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to increment share_count for {tour_id}: {e}")
