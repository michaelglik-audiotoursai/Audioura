"""
Shared fixtures for LOCAL-226 service-layer dry run.

Configures environment to point at audiotours_subscribed (port 5433)
and provides Flask test clients for wallet_api, news_orchestrator,
news_processor, and tour_orchestrator — all WITHOUT binding a port.
"""
import os
import sys
import uuid
import pytest
import psycopg2

# ─── Environment setup BEFORE any service imports ────────────────────────────
# Point all billing modules at audiotours_subscribed via localhost:5433
os.environ["DB_HOST"] = "localhost"
os.environ["DB_PORT"] = "5433"
os.environ["DB_NAME"] = "audiotours_subscribed"
os.environ["DB_USER"] = "admin"
os.environ["DB_PASSWORD"] = "password123"
os.environ["DATABASE_URL"] = (
    "postgresql://admin:password123@localhost:5433/audiotours_subscribed"
)
# Pricing multiplier (task says do NOT change)
os.environ.setdefault("PRICING_MULTIPLIER", "5.0")
# Internal service secret for trusted-caller path
os.environ.setdefault("INTERNAL_SERVICE_SECRET", "test-internal-secret-226")

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _get_conn():
    """Direct DB connection to audiotours_subscribed."""
    return psycopg2.connect(
        host="localhost", port="5433",
        dbname="audiotours_subscribed",
        user="admin", password="password123",
    )


@pytest.fixture(scope="session")
def db_conn():
    """Session-scoped DB connection for verification."""
    conn = _get_conn()
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def test_user_id():
    """Create a test user in audiotours_subscribed; clean up after session."""
    user_id = f"test-local226-{uuid.uuid4().hex[:8]}"
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (secret_id, app_version, plan) VALUES (%s, '9.9.9', 'free')",
        (user_id,),
    )
    conn.commit()
    cur.close()
    conn.close()
    yield user_id
    # Cleanup
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM cost_ledger WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (user_id,))
    cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE secret_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(scope="session")
def ppu_user_id():
    """Create a PPU user with active subscription and $10 balance."""
    user_id = f"test-local226-ppu-{uuid.uuid4().hex[:8]}"
    conn = _get_conn()
    cur = conn.cursor()
    # Create user with ppu plan
    cur.execute(
        "INSERT INTO users (secret_id, app_version, plan) VALUES (%s, '9.9.9', 'ppu')",
        (user_id,),
    )
    # Create active subscription
    cur.execute("""
        INSERT INTO subscriptions (user_id, tier, state, period_start, period_end)
        VALUES (%s, 'ppu', 'active', NOW() - interval '5 days', NOW() + interval '25 days')
    """, (user_id,))
    # Create wallet_subscription row
    cur.execute("""
        INSERT INTO wallet_subscription (user_id, tier, period_start, period_end)
        VALUES (%s, 'ppu', NOW() - interval '5 days', NOW() + interval '25 days')
    """, (user_id,))
    # Seed $10 balance via wallet_ledger
    cur.execute("""
        INSERT INTO wallet_ledger (user_id, movement_type, amount_cents, balance_after_cents, idempotency_key, description)
        VALUES (%s, 'topup', 1000, 1000, %s, 'Seed topup for LOCAL-226 test')
    """, (user_id, f"seed:{user_id}:initial"))
    cur.execute("""
        INSERT INTO wallet_balance_cache (user_id, balance_cents, updated_at)
        VALUES (%s, 1000, NOW())
    """, (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    yield user_id
    # Cleanup
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM wallet_ledger WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM wallet_balance_cache WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM cost_ledger WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM wallet_subscription WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM subscriptions WHERE user_id = %s", (user_id,))
    cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (user_id,))
    cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (user_id,))
    cur.execute("DELETE FROM users WHERE secret_id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(scope="session")
def wallet_client():
    """Flask test client for the tour_orchestrator (which hosts wallet_api)."""
    # We import and build a minimal Flask app that registers wallet_bp
    from flask import Flask
    from wallet_api import wallet_bp
    app = Flask(__name__)
    app.register_blueprint(wallet_bp)
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def news_orchestrator_client():
    """Flask test client for the news_orchestrator_service."""
    # Import the Flask app directly — it's defined at module level
    from news_orchestrator_service import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def news_processor_client():
    """Flask test client for the news_processor_service."""
    from news_processor_service import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def tour_orchestrator_client():
    """Flask test client for the tour_orchestrator_service."""
    from tour_orchestrator_service import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
