"""
Shared fixtures for billing dry-run tests against audiotours_subscribed.
Connects to localhost:5433/audiotours_subscribed explicitly.
Never touches audiotours.
"""
import os
import sys
import uuid
import psycopg2
import pytest

# ── Point all billing code at audiotours_subscribed on host port ──────────────
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["DB_NAME"] = "audiotours_subscribed"
os.environ["DB_USER"] = "admin"
os.environ["DB_PASSWORD"] = "password123"
os.environ["DATABASE_URL"] = (
    "postgresql://admin:password123@localhost:5433/audiotours_subscribed"
)

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def get_subscribed_conn():
    """Direct connection to audiotours_subscribed."""
    return psycopg2.connect(
        host="localhost", port=5433,
        dbname="audiotours_subscribed",
        user="admin", password="password123",
    )


@pytest.fixture
def conn():
    """Yield a connection to audiotours_subscribed; rollback on teardown."""
    c = get_subscribed_conn()
    yield c
    c.rollback()
    c.close()


@pytest.fixture
def test_user_id():
    """A unique user_id for this test run."""
    return f"dryrun-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def setup_test_user(test_user_id):
    """Create a user in audiotours_subscribed for the lifecycle test.
    Tear down all rows for this user after the test.
    """
    c = get_subscribed_conn()
    cur = c.cursor()
    # Insert user on free plan
    cur.execute(
        "INSERT INTO users (secret_id, plan) VALUES (%s, 'free') ON CONFLICT DO NOTHING",
        (test_user_id,),
    )
    c.commit()
    yield
    # Cleanup: remove all trace of this user (order matters for FK constraints)
    c2 = get_subscribed_conn()
    c2.autocommit = True
    cur2 = c2.cursor()
    # Tables with user_id column
    for table in [
        "wallet_ledger", "wallet_balance_cache", "wallet_subscription",
        "cost_ledger", "subscriptions", "subscription_transactions",
        "low_balance_events",
    ]:
        try:
            cur2.execute(f"DELETE FROM {table} WHERE user_id = %s", (test_user_id,))
        except Exception:
            pass
    # Tables with secret_id column
    for table in ["tour_requests", "article_requests"]:
        try:
            cur2.execute(f"DELETE FROM {table} WHERE secret_id = %s", (test_user_id,))
        except Exception:
            pass
    # Finally the user
    try:
        cur2.execute("DELETE FROM users WHERE secret_id = %s", (test_user_id,))
    except Exception:
        pass
    cur2.close()
    c2.close()
    cur.close()
    c.close()
