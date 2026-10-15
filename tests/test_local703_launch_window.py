"""
test_local703_launch_window.py — LOCAL-703 / D664.

The community LAUNCH WINDOW in communities_api.py. A new community must win its
first two QUALIFYING members (excluding the owner) within COMMUNITY_LAUNCH_HOURS
(168 h) of creation, or the launch-window job archives it and its invite code
stops working. The organiser sees a live countdown and is reminded at 48 h and
12 h left.

Covered (every spec case in the task):

  * DEADLINE on create          — a new community carries launch_deadline and a
                                  launch payload with members_needed=2.
  * PAID launches on 2 paid      — 1 paid member is not launched; the 2nd paid
                                  member launches it; the owner is excluded; a
                                  FREE join never counts toward a PAID community.
  * FREE launches on 2 joins     — two free joins (owner excluded) launch it.
  * JOB archives a miss          — a past-deadline, un-launched community is
                                  archived (reason launch_window_missed) and its
                                  code resolves to 410 community_closed.
  * LAUNCHED never archived      — a launched community past the deadline is left
                                  alone by the job.
  * REMINDERS 48/12 h once each  — the job stamps each reminder exactly once.
  * hours_left MATH              — the payload's countdown is correct and never
                                  negative.

DB-backed, in-process Flask client (communities + entitlements blueprints), stub
IAP mode — the SAME harness as test_local702_organiser_steps_down.py. Every row
uses the 'TEST-703-' prefix; cleanup touches only those rows.
"""

import os
import sys
import importlib.util
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("IAP_VERIFY_MODE", "stub")
os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, get_database_url  # noqa: E402

TEST_PREFIX = "TEST-703-"


@pytest.fixture(scope="module", autouse=True)
def _isolate_entitlements_env():
    keys = ("GATEWAY_API_KEY", "IAP_VERIFY_MODE", "ALLOW_UNAUTHENTICATED_ENTITLEMENTS")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ["GATEWAY_API_KEY"] = ""
    os.environ["IAP_VERIFY_MODE"] = "stub"
    os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _load_module(name, rel_path):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def modules(_isolate_entitlements_env):
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    _load_module("communities_rss", "user-tracking/communities_rss.py")
    ca = _load_module("communities_api", "user-tracking/communities_api.py")
    ea = _load_module("entitlements_api_703", "user-tracking/entitlements_api.py")
    ea.API_KEY = ""
    ea.IAP_VERIFY_MODE = "stub"
    return {"ca": ca, "ea": ea}


@pytest.fixture(scope="module")
def client(modules):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(modules["ca"].communities_bp)
    app.register_blueprint(modules["ea"].entitlements_bp)
    app.testing = True
    return app.test_client()


@pytest.fixture
def db():
    conn = get_connection()
    yield conn
    conn.close()


def _cleanup(db):
    cur = db.cursor()
    cur.execute("SELECT id FROM communities WHERE name LIKE %s", (TEST_PREFIX + '%',))
    ids = [r[0] for r in cur.fetchall()]
    if ids:
        for tbl in ("community_organiser_offers", "community_reports",
                    "community_episodes", "community_passes",
                    "community_memberships"):
            cur.execute(f"DELETE FROM {tbl} WHERE community_id = ANY(%s)", (ids,))
        cur.execute("DELETE FROM communities WHERE id = ANY(%s)", (ids,))
    cur.execute("DELETE FROM purchases WHERE transaction_id LIKE %s", (TEST_PREFIX + '%',))
    cur.execute("DELETE FROM device_entitlement WHERE user_id LIKE %s", (TEST_PREFIX + '%',))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db):
    _cleanup(db)
    yield
    _cleanup(db)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _seed_level(user_id, level):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO device_entitlement (user_id, level, last_activity_at) "
            "VALUES (%s, %s, NOW()) "
            "ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level",
            (user_id, level),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _create(client, owner, name, level="l2", **overrides):
    _seed_level(owner, level)
    body = {"owner_user_id": owner, "name": name}
    body.update(overrides)
    r = client.post("/communities", json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _join_free(client, cid, user_id):
    return client.post(f"/communities/{cid}/join", json={"user_id": user_id})


def _buy_pass(client, cid, user_id, product="audioura.pass.usd5", length="month",
              txid=None):
    """Buy a community pass through the real /purchases/verify path (stub IAP)."""
    txid = txid or (TEST_PREFIX + f"txn-{user_id}-{cid}")
    return client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": txid,
        "product": product, "length": length,
        "user_id": user_id, "community_id": cid,
    })


def _paid_community(client, owner, name):
    return _create(client, owner, name, is_paid=True,
                   pass_products=[{"product_id": "audioura.pass.usd5",
                                   "length": "month"}])


def _set_deadline(db, cid, when):
    """Force a community's launch_deadline to an absolute instant."""
    cur = db.cursor()
    cur.execute("UPDATE communities SET launch_deadline = %s WHERE id = %s",
                (when, cid))
    db.commit()
    cur.close()


def _row(db, cid):
    cur = db.cursor()
    cur.execute(
        "SELECT status, launched_at, archived_reason, archived_at, "
        "launch_reminded_48h_at, launch_reminded_12h_at "
        "FROM communities WHERE id = %s", (cid,))
    row = cur.fetchone()
    cur.close()
    return {
        "status": row[0], "launched_at": row[1], "archived_reason": row[2],
        "archived_at": row[3], "reminded_48h": row[4], "reminded_12h": row[5],
    }


def _now_utc():
    return datetime.now(timezone.utc)


# ─── DEADLINE on create ─────────────────────────────────────────────────────

def test_create_sets_launch_deadline_and_payload(client, db):
    owner = TEST_PREFIX + "cr-owner"
    c = _create(client, owner, TEST_PREFIX + "Fresh")
    assert "launch" in c
    assert c["launch"]["members_needed"] == 2
    assert c["launch"]["members_so_far"] == 0
    assert c["launch"]["launched"] is False
    assert c["launch"]["deadline"] is not None
    # The deadline is ~168 h out; hours_left is close to 168 (167 or 168).
    assert 160 <= c["launch"]["hours_left"] <= 168
    # And the DB row carries the deadline.
    assert _row(db, c["id"])["launched_at"] is None


# ─── PAID: 1 paid member not launched, 2 → launched ─────────────────────────

def test_paid_one_member_not_launched(client, db):
    owner = TEST_PREFIX + "p1-owner"
    c = _paid_community(client, owner, TEST_PREFIX + "Paid One")
    cid = c["id"]
    r = _buy_pass(client, cid, TEST_PREFIX + "p1-m1")
    assert r.status_code == 200, r.get_json()
    # The verify receipt is the membership; launch state is on the community page.
    page = client.get(f"/communities/{cid}",
                      query_string={"user_id": owner}).get_json()
    assert page["launch"]["members_so_far"] == 1
    assert page["launch"]["launched"] is False
    assert _row(db, cid)["launched_at"] is None


def test_paid_two_members_launch(client, db):
    owner = TEST_PREFIX + "p2-owner"
    c = _paid_community(client, owner, TEST_PREFIX + "Paid Two")
    cid = c["id"]
    _buy_pass(client, cid, TEST_PREFIX + "p2-m1")
    r2 = _buy_pass(client, cid, TEST_PREFIX + "p2-m2")
    assert r2.status_code == 200
    page = client.get(f"/communities/{cid}",
                      query_string={"user_id": owner}).get_json()
    assert page["launch"]["members_so_far"] == 2
    assert page["launch"]["launched"] is True
    row = _row(db, cid)
    assert row["launched_at"] is not None
    assert row["status"] == "active"  # launch does not change status


def test_paid_owner_does_not_count(client, db):
    """The owner buying a pass of their own community does not count toward the
    bar — only members excluding the owner do."""
    owner = TEST_PREFIX + "po-owner"
    c = _paid_community(client, owner, TEST_PREFIX + "Owner Excluded")
    cid = c["id"]
    # Owner "buys" (counts as owner, excluded) + one real member → still 1.
    _buy_pass(client, cid, owner, txid=TEST_PREFIX + "owner-self")
    _buy_pass(client, cid, TEST_PREFIX + "po-m1")
    page = client.get(f"/communities/{cid}",
                      query_string={"user_id": owner}).get_json()
    assert page["launch"]["members_so_far"] == 1
    assert page["launch"]["launched"] is False
    assert _row(db, cid)["launched_at"] is None


def test_free_join_does_not_count_for_paid(client, db):
    """A paid community's bar is PAID members; a free join of a paid community
    (which the API refuses with 402 anyway) never counts. We assert that a paid
    community with only paid members launches, and that the paid count is what
    gates it."""
    owner = TEST_PREFIX + "fp-owner"
    c = _paid_community(client, owner, TEST_PREFIX + "Paid Needs Paid")
    cid = c["id"]
    # A free join is refused for a paid community (402) — it cannot pad the bar.
    r = _join_free(client, cid, TEST_PREFIX + "fp-freeloader")
    assert r.status_code == 402
    # Only after two PAID members does it launch.
    _buy_pass(client, cid, TEST_PREFIX + "fp-m1")
    assert _row(db, cid)["launched_at"] is None
    _buy_pass(client, cid, TEST_PREFIX + "fp-m2")
    assert _row(db, cid)["launched_at"] is not None


# ─── FREE: 2 joins → launched ───────────────────────────────────────────────

def test_free_two_joins_launch(client, db):
    owner = TEST_PREFIX + "f2-owner"
    c = _create(client, owner, TEST_PREFIX + "Free Two")  # free by default
    cid = c["id"]
    r1 = _join_free(client, cid, TEST_PREFIX + "f2-m1")
    assert r1.status_code == 200
    assert r1.get_json()["launch"]["members_so_far"] == 1
    assert r1.get_json()["launch"]["launched"] is False
    r2 = _join_free(client, cid, TEST_PREFIX + "f2-m2")
    assert r2.status_code == 200
    assert r2.get_json()["launch"]["members_so_far"] == 2
    assert r2.get_json()["launch"]["launched"] is True
    assert _row(db, cid)["launched_at"] is not None


def test_free_owner_does_not_count(client, db):
    owner = TEST_PREFIX + "fo-owner"
    c = _create(client, owner, TEST_PREFIX + "Free Owner Excluded")
    cid = c["id"]
    # Owner "joins" own community (excluded) + one member → 1, not launched.
    _join_free(client, cid, owner)
    r = _join_free(client, cid, TEST_PREFIX + "fo-m1")
    assert r.get_json()["launch"]["members_so_far"] == 1
    assert r.get_json()["launch"]["launched"] is False
    assert _row(db, cid)["launched_at"] is None


# ─── JOB archives a past-deadline unlaunched community; code → 410 ──────────

def test_job_archives_past_deadline_miss_and_code_410(client, db):
    owner = TEST_PREFIX + "mj-owner"
    c = _create(client, owner, TEST_PREFIX + "Missed It")
    cid = c["id"]
    code = c["join_code"]
    # One member only — short of the bar.
    _join_free(client, cid, TEST_PREFIX + "mj-m1")
    # Deadline already passed.
    _set_deadline(db, cid, _now_utc() - timedelta(hours=1))
    r = client.post("/communities/launch-window/run")
    assert r.status_code == 200
    assert cid in r.get_json()["archived"]
    row = _row(db, cid)
    assert row["status"] == "archived"
    assert row["archived_reason"] == "launch_window_missed"
    assert row["archived_at"] is not None
    # The invite code now resolves to 410 community_closed.
    rc = client.get(f"/communities/by-code/{code}")
    assert rc.status_code == 410
    assert rc.get_json()["error"] == "community_closed"
    assert "closed" in rc.get_json()["message"].lower()


def test_job_is_idempotent(client, db):
    owner = TEST_PREFIX + "ij-owner"
    c = _create(client, owner, TEST_PREFIX + "Idem Job")
    cid = c["id"]
    _set_deadline(db, cid, _now_utc() - timedelta(hours=2))
    first = client.post("/communities/launch-window/run").get_json()
    assert cid in first["archived"]
    second = client.post("/communities/launch-window/run").get_json()
    assert cid not in second["archived"]  # already archived, not touched again


def test_job_leaves_in_window_community_active(client, db):
    owner = TEST_PREFIX + "iw-owner"
    c = _create(client, owner, TEST_PREFIX + "Still In Window")
    cid = c["id"]
    # Deadline well in the future (default ~168 h) — not archived.
    r = client.post("/communities/launch-window/run")
    assert cid not in r.get_json()["archived"]
    assert _row(db, cid)["status"] == "active"


# ─── LAUNCHED never archived by the job ─────────────────────────────────────

def test_launched_never_archived(client, db):
    owner = TEST_PREFIX + "ln-owner"
    c = _create(client, owner, TEST_PREFIX + "Launched Stays")
    cid = c["id"]
    _join_free(client, cid, TEST_PREFIX + "ln-m1")
    _join_free(client, cid, TEST_PREFIX + "ln-m2")  # launches it
    assert _row(db, cid)["launched_at"] is not None
    # Push the deadline into the past — a launched community is still safe.
    _set_deadline(db, cid, _now_utc() - timedelta(hours=5))
    r = client.post("/communities/launch-window/run")
    assert cid not in r.get_json()["archived"]
    row = _row(db, cid)
    assert row["status"] == "active"
    assert row["archived_reason"] is None


# ─── REMINDERS at 48 h and 12 h left, once each ─────────────────────────────

def test_reminder_48h_fires_once(client, db):
    owner = TEST_PREFIX + "r48-owner"
    c = _create(client, owner, TEST_PREFIX + "Remind 48")
    cid = c["id"]
    # 40 h left → inside the 48 h window, outside 12 h.
    _set_deadline(db, cid, _now_utc() + timedelta(hours=40))
    first = client.post("/communities/launch-window/run").get_json()
    assert cid in first["reminded_48h"]
    assert cid not in first["reminded_12h"]
    assert _row(db, cid)["reminded_48h"] is not None
    # A second run does not re-send the 48 h reminder.
    second = client.post("/communities/launch-window/run").get_json()
    assert cid not in second["reminded_48h"]


def test_reminder_12h_fires_once(client, db):
    owner = TEST_PREFIX + "r12-owner"
    c = _create(client, owner, TEST_PREFIX + "Remind 12")
    cid = c["id"]
    # 6 h left → inside BOTH windows; both reminders fire (once each).
    _set_deadline(db, cid, _now_utc() + timedelta(hours=6))
    first = client.post("/communities/launch-window/run").get_json()
    assert cid in first["reminded_48h"]
    assert cid in first["reminded_12h"]
    row = _row(db, cid)
    assert row["reminded_48h"] is not None
    assert row["reminded_12h"] is not None
    # Neither re-sends.
    second = client.post("/communities/launch-window/run").get_json()
    assert cid not in second["reminded_48h"]
    assert cid not in second["reminded_12h"]


def test_launched_community_gets_no_reminders(client, db):
    owner = TEST_PREFIX + "lr-owner"
    c = _create(client, owner, TEST_PREFIX + "Launched No Remind")
    cid = c["id"]
    _join_free(client, cid, TEST_PREFIX + "lr-m1")
    _join_free(client, cid, TEST_PREFIX + "lr-m2")  # launched
    _set_deadline(db, cid, _now_utc() + timedelta(hours=6))
    r = client.post("/communities/launch-window/run").get_json()
    assert cid not in r["reminded_48h"]
    assert cid not in r["reminded_12h"]


# ─── hours_left MATH ────────────────────────────────────────────────────────

def test_hours_left_math_and_never_negative(client, db):
    owner = TEST_PREFIX + "hl-owner"
    c = _create(client, owner, TEST_PREFIX + "Hours Math")
    cid = c["id"]
    # Exactly ~50 h left → hours_left should read 50 (ceil of a hair under 50).
    _set_deadline(db, cid, _now_utc() + timedelta(hours=50))
    page = client.get(f"/communities/{cid}",
                      query_string={"user_id": owner}).get_json()
    assert 49 <= page["launch"]["hours_left"] <= 50
    # A past deadline reads 0 (never negative), even before the job runs.
    _set_deadline(db, cid, _now_utc() - timedelta(hours=3))
    page2 = client.get(f"/communities/{cid}",
                       query_string={"user_id": owner}).get_json()
    assert page2["launch"]["hours_left"] == 0


def test_last_partial_hour_reads_one(client, db):
    owner = TEST_PREFIX + "lph-owner"
    c = _create(client, owner, TEST_PREFIX + "Last Hour")
    cid = c["id"]
    # 20 minutes left → the final partial hour still reads 1 (hourly cadence).
    _set_deadline(db, cid, _now_utc() + timedelta(minutes=20))
    page = client.get(f"/communities/{cid}",
                      query_string={"user_id": owner}).get_json()
    assert page["launch"]["hours_left"] == 1
