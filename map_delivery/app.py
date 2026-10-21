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
import uuid
import zipfile
from io import BytesIO
from datetime import datetime
from flask import Flask, request, jsonify, send_file, make_response

# [LOCAL-689] Personal Match % — deterministic, no model call. The formula lives
# in personal_match.py (copied into this image by the Dockerfile's COPY . .).
import personal_match

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
                   {_ratings_select(cur)},
                   {_is_paid_select(cur)} AS is_paid,
                   {_price_tier_select(cur)} AS price_tier,
                   {_short_title_select(cur)} AS short_title,
                   {_ORIGINAL_LANGUAGE_SELECT},
                   {_content_rating_select(cur)}
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
            {_ORIGINAL_LANGUAGE_JOIN}
            WHERE t.id = %s
        """, (row[0], row[0]))
        t = cur.fetchone()
        editor = _editor_scores(cur)  # [LOCAL-685]
        cur.close()
        conn.close()
        if not t:
            return jsonify({'error': 'tour not found'}), 404

        (tour_id, tour_name, request_string, tour_lat, tour_lng, requests,
         language, original_id, max_vn, last_replaced, created_at,
         source_version, source_max_vn, rating_count, rating_values,
         verified_values, created_values, is_paid, price_tier, short_title,
         own_content_language, source_content_language,
         content_rating, content_review_status) = _row_with_rating(t, 22)
        # [LOCAL-687] Content gate for a shared code. A hidden tour (not_allowed,
        # or pending/rejected review) is a clean 404 — the same as a code that
        # resolves to nothing, so a held tour is indistinguishable from no tour.
        # A MATURE tour the caller has not confirmed 18+ for (no adult=1) is a 403
        # age_restricted — the app shows "turn on 18+ tours in Settings". A mature
        # tour WITH adult=1, and any general tour, resolve normally.
        adult = _adult_requested(request.args)
        _rating = (content_rating or 'general').strip().lower()
        _status = (content_review_status or '').strip().lower()
        if _rating == 'not_allowed' or _status in ('pending', 'rejected'):
            return jsonify({'error': 'tour not found'}), 404
        if _rating == 'mature' and not adult:
            return jsonify({'error': 'age_restricted'}), 403
        # [LOCAL-666] A share code can point at a translation row (original_tour_id
        # set, e.g. Russian 615 of 557) as well as an original. For a translation we
        # report the SOURCE tour's version (its pinned source_version, else the
        # source's live version) with the translation's own created_at as the
        # "updated" date — so the Russian copy of v10 says v10, not v1 (the number
        # LOCAL-657 produced by joining on the translation's never-replaced own id).
        # Originals are unchanged.
        version, updated_at = _resolved_version_fields(
            original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
        original_language = _resolved_original_language(
            own_content_language, original_id, source_content_language)
        # Same keys as a /tours-near element. distance_km is None, not 0: the listener
        # is not near it, and 0 would sort it to the top under false pretences.
        return jsonify({
            'tours': [{
                'id': tour_id,
                'name': tour_name,
                # [LOCAL-711 / D673] Server short title (NULL until generated);
                # the app shows it in the share email, else shortTourTitle(name).
                'short_title': short_title,
                'request_string': request_string,
                'lat': tour_lat,
                'lng': tour_lng,
                'distance_km': None,
                'popularity': requests,
                'type': 'walking_tour',
                'language': language or 'en',
                'original_tour_id': original_id,
                'original_language': original_language,
                'via_share_code': code,
                'version': version,
                'updated_at': updated_at,
                'content_rating': _content_rating_field(content_rating),
                **_rating_payload(rating_values, verified_values, created_values, is_paid,
                                  prior=_prior_for(editor, tour_id, original_id)),
                **_price_block(price_tier),
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
@app.route('/tour/<int:tour_id>/preview-audio', methods=['OPTIONS'])
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

def _ensure_tour_reports_table(cur):
    """LOCAL-724 item 5: self-healing create of tour_reports (migration 042), so
    /report-tour works on any DB whether or not the migration has run. Additive
    and idempotent."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tour_reports (
            id            SERIAL PRIMARY KEY,
            tour_id       INTEGER REFERENCES audio_tours(id) ON DELETE SET NULL,
            tour_name     TEXT,
            reason        TEXT,
            reporter_user_id TEXT,
            status        VARCHAR(16) NOT NULL DEFAULT 'open'
                          CHECK (status IN ('open', 'reviewed', 'dismissed')),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


@app.route('/report-tour', methods=['POST', 'OPTIONS'])
def report_tour():
    """LOCAL-724 item 5: record an in-app content report as ONE row in
    tour_reports. The app's "Report This Tour" posts here instead of opening a
    mailto:, so each report is a reviewable row, not an inbox message. This
    endpoint ONLY records a report; it never hides, lists, approves or rejects a
    tour — triage and the approve/reject decision stay with a human
    (review_queue.py; D656 add. 2).

    Body (JSON): { "tour_id": <int, optional>, "tour_name": <str, optional>,
                   "reason": <str, optional>, "user_id": <str, optional> }
    At least one of tour_id / tour_name must be present.
    Returns 201 { "status": "received", "report_id": <int> } on success.
    """
    if request.method == 'OPTIONS':
        return make_response(('', 204))
    data = request.get_json(silent=True) or {}
    tour_id = data.get('tour_id')
    tour_name = (data.get('tour_name') or '').strip() or None
    reason = (data.get('reason') or '').strip() or None
    reporter_user_id = (data.get('user_id') or '').strip() or None
    try:
        tour_id = int(tour_id) if tour_id is not None and str(tour_id).strip() != '' else None
    except (TypeError, ValueError):
        tour_id = None
    if tour_id is None and not tour_name:
        return jsonify({'status': 'error',
                        'error': 'tour_id or tour_name is required'}), 400
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        _ensure_tour_reports_table(cur)
        cur.execute(
            """INSERT INTO tour_reports (tour_id, tour_name, reason, reporter_user_id)
               VALUES (%s, %s, %s, %s) RETURNING id""",
            (tour_id, tour_name, reason, reporter_user_id))
        report_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        print(f"[LOCAL-724] content report #{report_id} for tour_id={tour_id} "
              f"name={tour_name!r}")
        return jsonify({'status': 'received', 'report_id': report_id}), 201
    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"[LOCAL-724] /report-tour failed: {e}")
        return jsonify({'status': 'error', 'error': 'could not record report'}), 500
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


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


# [LOCAL-671] The SOURCE language every tour element carries. "Original: English"
# in the tour dialogs is NOT the tour's own language (a Russian translation's own
# content_language is 'ru'); it is the language the tour was originally written in.
#   * An ORIGINAL row (original_tour_id NULL) was written in its own
#     content_language — so original_language == its own content_language.
#   * A TRANSLATION row (original_tour_id set) was translated FROM its original,
#     so original_language == that original's content_language, carried here by a
#     LEFT JOIN on the source id (orig.content_language). The translation's own
#     content_language ('ru', 'fr', …) is NOT the original language and is ignored.
# Defaults to 'en' when unknown (NULL on either side), matching the rest of the
# service, so the dialog never shows a blank "Original:".
def _resolved_original_language(own_content_language, original_tour_id,
                                source_content_language):
    """original_language for a row that may be an ORIGINAL or a TRANSLATION."""
    if original_tour_id is None:
        return own_content_language or 'en'
    # Translation: the original's language. Fall back to 'en' if the source row's
    # content_language is NULL (legacy originals predate the column's default).
    return source_content_language or 'en'


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


# [LOCAL-711 / D673] The server-written SHORT title (migration 040). Exposed on
# every payload that already carries tour_name, so the app can show it in the
# share email (title + subject) and fall back to its own shortTourTitle() only
# when the column is NULL. Probed once + cached; absent column reads as NULL,
# fails OPEN to today's behaviour. A TRANSLATION carries its OWN translated
# short_title (translation-service writes it), so this uses the ROW's own
# t.short_title — not the original's — exactly like t.tour_name.
_HAS_SHORT_TITLE_COLUMN = None


def _has_short_title_column(cur):
    global _HAS_SHORT_TITLE_COLUMN
    if _HAS_SHORT_TITLE_COLUMN is None:
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'short_title'
            """)
            _HAS_SHORT_TITLE_COLUMN = cur.fetchone() is not None
        except Exception:
            _HAS_SHORT_TITLE_COLUMN = False
    return _HAS_SHORT_TITLE_COLUMN


def _short_title_select(cur):
    """SQL fragment selecting short_title (or a NULL literal on an older schema)."""
    return "t.short_title" if _has_short_title_column(cur) else "NULL::text"


# [LOCAL-671] original_language is appended as the LAST two SELECTed columns on every
# endpoint, in this fixed order:
#     ..., t.content_language AS own_content_language,
#          orig.content_language AS source_content_language
# own_content_language is the row's own language (used verbatim for an ORIGINAL);
# source_content_language is the ORIGINAL tour's language, reached by a LEFT JOIN of
# audio_tours onto itself on t.original_tour_id (NULL for an original row, since the
# join finds nothing). _resolved_original_language collapses the two into the single
# original_language value the app shows. Appending (not inserting) keeps the existing
# column positions — and therefore every sibling test fixture — stable except for two
# new trailing values, mirroring how LOCAL-670 appended its rating columns.
_ORIGINAL_LANGUAGE_SELECT = ("t.content_language AS own_content_language, "
                             "orig.content_language AS source_content_language")

# LEFT JOIN the source (original) tour so a translation can read its ORIGINAL's
# content_language. Inert for an original row (original_tour_id NULL → no match).
_ORIGINAL_LANGUAGE_JOIN = """
    LEFT JOIN audio_tours orig ON orig.id = t.original_tour_id
"""


# ─── [LOCAL-687 / D656] Content rating + review gate ──────────────────────────
#
# Every tour carries a content_rating (general | mature | not_allowed; NULL =
# NOT RATED YET, treated as general so old tours keep working) and a
# review_status (pending | approved | rejected; NULL = no review needed). Both
# are written by tour_content_rating.py (migration 027). The LISTING RULE, applied
# on every endpoint:
#   * not_allowed                         -> never listed (hidden).
#   * review_status pending | rejected    -> hidden until a human approves.
#   * mature                              -> listed ONLY when the request carries
#                                            adult=1 (listener confirmed 18+).
#   * general / NULL (and approved)       -> listed for everyone.
# A translation INHERITS its ORIGINAL's rating and review_status, read through the
# `orig` self-join the endpoints already have (COALESCE(orig.*, t.*)), exactly as
# price_tier / is_paid do. Appended as the LAST two SELECTed columns on every
# endpoint — content_rating, content_review_status — so existing column positions
# (and sibling test fixtures) stay stable, mirroring LOCAL-671/670.
_HAS_CONTENT_RATING_COLUMN = None


def _has_content_rating_column(cur):
    """True if audio_tours.content_rating exists (migration 027). Probed once +
    cached. Absent (older schema) → every tour reads as NULL == general and lists
    as before — content rating fails OPEN to the old behaviour, never a 500."""
    global _HAS_CONTENT_RATING_COLUMN
    if _HAS_CONTENT_RATING_COLUMN is None:
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'content_rating'
            """)
            _HAS_CONTENT_RATING_COLUMN = cur.fetchone() is not None
        except Exception:
            _HAS_CONTENT_RATING_COLUMN = False
    return _HAS_CONTENT_RATING_COLUMN


def _content_rating_select(cur):
    """SQL fragment selecting (content_rating, review_status), inheriting a
    translation's values from its ORIGINAL via the `orig` self-join — so a
    translation of a mature/not_allowed/pending original is hidden too. Two NULL
    literals on an older schema (→ everything reads as general, lists as before).
    Always two columns in a fixed order, appended LAST."""
    if _has_content_rating_column(cur):
        return ("COALESCE(orig.content_rating, t.content_rating) AS content_rating, "
                "COALESCE(orig.review_status, t.review_status) AS content_review_status")
    return ("NULL::varchar AS content_rating, "
            "NULL::varchar AS content_review_status")


def _adult_requested(args):
    """True when the request confirmed the listener is 18+ (adult=1). Accepts
    adult=1/true/yes. Anything else (absent, 0, blank) → False, so mature tours
    stay hidden by default."""
    raw = (args.get('adult') or '').strip().lower()
    return raw in ('1', 'true', 'yes')


def _content_visible(content_rating, review_status, adult):
    """The listing decision for ONE tour. Returns True if it may be listed.

    NULL content_rating == 'general' (old tours keep working until scored).
      * not_allowed                      -> hidden (never listed).
      * review_status pending | rejected -> hidden (awaiting / failed review).
      * mature                           -> only when adult is True.
      * general                          -> listed.
    An 'approved' review_status lists per the tour's rating (mature still needs
    adult=1); NULL review_status (general, no review needed) lists too.
    """
    rating = (content_rating or 'general').strip().lower()
    status = (review_status or '').strip().lower()
    if rating == 'not_allowed':
        return False
    if status in ('pending', 'rejected'):
        return False
    if rating == 'mature':
        return bool(adult)
    return True


def _content_rating_field(content_rating):
    """The content_rating value put on every tour payload. NULL → 'general' so the
    app always sees one of the three known values (the app shows an 18+ chip when
    it is 'mature')."""
    return (content_rating or 'general').strip().lower()


def _row_with_rating(row, head_len):
    """Return (row_padded_to_head_len+2). The content_rating + review_status pair
    was APPENDED as the last two SELECT columns (LOCAL-687). A production row
    always carries them; a row from an older code path (or a sibling unit-test
    fixture written before 687) carries only the first head_len values. Pad the
    missing trailing pair with (None, None) — which reads as general/no-review, so
    those rows list exactly as they did before 687. This keeps the unpack arity
    fixed without forcing every pre-687 fixture to grow two columns."""
    row = tuple(row)
    if len(row) >= head_len + 2:
        return row[:head_len + 2]
    return row[:head_len] + (None, None)


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


def _editor_scores(cur):
    """[LOCAL-685] {tour_id: editor_score} for every scored tour (5.0–8.0, written
    by tour_editor_score.py). Empty on a schema without the column or on error,
    which falls back to the flat 7.5 — never a 500. One small query per request."""
    try:
        cur.execute("SELECT id, editor_score FROM audio_tours WHERE editor_score IS NOT NULL")
        return {int(i): float(v) for i, v in cur.fetchall()}
    except Exception:
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return {}


def _prior_for(editor_scores, tour_id, original_id):
    """A translation shows its ORIGINAL's evaluated score (ratings pool there too)."""
    key = original_id if original_id is not None else tour_id
    return editor_scores.get(int(key)) if key is not None else None


# ─── [LOCAL-689] Personal Match % ────────────────────────────────────────────
#
# A listener's swipe-preference vector (user_class_prefs) + a tour's story
# character (mean of stop_metrics.class_* over its stops) + the tour's evaluated
# score (editor_score) → a 0–100 "Match %" and two short reasons. All arithmetic
# is in personal_match.py; this file only READS the three inputs from the DB.
# A translation uses its ORIGINAL tour's metrics AND score (the stops and the
# evaluation both live on the original), exactly like _prior_for for the rating.
#
# Everything here is designed to be BATCHED: _user_prefs is one query, and
# _tour_characters aggregates the stop_metrics of MANY tours in a single
# GROUP BY — so /tours-near and /search-tours add Match % with two extra queries
# total, never one-per-tour (no N+1).


def _user_prefs(cur, user_id):
    """(prefs_dict | None, swipe_count) for a listener.

    prefs_dict is {details, historic, social} in [0,1]; None when the listener
    has no user_class_prefs row at all (pure cold start). swipe_count is 0 then.
    Never raises — returns (None, 0) on any error or missing table."""
    if not user_id:
        return None, 0
    try:
        cur.execute(
            "SELECT pref_details, pref_historic, pref_social, swipe_count "
            "FROM user_class_prefs WHERE user_id = %s", (str(user_id),))
        row = cur.fetchone()
    except Exception:  # noqa: BLE001 — schema predates the table → cold
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return None, 0
    if not row:
        return None, 0
    prefs = {
        'details': float(row[0]) if row[0] is not None else 0.5,
        'historic': float(row[1]) if row[1] is not None else 0.5,
        'social': float(row[2]) if row[2] is not None else 0.5,
    }
    swipe_count = int(row[3]) if row[3] is not None else 0
    return prefs, swipe_count


def _tour_characters(cur, original_ids):
    """{original_tour_id: {details, historic, social}} for many tours in ONE
    query (no N+1). Aggregates stop_metrics.class_* as a per-tour mean over the
    tour's stops. Tours with no stop_metrics rows are simply absent from the
    result; the caller treats a missing character as a neutral tour.

    `original_ids` is the set of GOVERNING tour ids (translations already
    resolved to their original) to aggregate. Empty / error → {}."""
    ids = sorted({int(i) for i in original_ids if i is not None})
    if not ids:
        return {}
    try:
        cur.execute(
            "SELECT tour_id, "
            "       AVG(class_details)  AS d, "
            "       AVG(class_historic) AS h, "
            "       AVG(class_social)   AS s "
            "FROM stop_metrics "
            "WHERE tour_id = ANY(%s) "
            "  AND class_details IS NOT NULL "
            "GROUP BY tour_id", (ids,))
        rows = cur.fetchall()
    except Exception:  # noqa: BLE001 — schema predates stop_metrics → no chars
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return {}
    out = {}
    for tour_id, d, h, s in rows:
        # Renormalise the mean so the three shares sum to 1 (personal_match also
        # defends against this, but keep the stored value clean).
        d, h, s = float(d or 0), float(h or 0), float(s or 0)
        tot = d + h + s
        if tot <= 0:
            continue
        out[int(tour_id)] = {'details': d / tot, 'historic': h / tot, 'social': s / tot}
    return out


def _match_block(prefs, swipe_count, character, editor_score):
    """The public shape added to a tour item / returned by the endpoint:
        {match_percent: int|None, match_reasons: [str,...], match_reason: str|None}
    `match_reason` is the single cold-start sentence (null once a match exists);
    `match_reasons` is the two phrases (empty on cold start)."""
    result = personal_match.compute_match(prefs, swipe_count, character, editor_score)
    if result['cold_start']:
        return {
            'match_percent': None,
            'match_reasons': [],
            'match_reason': personal_match.NO_MATCH_REASON,
        }
    return {
        'match_percent': result['match_percent'],
        'match_reasons': result['reasons'],
        'match_reason': None,
    }


def _attach_match(cur, user_id, tours_list, editor_scores):
    """[LOCAL-689] Add match_percent + reasons to EVERY item of a list endpoint,
    in-place, with no N+1. Two queries total: _user_prefs (once) and
    _tour_characters (once, batched over all governing tour ids).

    Each tour item must carry 'id' and (for /tours-near originals) None or (for
    /search-tours) 'parent_tour_id' / 'original_tour_id' so a translation maps
    to its original's metrics+score. When user_id is absent or the listener has
    < MIN_SWIPES swipes, every item gets the cold-start block (match_percent
    null) — a uniform shape the app can rely on."""
    prefs, swipe_count = _user_prefs(cur, user_id)

    def _governing(item):
        gid = item.get('original_tour_id', None)
        if gid is None:
            gid = item.get('parent_tour_id', None)
        return int(gid) if gid is not None else int(item['id'])

    governing_ids = {_governing(t) for t in tours_list}
    characters = _tour_characters(cur, governing_ids) if (
        prefs is not None and swipe_count >= personal_match.MIN_SWIPES) else {}

    for t in tours_list:
        gid = _governing(t)
        character = characters.get(gid, {'details': 1 / 3, 'historic': 1 / 3, 'social': 1 / 3})
        editor_score = editor_scores.get(gid)
        t.update(_match_block(prefs, swipe_count, character, editor_score))


def _single_tour_match(cur, user_id, tour_id):
    """[LOCAL-689] The GET /tour/<id>/match payload for one tour. Resolves a
    translation to its original for BOTH the metrics and the evaluated score."""
    original_id = _resolve_original_id(cur, tour_id)
    prefs, swipe_count = _user_prefs(cur, user_id)
    editor = _editor_scores(cur)
    editor_score = _prior_for(editor, tour_id, original_id)
    if prefs is not None and swipe_count >= personal_match.MIN_SWIPES:
        characters = _tour_characters(cur, [original_id])
        character = characters.get(int(original_id),
                                   {'details': 1 / 3, 'historic': 1 / 3, 'social': 1 / 3})
    else:
        character = {'details': 1 / 3, 'historic': 1 / 3, 'social': 1 / 3}
    block = _match_block(prefs, swipe_count, character, editor_score)
    block['tour_id'] = int(tour_id)
    block['scored_tour_id'] = int(original_id)
    return block


def compute_rating(ratings, verified=None, paid=False, prior=None):
    """{score, count, label} from a list of REAL ratings (may be empty).

    Identical rule to tour_rating_service.compute_score (LOCAL-670 / D647).

    [LOCAL-672] On a PAID tour only VERIFIED ratings count toward the shown
    score; on a FREE tour all download-gated ratings count (unchanged LOCAL-670).
    Pass the parallel `verified` list (same order as `ratings`) and paid=True to
    restrict to verified ratings. The SHOWN score rule itself (prior/median) is
    unchanged — only the input set differs on a paid tour.
    """
    pairs = [(int(r), bool(verified[i]) if verified and i < len(verified) and verified[i] is not None else False)
             for i, r in enumerate(ratings or []) if r is not None]
    if paid:
        pairs = [p for p in pairs if p[1]]
    ratings = [r for r, _ in pairs]
    count = len(ratings)
    # [LOCAL-685] The tour's evaluated score replaces the flat 7.5 when it has one.
    base = float(prior) if prior is not None else RATING_DEFAULT_SCORE
    if count == 0:
        return {"score": base, "count": 0,
                "label": "Audioura score" if prior is not None else "New"}
    if count < RATING_MEDIAN_SWITCH_COUNT:
        blended = [base] + [float(r) for r in ratings]
        score = _rating_round_1dp(sum(blended) / len(blended))
    else:
        score = _rating_round_1dp(_rating_median(ratings))
    label = f"{count} rating" if count == 1 else f"{count} ratings"
    return {"score": score, "count": count, "label": label}


# ─── [LOCAL-672] Verified counting, Bayesian ranking, distribution ────────────
#
# This directory deploys as its own image and cannot import tour_reviews_service,
# so the rank rule and the five distribution bands are a self-contained copy of
# that module's logic (items 4, 8, 11). Keep them in lock-step; both are unit-
# tested against the brief. All of this is LIST-ORDER / display only — the SHOWN
# score stays D647.

RANK_PRIOR_COUNT = 3
RANK_PRIOR_SCORE = 7.5
WEIGHT_VERIFIED = 1.0
WEIGHT_UNVERIFIED = 0.5
WEIGHT_STALE = 0.5
STALE_AFTER_DAYS = 365

# Five bands (item 8): 9-10, 7-8, 5-6, 3-4, 1-2.
_BANDS = [(9, 10), (7, 8), (5, 6), (3, 4), (1, 2)]


def _band_of(rating):
    for lo, hi in _BANDS:
        if lo <= rating <= hi:
            return f"{lo}-{hi}"
    return None


def _is_stale(created_at, now, current_version_date):
    if created_at is None:
        return False
    try:
        age_days = (now - created_at).days
    except Exception:
        return False
    if age_days > STALE_AFTER_DAYS:
        return True
    if current_version_date is not None:
        try:
            if created_at < current_version_date:
                return True
        except Exception:
            return False
    return False


def rank_score(ratings, verified=None, created=None, now=None, current_version_date=None,
               prior=None):
    """Bayesian list-ORDER key (items 4 & 11). NOT the shown score.

    score = (C*7.5 + sum(w_i*rating_i)) / (C + sum(w_i)), C=3.
    w_i = (1.0 verified | 0.5 unverified) * (0.5 if stale else 1.0),
    stale = older than 12 months OR before the tour's current version date.
    Parallel lists `verified` and `created` align with `ratings` (missing → False
    / None). No ratings → the 7.5 prior (a new tour sorts mid-list)."""
    from datetime import datetime as _dt
    if now is None:
        now = _dt.now()
    # [LOCAL-685] Per-tour evaluated prior when present, else the flat 7.5.
    prior_score = float(prior) if prior is not None else RANK_PRIOR_SCORE
    num = RANK_PRIOR_COUNT * prior_score
    den = float(RANK_PRIOR_COUNT)
    for i, r in enumerate(ratings or []):
        if r is None:
            continue
        v = bool(verified[i]) if verified and i < len(verified) and verified[i] is not None else False
        c = created[i] if created and i < len(created) else None
        w = WEIGHT_VERIFIED if v else WEIGHT_UNVERIFIED
        if _is_stale(c, now, current_version_date):
            w *= WEIGHT_STALE
        num += w * int(r)
        den += w
    return num / den if den > 0 else prior_score


def compute_distribution(ratings, verified=None, paid=False):
    """The five-band distribution (item 8) with counts + percentages.

    Verified ratings on a PAID tour; all counted ratings on a FREE tour."""
    pairs = [(int(r), bool(verified[i]) if verified and i < len(verified) and verified[i] is not None else False)
             for i, r in enumerate(ratings or []) if r is not None]
    if paid:
        pairs = [p for p in pairs if p[1]]
    vals = [r for r, _ in pairs]
    total = len(vals)
    bands = []
    for lo, hi in _BANDS:
        c = sum(1 for r in vals if lo <= r <= hi)
        bands.append({"band": f"{lo}-{hi}", "count": c,
                      "percent": round((c / total) * 100) if total else 0})
    return {"total": total, "bands": bands}


def _rating_payload(rating_values, verified_values, created_values, paid, prior=None):
    """Build the full per-tour rating block for a response (LOCAL-670 + 672).

    Returns a dict with:
      rating_score / rating_count / rating_label  — the SHOWN score (D647);
          on a PAID tour computed from VERIFIED ratings only, on a FREE tour
          from all counted ratings (LOCAL-670).
      verified_count          — how many of the ratings are verified.
      is_paid                 — whether this tour is treated as paid.
      rank_score              — the Bayesian list-ORDER key (items 4/11).
      rating_distribution     — the five-band distribution (item 8), from the
          same source set as the shown score (verified on paid, all on free).
    The caller supplies the already-fetched arrays and the paid flag, so this is
    a pure function (unit-testable, no DB)."""
    rating = compute_rating(rating_values, verified=verified_values, paid=paid, prior=prior)
    vals = [r for r in (rating_values or []) if r is not None]
    verified_count = sum(1 for v in (verified_values or []) if v)
    return {
        'rating_score': rating['score'],
        'rating_count': rating['count'],
        'rating_label': rating['label'],
        'verified_count': verified_count,
        'is_paid': bool(paid),
        'rank_score': round(rank_score(rating_values, verified=verified_values,
                                        created=created_values, prior=prior), 4),
        'rating_distribution': compute_distribution(
            rating_values, verified=verified_values, paid=paid),
    }



# [LOCAL-672] Also aggregates the verified flag and created_at (same ARRAY_AGG
# order as rating_values) so paid-tour counting, the distribution and the
# Bayesian rank key have what they need in the same single pass. The verified /
# created_at columns are included only when the schema has them (see
# _ratings_select), so an older DB still works.
_RATINGS_AGG_SUBQUERY = """
    LEFT JOIN (
        SELECT tour_id,
               COUNT(*)                 AS rating_count,
               ARRAY_AGG(rating)        AS rating_values,
               ARRAY_AGG(verified)      AS verified_values,
               ARRAY_AGG(created_at)    AS created_values
        FROM tour_ratings
        GROUP BY tour_id
    ) r ON r.tour_id = COALESCE(t.original_tour_id, t.id)
"""

# Fallback aggregate for a schema that has tour_ratings but NOT the LOCAL-672
# verified column: emit NULL literals for the two new arrays so the tuple shape
# is identical and no endpoint needs a second code path.
_RATINGS_AGG_SUBQUERY_NO_VERIFIED = """
    LEFT JOIN (
        SELECT tour_id,
               COUNT(*)              AS rating_count,
               ARRAY_AGG(rating)     AS rating_values,
               NULL::boolean[]       AS verified_values,
               ARRAY_AGG(created_at) AS created_values
        FROM tour_ratings
        GROUP BY tour_id
    ) r ON r.tour_id = COALESCE(t.original_tour_id, t.id)
"""

_HAS_TOUR_RATINGS = None
_HAS_VERIFIED_COLUMN = None
_HAS_IS_PAID_COLUMN = None


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


def _has_verified_column(cur):
    """True if tour_ratings.verified exists (LOCAL-672). Probed once + cached.
    When absent, verified counting degrades to the LOCAL-670 all-ratings rule."""
    global _HAS_VERIFIED_COLUMN
    if _HAS_VERIFIED_COLUMN is None:
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'tour_ratings' AND column_name = 'verified'
            """)
            _HAS_VERIFIED_COLUMN = cur.fetchone() is not None
        except Exception:
            _HAS_VERIFIED_COLUMN = False
    return _HAS_VERIFIED_COLUMN


def _has_is_paid_column(cur):
    """True if audio_tours.is_paid exists. Probed once + cached. Absent → every
    tour is treated as FREE (no per-tour price mapping yet, D624 pending)."""
    global _HAS_IS_PAID_COLUMN
    if _HAS_IS_PAID_COLUMN is None:
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'is_paid'
            """)
            _HAS_IS_PAID_COLUMN = cur.fetchone() is not None
        except Exception:
            _HAS_IS_PAID_COLUMN = False
    return _HAS_IS_PAID_COLUMN


def _search_like_pattern(pattern):
    """[LOCAL-680] Turn the listener's search text into an ILIKE pattern.

    No '*'  → substring match, as before: "Boston" finds any name containing Boston.
    With '*' → the stars are the ONLY wildcards and the text is anchored:
        "Boston*"   starts with Boston
        "*Boston"   ends with Boston
        "*Boston*"  contains Boston
    Michael, 2026-10-14: "Boston*" returned every tour mentioning Boston because
    the old code always wrapped the text in %...%.

    The app sends '*' as the regex '.*'; both spellings are accepted. Literal
    '%', '_' and '\\' are escaped so they never act as SQL wildcards.
    """
    p = (pattern or '').strip().replace('.*', '*')
    p = p.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    if '*' not in p:
        return f'%{p}%'
    return p.replace('*', '%')


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


def _wants_top_rated(args):
    """True when the caller asked for the 'Top rated' order (item 4/11). Accepts
    ?sort=top_rated (and the convenience alias ?sort=rating)."""
    s = (args.get('sort') or '').strip().lower()
    return s in ('top_rated', 'top-rated', 'rating', 'top')


def _ratings_select(cur):
    """SQL fragment selecting the rating aggregates, or NULL literals on an older
    schema. Always four columns in a fixed order:
        rating_count, rating_values, verified_values, created_values
    so every endpoint unpacks the same shape regardless of schema age. The
    verified array is real only when the LOCAL-672 column exists; otherwise it is
    NULL (→ treated as all-unverified, i.e. the LOCAL-670 counting rule)."""
    if _has_tour_ratings_table(cur):
        return "r.rating_count, r.rating_values, r.verified_values, r.created_values"
    return ("NULL::bigint AS rating_count, NULL::smallint[] AS rating_values, "
            "NULL::boolean[] AS verified_values, NULL::timestamp[] AS created_values")


def _ratings_join(cur):
    """The grouped LEFT JOIN over tour_ratings, or empty string on older schema.
    Picks the verified-aware aggregate when the column exists (LOCAL-672), else
    the fallback that NULLs the verified array so the SELECT shape is identical."""
    if not _has_tour_ratings_table(cur):
        return ""
    if _has_verified_column(cur):
        return _RATINGS_AGG_SUBQUERY
    return _RATINGS_AGG_SUBQUERY_NO_VERIFIED


def _is_paid_select(cur):
    """SQL fragment selecting the tour's paid flag. Uses audio_tours.is_paid when
    that column exists (per-tour price mapping, D624/LOCAL-677), else a FALSE
    literal — every tour reads as FREE on a schema that predates it.

    [LOCAL-677] A translation inherits its SOURCE tour's paid flag: the endpoints
    LEFT JOIN the original row as `orig`, so COALESCE(orig.is_paid, t.is_paid)
    makes a translation of a paid tour read as paid (its own price_tier is always
    NULL — only originals are priced). Falls back to the own flag for an original
    (orig is NULL there)."""
    if _has_is_paid_column(cur):
        return "COALESCE(orig.is_paid, t.is_paid, FALSE)"
    return "FALSE"


# ─── [LOCAL-677] Price tier + Free/Paid filter ───────────────────────────────
#
# A paid tour carries a price_tier (1..5); the tier maps to a dollar label the
# home list shows next to the ★ rating. map-delivery deploys as its own image
# and cannot import the repo-root price_tiers module, so the tier→label map is a
# self-contained copy of the D652 defaults (migration 022 seeds the same rows).
# The price_tiers TABLE is authoritative when present (Michael's SQL edits take
# effect); the constants are the fallback for a DB that predates it. Keep these
# entries in lock-step with migrations 022/024/026 (7 legacy .99 tiers + the 34
# round-dollar ladder tiers 8..41, LOCAL-686).
_DEFAULT_TIER_LABELS = {1: "$1.99", 2: "$2.99", 3: "$4.99", 4: "$7.99", 5: "$9.99",
                        6: "$19.99", 7: "$49.99",  # [LOCAL-684] legacy .99 tiers 1-7, migrations 022/024
                        # [LOCAL-686] the round-dollar ladder, tiers 8..41 (migration 026)
                        8: "$2", 9: "$3", 10: "$4", 11: "$5", 12: "$6", 13: "$7",
                        14: "$8", 15: "$9", 16: "$10", 17: "$11", 18: "$12", 19: "$13",
                        20: "$14", 21: "$15", 22: "$16", 23: "$17", 24: "$18", 25: "$19",
                        26: "$20", 27: "$25", 28: "$30", 29: "$35", 30: "$40", 31: "$45",
                        32: "$50", 33: "$60", 34: "$70", 35: "$80", 36: "$90", 37: "$100",
                        38: "$125", 39: "$150", 40: "$175", 41: "$200"}
_TIER_LABELS = None  # cached per process after the first DB read

_HAS_PRICE_TIER_COLUMN = None
_HAS_PRICE_TIERS_TABLE = None


def _has_price_tier_column(cur):
    """True if audio_tours.price_tier exists. Probed once + cached. Absent (pre-
    022) → every tour reads as FREE (price_tier NULL), unchanged from before."""
    global _HAS_PRICE_TIER_COLUMN
    if _HAS_PRICE_TIER_COLUMN is None:
        try:
            cur.execute("""
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'audio_tours' AND column_name = 'price_tier'
            """)
            _HAS_PRICE_TIER_COLUMN = cur.fetchone() is not None
        except Exception:
            _HAS_PRICE_TIER_COLUMN = False
    return _HAS_PRICE_TIER_COLUMN


def _price_tier_select(cur):
    """SQL fragment selecting the tour's price_tier, or NULL on an older schema.

    A translation inherits its SOURCE tour's price: the endpoints already LEFT
    JOIN the original row as `orig` (ON orig.id = t.original_tour_id) for the
    original-language field, so COALESCE(orig.price_tier, t.price_tier) gives the
    translation its source's tier and an original its own — no extra join."""
    if _has_price_tier_column(cur):
        return "COALESCE(orig.price_tier, t.price_tier)"
    return "NULL::smallint"


def _tier_labels(cur):
    """{tier: label} from the price_tiers table when present, else the D652
    defaults. Cached per process (prices change rarely; a restart re-reads). A
    None cursor returns the cache if warmed, else the defaults — so a single-tour
    endpoint that already closed its cursor still renders a correct label."""
    global _TIER_LABELS
    if _TIER_LABELS is not None:
        return _TIER_LABELS
    if cur is None:
        return dict(_DEFAULT_TIER_LABELS)
    labels = dict(_DEFAULT_TIER_LABELS)
    try:
        cur.execute("""
            SELECT 1 FROM information_schema.tables WHERE table_name = 'price_tiers'
        """)
        if cur.fetchone() is not None:
            cur.execute("SELECT tier, label FROM price_tiers WHERE COALESCE(active, TRUE) = TRUE")
            rows = cur.fetchall()
            if rows:
                labels = {int(t): (lbl or _DEFAULT_TIER_LABELS.get(int(t), ""))
                          for t, lbl in rows}
    except Exception:
        pass
    _TIER_LABELS = labels
    return _TIER_LABELS


def _price_label_for(tier, cur):
    """'$4.99' for a priced tier, 'Free' for a NULL/unknown tier."""
    if tier is None:
        return "Free"
    try:
        return _tier_labels(cur).get(int(tier), "Free")
    except (TypeError, ValueError):
        return "Free"


def _price_block(price_tier, cur=None):
    """The price fields appended to every tour payload: price_tier (int|None)
    and price_label ('$4.99' | 'Free'). is_paid already comes from the rating
    block; this adds the tier + its human label the home list shows. `cur` is
    optional (a closed-cursor single-tour endpoint passes None → cached/default
    labels)."""
    tier = int(price_tier) if price_tier is not None else None
    return {"price_tier": tier, "price_label": _price_label_for(tier, cur)}


def _parse_price_filter(args):
    """Parse the optional ?price=free|paid query param. Returns 'free', 'paid',
    or None (absent/blank/invalid → no filter)."""
    raw = (args.get('price') or '').strip().lower()
    if raw in ('free', 'paid'):
        return raw
    return None


def _passes_price_filter(price_filter, is_paid):
    """True if a tour with the given is_paid flag passes the price filter.
    None filter → everything passes (Any)."""
    if price_filter is None:
        return True
    if price_filter == 'free':
        return not is_paid
    return bool(is_paid)  # 'paid'


# ─── [LOCAL-677C / D654] Pay-before-download enforcement ─────────────────────
#
# D654 moves the paywall BEFORE the download. /download-tour/<id> returns
# HTTP 402 purchase_required for a PAID language row the caller has not unlocked,
# with the two carve-outs the ticket requires unchanged:
#   * FREE rows (price_tier NULL) download as before;
#   * the CURATOR's OWN tour (its creator) downloads their own tour unpriced;
#   * GRANDFATHERING: a user who downloaded this row while it was free keeps
#     access (tour_downloads.was_free = TRUE for this user+row).
#
# map_delivery deploys as its own image and cannot import the repo-root pricing
# module, so these are self-contained DB reads against the SAME postgres-2 DB —
# the same pattern _is_paid_select / _price_tier_select already use. Every read
# fails OPEN only for the FREE path and fails CLOSED (treats as not-unlocked)
# only after we have positively established the row is paid: a lookup error on
# the unlock/grandfather side never turns a free tour into a 402, and never
# silently unlocks a paid one.

_HAS_TOUR_UNLOCKS_TABLE = None
_HAS_TOUR_DOWNLOADS_TABLE = None
# [LOCAL-693 / D660] Cache for the per-download consumption columns on
# tour_unlocks (consumed_at, consumed_by_download_id + partial active index).
_HAS_UNLOCK_CONSUMPTION_COLS = False


def _table_exists(cur, table_name):
    """True if a table with this name exists in the current database."""
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = %s",
            (table_name,),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def _resolve_original_id(cur, tour_id):
    """The ORIGINAL audio_tours.id for a (possibly translation) row.

    A translation carries original_tour_id; an original has it NULL and is its
    own original. Mirrors tour_rating_service.resolve_original_id so pricing,
    reviews and this gate all agree on which row carries the price. Never raises
    — returns the given id on any error."""
    try:
        cur.execute(
            "SELECT original_tour_id FROM audio_tours WHERE id = %s", (int(tour_id),)
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:  # noqa: BLE001
        pass
    return int(tour_id)


def _row_price_tier(cur, tour_id):
    """The price_tier that governs this language row, resolving a translation to
    its SOURCE (a translation inherits its original's price). None = free. None
    on any error or on a schema that predates price_tier (fail to FREE)."""
    if not _has_price_tier_column(cur):
        return None
    try:
        original_id = _resolve_original_id(cur, tour_id)
        cur.execute("SELECT price_tier FROM audio_tours WHERE id = %s", (original_id,))
        row = cur.fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except Exception:  # noqa: BLE001
        return None
    return None


def _ensure_unlock_consumption_columns(cur):
    """[LOCAL-693 / D660] Self-healing DDL for the consumption columns on
    tour_unlocks (mirrors migration 031), so the per-download gate works whether
    or not the migration file has run on this DB. Adds consumed_at and
    consumed_by_download_id (both NULL = unconsumed), and the partial unique
    index that lets a user re-buy after consuming while still rejecting a second
    ACTIVE unlock. Idempotent (ADD COLUMN / CREATE INDEX IF NOT EXISTS). Caches
    success so we touch the schema at most once per process. Does NOT commit (the
    caller owns the transaction). Returns True if the columns are present."""
    global _HAS_UNLOCK_CONSUMPTION_COLS
    if _HAS_UNLOCK_CONSUMPTION_COLS:
        return True
    try:
        cur.execute(
            "ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ"
        )
        cur.execute(
            "ALTER TABLE tour_unlocks "
            "ADD COLUMN IF NOT EXISTS consumed_by_download_id VARCHAR(255)"
        )
        # [LOCAL-693B / D660] restored_at: a consumed unlock that was restored
        # ONCE by a download-failed report (mirrors migration 032).
        cur.execute(
            "ALTER TABLE tour_unlocks "
            "ADD COLUMN IF NOT EXISTS restored_at TIMESTAMPTZ"
        )
        # Relax the old full UNIQUE so a re-buy after consumption is possible,
        # then enforce "at most one ACTIVE unlock" with a partial unique index.
        cur.execute(
            "DO $$ BEGIN "
            "IF EXISTS (SELECT 1 FROM pg_constraint "
            "WHERE conname = 'uq_tour_unlocks_user_tour' "
            "AND conrelid = 'tour_unlocks'::regclass) THEN "
            "ALTER TABLE tour_unlocks DROP CONSTRAINT uq_tour_unlocks_user_tour; "
            "END IF; END $$;"
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_tour_unlocks_active "
            "ON tour_unlocks (user_id, tour_id) WHERE consumed_at IS NULL"
        )
        _HAS_UNLOCK_CONSUMPTION_COLS = True
        return True
    except Exception:  # noqa: BLE001 — must never fail a download/gate
        return False


def _user_has_unlock(cur, user_id, tour_id):
    """[LOCAL-693 / D660] True if this user holds an UNCONSUMED tour_unlocks row
    for THIS language row's own id (per-language unlock, 677B/D653). D660: a
    purchase grants ONE download, so only an unlock whose consumed_at IS NULL
    counts — once a download has spent it, the row stays (it keeps the buyer
    Verified, D647) but no longer authorises a download, and a 402 asks the
    listener to buy again. Absent table (pre-022) → not unlocked. A schema that
    predates the consumed_at column (pre-031 and self-heal failed) falls back to
    the presence check so a paid tour is never wrongly refused on an old DB."""
    global _HAS_TOUR_UNLOCKS_TABLE
    if not user_id:
        return False
    if _HAS_TOUR_UNLOCKS_TABLE is None:
        _HAS_TOUR_UNLOCKS_TABLE = _table_exists(cur, 'tour_unlocks')
    if not _HAS_TOUR_UNLOCKS_TABLE:
        return False
    has_cols = _ensure_unlock_consumption_columns(cur)
    try:
        if has_cols:
            cur.execute(
                "SELECT 1 FROM tour_unlocks "
                "WHERE user_id = %s AND tour_id = %s AND consumed_at IS NULL LIMIT 1",
                (user_id, int(tour_id)),
            )
        else:
            # Pre-031 DB without the column — behave as before 693 (presence).
            cur.execute(
                "SELECT 1 FROM tour_unlocks WHERE user_id = %s AND tour_id = %s LIMIT 1",
                (user_id, int(tour_id)),
            )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def _consume_unlock(cur, user_id, tour_id, download_id):
    """[LOCAL-693 / D660 + LOCAL-693B LEAD] Spend ONE unconsumed unlock for
    (user, language row): stamp the OLDEST unconsumed row's consumed_at = NOW()
    and record the download id that spent it.

    LEAD review (693B): this is now called by the SERVER itself, from the
    download streaming generator AFTER the LAST byte of the zip has been yielded
    — server-side truth. A cut-off stream closes the generator before that point
    (GeneratorExit), so a failed/partial download never reaches here and the
    unlock stays unconsumed (D660: "a download that FAILS does not consume the
    purchase"). The app no longer confirms success; it only reports FAILURE (see
    _restore_unlock / POST /tour/<id>/download-failed).

    Returns (consumed: bool, remaining_unconsumed: int). consumed is False when
    the user had no unconsumed unlock (e.g. a free/grandfathered/curator download,
    or a double-consume) — a harmless no-op. Marks exactly ONE row even if the
    user somehow holds several. Never raises."""
    global _HAS_TOUR_UNLOCKS_TABLE
    if not user_id:
        return False, 0
    if _HAS_TOUR_UNLOCKS_TABLE is None:
        _HAS_TOUR_UNLOCKS_TABLE = _table_exists(cur, 'tour_unlocks')
    if not _HAS_TOUR_UNLOCKS_TABLE:
        return False, 0
    if not _ensure_unlock_consumption_columns(cur):
        return False, 0
    try:
        cur.execute(
            """
            UPDATE tour_unlocks
            SET consumed_at = NOW(),
                consumed_by_download_id = %s
            WHERE id = (
                SELECT id FROM tour_unlocks
                WHERE user_id = %s AND tour_id = %s AND consumed_at IS NULL
                ORDER BY created_at ASC, id ASC
                LIMIT 1
            )
            RETURNING id
            """,
            (str(download_id) if download_id is not None else None,
             user_id, int(tour_id)),
        )
        consumed = cur.fetchone() is not None
        cur.execute(
            "SELECT COUNT(*) FROM tour_unlocks "
            "WHERE user_id = %s AND tour_id = %s AND consumed_at IS NULL",
            (user_id, int(tour_id)),
        )
        row = cur.fetchone()
        remaining = int(row[0]) if row and row[0] is not None else 0
        return consumed, remaining
    except Exception:  # noqa: BLE001
        return False, 0


def _consume_unlock_after_stream(user_id, tour_id, download_id):
    """[LOCAL-693B / D660 LEAD] Open a short-lived connection and consume one
    unlock, called from the download streaming generator AFTER the last byte was
    yielded. The request-scoped cursor is long closed by the time the generator
    runs, so this owns its own connection/transaction. Never raises (a failure
    to stamp consumed_at must not corrupt the already-delivered download; worst
    case the listener keeps an unconsumed unlock, which errs in the listener's
    favour and is self-corrected on their next successful download)."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            consumed, remaining = _consume_unlock(cur, user_id, tour_id, download_id)
            conn.commit()
            print(f"download tour {tour_id} user {user_id}: last byte sent — "
                  f"consumed={consumed} remaining={remaining} id={download_id or '-'}")
        except Exception:  # noqa: BLE001
            conn.rollback()
        finally:
            cur.close()
            conn.close()
        sys.stdout.flush()
    except Exception as e:  # noqa: BLE001
        print(f"ERROR consuming unlock after stream for tour {tour_id}: {e}")
        sys.stdout.flush()


# How long after consumption a failed-download report can restore a purchase.
_RESTORE_WINDOW_HOURS = 24


def _restore_unlock(cur, user_id, tour_id):
    """[LOCAL-693B / D660 LEAD] Restore (un-consume) a purchase ONCE after a
    download-failed report.

    Finds the MOST-RECENTLY consumed unlock for (user, language row) that is
    still eligible: consumed within the last 24h and never restored before
    (restored_at IS NULL). Clears consumed_at / consumed_by_download_id and
    stamps restored_at = NOW(), so the listener may download once more for free.

    Returns one of:
      ('restored', remaining_unconsumed)  — a purchase was restored.
      ('conflict', reason)                — nothing eligible: already restored,
                                            past the 24h window, or no consumed
                                            unlock. The endpoint maps this to 409.
      ('noop', reason)                    — schema/table missing; endpoint 409s.
    Never raises."""
    global _HAS_TOUR_UNLOCKS_TABLE
    if not user_id:
        return 'conflict', 'no_user'
    if _HAS_TOUR_UNLOCKS_TABLE is None:
        _HAS_TOUR_UNLOCKS_TABLE = _table_exists(cur, 'tour_unlocks')
    if not _HAS_TOUR_UNLOCKS_TABLE:
        return 'noop', 'no_table'
    if not _ensure_unlock_consumption_columns(cur):
        return 'noop', 'no_columns'
    try:
        # Candidate: the latest consumed, not-yet-restored unlock for this row.
        cur.execute(
            """
            SELECT id, consumed_at,
                   consumed_at >= NOW() - INTERVAL '%s hours' AS within_window
            FROM tour_unlocks
            WHERE user_id = %s AND tour_id = %s AND consumed_at IS NOT NULL
            ORDER BY consumed_at DESC, id DESC
            LIMIT 1
            """,
            (_RESTORE_WINDOW_HOURS, user_id, int(tour_id)),
        )
        cand = cur.fetchone()
        if cand is None:
            # Either never consumed, or a previous restore already cleared the
            # most recent consumption (restored_at set but consumed_at NULL).
            # Distinguish an already-restored purchase for a precise reason.
            cur.execute(
                "SELECT 1 FROM tour_unlocks "
                "WHERE user_id = %s AND tour_id = %s AND restored_at IS NOT NULL "
                "LIMIT 1",
                (user_id, int(tour_id)),
            )
            if cur.fetchone() is not None:
                return 'conflict', 'already_restored'
            return 'conflict', 'not_consumed'
        row_id, _consumed_at, within_window = cand
        if not within_window:
            return 'conflict', 'window_expired'
        # Eligible — restore exactly this row, guarding restored_at IS NULL so a
        # concurrent second report cannot restore twice (one restore per
        # purchase).
        cur.execute(
            """
            UPDATE tour_unlocks
            SET consumed_at = NULL,
                consumed_by_download_id = NULL,
                restored_at = NOW()
            WHERE id = %s AND restored_at IS NULL AND consumed_at IS NOT NULL
            RETURNING id
            """,
            (row_id,),
        )
        if cur.fetchone() is None:
            # Lost a race — someone restored it first.
            return 'conflict', 'already_restored'
        cur.execute(
            "SELECT COUNT(*) FROM tour_unlocks "
            "WHERE user_id = %s AND tour_id = %s AND consumed_at IS NULL",
            (user_id, int(tour_id)),
        )
        cnt = cur.fetchone()
        remaining = int(cnt[0]) if cnt and cnt[0] is not None else 0
        return 'restored', remaining
    except Exception:  # noqa: BLE001
        return 'noop', 'error'


def _user_is_tour_creator(cur, user_id, tour_id):
    """True if user_id created this tour (its original). The curator downloads
    their OWN tour unpriced. Resolution mirrors
    tour_reviews_service.resolve_tour_creator: an optional explicit
    audio_tours.creator_user_id, else the earliest tour_requests.secret_id for
    the original id. Never raises → unresolved creator means NOT the creator (the
    gate then relies on the unlock/grandfather paths, never falsely free)."""
    if not user_id:
        return False
    try:
        original_id = _resolve_original_id(cur, tour_id)
        # Optional explicit creator column (forward compatible).
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'audio_tours' AND column_name = 'creator_user_id'"
        )
        if cur.fetchone() is not None:
            cur.execute(
                "SELECT creator_user_id FROM audio_tours WHERE id = %s", (original_id,)
            )
            row = cur.fetchone()
            if row and row[0]:
                return str(row[0]) == str(user_id)
        # Earliest requester of the tour.
        cur.execute(
            """
            SELECT secret_id FROM tour_requests
            WHERE tour_id = %s AND secret_id IS NOT NULL
            ORDER BY created_at ASC LIMIT 1
            """,
            (str(original_id),),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]) == str(user_id)
    except Exception:  # noqa: BLE001
        return False
    return False


def _user_grandfathered(cur, user_id, tour_id):
    """True if this user downloaded THIS language row while it was free
    (tour_downloads.was_free = TRUE for user+row). Absent table (pre-023) → not
    grandfathered. Per language, like the unlock."""
    global _HAS_TOUR_DOWNLOADS_TABLE
    if not user_id:
        return False
    if _HAS_TOUR_DOWNLOADS_TABLE is None:
        _HAS_TOUR_DOWNLOADS_TABLE = _table_exists(cur, 'tour_downloads')
    if not _HAS_TOUR_DOWNLOADS_TABLE:
        return False
    try:
        cur.execute(
            "SELECT 1 FROM tour_downloads "
            "WHERE user_id = %s AND tour_id = %s AND was_free = TRUE LIMIT 1",
            (user_id, int(tour_id)),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


def _ensure_tour_downloads(cur):
    """Self-healing DDL for the grandfathering ledger (mirrors migration 023),
    so the 402 gate records and honours free downloads whether or not the
    migration file has been run on this DB. Idempotent (CREATE TABLE IF NOT
    EXISTS). Caches success so we create at most once per process. Does NOT
    commit (the caller owns the transaction)."""
    global _HAS_TOUR_DOWNLOADS_TABLE
    if _HAS_TOUR_DOWNLOADS_TABLE:
        return True
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tour_downloads (
                id          SERIAL PRIMARY KEY,
                user_id     VARCHAR(255) NOT NULL,
                tour_id     INTEGER      NOT NULL,
                was_free    BOOLEAN      NOT NULL,
                created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_tour_downloads_user_tour UNIQUE (user_id, tour_id)
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_tour_downloads_user_tour "
            "ON tour_downloads(user_id, tour_id)"
        )
        _HAS_TOUR_DOWNLOADS_TABLE = True
        return True
    except Exception:  # noqa: BLE001 — must never fail a download
        return False


def _record_download_event(cur, user_id, tour_id, was_free):
    """Record (idempotently) that user_id downloaded this language row, noting
    whether it was free at that moment. UNIQUE(user_id, tour_id) → the FIRST
    download is the one that counts; a later re-download never flips a free
    grandfather row to paid and never adds a second row. Self-heals the table if
    absent (pre-023). Does NOT commit (the caller owns the transaction)."""
    if not user_id:
        return
    if not _ensure_tour_downloads(cur):
        return
    try:
        cur.execute(
            "INSERT INTO tour_downloads (user_id, tour_id, was_free) "
            "VALUES (%s, %s, %s) ON CONFLICT (user_id, tour_id) DO NOTHING",
            (user_id, int(tour_id), bool(was_free)),
        )
    except Exception:  # noqa: BLE001 — a ledger write must never fail the download
        pass


# ─── [LOCAL-701 / D663 §3] Community tours ────────────────────────────────────
#
# A tour generated FOR a community carries two columns on audio_tours (migration
# 035): community_id and community_visibility ('members' | 'public'). map_delivery
# deploys as its own image and cannot import community_tours_service, so these are
# self-contained DB reads against the SAME postgres-2 DB — the same pattern the
# paid-gate helpers use. The listing + download rules (D663 §3):
#   * members-only community tour  → NEVER on /tours-near, /search, /tour-by-code
#                                    or /tour-info (community page only). Download
#                                    only by an active member.
#   * public community tour        → shown on the map/search WITH the community
#                                    badge; download requires an active membership
#                                    (non-member → 402 membership_required).
#   * members download free of extra charge (the pass is the payment); D660
#     per-download rules do NOT apply to community tours.
_HAS_COMMUNITY_COLUMNS = None


def _has_community_columns(cur):
    """True if audio_tours.community_id + community_visibility exist (migration
    035). Probed once + cached. Absent (older schema) → every tour is an
    ordinary public tour and the community rules are inert (feature OFF, never a
    500)."""
    global _HAS_COMMUNITY_COLUMNS
    if _HAS_COMMUNITY_COLUMNS is None:
        try:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name = 'audio_tours' "
                "AND column_name IN ('community_id', 'community_visibility')"
            )
            _HAS_COMMUNITY_COLUMNS = (cur.fetchone()[0] == 2)
        except Exception:  # noqa: BLE001
            _HAS_COMMUNITY_COLUMNS = False
    return _HAS_COMMUNITY_COLUMNS


def _community_tag(cur, tour_id):
    """(community_id, visibility) for a tour, resolving a translation to its
    original, or (None, None) for an ordinary tour / older schema. Never
    raises."""
    if not _has_community_columns(cur):
        return None, None
    try:
        cur.execute(
            "SELECT COALESCE(orig.community_id, t.community_id), "
            "       COALESCE(orig.community_visibility, t.community_visibility) "
            "FROM audio_tours t "
            "LEFT JOIN audio_tours orig ON orig.id = t.original_tour_id "
            "WHERE t.id = %s",
            (int(tour_id),),
        )
        row = cur.fetchone()
    except Exception:  # noqa: BLE001
        return None, None
    if row and row[0] is not None:
        return int(row[0]), row[1]
    return None, None


def _community_tags_batch(cur, tour_ids):
    """{tour_id: (community_id, visibility)} for many tour ids in ONE query (no
    N+1), for the list endpoints. Only rows that ARE community tours appear;
    everything else is simply absent (the caller treats absence as ordinary).
    Empty on an older schema / error."""
    ids = sorted({int(i) for i in tour_ids if i is not None})
    if not ids or not _has_community_columns(cur):
        return {}
    try:
        cur.execute(
            "SELECT id, community_id, community_visibility FROM audio_tours "
            "WHERE id = ANY(%s) AND community_id IS NOT NULL",
            (ids,),
        )
        return {int(r[0]): (int(r[1]), r[2]) for r in cur.fetchall()}
    except Exception:  # noqa: BLE001
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return {}


def _community_name(cur, community_id):
    """The community's name (for the badge label), or None. Never raises."""
    if community_id is None:
        return None
    try:
        cur.execute("SELECT name FROM communities WHERE id = %s", (int(community_id),))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception:  # noqa: BLE001
        return None


def _is_active_member(cur, user_id, community_id, now=None):
    """True iff user_id is an ACTIVE member of the community, or its OWNER.

    An active member has a membership row with NULL expiry (free community) or a
    future expiry; the owner always qualifies (they made the tour). Mirrors
    communities_api.is_membership_active. Never raises → False (fail closed: a
    lookup problem must not hand out community content)."""
    if not user_id or community_id is None:
        return False
    from datetime import datetime
    now = now or datetime.utcnow()
    try:
        cur.execute("SELECT owner_user_id FROM communities WHERE id = %s",
                    (int(community_id),))
        row = cur.fetchone()
        if row and row[0] is not None and str(row[0]) == str(user_id):
            return True  # the owner
        cur.execute(
            "SELECT expires_at FROM community_memberships "
            "WHERE user_id = %s AND community_id = %s",
            (str(user_id), int(community_id)),
        )
        m = cur.fetchone()
        if m is None:
            return False
        return m[0] is None or m[0] > now
    except Exception:  # noqa: BLE001
        return False


def _community_download_decision(cur, user_id, tour_id):
    """The community part of the download gate for ONE tour.

    Returns (relevant, allowed, deny):
      * relevant=False → not a community tour; the caller runs the ordinary
        paid/free gate unchanged.
      * relevant=True, allowed=True → an active member (or the owner) — allowed,
        and D660 per-download rules do NOT apply (the pass is the payment).
      * relevant=True, allowed=False → a non-member/expired member: `deny` is the
        402 body {error:'membership_required', community_id, tour_id}; the app
        opens the community page (join / buy pass)."""
    community_id, _vis = _community_tag(cur, tour_id)
    if community_id is None:
        return False, True, None
    if _is_active_member(cur, user_id, community_id):
        return True, True, None
    return True, False, {
        "error": "membership_required",
        "community_id": int(community_id),
        "tour_id": int(tour_id),
    }


def _download_gate(cur, user_id, tour_id):
    """The pay-before-download decision for ONE language row.

    Returns (allowed: bool, info: dict). When allowed is False, `info` is the
    402 body: {error: 'purchase_required', tour_id, price_tier, price}.

    Order (the first that applies wins):
      1. FREE row (price_tier NULL)            → allowed.
      2. The tour's CREATOR (curator's own)    → allowed.
      3. [LOCAL-695] The device was MOVED AWAY  → 402 profile_moved for a paid
         by a recovery-code restore            row it is not grandfathered on.
                                                 The profile (and its restore
                                                 grants) now live on another
                                                 phone; this phone is no longer
                                                 offered re-downloads. Tours
                                                 already on it keep playing
                                                 (local/offline, D654).
      4. The user has an UNCONSUMED UNLOCK     → allowed (D660: one download per
                                                 purchase; a consumed unlock no
                                                 longer authorises a download).
      5. The user is GRANDFATHERED (free dl)   → allowed (LOCAL-677C, unchanged).
      6. otherwise                             → 402 purchase_required (also the
                                                 already-consumed-and-not-rebought
                                                 case: buy again to download again).
    """
    # [LOCAL-701 / D663 §3] A COMMUNITY tour is gated by MEMBERSHIP, not price.
    # Decide this FIRST: a community tour never follows the paid/unlock path —
    # an active member (or the owner) downloads it (members download free of
    # extra charge; D660 per-download rules do NOT apply), and a non-member gets
    # 402 membership_required so the app opens the community page.
    _ct_relevant, _ct_allowed, _ct_deny = _community_download_decision(
        cur, user_id, tour_id)
    if _ct_relevant:
        if _ct_allowed:
            return True, None
        return False, _ct_deny

    tier = _row_price_tier(cur, tour_id)
    if tier is None:
        return True, None  # free row — unchanged behaviour
    if _user_is_tour_creator(cur, user_id, tour_id):
        return True, None  # the curator downloads their own tour
    # [LOCAL-695] Abuse guard: a device unlinked by a later restore (the profile
    # moved to a new phone) is not offered re-downloads of paid rows. A
    # grandfathered (downloaded-while-free) row still downloads — that is the
    # phone's own history, not the moved profile's grant.
    if _device_moved_away(cur, user_id) and not _user_grandfathered(cur, user_id, tour_id):
        return False, {
            "error": "profile_moved",
            "message": "This profile was restored on another device. Tours already "
                       "on this phone keep playing.",
            "tour_id": int(tour_id),
        }
    if _user_has_unlock(cur, user_id, tour_id):
        return True, None  # bought this language
    if _user_grandfathered(cur, user_id, tour_id):
        return True, None  # downloaded while free — keeps access
    price = _price_label_for(tier, cur)
    # The 402 body: the app shows the Buy button again from this.
    return False, {
        "error": "purchase_required",
        "tour_id": int(tour_id),
        "price_tier": int(tier),
        "price": (price[1:] if isinstance(price, str) and price.startswith("$") else price),
    }


# [LOCAL-695] Cache for presence of the device_consolidation_history table +
# unlinked_at column (migration 033). Resolved once per process.
_HAS_CONSOLIDATION_HISTORY = None


def _device_moved_away(cur, user_id):
    """[LOCAL-695] True if this device was UNLINKED from its profile by a later
    recovery-code restore (the profile moved to another phone). Self-contained
    DB read (map_delivery is its own image and cannot import the repo-root
    recovery module), mirroring recovery_code_service.profile_was_moved:

      * the device is NOT a current primary_device_id of any profile, AND
      * its MOST-RECENT device_consolidation_history row has unlinked_at set.

    Absent table/column (pre-033) → False (feature off; never refuses a normal
    download). Never raises — any error fails OPEN to 'not moved' so a lookup
    problem can never wrongly refuse a paid download the gate would otherwise
    allow via the unlock/grandfather paths below."""
    global _HAS_CONSOLIDATION_HISTORY
    if not user_id:
        return False
    if _HAS_CONSOLIDATION_HISTORY is None:
        try:
            _HAS_CONSOLIDATION_HISTORY = (
                _table_exists(cur, 'device_consolidation_history')
                and _column_exists(cur, 'device_consolidation_history', 'unlinked_at')
            )
        except Exception:  # noqa: BLE001
            _HAS_CONSOLIDATION_HISTORY = False
    if not _HAS_CONSOLIDATION_HISTORY:
        return False
    try:
        cur.execute(
            "SELECT 1 FROM user_consolidation_map WHERE primary_device_id = %s LIMIT 1",
            (user_id,),
        )
        if cur.fetchone() is not None:
            return False  # still a primary device somewhere → not moved
        cur.execute(
            "SELECT unlinked_at FROM device_consolidation_history "
            "WHERE merged_device_id = %s ORDER BY merged_at DESC, id DESC LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False
        return row[0] is not None
    except Exception:  # noqa: BLE001
        return False


def _column_exists(cur, table_name, column_name):
    """True if a column exists on a table in the current database."""
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = %s AND column_name = %s",
            (table_name, column_name),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


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
        # [LOCAL-677] Optional Free/Paid filter (home page: Free/Paid/Any).
        price_filter = _parse_price_filter(request.args)

        cur.execute(f"""
            SELECT t.id, t.tour_name, t.request_string, t.lat, t.lng,
                   t.number_requested, t.content_language, t.original_tour_id,
                   v.max_version_no, v.last_replaced_at, t.created_at,
                   {_source_version_select(cur)} AS source_version,
                   sv.max_version_no AS source_max_version_no,
                   {_ratings_select(cur)},
                   {_is_paid_select(cur)} AS is_paid,
                   {_price_tier_select(cur)} AS price_tier,
                   {_short_title_select(cur)} AS short_title,
                   {_ORIGINAL_LANGUAGE_SELECT},
                   {_content_rating_select(cur)}
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
            {_ORIGINAL_LANGUAGE_JOIN}
            WHERE t.lat IS NOT NULL AND t.lng IS NOT NULL
            AND (t.content_language = 'en' OR t.content_language IS NULL)
            AND t.original_tour_id IS NULL
            AND (t.is_test IS NOT TRUE)
        """)
        
        tours = cur.fetchall()
        editor = _editor_scores(cur)  # [LOCAL-685]
        # [LOCAL-701 / D663 §3] Batch the community tags for every fetched tour
        # (one query, no N+1). A members-only community tour is HIDDEN from the
        # map; a public one is shown WITH a community badge.
        _ct_tags = _community_tags_batch(cur, [t[0] for t in tours])
        _ct_names = {}
        tours_list = []
        adult = _adult_requested(request.args)  # [LOCAL-687] 18+ confirmed?
        
        for tour in tours:
            (tour_id, tour_name, request_string, tour_lat, tour_lng, requests,
             language, original_id, max_vn, last_replaced, created_at,
             source_version, source_max_vn, rating_count, rating_values,
             verified_values, created_values, is_paid, price_tier, short_title,
             own_content_language, source_content_language,
             content_rating, content_review_status) = _row_with_rating(tour, 22)
            
            # [LOCAL-687] Content gate: hide not_allowed, hide pending/rejected,
            # hide mature unless adult=1. NULL rating == general (old tours list).
            if not _content_visible(content_rating, content_review_status, adult):
                continue

            # [LOCAL-701 / D663 §3] Community-tour visibility. A members-only
            # community tour never appears on the map (community page only); a
            # public one is shown and will carry a community badge below.
            _ct_cid, _ct_vis = _ct_tags.get(tour_id, (None, None))
            if _ct_cid is not None and _ct_vis != 'public':
                continue
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    version, updated_at = _resolved_version_fields(
                        original_id, source_version, source_max_vn,
                        max_vn, last_replaced, created_at)
                    rating_block = _rating_payload(
                        rating_values, verified_values, created_values, is_paid,
                        prior=_prior_for(editor, tour_id, original_id))
                    # Server-side min_rating filter: skip tours below the bar.
                    if min_rating is not None and rating_block['rating_score'] < min_rating:
                        continue
                    # [LOCAL-677] Free/Paid filter: skip tours that don't match.
                    if not _passes_price_filter(price_filter, rating_block['is_paid']):
                        continue
                    original_language = _resolved_original_language(
                        own_content_language, original_id, source_content_language)
                    tour_data = {
                        'id': tour_id,
                        'name': tour_name,
                        # [LOCAL-711 / D673] Server short title (NULL until set).
                        'short_title': short_title,
                        'request_string': request_string,
                        'lat': tour_lat,
                        'lng': tour_lng,
                        'distance_km': round(distance, 2),
                        'popularity': requests,
                        'type': 'walking_tour',
                        'language': language or 'en',
                        'original_tour_id': original_id,
                        'original_language': original_language,
                        'version': version,
                        'updated_at': updated_at,
                        'content_rating': _content_rating_field(content_rating),
                        **rating_block,
                        **_price_block(price_tier, cur),
                    }
                    # [LOCAL-701 / D663 §3] A PUBLIC community tour carries the
                    # community badge (like the gold $ for paid). members-only
                    # tours were already skipped above, so only public reach here.
                    if _ct_cid is not None:
                        if _ct_cid not in _ct_names:
                            _ct_names[_ct_cid] = _community_name(cur, _ct_cid)
                        tour_data['community_id'] = _ct_cid
                        tour_data['community_name'] = _ct_names[_ct_cid]
                        tour_data['community_visibility'] = _ct_vis
                        tour_data['badge'] = 'community'
                    tours_list.append(tour_data)
        
        # [LOCAL-689] Add a personal match_percent + reasons to every item when
        # ?user_id is passed (one prefs query + one batched stop_metrics
        # aggregate — never one query per tour). editor is the {id: editor_score}
        # map already fetched above, reused as the match's quality input.
        _attach_match(cur, request.args.get('user_id'), tours_list, editor)

        # [LOCAL-672] "Top rated" sort (?sort=top_rated): order by the Bayesian
        # rank_score (verified 1.0 / unverified 0.5, 12-month & pre-version decay,
        # C=3 prior) descending, breaking ties by distance so near tours win among
        # equally-ranked ones. Default remains nearest-first (the original behaviour).
        # [LOCAL-689] ?sort=match: best personal match first. Tours with no match
        # (cold start / null) sort to the end, then by distance.
        sort_arg = (request.args.get('sort') or '').strip().lower()
        if sort_arg == 'match':
            tours_list.sort(key=lambda x: (
                -(x.get('match_percent') if x.get('match_percent') is not None else -1),
                x['distance_km']))
        elif _wants_top_rated(request.args):
            tours_list.sort(key=lambda x: (-x.get('rank_score', RANK_PRIOR_SCORE),
                                           x['distance_km']))
        else:
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
        
        # ─── [LOCAL-677C / D654] Pay before download ─────────────────────────
        # A PAID language row the caller has not unlocked (and is not the curator
        # of, and was not grandfathered on) is refused with HTTP 402 BEFORE the
        # zip is streamed. Free rows, the curator's own tour, an unlocked row and
        # a grandfathered (downloaded-while-free) row are unchanged.
        #
        # [LOCAL-693 / D660 + LOCAL-693B LEAD] A paid download SPENDS an unlock —
        # exactly ONE successful download per purchase, and a FAILED/cut-off
        # download must NOT spend it. LEAD review of 693: the SERVER decides
        # consumption, not the app (the app can be modified, and the gateway key
        # ships inside it). So we consume HERE, inside the streaming generator,
        # only AFTER the LAST byte of the zip has been yielded. A mid-stream
        # disconnect closes the generator early (GeneratorExit) before that
        # point, so a failed download never consumes and the listener retries
        # free. The app's job is only to REPORT failure (POST
        # /tour/<id>/download-failed) so the server can restore the purchase once.
        allowed, deny = _download_gate(cur, user_id, tour_id)
        if not allowed:
            print(f"Tour {tour_id} is paid and not unlocked for {user_id}: 402")
            sys.stdout.flush()
            cur.close()
            conn.close()
            return jsonify(deny), 402

        # Does THIS download consume an unlock? Only when the row is paid AND the
        # listener is riding an unlock (not free, not the curator's own, not
        # grandfathered). We decide it now, while the cursor is open.
        tier_now = _row_price_tier(cur, tour_id)
        is_paid_now = tier_now is not None
        consumes_unlock = bool(
            is_paid_now
            and not _user_is_tour_creator(cur, user_id, tour_id)
            and not _user_grandfathered(cur, user_id, tour_id)
            and _user_has_unlock(cur, user_id, tour_id)
        )
        # A short, unguessable id that ties this download to the consumption (and
        # to any later download-failed restore audit trail).
        download_id = uuid.uuid4().hex if consumes_unlock else ""

        # Record the download event (idempotent) so a free download now
        # grandfathers this user if the curator later prices the tour. was_free
        # is read from the row's governing tier at THIS moment.
        _record_download_event(cur, user_id, tour_id,
                               was_free=(tier_now is None))

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
        
        print(f"Sending tour file: {filename} (consumes_unlock={consumes_unlock}, "
              f"download_id={download_id or '-'})")
        sys.stdout.flush()
        
        # Use streaming response for large files
        from flask import Response

        # Capture the values the generator needs; the request-scoped cursor is
        # already closed, so consumption opens its OWN short-lived connection.
        _consume_after_stream = consumes_unlock
        _consume_user_id = user_id
        _consume_tour_id = tour_id
        _consume_download_id = download_id
        total_len = len(audio_tour_data)

        def generate():
            # Stream the file in chunks. [LOCAL-693B] We consume the unlock
            # server-side ONLY after the final byte is yielded — the generator
            # reaching its normal end IS the server's proof the whole zip left
            # the server. A client disconnect raises GeneratorExit mid-loop
            # (caught below) so a cut-off download never consumes (D660).
            chunk_size = 8192  # 8KB chunks
            data = BytesIO(audio_tour_data)
            sent = 0
            try:
                while True:
                    chunk = data.read(chunk_size)
                    if not chunk:
                        break
                    sent += len(chunk)
                    yield chunk
            except GeneratorExit:
                # Client went away before the last byte — do NOT consume.
                print(f"download tour {_consume_tour_id} user {_consume_user_id}: "
                      f"stream cut off at {sent}/{total_len} bytes — NOT consuming")
                sys.stdout.flush()
                raise
            # Reached here => every byte was yielded. Now spend the unlock.
            if _consume_after_stream and sent >= total_len:
                _consume_unlock_after_stream(
                    _consume_user_id, _consume_tour_id, _consume_download_id)

        resp_headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Length': str(total_len),
            'Content-Type': 'application/zip',
        }
        # [LOCAL-693B / D660] Tell the app whether this download consumed a
        # purchase, and with which id, so it can report a save/validate FAILURE
        # via POST /tour/<id>/download-failed (which restores the purchase once).
        # Empty header (free / creator / grandfathered / unpaid) → nothing to
        # restore even if the save fails. Exposed via Access-Control-Expose-
        # Headers so a browser client can read it under CORS.
        resp_headers['X-Download-Id'] = download_id
        resp_headers['X-Download-Consumes-Unlock'] = '1' if consumes_unlock else '0'
        resp_headers['Access-Control-Expose-Headers'] = (
            'X-Download-Id, X-Download-Consumes-Unlock'
        )
        return Response(
            generate(),
            mimetype='application/zip',
            headers=resp_headers,
        )
        
    except Exception as e:
        print(f"ERROR in download_tour: {e}")
        sys.stdout.flush()
        return jsonify({'error': str(e)}), 500


@app.route('/tour/<int:tour_id>/download-failed', methods=['POST', 'OPTIONS'])
def download_failed(tour_id):
    """[LOCAL-693B / D660 LEAD] Report a FAILED paid download and RESTORE the
    purchase once.

    LEAD review of 693: the server, not the app, decides consumption — a paid
    download is spent server-side when the streaming generator yields the last
    byte of the zip (see download_tour). The app therefore no longer confirms
    success; it reports FAILURE here when it received the bytes but could not
    save or validate the zip (truncated file, bad checksum, no disk space, …).

    The server restores that purchase EXACTLY ONCE, and only within 24h of
    consumption: it clears consumed_at and stamps restored_at so the listener can
    download once more for free. A second failed-report for the same purchase
    (restored_at already set), or one past the 24h window, or when nothing was
    consumed, returns 409 — so a modified app cannot loop failed-download to
    download forever.

    Body (JSON): {"user_id": "...", "reason": "<free text>"}.

    Returns 200 {restored:true, remaining_unconsumed, tour_id} on a restore, or
    409 {restored:false, reason, tour_id} when no restore is allowed."""
    if request.method == 'OPTIONS':
        return ('', 204)
    data = request.get_json(silent=True) or {}
    user_id = data.get('user_id') or request.args.get('user_id') or 'anonymous'
    reason = (data.get('reason') or request.args.get('reason') or '').strip()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            outcome, detail = _restore_unlock(cur, user_id, tour_id)
            if outcome == 'restored':
                conn.commit()
            else:
                conn.rollback()
        except Exception:  # noqa: BLE001
            conn.rollback()
            outcome, detail = 'noop', 'error'
        finally:
            cur.close()
            conn.close()
        print(f"download-failed tour {tour_id} user {user_id}: "
              f"outcome={outcome} detail={detail} reason={reason or '-'}")
        sys.stdout.flush()
        if outcome == 'restored':
            return jsonify({
                "tour_id": int(tour_id),
                "restored": True,
                "remaining_unconsumed": int(detail),
            }), 200
        # Any non-restore (already restored, window expired, not consumed, or a
        # schema no-op) is a 409: the purchase cannot be restored again.
        return jsonify({
            "tour_id": int(tour_id),
            "restored": False,
            "reason": detail,
        }), 409
    except Exception as e:  # noqa: BLE001
        print(f"ERROR in download_failed: {e}")
        sys.stdout.flush()
        return jsonify({"tour_id": int(tour_id), "restored": False,
                        "reason": "error", "error": str(e)}), 500

@app.route('/tour/<int:tour_id>/preview-audio', methods=['GET'])
def preview_tour_audio(tour_id):
    """[LOCAL-677C / D654] Stream ONLY Stop 1's audio of a tour, for a free
    preview of a paid tour before purchase.

    The listener taps "▶ Preview Stop 1" in the download dialog; the app streams
    this endpoint and plays it (online only, nothing saved). It serves EXACTLY
    `audio_1.mp3` (Stop 1) extracted from the tour zip — no other stop's audio,
    no text, no zip, no HTML. It works with NO unlock (that is the whole point:
    the preview is what you get before you buy). A free tour previews too.

    The audio members in a tour zip are named audio_1.mp3 (Stop 1 / summary),
    audio_2.mp3, … (tour_generation / translation_service). We open the stored
    zip, read ONLY the audio_1 member, and stream its bytes. If the zip has no
    audio_1 member the tour cannot be previewed → 404 (never fall through to any
    other stop).
    """
    print(f"Preview Stop 1 audio for tour ID: {tour_id}")
    sys.stdout.flush()
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT audio_tour FROM audio_tours WHERE id = %s AND audio_tour IS NOT NULL",
            (tour_id,),
        )
        result = cur.fetchone()
        cur.close()
        conn.close()

        if not result or not result[0]:
            return jsonify({'error': 'Tour not found'}), 404

        audio_tour_data = result[0]

        # Open the zip and pull ONLY Stop 1's audio member. We accept the exact
        # name `audio_1.mp3` (what the generator/translator write); as a tolerant
        # fallback we take the lexicographically-first `audio_<n>.mp3` whose n is
        # 1 — never any other stop. Nothing but that single mp3 is read or served.
        stop1_bytes = None
        try:
            with zipfile.ZipFile(BytesIO(audio_tour_data)) as zf:
                names = zf.namelist()
                # Only ever consider the Stop-1 member. Match the basename so a
                # zip that nests files in a folder still resolves (…/audio_1.mp3).
                target = None
                for n in names:
                    base = n.rsplit('/', 1)[-1].lower()
                    if base == 'audio_1.mp3':
                        target = n
                        break
                if target is not None:
                    stop1_bytes = zf.read(target)
        except zipfile.BadZipFile:
            return jsonify({'error': 'Tour archive unreadable'}), 404

        if not stop1_bytes:
            # No Stop-1 audio in this tour → cannot preview. Do NOT serve any
            # other stop or any other member.
            return jsonify({'error': 'Preview not available'}), 404

        from flask import Response

        def generate():
            chunk_size = 8192
            data = BytesIO(stop1_bytes)
            while True:
                chunk = data.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        return Response(
            generate(),
            mimetype='audio/mpeg',
            headers={
                'Content-Type': 'audio/mpeg',
                'Content-Length': str(len(stop1_bytes)),
                'Content-Disposition': f'inline; filename="preview_stop1_{tour_id}.mp3"',
                'Cache-Control': 'no-store',
            },
        )
    except Exception as e:
        print(f"ERROR in preview_tour_audio: {e}")
        traceback.print_exc()
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
                   {_ratings_select(cur)},
                   {_is_paid_select(cur)} AS is_paid,
                   {_price_tier_select(cur)} AS price_tier,
                   {_short_title_select(cur)} AS short_title,
                   {_ORIGINAL_LANGUAGE_SELECT},
                   {_content_rating_select(cur)}
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
            {_ORIGINAL_LANGUAGE_JOIN}
            WHERE t.id = %s
        """, (tour_id,))
        
        result = cur.fetchone()
        
        if not result:
            print(f"Tour {tour_id} not found")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        (tour_id, tour_name, request_string, lat, lng, requests, language, original_id,
         max_vn, last_replaced, created_at, source_version, source_max_vn,
         rating_count, rating_values, verified_values, created_values, is_paid, price_tier,
         short_title,
         own_content_language, source_content_language,
         content_rating, content_review_status) = _row_with_rating(result, 22)
        editor = _editor_scores(cur)  # [LOCAL-685]
        cur.close()
        conn.close()
        
        # [LOCAL-687] Apply the same listing gate to the detail view: a tour that
        # would not be listed is a 404 here too (not_allowed, or pending/rejected
        # review; mature without adult=1). NULL rating == general. This keeps a
        # hidden tour un-reachable through its info endpoint, not just the list.
        adult = _adult_requested(request.args)
        if not _content_visible(content_rating, content_review_status, adult):
            print(f"Tour {tour_id} hidden by content rating "
                  f"({content_rating}/{content_review_status}, adult={adult})")
            sys.stdout.flush()
            return jsonify({'error': 'Tour not found'}), 404
        
        is_translation = original_id is not None and (language and language != 'en')
        version, updated_at = _resolved_version_fields(
            original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
        original_language = _resolved_original_language(
            own_content_language, original_id, source_content_language)
        
        return jsonify({
            'id': tour_id,
            'name': tour_name,
            # [LOCAL-711 / D673] Server short title (NULL until generated).
            'short_title': short_title,
            'request_string': request_string,
            'lat': lat,
            'lng': lng,
            'downloads': requests,
            'has_audio': True,
            'language': language or 'en',
            'is_translation': is_translation,
            'parent_tour_id': original_id,
            'original_language': original_language,
            'version': version,
            'updated_at': updated_at,
            'content_rating': _content_rating_field(content_rating),
            **_rating_payload(rating_values, verified_values, created_values, is_paid,
                              prior=_prior_for(editor, tour_id, original_id)),
            **_price_block(price_tier),
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
        
        # [LOCAL-680] '*' anchors the match (Boston* = starts with); no '*' = contains.
        sql_pattern = _search_like_pattern(pattern)
        # [LOCAL-670] Optional server-side rating filter.
        min_rating = _parse_min_rating(request.args)
        # [LOCAL-677] Optional Free/Paid filter.
        price_filter = _parse_price_filter(request.args)
        
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
                   {_ratings_select(cur)},
                   {_is_paid_select(cur)} AS is_paid,
                   {_price_tier_select(cur)} AS price_tier,
                   {_ORIGINAL_LANGUAGE_SELECT},
                   {_content_rating_select(cur)}
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
            {_ORIGINAL_LANGUAGE_JOIN}
            WHERE (t.tour_name ILIKE %s OR t.request_string ILIKE %s)
            AND t.lat IS NOT NULL AND t.lng IS NOT NULL
            AND (t.is_test IS NOT TRUE)
            ORDER BY t.number_requested DESC
            LIMIT 50
        """, (sql_pattern, sql_pattern))
        
        tours = cur.fetchall()
        editor = _editor_scores(cur)  # [LOCAL-685]
        # [LOCAL-701 / D663 §3] Batch community tags: hide members-only tours
        # from search; badge public ones.
        _ct_tags = _community_tags_batch(cur, [t[0] for t in tours])
        _ct_names = {}
        search_results = []
        adult = _adult_requested(request.args)  # [LOCAL-687] 18+ confirmed?
        
        for tour in tours:
            (tour_id, tour_name, request_string, tour_lat, tour_lng, requests, language, original_id,
             max_vn, last_replaced, created_at, source_version, source_max_vn,
             rating_count, rating_values, verified_values, created_values, is_paid, price_tier,
             own_content_language, source_content_language,
             content_rating, content_review_status) = _row_with_rating(tour, 21)
            # [LOCAL-687] Content gate: hide not_allowed, hide pending/rejected,
            # hide mature unless adult=1. NULL rating == general.
            if not _content_visible(content_rating, content_review_status, adult):
                continue
            # [LOCAL-701 / D663 §3] A members-only community tour never appears in
            # search (community page only); a public one is badged below.
            _ct_cid, _ct_vis = _ct_tags.get(tour_id, (None, None))
            if _ct_cid is not None and _ct_vis != 'public':
                continue
            version, updated_at = _resolved_version_fields(
                original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
            rating_block = _rating_payload(
                rating_values, verified_values, created_values, is_paid,
                prior=_prior_for(editor, tour_id, original_id))
            # Server-side min_rating filter.
            if min_rating is not None and rating_block['rating_score'] < min_rating:
                continue
            # [LOCAL-677] Free/Paid filter.
            if not _passes_price_filter(price_filter, rating_block['is_paid']):
                continue
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                is_translation = original_id is not None and (language and language != 'en')
                original_language = _resolved_original_language(
                    own_content_language, original_id, source_content_language)
                
                search_result = {
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
                    'original_language': original_language,
                    'version': version,
                    'updated_at': updated_at,
                    'content_rating': _content_rating_field(content_rating),
                    **rating_block,
                    **_price_block(price_tier, cur),
                }
                # [LOCAL-701 / D663 §3] Public community tour → community badge.
                if _ct_cid is not None:
                    if _ct_cid not in _ct_names:
                        _ct_names[_ct_cid] = _community_name(cur, _ct_cid)
                    search_result['community_id'] = _ct_cid
                    search_result['community_name'] = _ct_names[_ct_cid]
                    search_result['community_visibility'] = _ct_vis
                    search_result['badge'] = 'community'
                search_results.append(search_result)
        
        # [LOCAL-689] Personal match_percent + reasons for every result when
        # ?user_id is passed (batched; a translation maps to its original's
        # metrics+score via its parent_tour_id). editor reused as the quality input.
        _attach_match(cur, request.args.get('user_id'), search_results, editor)

        # [LOCAL-672] "Top rated" sort (?sort=top_rated): the Bayesian rank_score
        # descending, tie-broken by popularity then distance. Default stays
        # popularity-then-distance (the original search order).
        # [LOCAL-689] ?sort=match: best personal match first; no-match items last.
        sort_arg = (request.args.get('sort') or '').strip().lower()
        if sort_arg == 'match':
            search_results.sort(key=lambda x: (
                -(x.get('match_percent') if x.get('match_percent') is not None else -1),
                -x['popularity'], x['distance_km']))
        elif _wants_top_rated(request.args):
            search_results.sort(key=lambda x: (-x.get('rank_score', RANK_PRIOR_SCORE),
                                               -x['popularity'], x['distance_km']))
        else:
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

# ─── [LOCAL-688] Why this score + public page + one free re-score ─────────────
#
# These are the "why" behind the number LOCAL-685 publishes. All three are
# PUBLIC and FREE (Michael, 2026-10-14: it must look objective and cost nothing).
# The explanation and the page read what tour_editor_score.py already wrote into
# audio_tours.editor_score_detail — no model call here. The re-score request is
# the one write: it clears a guide's own tour's score so the 5-minute tick
# re-scores it, once per content version.

# Human labels + fixed display order for the five rubric criteria. The detail
# JSON keys are the lowercase names tour_editor_score.CRITERIA writes.
_SCORE_CRITERIA = [
    ('story', 'Story'),
    ('specificity', 'Specificity'),
    ('place', 'Sense of place'),
    ('flow', 'Flow'),
    ('accuracy', 'Accuracy'),
]


def _tour_version_number(cur, tour_id):
    """The tour's live content version: COALESCE(MAX(version_no),0)+1 over its
    OWN id in audio_tour_versions (LOCAL-657). An unedited tour is version 1.
    Never raises — returns 1 on any error / missing table."""
    try:
        cur.execute(
            "SELECT COALESCE(MAX(version_no), 0) FROM audio_tour_versions WHERE tour_id = %s",
            (int(tour_id),))
        row = cur.fetchone()
        return int(row[0] or 0) + 1
    except Exception:  # noqa: BLE001
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return 1


def _score_explanation_payload(cur, tour_id):
    """Build the Why-this-score block for a tour, or None when the governing
    (original) tour has no evaluated score yet.

    A translation shows its ORIGINAL's explanation (the score lives on the
    original, exactly like the shown rating prior — _prior_for). Reads only what
    tour_editor_score.py wrote: editor_score / editor_score_detail /
    editor_scored_at. No model call."""
    original_id = _resolve_original_id(cur, tour_id)
    try:
        cur.execute(
            "SELECT editor_score, editor_score_detail, editor_scored_at "
            "FROM audio_tours WHERE id = %s", (int(original_id),))
    except Exception:  # noqa: BLE001 — schema predates the columns → unscored
        try:
            cur.connection.rollback()
        except Exception:
            pass
        return None
    row = cur.fetchone()
    if not row or row[0] is None:
        return None
    score, detail, scored_at = row
    detail = detail or {}
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except Exception:  # noqa: BLE001
            detail = {}
    evidence = detail.get('evidence') or {}
    criteria = []
    for key, label in _SCORE_CRITERIA:
        grade = detail.get(key)
        criteria.append({
            'name': key,
            'label': label,
            'grade': float(grade) if grade is not None else None,
            'evidence': evidence.get(key, ''),
        })
    return {
        'tour_id': int(tour_id),
        'scored_tour_id': int(original_id),
        'score': float(score),
        'label': 'Audioura score',
        'criteria': criteria,
        'summary': detail.get('summary', ''),
        'scored_at': _iso_date(scored_at),
        'rubric_version': detail.get('rubric_version'),
    }


@app.route('/tour/<int:tour_id>/score-explanation', methods=['GET', 'OPTIONS'])
def get_score_explanation(tour_id):
    """[LOCAL-688] Why this score — PUBLIC, no auth, free.

    {score, label, criteria:[{name,label,grade,evidence}], summary, scored_at,
    rubric_version}. A translation returns its original's explanation. 404 when
    the governing tour has no evaluated score yet."""
    if request.method == 'OPTIONS':
        return add_cors_headers(make_response())
    print(f"[LOCAL-688] score-explanation for tour {tour_id}")
    sys.stdout.flush()
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        payload = _score_explanation_payload(cur, tour_id)
        cur.close()
        if payload is None:
            return jsonify({'error': 'tour not scored'}), 404
        return jsonify(payload)
    except Exception as e:  # noqa: BLE001
        print(f"[LOCAL-688] score-explanation failed for {tour_id}: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        return jsonify({'error': 'tour not scored'}), 404
    finally:
        if conn is not None:
            conn.close()


@app.route('/tour/<int:tour_id>/match', methods=['GET', 'OPTIONS'])
def get_tour_match(tour_id):
    """[LOCAL-689] Personal Match % for a listener — PUBLIC, free, deterministic.

    GET /tour/<id>/match?user_id=<device user id>
      → {match_percent: 0..100, reasons: [two short phrases], ...}
      → {match_percent: null, reason: "Swipe a few stops to get matches"} when
        the listener has fewer than personal_match.MIN_SWIPES swipes (or no
        user_id is passed).

    No model call: the number comes only from the listener's swipe-preference
    vector, the tour's story character (mean of stop_metrics.class_*), and the
    tour's evaluated score. A translation uses its ORIGINAL tour's metrics and
    score. Never 500s on a listener with no history — that is a normal cold
    start, returned as match_percent null."""
    if request.method == 'OPTIONS':
        return add_cors_headers(make_response())
    user_id = request.args.get('user_id')
    print(f"[LOCAL-689] match for tour {tour_id}, user {user_id}")
    sys.stdout.flush()
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        block = _single_tour_match(cur, user_id, tour_id)
        cur.close()
        # Public shape: match_percent + reasons; cold start carries a single
        # `reason` sentence and match_percent null.
        payload = {
            'tour_id': block['tour_id'],
            'scored_tour_id': block['scored_tour_id'],
            'match_percent': block['match_percent'],
            'reasons': block['match_reasons'],
        }
        if block['match_percent'] is None:
            payload['reason'] = block['match_reason']
        return jsonify(payload)
    except Exception as e:  # noqa: BLE001
        print(f"[LOCAL-689] match failed for {tour_id}: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        # Fail SOFT to a cold-start shape — a listener should never see a 500
        # where a match belongs.
        return jsonify({
            'tour_id': int(tour_id),
            'match_percent': None,
            'reasons': [],
            'reason': personal_match.NO_MATCH_REASON,
        })
    finally:
        if conn is not None:
            conn.close()


@app.route('/tour/<int:tour_id>/rescore-request', methods=['POST', 'OPTIONS'])
def request_rescore(tour_id):
    """[LOCAL-688] A guide requests ONE free re-score of their OWN tour after an
    edit. Clears the original's editor_score so the 5-minute tick re-scores it,
    and records the content version it was requested for.

    Ownership is the SAME check the curator Price control uses
    (_user_is_tour_creator → earliest tour_requests.secret_id of the original,
    or an explicit creator_user_id). user_id comes from the JSON body / query /
    header, matching the rest of the service.

    403 non-owner; 409 a second request for the SAME content version (one per
    version); 200 {status:'queued', version} on success. The score is cleared on
    the ORIGINAL (translations share it)."""
    if request.method == 'OPTIONS':
        return add_cors_headers(make_response())
    print(f"[LOCAL-688] rescore-request for tour {tour_id}")
    sys.stdout.flush()
    body = request.get_json(silent=True) or {}
    user_id = (body.get('user_id') or request.args.get('user_id')
               or request.headers.get('X-User-Id'))
    if not user_id:
        return jsonify({'error': 'user_id required'}), 403
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Ownership — on the ORIGINAL (a guide owns the tour, not a translation row).
        original_id = _resolve_original_id(cur, tour_id)
        if not _user_is_tour_creator(cur, user_id, original_id):
            cur.close()
            return jsonify({'error': 'not your tour'}), 403

        # One re-score per content version. The rescore_requested_version
        # column (migration 028) may not yet be applied on this DB; when it is
        # absent we still honour the request (clear the score) but cannot track
        # the per-version limit — fail OPEN, never 500.
        version = _tour_version_number(cur, original_id)
        has_version_col = False
        try:
            cur.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name = "
                "'audio_tours' AND column_name = 'rescore_requested_version'")
            has_version_col = cur.fetchone() is not None
        except Exception:  # noqa: BLE001
            try:
                conn.rollback()
            except Exception:
                pass
            has_version_col = False

        if has_version_col:
            cur.execute(
                "SELECT rescore_requested_version FROM audio_tours WHERE id = %s",
                (original_id,))
            prev = cur.fetchone()
            prev_version = prev[0] if prev else None
            if prev_version is not None and int(prev_version) == int(version):
                cur.close()
                return jsonify({
                    'error': 'already requested',
                    'message': ("You have already requested a re-score for this "
                                "version of the tour. Edit the tour again to earn "
                                "another free re-score."),
                    'version': version,
                }), 409
            cur.execute(
                "UPDATE audio_tours SET editor_score = NULL, "
                "rescore_requested_version = %s WHERE id = %s",
                (version, original_id))
        else:
            cur.execute(
                "UPDATE audio_tours SET editor_score = NULL WHERE id = %s",
                (original_id,))
        conn.commit()
        cur.close()
        return jsonify({'status': 'queued', 'tour_id': int(original_id),
                        'version': version})
    except Exception as e:  # noqa: BLE001
        print(f"[LOCAL-688] rescore-request failed for {tour_id}: {e}")
        traceback.print_exc()
        sys.stdout.flush()
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({'error': 'rescore request failed'}), 500
    finally:
        if conn is not None:
            conn.close()


# The public "How Audioura scores tours" page. Plain, self-contained HTML (no
# external CSS/JS) so it renders on any phone browser the app links out to.
# Static text — the actual grades live per-tour in the explanation endpoint.
_HOW_WE_SCORE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>How Audioura scores tours</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         line-height: 1.5; margin: 0; padding: 1.25rem; max-width: 44rem;
         margin-inline: auto; }
  h1 { font-size: 1.5rem; margin-top: 0; }
  h2 { font-size: 1.15rem; margin-top: 1.75rem; }
  .crit { margin: 0.75rem 0; }
  .crit b { display: block; }
  table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; font-size: 0.95rem; }
  th, td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #8884; vertical-align: top; }
  .note { opacity: 0.8; font-size: 0.95rem; }
  footer { margin-top: 2rem; font-size: 0.85rem; opacity: 0.7; }
</style>
</head>
<body>
<h1>How Audioura scores tours</h1>

<p>Every tour on Audioura starts with a score between <b>5.0 and 8.0</b> &mdash; the
<b>Audioura score</b>. It is our editor's read of the tour's script, so a brand-new
tour nobody has rated yet still tells you something honest about its quality.
The explanation is <b>free for everyone</b>, and the same rules apply to every
tour, whoever made it.</p>

<h2>The five things we grade</h2>
<p>A demanding editor grades the script on five criteria, each from 1 to 10. We
grade the <em>same</em> script three times and average the results, so the number
is steady and not a lucky or unlucky single read.</p>

<div class="crit"><b>Story</b>Narrative pull &mdash; named people, events, stakes and
surprise, rather than a list of facts or brochure praise.</div>
<div class="crit"><b>Specificity</b>Concrete names, dates, numbers and details a
real local guide would know &mdash; not "rich history" and "vibrant atmosphere".</div>
<div class="crit"><b>Sense of place</b>Tied to what you actually see or do at each
stop, with usable directions between stops.</div>
<div class="crit"><b>Flow</b>The stops connect into one tour; no repetition,
padding or the same opening line at every stop.</div>
<div class="crit"><b>Accuracy</b>Internally consistent and plausible; no
contradictions, vague hedging or claims that look invented.</div>

<h2>What the grades mean</h2>
<table>
  <tr><th>Grade</th><th>Reading</th></tr>
  <tr><td>3</td><td>Weak</td></tr>
  <tr><td>5</td><td>Mediocre / generic</td></tr>
  <tr><td>6.5</td><td>Competent</td></tr>
  <tr><td>8</td><td>Genuinely good</td></tr>
  <tr><td>9.5</td><td>Exceptional (rare)</td></tr>
</table>

<h2>Why the range is 5 to 8</h2>
<p class="note">Below 5 would bury a tour nobody has had the chance to hear yet;
above 8 would claim more than an unrated tour has earned. <b>9 and 10 are
reserved for listeners</b> &mdash; only real ratings reach the top of the scale.</p>

<h2>Listeners take over</h2>
<p>The Audioura score is only the starting point. Once a tour has a few ratings
they blend in, and <b>from the fourth rating onward the listeners' score decides</b>
&mdash; the Audioura score steps aside.</p>

<h2>Guides: one free re-score</h2>
<p>Edited your tour and think it reads better now? A guide may request <b>one free
re-score</b> after an edit, from the tour's menu. We grade the new version and
publish the fresh number. Edit again, and another free re-score is available.</p>

<footer>Audioura &mdash; the same rules for every tour, free to see.</footer>
</body>
</html>"""


@app.route('/how-we-score', methods=['GET'])
def how_we_score():
    """[LOCAL-688] Public 'How Audioura scores tours' page. Static HTML, no auth."""
    resp = make_response(_HOW_WE_SCORE_HTML)
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    return resp


if __name__ == '__main__':
    print("Starting Map Delivery Service...")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /tours-near/<lat>/<lng>?radius=<km> - Get tours near location")
    print("  GET /download-tour/<tour_id> - Download tour zip file")
    print("  GET /tour-info/<tour_id> - Get tour information")
    print("  GET /search-tours?pattern=<pattern>&lat=<lat>&lng=<lng> - Search tours by pattern")
    print("  GET /tour/<tour_id>/score-explanation - Why this score (public)")
    print("  POST /tour/<tour_id>/rescore-request - Guide's one free re-score after an edit")
    print("  GET /how-we-score - Public 'How Audioura scores tours' page")
    sys.stdout.flush()
    
    app.run(host='0.0.0.0', port=5005, debug=True)
