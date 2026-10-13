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
import zipfile
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
                   {_ratings_select(cur)},
                   {_is_paid_select(cur)} AS is_paid,
                   {_price_tier_select(cur)} AS price_tier,
                   {_ORIGINAL_LANGUAGE_SELECT}
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
        cur.close()
        conn.close()
        if not t:
            return jsonify({'error': 'tour not found'}), 404

        (tour_id, tour_name, request_string, tour_lat, tour_lng, requests,
         language, original_id, max_vn, last_replaced, created_at,
         source_version, source_max_vn, rating_count, rating_values,
         verified_values, created_values, is_paid, price_tier,
         own_content_language, source_content_language) = t
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
                **_rating_payload(rating_values, verified_values, created_values, is_paid),
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


def compute_rating(ratings, verified=None, paid=False):
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
    if count == 0:
        return {"score": RATING_DEFAULT_SCORE, "count": 0, "label": "New"}
    if count < RATING_MEDIAN_SWITCH_COUNT:
        blended = [RATING_DEFAULT_SCORE] + [float(r) for r in ratings]
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


def rank_score(ratings, verified=None, created=None, now=None, current_version_date=None):
    """Bayesian list-ORDER key (items 4 & 11). NOT the shown score.

    score = (C*7.5 + sum(w_i*rating_i)) / (C + sum(w_i)), C=3.
    w_i = (1.0 verified | 0.5 unverified) * (0.5 if stale else 1.0),
    stale = older than 12 months OR before the tour's current version date.
    Parallel lists `verified` and `created` align with `ratings` (missing → False
    / None). No ratings → the 7.5 prior (a new tour sorts mid-list)."""
    from datetime import datetime as _dt
    if now is None:
        now = _dt.now()
    num = RANK_PRIOR_COUNT * RANK_PRIOR_SCORE
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
    return num / den if den > 0 else RANK_PRIOR_SCORE


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


def _rating_payload(rating_values, verified_values, created_values, paid):
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
    rating = compute_rating(rating_values, verified=verified_values, paid=paid)
    vals = [r for r in (rating_values or []) if r is not None]
    verified_count = sum(1 for v in (verified_values or []) if v)
    return {
        'rating_score': rating['score'],
        'rating_count': rating['count'],
        'rating_label': rating['label'],
        'verified_count': verified_count,
        'is_paid': bool(paid),
        'rank_score': round(rank_score(rating_values, verified=verified_values,
                                        created=created_values), 4),
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
# effect); the constants are the fallback for a DB that predates it. Keep the
# five entries in lock-step with migration 022.
_DEFAULT_TIER_LABELS = {1: "$1.99", 2: "$2.99", 3: "$4.99", 4: "$7.99", 5: "$9.99"}
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


def _user_has_unlock(cur, user_id, tour_id):
    """True if this user has a tour_unlocks row for THIS language row's own id
    (per-language unlock, 677B/D653). Absent table (pre-022) → not unlocked."""
    global _HAS_TOUR_UNLOCKS_TABLE
    if not user_id:
        return False
    if _HAS_TOUR_UNLOCKS_TABLE is None:
        _HAS_TOUR_UNLOCKS_TABLE = _table_exists(cur, 'tour_unlocks')
    if not _HAS_TOUR_UNLOCKS_TABLE:
        return False
    try:
        cur.execute(
            "SELECT 1 FROM tour_unlocks WHERE user_id = %s AND tour_id = %s LIMIT 1",
            (user_id, int(tour_id)),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001
        return False


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


def _download_gate(cur, user_id, tour_id):
    """The pay-before-download decision for ONE language row.

    Returns (allowed: bool, info: dict). When allowed is False, `info` is the
    402 body: {error: 'purchase_required', tour_id, price_tier, price}.

    Order (the first that applies wins):
      1. FREE row (price_tier NULL)            → allowed.
      2. The tour's CREATOR (curator's own)    → allowed.
      3. The user has an UNLOCK for this row   → allowed.
      4. The user is GRANDFATHERED (free dl)   → allowed.
      5. otherwise                             → 402 purchase_required.
    """
    tier = _row_price_tier(cur, tour_id)
    if tier is None:
        return True, None  # free row — unchanged behaviour
    if _user_is_tour_creator(cur, user_id, tour_id):
        return True, None  # the curator downloads their own tour
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
                   {_ORIGINAL_LANGUAGE_SELECT}
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
        tours_list = []
        
        for tour in tours:
            (tour_id, tour_name, request_string, tour_lat, tour_lng, requests,
             language, original_id, max_vn, last_replaced, created_at,
             source_version, source_max_vn, rating_count, rating_values,
             verified_values, created_values, is_paid, price_tier,
             own_content_language, source_content_language) = tour
            
            if tour_lat and tour_lng:
                distance = calculate_distance(lat, lng, tour_lat, tour_lng)
                
                if distance <= radius_km:
                    version, updated_at = _resolved_version_fields(
                        original_id, source_version, source_max_vn,
                        max_vn, last_replaced, created_at)
                    rating_block = _rating_payload(
                        rating_values, verified_values, created_values, is_paid)
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
                        **rating_block,
                        **_price_block(price_tier, cur),
                    }
                    tours_list.append(tour_data)
        
        # [LOCAL-672] "Top rated" sort (?sort=top_rated): order by the Bayesian
        # rank_score (verified 1.0 / unverified 0.5, 12-month & pre-version decay,
        # C=3 prior) descending, breaking ties by distance so near tours win among
        # equally-ranked ones. Default remains nearest-first (the original behaviour).
        if _wants_top_rated(request.args):
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
        allowed, deny = _download_gate(cur, user_id, tour_id)
        if not allowed:
            print(f"Tour {tour_id} is paid and not unlocked for {user_id}: 402")
            sys.stdout.flush()
            cur.close()
            conn.close()
            return jsonify(deny), 402

        # Record the download event (idempotent) so a free download now
        # grandfathers this user if the curator later prices the tour. was_free
        # is read from the row's governing tier at THIS moment.
        _record_download_event(cur, user_id, tour_id,
                               was_free=(_row_price_tier(cur, tour_id) is None))

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
                   {_ORIGINAL_LANGUAGE_SELECT}
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
         own_content_language, source_content_language) = result
        cur.close()
        conn.close()
        
        is_translation = original_id is not None and (language and language != 'en')
        version, updated_at = _resolved_version_fields(
            original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
        original_language = _resolved_original_language(
            own_content_language, original_id, source_content_language)
        
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
            'original_language': original_language,
            'version': version,
            'updated_at': updated_at,
            **_rating_payload(rating_values, verified_values, created_values, is_paid),
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
        
        # Use ILIKE for case-insensitive pattern matching
        # Convert regex pattern back to SQL LIKE pattern
        sql_pattern = pattern.replace('.*', '%')
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
                   {_ORIGINAL_LANGUAGE_SELECT}
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
        """, (f'%{sql_pattern}%', f'%{sql_pattern}%'))
        
        tours = cur.fetchall()
        search_results = []
        
        for tour in tours:
            (tour_id, tour_name, request_string, tour_lat, tour_lng, requests, language, original_id,
             max_vn, last_replaced, created_at, source_version, source_max_vn,
             rating_count, rating_values, verified_values, created_values, is_paid, price_tier,
             own_content_language, source_content_language) = tour
            version, updated_at = _resolved_version_fields(
                original_id, source_version, source_max_vn, max_vn, last_replaced, created_at)
            rating_block = _rating_payload(
                rating_values, verified_values, created_values, is_paid)
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
                    'original_language': original_language,
                    'version': version,
                    'updated_at': updated_at,
                    **rating_block,
                    **_price_block(price_tier, cur),
                })
        
        # [LOCAL-672] "Top rated" sort (?sort=top_rated): the Bayesian rank_score
        # descending, tie-broken by popularity then distance. Default stays
        # popularity-then-distance (the original search order).
        if _wants_top_rated(request.args):
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
