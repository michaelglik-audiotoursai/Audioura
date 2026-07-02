"""
Deep-Link Resolution Endpoint — GET /resolve/tour/{share_id}
==============================================================
Task [S83]: Resolves a shared tour ID to the full tour data.
Used by the mobile app when opening a shared deep link.
Added to the tour-id-resolution service.
"""
import os
import logging

from flask import Blueprint, jsonify

from tour_sharing import get_shared_tour

logger = logging.getLogger(__name__)

deeplink_bp = Blueprint('deeplink', __name__)

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:admin@localhost:5432/audiotours')


@deeplink_bp.route('/resolve/tour/<share_id>', methods=['GET'])
def resolve_shared_tour(share_id):
    """Resolve a shared tour deep link to full tour data.

    Public endpoint — no API key required (shared links are public).

    Returns:
        200 with {share_id, tour_id, tour_text, location, tour_type, total_stops, share_count, share_url, created_at}
        404 with {error: "shared tour not found"} if ID unknown
    """
    if not share_id or len(share_id) > 10:
        return jsonify({"error": "invalid share_id"}), 400

    tour = get_shared_tour(share_id, DATABASE_URL)
    if not tour:
        return jsonify({"error": "shared tour not found"}), 404

    # Increment share_count
    _increment_share_count(share_id)

    # Build share_url
    from tour_sharing import build_share_url
    BASE_URL = os.getenv('BASE_URL', 'https://audioura.io')
    share_url = build_share_url(share_id, BASE_URL)

    return jsonify({
        "share_id": share_id,
        "tour_id": share_id,  # For mobile deep-link navigation
        "tour_text": tour["tour_text"],
        "location": tour["location"],
        "tour_type": tour["tour_type"],
        "total_stops": tour["total_stops"],
        "share_count": tour.get("share_count", 0) + 1,
        "share_url": share_url,
        "created_at": tour.get("created_at"),
    }), 200


def _increment_share_count(share_id: str) -> None:
    """Increment share_count. Best-effort."""
    import psycopg2
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("UPDATE shared_tours SET share_count = share_count + 1 WHERE tour_id = %s", (share_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to increment share_count for {share_id}: {e}")
