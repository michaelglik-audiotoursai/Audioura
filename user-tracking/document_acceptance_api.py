"""
document_acceptance_api.py — LOCAL-691 legal-page acceptance capture.

Self-contained Flask blueprint for the user-api service (user-tracking/app.py),
self-contained ON PURPOSE: the user-api container's build context is
./user-tracking and cannot import repo-root modules (exactly like
entitlements_api.py and communities_api.py). It owns a tiny HTTP surface:

  POST /document-acceptance
       body: {"user_id": "...", "document": "guide_terms",
              "version": "2026-10-14-draft1"}
       Records that the user accepted the document at this version. Idempotent:
       re-accepting the same (user, document, version) is a no-op. Returns
       {"status": "recorded", "already": bool}.

  GET  /document-acceptance?user_id=...[&document=...]
       Lists this user's acceptances (optionally filtered to one document),
       newest first: {"acceptances": [{document, version, accepted_at}, ...]}.

Acceptance is REQUIRED and stored for selling a guide tour and creating a
community (the app blocks those actions until the POST succeeds). The Buy /
community-pass "By buying you agree to the Terms" line records a 'terms'
acceptance the same way.

Auth mirrors entitlements_api / communities_api: an X-API-Key is required in
production, with the ALLOW_UNAUTHENTICATED_ENTITLEMENTS escape hatch for local
dev / tests.
"""

import os
import hmac
import logging

import psycopg2
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

document_acceptance_bp = Blueprint('document_acceptance', __name__)

DATABASE_URL = os.getenv(
    'DATABASE_URL', 'postgresql://admin:password123@localhost:5432/audiotours')
API_KEY = os.getenv('GATEWAY_API_KEY', '')

# The documents the app can record acceptance for. Kept deliberately permissive
# (validated as a known slug, but a new document does NOT need a migration — the
# table does not constrain the value). These match the legal/ slugs.
KNOWN_DOCUMENTS = {
    'terms', 'privacy', 'refunds',
    'guide_terms', 'organiser_terms', 'content_policy',
}


def _get_db():
    return psycopg2.connect(DATABASE_URL)


# ─── Auth — identical pattern to entitlements_api._require_api_key ──────────
def _unauthenticated_allowed():
    return os.getenv('ALLOW_UNAUTHENTICATED_ENTITLEMENTS', '').lower() in (
        'true', '1', 'yes')


def _require_api_key():
    if not API_KEY:
        if _unauthenticated_allowed():
            return None
        return jsonify({"error": "service_misconfigured"}), 503
    client_key = request.headers.get('X-API-Key', '')
    if not client_key or not hmac.compare_digest(client_key, API_KEY):
        return jsonify({"error": "unauthorized"}), 401
    return None


def _normalise_document(doc):
    """Lower-case, trim, and map a few friendly aliases to canonical slugs."""
    if not doc:
        return None
    d = str(doc).strip().lower().replace('-', '_')
    aliases = {
        'content_policy': 'content_policy',
        'guide': 'guide_terms',
        'organiser': 'organiser_terms',
        'organizer_terms': 'organiser_terms',
        'tos': 'terms',
        'terms_of_service': 'terms',
    }
    return aliases.get(d, d)


# ─── POST /document-acceptance ─────────────────────────────────────────────
@document_acceptance_bp.route('/document-acceptance', methods=['POST'])
def record_acceptance():
    auth = _require_api_key()
    if auth is not None:
        return auth

    data = request.get_json(silent=True) or {}
    user_id = (data.get('user_id') or '').strip()
    document = _normalise_document(data.get('document'))
    version = (data.get('version') or '').strip()

    if not user_id or not document or not version:
        return jsonify({
            "error": "missing_fields",
            "required": ["user_id", "document", "version"],
        }), 400
    if document not in KNOWN_DOCUMENTS:
        return jsonify({"error": "unknown_document", "document": document}), 400

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor()
        # Idempotent: a repeat acceptance of the same version is a no-op. We
        # detect that via rowcount so the caller learns whether it was new.
        cur.execute(
            """
            INSERT INTO document_acceptance (user_id, document, version)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, document, version) DO NOTHING
            """,
            (user_id, document, version),
        )
        inserted = cur.rowcount == 1
        conn.commit()
        cur.close()
        return jsonify({"status": "recorded", "already": not inserted}), 200
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("record_acceptance failed")
        if conn is not None:
            conn.rollback()
        return jsonify({"error": "server_error", "detail": str(exc)}), 500
    finally:
        if conn is not None:
            conn.close()


# ─── GET /document-acceptance ──────────────────────────────────────────────
@document_acceptance_bp.route('/document-acceptance', methods=['GET'])
def list_acceptances():
    auth = _require_api_key()
    if auth is not None:
        return auth

    user_id = (request.args.get('user_id') or '').strip()
    if not user_id:
        return jsonify({"error": "missing_fields", "required": ["user_id"]}), 400
    document = _normalise_document(request.args.get('document'))

    conn = None
    try:
        conn = _get_db()
        cur = conn.cursor()
        if document:
            cur.execute(
                """
                SELECT document, version, accepted_at
                FROM document_acceptance
                WHERE user_id = %s AND document = %s
                ORDER BY accepted_at DESC
                """,
                (user_id, document),
            )
        else:
            cur.execute(
                """
                SELECT document, version, accepted_at
                FROM document_acceptance
                WHERE user_id = %s
                ORDER BY accepted_at DESC
                """,
                (user_id,),
            )
        rows = cur.fetchall()
        cur.close()
        acceptances = [
            {
                "document": r[0],
                "version": r[1],
                "accepted_at": r[2].isoformat() if r[2] else None,
            }
            for r in rows
        ]
        return jsonify({"acceptances": acceptances}), 200
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("list_acceptances failed")
        return jsonify({"error": "server_error", "detail": str(exc)}), 500
    finally:
        if conn is not None:
            conn.close()
