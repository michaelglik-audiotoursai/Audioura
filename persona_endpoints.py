"""
Persona Endpoints — POST /user/persona and GET /user/persona
==============================================================
Flask blueprint providing user persona persistence endpoints.
Requires API key header (X-API-Key) for both operations.

Task [S45]: Add POST /user/persona and GET /user/persona endpoints
to tour-generator service.
"""
import os
import logging

from flask import Blueprint, request, jsonify

from persona_preference_store import save_persona, get_persona
from onboarding_preference import UserPersona

logger = logging.getLogger(__name__)

persona_bp = Blueprint('persona', __name__)

# Database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://admin:admin@localhost:5432/audiotours')

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


@persona_bp.route('/user/persona', methods=['POST'])
def set_user_persona():
    """Save a user's persona preference.

    Body: {"user_id": "...", "persona": "art_lover"}
    Returns: 200 {"saved": true} or 400/401.
    """
    err = _require_api_key()
    if err:
        return err

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    user_id = data.get('user_id')
    persona_str = data.get('persona')

    if not user_id or not persona_str:
        return jsonify({"error": "user_id and persona are required"}), 400

    # Validate persona value
    try:
        persona_enum = UserPersona(persona_str.strip().lower())
    except ValueError:
        valid = [p.value for p in UserPersona]
        return jsonify({"error": f"Invalid persona. Valid values: {valid}"}), 400

    success = save_persona(user_id, persona_enum, DATABASE_URL)
    if success:
        logger.info(f"Persona saved: user_id={user_id} persona={persona_str}")
        return jsonify({"saved": True}), 200
    else:
        return jsonify({"error": "Failed to save persona"}), 500


@persona_bp.route('/user/persona', methods=['GET'])
def get_user_persona():
    """Retrieve a user's persona preference.

    Query: ?user_id=X
    Returns: 200 {"persona": "art_lover"} or 404 {"persona": null}.
    """
    err = _require_api_key()
    if err:
        return err

    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({"error": "user_id query parameter required"}), 400

    persona = get_persona(user_id, DATABASE_URL)
    if persona is None:
        return jsonify({"persona": None}), 404

    return jsonify({"persona": persona.value}), 200
