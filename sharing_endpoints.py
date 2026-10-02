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
        # [ST-4] Local Docker has no GATEWAY_API_KEY, so sharing returned 503 and the
        # feature could not be tested on the Mac Mini at all.
        #
        # Deliberately NOT a silent fail-open: this endpoint WRITES, and an
        # unauthenticated write endpoint reachable from a network is a spam vector.
        # Michael's "everything in Audioura must be public" (2026-09-24) is about
        # shared tours being readable by anyone -- resolution -- not about letting
        # anyone write rows.
        #
        # So it opens only when someone has explicitly said so, by setting
        # ALLOW_UNAUTHENTICATED_SHARING=true. That is set in the LOCAL compose file
        # and nowhere else. Cloud has a real GATEWAY_API_KEY, so this branch is not
        # even reached there, and the fail-closed 503 remains for any deployment that
        # is genuinely misconfigured.
        if os.getenv('ALLOW_UNAUTHENTICATED_SHARING', '').lower() in ('true', '1', 'yes'):
            return None
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
    # [ST-4] Share by TOUR ID. The app already has the tour; making it re-upload the
    # whole text to share it is wasteful and, since ST-1, unnecessary -- a share
    # references the row. Everything else is derived here from the row itself, so the
    # client sends one integer instead of a document.
    audio_tour_id = data.get('audio_tour_id')
    if audio_tour_id and not all([location, tour_type, total_stops, tour_text]):
        try:
            import psycopg2 as _pg
            _conn = _pg.connect(DATABASE_URL)
            with _conn.cursor() as _cur:
                _cur.execute(
                    "SELECT tour_name, request_string, stops_count, tour_content "
                    "FROM audio_tours WHERE id = %s", (int(audio_tour_id),))
                _row = _cur.fetchone()
            _conn.close()
            if not _row:
                return jsonify({"error": "tour not found"}), 404
            _name, _req, _stops, _content = _row
            location = location or _req or _name
            tour_type = tour_type or 'walking'
            total_stops = total_stops or _stops or 1
            # tour_text is legacy: the share resolves through audio_tour_id now. Keep a
            # copy only so pre-ST-1 readers do not see an empty row.
            tour_text = tour_text or (_content or '')[:200000] or '(referenced)'
        except Exception as _e:
            return jsonify({"error": f"could not read tour: {_e}"}), 500

    if not all([location, tour_type, total_stops, tour_text]):
        return jsonify({"error": "location, tour_type, total_stops, and tour_text are required "
                                 "(or pass audio_tour_id)"}), 400

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
        # [ST-1/ST-4] The reference is what makes download and translation work.
        audio_tour_id=int(audio_tour_id) if audio_tour_id else None,
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
