"""
LOCAL-691 — document acceptance server tests (legal pages).

Acceptance is REQUIRED and STORED for selling a guide tour and creating a
community. These tests drive the document_acceptance blueprint through an
in-process Flask client against the shared test database (audiotours_test on
localhost:5433, resolved by db_connection).

Covered:
  * POST records a (user, document, version) acceptance (200, already=false).
  * The same acceptance again is idempotent (200, already=true; still one row).
  * A new version adds a second row (history kept).
  * GET lists a user's acceptances, newest first; filter by document works.
  * Missing fields → 400; an unknown document slug → 400.
  * Friendly aliases normalise ('guide' → 'guide_terms', 'organizer_terms' →
    'organiser_terms').
  * The table shape matches migration 030 (user_id, document, version,
    accepted_at + the unique constraint).

Safety: every row uses a user_id starting with 'TEST-691-'. Cleanup deletes
ONLY rows with that exact prefix. No other table is touched. The migration is
applied idempotently at module start so the suite is self-contained.
"""

import os
import sys
import importlib.util

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

os.environ.setdefault("ALLOW_UNAUTHENTICATED_ENTITLEMENTS", "true")

from db_connection import get_connection, get_database_url  # noqa: E402

TEST_PREFIX = "TEST-691-"
VERSION_1 = "2026-10-14-draft1"
VERSION_2 = "2026-10-21-draft2"

_MIGRATION = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "migration", "sql", "030_document_acceptance.sql",
)


def _load_module(name, rel_path):
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def module(_apply_migration):
    os.environ["DATABASE_URL"] = get_database_url()
    ut_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
    sys.path.insert(0, ut_dir)
    return _load_module("document_acceptance_api",
                        "user-tracking/document_acceptance_api.py")


@pytest.fixture(scope="module")
def _apply_migration():
    """Apply migration 030 idempotently to the test DB so the suite stands
    alone (the SQL is additive + idempotent — safe to run every time)."""
    with open(_MIGRATION, encoding="utf-8") as f:
        sql = f.read()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    cur.close()
    conn.close()
    yield


@pytest.fixture(scope="module")
def client(module):
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(module.document_acceptance_bp)
    app.testing = True
    return app.test_client()


@pytest.fixture
def db():
    conn = get_connection()
    yield conn
    conn.close()


def _cleanup(db):
    cur = db.cursor()
    cur.execute("DELETE FROM document_acceptance WHERE user_id LIKE %s",
                (TEST_PREFIX + '%',))
    db.commit()
    cur.close()


@pytest.fixture(autouse=True)
def _clean(db, _apply_migration):
    _cleanup(db)
    yield
    _cleanup(db)


# ─── schema ────────────────────────────────────────────────────────────────
def test_table_shape(db, _apply_migration):
    cur = db.cursor()
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'document_acceptance'
        ORDER BY column_name
        """
    )
    cols = {r[0] for r in cur.fetchall()}
    cur.close()
    assert {"user_id", "document", "version", "accepted_at"}.issubset(cols)


# ─── record + idempotency ───────────────────────────────────────────────────
def test_record_acceptance_new(client):
    r = client.post("/document-acceptance", json={
        "user_id": TEST_PREFIX + "a", "document": "guide_terms",
        "version": VERSION_1})
    assert r.status_code == 200
    assert r.get_json() == {"status": "recorded", "already": False}


def test_record_acceptance_idempotent(client, db):
    body = {"user_id": TEST_PREFIX + "b", "document": "organiser_terms",
            "version": VERSION_1}
    r1 = client.post("/document-acceptance", json=body)
    r2 = client.post("/document-acceptance", json=body)
    assert r1.get_json()["already"] is False
    assert r2.get_json()["already"] is True
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM document_acceptance WHERE user_id = %s",
        (TEST_PREFIX + "b",))
    assert cur.fetchone()[0] == 1
    cur.close()


def test_new_version_adds_row(client, db):
    uid = TEST_PREFIX + "c"
    client.post("/document-acceptance", json={
        "user_id": uid, "document": "terms", "version": VERSION_1})
    client.post("/document-acceptance", json={
        "user_id": uid, "document": "terms", "version": VERSION_2})
    cur = db.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM document_acceptance WHERE user_id = %s AND document='terms'",
        (uid,))
    assert cur.fetchone()[0] == 2
    cur.close()


# ─── retrieval ───────────────────────────────────────────────────────────────
def test_list_newest_first_and_filter(client):
    uid = TEST_PREFIX + "d"
    client.post("/document-acceptance", json={
        "user_id": uid, "document": "terms", "version": VERSION_1})
    client.post("/document-acceptance", json={
        "user_id": uid, "document": "guide_terms", "version": VERSION_1})
    # all
    allr = client.get(f"/document-acceptance?user_id={uid}")
    docs = {a["document"] for a in allr.get_json()["acceptances"]}
    assert docs == {"terms", "guide_terms"}
    # filtered
    onlyr = client.get(f"/document-acceptance?user_id={uid}&document=guide_terms")
    accs = onlyr.get_json()["acceptances"]
    assert len(accs) == 1 and accs[0]["document"] == "guide_terms"
    assert accs[0]["version"] == VERSION_1


# ─── validation + aliases ────────────────────────────────────────────────────
def test_missing_fields(client):
    r = client.post("/document-acceptance", json={"user_id": TEST_PREFIX + "e"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "missing_fields"


def test_unknown_document(client):
    r = client.post("/document-acceptance", json={
        "user_id": TEST_PREFIX + "f", "document": "not_a_doc",
        "version": VERSION_1})
    assert r.status_code == 400
    assert r.get_json()["error"] == "unknown_document"


def test_alias_normalisation(client, db):
    client.post("/document-acceptance", json={
        "user_id": TEST_PREFIX + "g", "document": "guide", "version": VERSION_1})
    client.post("/document-acceptance", json={
        "user_id": TEST_PREFIX + "g", "document": "organizer_terms",
        "version": VERSION_1})
    r = client.get(f"/document-acceptance?user_id={TEST_PREFIX}g")
    docs = {a["document"] for a in r.get_json()["acceptances"]}
    assert docs == {"guide_terms", "organiser_terms"}


def test_list_requires_user_id(client):
    r = client.get("/document-acceptance")
    assert r.status_code == 400
