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
        200 with {tour_text, location, tour_type, total_stops, share_count}
        404 with {error: "shared tour not found"} if ID unknown
    """
    if not share_id or len(share_id) > 10:
        return jsonify({"error": "invalid share_id"}), 400

    tour = get_shared_tour(share_id, DATABASE_URL)
    if not tour:
        return jsonify({"error": "shared tour not found"}), 404

    return jsonify({
        "share_id": share_id,
        "tour_text": tour["tour_text"],
        "location": tour["location"],
        "tour_type": tour["tour_type"],
        "total_stops": tour["total_stops"],
        "share_count": tour.get("share_count", 0),
        "created_at": tour.get("created_at"),
    }), 200
