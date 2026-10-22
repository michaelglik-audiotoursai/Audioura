"""
test_local734_per_store_route.py — LOCAL-734 end-to-end, DB-backed route test
for the per_store tour purchase path through POST /purchases/verify.

This complements the pure test_local734_per_store_verify.py by driving the REAL
Flask route against a Postgres (so it exercises the dispatcher, idempotency and
the tour_unlocks write), and it is the ROUTE-LEVEL red test:

  * with IAP_ALLOW_STUB_STORE unset, a store=stub tour purchase is REFUSED (402,
    nothing written) — the test fails if it is granted;
  * with the flag on, the same purchase is GRANTED (200, one tour_unlocks row).

It is SKIPPED when no test database is reachable (e.g. CI with no Postgres), so
it never turns a missing-DB environment into a red build. Point it at a DB with
DATABASE_URL, or the default test host (localhost:5433, audiotours_test); the
LOCAL-734 live harness exposes one on localhost:5544.

Row counts for every written table are asserted before/after (D690: no deletes
of purchase-bearing rows; this test only INSERTs its own throwaway rows).
"""

import importlib.util
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
_UT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "user-tracking")
if _UT_DIR not in sys.path:
    sys.path.insert(0, _UT_DIR)

psycopg2 = pytest.importorskip("psycopg2")


def _candidate_urls():
    if os.environ.get("DATABASE_URL"):
        yield os.environ["DATABASE_URL"]
    # The LOCAL-734 live harness, then the standard Mac Mini test port.
    yield "postgresql://admin:password123@localhost:5544/audiotours_test"
    yield "postgresql://admin:password123@localhost:5433/audiotours_test"


def _reachable_db():
    for url in _candidate_urls():
        try:
            c = psycopg2.connect(url, connect_timeout=3)
            # [LOCAL-734] autocommit so the probe never leaves an open
            # transaction holding an ACCESS SHARE lock on tour_unlocks while the
            # app route's `ALTER TABLE tour_unlocks ADD COLUMN …` waits for an
            # ACCESS EXCLUSIVE lock — the self-deadlock LEAD hit (43-min hang).
            c.autocommit = True
            # The path needs these tables; skip (not fail) if the schema is absent.
            cur = c.cursor()
            cur.execute("SELECT to_regclass('public.purchases'), "
                        "to_regclass('public.tour_unlocks'), "
                        "to_regclass('public.audio_tours')")
            regs = cur.fetchone()
            cur.close()
            if all(regs):
                return url, c
            c.close()
        except Exception:
            continue
    return None, None


_DB_URL, _CONN = _reachable_db()
pytestmark = pytest.mark.skipif(
    _DB_URL is None,
    reason="no test Postgres with the purchase schema reachable "
           "(set DATABASE_URL or run the LOCAL-734 live harness on :5544)")


def _load_ea():
    os.environ["DATABASE_URL"] = _DB_URL
    os.environ["ALLOW_UNAUTHENTICATED_ENTITLEMENTS"] = "true"
    spec = importlib.util.spec_from_file_location(
        "entitlements_api_route734", os.path.join(_UT_DIR, "entitlements_api.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["entitlements_api_route734"] = mod
    spec.loader.exec_module(mod)
    mod.API_KEY = ""
    mod.IAP_VERIFY_MODE = "per_store"
    return mod


@pytest.fixture()
def ctx():
    ea = _load_ea()
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ea.entitlements_bp)
    app.testing = True
    client = app.test_client()
    # A throwaway tour row the unlock can key on.
    tour_id = 734900 + (uuid.uuid4().int % 90)
    conn = psycopg2.connect(_DB_URL)
    # [LOCAL-734] The test's OWN connection is autocommit so its _counts SELECTs
    # never leave a transaction open holding an ACCESS SHARE lock on tour_unlocks
    # while the app route runs `ALTER TABLE tour_unlocks ADD COLUMN …` (needs
    # ACCESS EXCLUSIVE). That overlap was the 43-minute self-deadlock LEAD hit.
    conn.autocommit = True
    cur = conn.cursor()
    # Belt-and-braces guard: if a lock is ever contended again, fail fast (30 s)
    # instead of hanging the suite.
    cur.execute("SET statement_timeout = '30s'")
    # Run the one schema migration the route would otherwise ALTER on first call,
    # NOW, while nothing else holds the table — so the route's idempotent
    # `ADD COLUMN IF NOT EXISTS` is a no-op and never needs the exclusive lock
    # mid-request. autocommit means each statement commits immediately.
    cur.execute("ALTER TABLE tour_unlocks ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ")
    cur.execute("ALTER TABLE tour_unlocks "
                "ADD COLUMN IF NOT EXISTS consumed_by_download_id VARCHAR(255)")
    cur.execute("INSERT INTO audio_tours (id, tour_name, request_string, is_test) VALUES (%s, %s, %s, TRUE) "
                "ON CONFLICT (id) DO NOTHING RETURNING id",
                (tour_id, f"LOCAL-734 route test {tour_id}-{uuid.uuid4().hex[:8]}", "LOCAL-734 route test"))
    created_tour = cur.fetchone() is not None  # LEAD: delete only a row WE created
    yield ea, client, conn, cur, tour_id
    # Clean up ONLY our own throwaway rows (never a bulk/purchase-bearing delete
    # of anyone else's data — D690). Remove our unlock+purchase+tour by key.
    try:
        cur.execute("DELETE FROM tour_unlocks WHERE tour_id = %s", (tour_id,))
        cur.execute("DELETE FROM purchases WHERE transaction_id LIKE %s",
                    (f"t734route-{tour_id}%",))
        if created_tour:
            cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (tour_id,))
            row = cur.fetchone()
            if row and row[0] is True:  # D141: confirm is_test right before the delete
                cur.execute("DELETE FROM audio_tours WHERE id = %s", (tour_id,))
    finally:
        cur.close()
        conn.close()


def _counts(cur, tour_id, txid):
    cur.execute("SELECT count(*) FROM tour_unlocks WHERE tour_id = %s", (tour_id,))
    unlocks = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM purchases WHERE transaction_id = %s", (txid,))
    purchases = cur.fetchone()[0]
    return unlocks, purchases


def test_red_route_stub_tour_refused_without_flag(ctx):
    ea, client, conn, cur, tour_id = ctx
    ea.IAP_ALLOW_STUB_STORE = False  # the default; GCloud never sets it on.
    txid = f"t734route-{tour_id}-refuse"
    before = _counts(cur, tour_id, txid)
    r = client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": txid,
        "product": "audioura.tour.usd5", "user_id": "u734route", "tour_id": str(tour_id),
    })
    # Refused, not granted.
    assert r.status_code == 402, r.get_json()
    assert r.get_json().get("raw_status") == "stub_store_not_allowed"
    # NOTHING written — the red test fails if a row appeared.
    after = _counts(cur, tour_id, txid)
    assert after == before == (0, 0), (
        f"a stub tour purchase wrote rows without the flag: before={before} after={after}")


def test_route_stub_tour_granted_with_flag(ctx):
    ea, client, conn, cur, tour_id = ctx
    ea.IAP_ALLOW_STUB_STORE = True
    txid = f"t734route-{tour_id}-grant"
    before = _counts(cur, tour_id, txid)
    assert before == (0, 0)
    r = client.post("/purchases/verify", json={
        "store": "stub", "transaction_id": txid,
        "product": "audioura.tour.usd5", "user_id": "u734route", "tour_id": str(tour_id),
    })
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["verified"] is True and body["unlocked"] is True
    after = _counts(cur, tour_id, txid)
    assert after == (1, 1), f"grant did not write exactly one unlock+purchase: {after}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
