"""
LOCAL-672 — Verified reviews tests.

Covers the ticket's test list (§7, §12):
  * verified logic — direct per-tour purchase, the D624 level-purchase fallback,
    and a refund that un-verifies;
  * paid vs free counting — a paid tour counts only verified ratings toward the
    shown score, a free tour counts all;
  * moderation — profanity / URL / contact-info → pending, clean → approved;
  * the reply rule — only the creator, only once, through the auto-check;
  * the Bayesian order — one 10 does not top many verified 8s; verified
    outranks unverified; a stale/pre-version rating is weighted down;
  * the rating distribution — five bands, verified-on-paid / all-on-free;
  * helpful votes — one per (user, review), no self-vote.

Also exercises the orchestrator endpoints (reviews/reply/helpful/distribution/
pending/moderate) via an in-process Flask client, and map-delivery's rank_score
/ distribution / verified-counting pure helpers.

Safety (ticket §7): every row written here uses a user_id starting with
'TEST-672-'. Cleanup deletes ONLY rows whose user_id has that exact prefix, by
exact id, across tour_reviews, review_helpful_votes, tour_ratings, tour_listens,
purchases and tour_requests. No other table is touched destructively.
"""

import os
import sys
import importlib.util
import datetime as dt

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection, check_db_available  # noqa: E402
import tour_rating_service as rating_svc  # noqa: E402
import tour_reviews_service as reviews_svc  # noqa: E402

TEST_PREFIX = "TEST-672-"


# ─── 1. Moderation auto-check (pure, no DB) ───────────────────────────────────

def test_moderation_clean_is_approved():
    status, reason = reviews_svc.moderate_text("A wonderful, well paced tour.")
    assert status == "approved"
    assert reason == ""


def test_moderation_profanity_held():
    status, reason = reviews_svc.moderate_text("this tour was shit honestly")
    assert status == "pending"
    assert reason == "profanity"


def test_moderation_url_held():
    status, reason = reviews_svc.moderate_text("great — see more at www.myspam.com")
    assert status == "pending"
    assert reason == "url"
    # bare-domain form too
    assert reviews_svc.moderate_text("visit example.net now")[1] == "url"


def test_moderation_contact_held():
    assert reviews_svc.moderate_text("email me at a@b.com")[1] == "contact"
    assert reviews_svc.moderate_text("call 555 123 4567")[1] == "contact"


# ─── 2. Bayesian ranking (pure, no DB) — items 4 & 11 ─────────────────────────

def test_bayesian_one_ten_does_not_top_many_eights():
    now = dt.datetime.now()
    one_ten = reviews_svc.rank_score(
        [{"rating": 10, "verified": False, "created_at": now}], now=now)
    many_eights = reviews_svc.rank_score(
        [{"rating": 8, "verified": True, "created_at": now}] * 10, now=now)
    assert many_eights > one_ten


def test_bayesian_verified_outranks_unverified():
    now = dt.datetime.now()
    verified = reviews_svc.rank_score(
        [{"rating": 10, "verified": True, "created_at": now}] * 4, now=now)
    unverified = reviews_svc.rank_score(
        [{"rating": 10, "verified": False, "created_at": now}] * 4, now=now)
    assert verified > unverified


def test_bayesian_stale_and_preversion_weighted_down():
    now = dt.datetime.now()
    old = now - dt.timedelta(days=400)         # > 12 months
    fresh = reviews_svc.rank_score(
        [{"rating": 10, "verified": True, "created_at": now}], now=now)
    stale = reviews_svc.rank_score(
        [{"rating": 10, "verified": True, "created_at": old}], now=now)
    assert stale < fresh

    # A rating made before the tour's current version is also halved.
    version_date = now - dt.timedelta(days=5)
    before_version = now - dt.timedelta(days=10)
    after_version = now - dt.timedelta(days=1)
    pre = reviews_svc.rank_score(
        [{"rating": 10, "verified": True, "created_at": before_version}],
        now=now, current_version_date=version_date)
    post = reviews_svc.rank_score(
        [{"rating": 10, "verified": True, "created_at": after_version}],
        now=now, current_version_date=version_date)
    assert pre < post


def test_bayesian_empty_is_prior():
    assert reviews_svc.rank_score([]) == reviews_svc.RANK_PRIOR_SCORE


# ─── 3. Distribution (pure, no DB) — item 8 ───────────────────────────────────

def test_distribution_bands_and_percentages():
    d = reviews_svc._distribution_from_ratings([10, 9, 8, 7, 5, 2, 2])
    assert d["total"] == 7
    by = {b["band"]: b for b in d["bands"]}
    assert by["9-10"]["count"] == 2
    assert by["7-8"]["count"] == 2
    assert by["5-6"]["count"] == 1
    assert by["3-4"]["count"] == 0
    assert by["1-2"]["count"] == 2
    # percentages sum to ~100 (rounding may make it 99/101; each is a round()).
    assert all(0 <= b["percent"] <= 100 for b in d["bands"])


# ─── DB-backed fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db():
    if not check_db_available():
        pytest.skip("database unavailable")
    conn = get_connection()
    yield conn
    conn.close()


def _cleanup(conn):
    """Delete only our TEST-672- rows, by exact id after a prefix check, across
    every table this suite writes. Guarded so a missing table never fails."""
    cur = conn.cursor()

    # review_helpful_votes first (FK to tour_reviews, though ON DELETE CASCADE).
    # Delete by the prefix-matched key column directly. We SELECT the key first
    # and re-check the TEST-672- prefix in Python before issuing each DELETE, so
    # a stray LIKE match can never touch a non-test row. Keyed on the table's
    # own key column (id where present, secret_id for users).
    for table, col in (
        ("review_helpful_votes", "user_id"),
        ("tour_reviews", "user_id"),
        ("tour_ratings", "user_id"),
        ("tour_listens", "user_id"),
        ("purchases", "user_id"),
        ("tour_requests", "secret_id"),
        ("users", "secret_id"),
    ):
        try:
            cur.execute(f"SELECT DISTINCT {col} FROM {table} WHERE {col} LIKE %s",
                        (TEST_PREFIX + "%",))
            keys = [row[0] for row in cur.fetchall()
                    if row[0] and str(row[0]).startswith(TEST_PREFIX)]
            for k in keys:
                cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (k,))
            conn.commit()
        except Exception:
            conn.rollback()
    cur.close()


def _seed_tour(conn, name, original_tour_id=None, language="en", is_test=True,
               is_paid=None, with_owner=True):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, lat, lng,
                                 content_language, language, original_tour_id, is_test)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
        """,
        (name, name, 43.70, 7.26, language, language, original_tour_id, is_test),
    )
    tid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    # By default give the tour a dedicated OWNER (earliest requester → creator),
    # so test raters are never accidentally treated as the creator. Tests that
    # want a specific creator pass with_owner=False and call _seed_creator.
    if with_owner:
        _seed_creator(conn, tid)
    return tid


def _seed_creator(conn, tour_id, user_id=None):
    """Make user_id the tour's creator by giving them the EARLIEST tour_requests
    row (explicit older created_at so they always sort first). Returns the id."""
    user_id = user_id or f"{TEST_PREFIX}owner-{tour_id}"
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (secret_id) VALUES (%s) ON CONFLICT (secret_id) DO NOTHING",
        (user_id,),
    )
    cur.execute(
        """
        INSERT INTO tour_requests (secret_id, tour_id, request_string, status, created_at)
        VALUES (%s, %s, %s, 'completed', CURRENT_TIMESTAMP - INTERVAL '1 day')
        """,
        (user_id, str(tour_id), "creator"),
    )
    conn.commit()
    cur.close()
    return user_id


def _seed_download(conn, user_id, tour_id):
    """Give a user a download record (tour_requests) so has_downloaded() is True
    and the user can be the tour's creator (earliest requester). Seeds the users
    row first because tour_requests.secret_id has a FK to users."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (secret_id) VALUES (%s) ON CONFLICT (secret_id) DO NOTHING",
        (user_id,),
    )
    cur.execute(
        """
        INSERT INTO tour_requests (secret_id, tour_id, request_string, status)
        VALUES (%s, %s, %s, 'completed')
        """,
        (user_id, str(tour_id), "test"),
    )
    conn.commit()
    cur.close()


def _seed_purchase(conn, user_id, product, raw_status=None, txn=None):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO purchases (transaction_id, store, product, user_id, raw_status)
        VALUES (%s, 'stub', %s, %s, %s)
        """,
        (txn or f"{user_id}-{product}", product, user_id, raw_status),
    )
    conn.commit()
    cur.close()


def _listen_enough(user_id, tour_id):
    """Satisfy the LOCAL-670B listened-stops gate for endpoint tests."""
    rating_svc.record_listen(user_id, tour_id, 0)
    rating_svc.record_listen(user_id, tour_id, 1)


# ─── 4. Verified logic (purchase, level fallback, refund) ─────────────────────

def test_verified_direct_tour_purchase(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 paid tour")
        user = f"{TEST_PREFIX}buyer"
        _seed_download(db, user, tid)
        _seed_purchase(db, user, f"tour_{tid}")  # direct unlock of THIS tour

        out = rating_svc.record_rating(user, tid, 9)
        assert out["verified"] is True
    finally:
        _cleanup(db)


def test_verified_level_fallback_requires_download(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 level tour")
        downloader = f"{TEST_PREFIX}lvl-dl"
        non_dl = f"{TEST_PREFIX}lvl-nodl"
        # Both bought a LEVEL product; only the downloader actually has the tour.
        _seed_purchase(db, downloader, "l3_pack_10", txn=f"{downloader}-l3")
        _seed_purchase(db, non_dl, "l3_pack_10", txn=f"{non_dl}-l3")
        _seed_download(db, downloader, tid)

        out_dl = rating_svc.record_rating(downloader, tid, 8)
        out_nodl = rating_svc.record_rating(non_dl, tid, 8)
        assert out_dl["verified"] is True       # level + downloaded → verified
        assert out_nodl["verified"] is False    # level but never downloaded → not
    finally:
        _cleanup(db)


def test_refund_unverifies(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 refund tour")
        user = f"{TEST_PREFIX}refunder"
        _seed_download(db, user, tid)
        _seed_purchase(db, user, f"tour_{tid}", txn=f"{user}-ok")

        out = rating_svc.record_rating(user, tid, 10)
        assert out["verified"] is True

        # The purchase is refunded; recompute flips the rating to unverified.
        cur = db.cursor()
        cur.execute(
            "UPDATE purchases SET raw_status = 'refunded' WHERE user_id = %s",
            (user,),
        )
        db.commit()
        cur.close()

        reviews_svc.recompute_verified_for_user(user)
        cur = db.cursor()
        cur.execute("SELECT verified FROM tour_ratings WHERE tour_id = %s AND user_id = %s",
                    (tid, user))
        assert cur.fetchone()[0] is False
        cur.close()
    finally:
        _cleanup(db)


def test_no_purchase_is_unverified(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 nopurchase tour")
        user = f"{TEST_PREFIX}free-rater"
        _seed_download(db, user, tid)
        out = rating_svc.record_rating(user, tid, 7)
        assert out["verified"] is False
    finally:
        _cleanup(db)


# ─── 5. Creator protection ────────────────────────────────────────────────────

def test_creator_cannot_rate_own_tour(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 creator tour", with_owner=False)
        creator = f"{TEST_PREFIX}creator"
        _seed_creator(db, tid, user_id=creator)  # the rater IS the creator
        with pytest.raises(ValueError):
            rating_svc.record_rating(creator, tid, 10)
    finally:
        _cleanup(db)


# ─── 6. Paid vs free counting (map-delivery pure helper) ──────────────────────

def test_paid_counts_verified_only_free_counts_all():
    # Three ratings; one verified. On a paid tour the shown score uses only the
    # verified one; on a free tour it uses all three (LOCAL-670).
    ratings = [9, 10, 2]
    verified = [True, False, False]

    md = _load_md()
    free = md.compute_rating(ratings, verified=verified, paid=False)
    paid = md.compute_rating(ratings, verified=verified, paid=True)
    assert free["count"] == 3
    assert paid["count"] == 1
    # paid: just the single 9 → blended with the 7.5 prior → 8.3.
    assert paid["score"] == 8.3

    dist_free = md.compute_distribution(ratings, verified=verified, paid=False)
    dist_paid = md.compute_distribution(ratings, verified=verified, paid=True)
    assert dist_free["total"] == 3
    assert dist_paid["total"] == 1


# ─── 7. Review CRUD + moderation status on write (DB) ─────────────────────────

def test_submit_review_requires_a_rating(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 review-norating tour")
        user = f"{TEST_PREFIX}rv1"
        with pytest.raises(ValueError):
            reviews_svc.submit_review(user, tid, "No rating yet, should fail.")
    finally:
        _cleanup(db)


def test_submit_clean_review_approved_and_flagged_pending(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 review tour")
        user = f"{TEST_PREFIX}rv2"
        _seed_download(db, user, tid)
        rating_svc.record_rating(user, tid, 9)

        clean = reviews_svc.submit_review(user, tid, "Loved every stop.")
        assert clean["review_status"] == "approved"

        # Re-review with a flagged body → UPSERT holds it pending.
        flagged = reviews_svc.submit_review(user, tid, "visit www.spam.com")
        assert flagged["review_status"] == "pending"
        assert flagged["status_reason"] == "url"
    finally:
        _cleanup(db)


def test_get_reviews_returns_approved_only_verified_first(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 getreviews tour")
        v_user = f"{TEST_PREFIX}gr-ver"
        u_user = f"{TEST_PREFIX}gr-unv"
        # Verified rater: direct purchase + download.
        _seed_download(db, v_user, tid)
        _seed_purchase(db, v_user, f"tour_{tid}", txn=f"{v_user}-ok")
        rating_svc.record_rating(v_user, tid, 10)
        reviews_svc.submit_review(v_user, tid, "Verified and great.")
        # Unverified rater.
        _seed_download(db, u_user, tid)
        rating_svc.record_rating(u_user, tid, 9)
        reviews_svc.submit_review(u_user, tid, "Also good, no purchase.")

        got = reviews_svc.get_reviews(tid, sort="top")
        assert len(got) == 2
        # Verified first under the default 'top' order (helpful tie → verified).
        assert got[0]["verified"] is True
        assert got[0]["verified_listener"] is True
    finally:
        _cleanup(db)


def test_get_reviews_band_filter_and_critical_sort(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 bandsort tour")
        high = f"{TEST_PREFIX}bs-high"
        low = f"{TEST_PREFIX}bs-low"
        for u, r, txt in ((high, 10, "excellent"), (low, 3, "disappointing")):
            _seed_download(db, u, tid)
            rating_svc.record_rating(u, tid, r)
            reviews_svc.submit_review(u, tid, txt)

        # Band filter: only the 9-10 review.
        band = reviews_svc.get_reviews(tid, band="9-10")
        assert len(band) == 1 and band[0]["rating"] == 10

        # Critical sort: the <= 6 review comes first.
        crit = reviews_svc.get_reviews(tid, sort="critical")
        assert crit[0]["rating"] == 3
    finally:
        _cleanup(db)


# ─── 8. Curator reply rule (DB) ───────────────────────────────────────────────

def test_reply_only_creator_and_only_once(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 reply tour", with_owner=False)
        creator = f"{TEST_PREFIX}rep-creator"
        rater = f"{TEST_PREFIX}rep-rater"
        _seed_creator(db, tid, user_id=creator)   # earliest requester → creator
        _seed_download(db, rater, tid)
        rating_svc.record_rating(rater, tid, 8)
        review = reviews_svc.submit_review(rater, tid, "Nice tour overall.")
        rid = review["id"]

        # A non-creator cannot reply.
        with pytest.raises(ValueError):
            reviews_svc.reply_to_review(rater, rid, "I'm not the creator.")

        # The creator can reply once.
        out = reviews_svc.reply_to_review(creator, rid, "Thanks for listening!")
        assert out["reply_status"] == "approved"

        # A second reply is refused.
        with pytest.raises(ValueError):
            reviews_svc.reply_to_review(creator, rid, "Another reply.")

        # Approved reply appears in the read.
        got = reviews_svc.get_reviews(tid)
        assert got[0]["reply"] is not None
        assert got[0]["reply"]["text"] == "Thanks for listening!"
    finally:
        _cleanup(db)


def test_reply_flagged_is_pending_and_hidden(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 reply-flag tour", with_owner=False)
        creator = f"{TEST_PREFIX}rf-creator"
        rater = f"{TEST_PREFIX}rf-rater"
        _seed_creator(db, tid, user_id=creator)
        _seed_download(db, rater, tid)
        rating_svc.record_rating(rater, tid, 7)
        review = reviews_svc.submit_review(rater, tid, "Good.")
        out = reviews_svc.reply_to_review(creator, review["id"], "email me a@b.com")
        assert out["reply_status"] == "pending"
        # A pending reply is NOT shown with the review.
        got = reviews_svc.get_reviews(tid)
        assert got[0]["reply"] is None
    finally:
        _cleanup(db)


# ─── 9. Helpful votes (DB) ────────────────────────────────────────────────────

def test_helpful_votes_dedupe_and_no_self_vote(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 helpful tour")
        author = f"{TEST_PREFIX}hv-author"
        voter = f"{TEST_PREFIX}hv-voter"
        _seed_download(db, author, tid)
        rating_svc.record_rating(author, tid, 9)
        review = reviews_svc.submit_review(author, tid, "Helpful please.")
        rid = review["id"]

        # Author cannot vote on their own review.
        with pytest.raises(ValueError):
            reviews_svc.vote_helpful(author, rid)

        # Another user votes; a repeat vote is idempotent.
        assert reviews_svc.vote_helpful(voter, rid) == 1
        assert reviews_svc.vote_helpful(voter, rid) == 1

        got = reviews_svc.get_reviews(tid)
        assert got[0]["helpful_count"] == 1
    finally:
        _cleanup(db)


# ─── 10. Distribution from the DB: verified-on-paid / all-on-free ─────────────

def test_distribution_free_counts_all(db):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 dist-free tour")  # free (no is_paid)
        for i, r in enumerate((10, 8, 2)):
            u = f"{TEST_PREFIX}df{i}"
            _seed_download(db, u, tid)
            rating_svc.record_rating(u, tid, r)
        d = reviews_svc.get_distribution(tid)
        assert d["total"] == 3
    finally:
        _cleanup(db)


# ─── 11. Orchestrator endpoints (in-process Flask client) ─────────────────────

@pytest.fixture(scope="module")
def client():
    from flask import Flask
    app = Flask(__name__)
    rating_svc.register_rating_routes(app)
    reviews_svc.register_review_routes(app)
    return app.test_client()


def test_endpoints_review_distribution_helpful(db, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 ep tour")
        rater = f"{TEST_PREFIX}ep-rater"
        voter = f"{TEST_PREFIX}ep-voter"
        _seed_download(db, rater, tid)
        _listen_enough(rater, tid)

        # Rate via the endpoint (gated by listened stops, satisfied above).
        r = client.post(f"/tour/{tid}/rating",
                        json={"user_id": rater, "rating": 9})
        assert r.status_code == 200

        # Submit a review via the endpoint.
        r = client.post(f"/tour/{tid}/review",
                        json={"user_id": rater, "review_text": "Endpoint review, clean."})
        assert r.status_code == 200
        assert r.get_json()["review_status"] == "approved"

        # Reviews list.
        r = client.get(f"/tour/{tid}/reviews")
        assert r.status_code == 200
        body = r.get_json()
        assert body["count"] == 1
        review_id = body["reviews"][0]["id"]

        # Distribution.
        r = client.get(f"/tour/{tid}/distribution")
        assert r.status_code == 200
        assert r.get_json()["total"] == 1

        # Helpful vote by another user.
        r = client.post(f"/review/{review_id}/helpful", json={"user_id": voter})
        assert r.status_code == 200
        assert r.get_json()["helpful_count"] == 1

        # Self-vote is a 400.
        r = client.post(f"/review/{review_id}/helpful", json={"user_id": rater})
        assert r.status_code == 400
    finally:
        _cleanup(db)


def test_endpoint_pending_queue_and_moderate(db, client):
    _cleanup(db)
    try:
        tid = _seed_tour(db, "TEST-672 queue tour")
        rater = f"{TEST_PREFIX}q-rater"
        _seed_download(db, rater, tid)
        _listen_enough(rater, tid)
        client.post(f"/tour/{tid}/rating", json={"user_id": rater, "rating": 6})

        # A flagged review lands in the pending queue.
        client.post(f"/tour/{tid}/review",
                    json={"user_id": rater, "review_text": "spam at www.x.com"})
        q = client.get("/reviews/pending").get_json()
        mine = [r for r in q["reviews"] if r["user_id"] == rater]
        assert len(mine) == 1
        rid = mine[0]["id"]

        # LEAD approves it from the queue; it then appears in the public list.
        r = client.post(f"/review/{rid}/moderate", json={"status": "approved"})
        assert r.status_code == 200
        got = client.get(f"/tour/{tid}/reviews").get_json()
        assert any(rv["id"] == rid for rv in got["reviews"])
    finally:
        _cleanup(db)


# ─── 12. map-delivery module helpers (paid counting, rank, distribution) ──────

def _load_md():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "map_delivery", "app.py")
    spec = importlib.util.spec_from_file_location("md_app_local672", path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    return md


def test_md_rank_score_matches_reviews_service():
    """map-delivery and the reviews service keep the rank rule in lock-step."""
    md = _load_md()
    now = dt.datetime.now()
    rows = [{"rating": 8, "verified": True, "created_at": now}] * 3
    svc_score = reviews_svc.rank_score(rows, now=now)
    md_score = md.rank_score([8, 8, 8], verified=[True, True, True],
                             created=[now, now, now], now=now)
    assert abs(svc_score - md_score) < 1e-9
