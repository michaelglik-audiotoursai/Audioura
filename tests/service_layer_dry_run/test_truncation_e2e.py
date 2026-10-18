"""
Article truncation end-to-end through the per-plan resolution path
(LOCAL-708 / D670).

The listener's PLAN limit (plans.article_char_limit) governs article length.
truncate_for_user() resolves the device's level via the same entitlement lookup
the tour quota uses (subscription_levels.get_device_state → plans row) and reads
that plan's article_char_limit.

Requirements exercised here (against the live subscribed DB on :5433):
  - L1 (install/free listen)  → 5,000 chars, upsell notice naming 15,000.
  - L3 ($10 pack)             → 10,000 chars, no upsell.
  - admin (Administrator)     → 15,000 chars (~5 pages), no upsell.
  - No dollar figure in any user-facing string (D58).
  - Exact limit numbers in notices.

This test requires the D613 levels schema (device_entitlement table) AND the
LOCAL-708 column (plans.article_char_limit). On an un-migrated DB it SKIPS
rather than failing — LEAD applies migrations, and the pure-logic coverage in
tests/test_local708_article_length_per_plan.py proves the behaviour without a DB.
"""
import re
import uuid
import pytest
import psycopg2


def _get_conn():
    return psycopg2.connect(
        host="localhost", port="5433",
        dbname="audiotours_subscribed",
        user="admin", password="password123",
    )


def _levels_schema_ready():
    """True iff device_entitlement exists AND plans.article_char_limit exists."""
    try:
        conn = _get_conn()
    except Exception:
        return False
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'device_entitlement'"
        )
        has_table = cur.fetchone() is not None
        cur.execute(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = 'plans' AND column_name = 'article_char_limit'"
        )
        has_col = cur.fetchone() is not None
        cur.close()
        return has_table and has_col
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


pytestmark = pytest.mark.skipif(
    not _levels_schema_ready(),
    reason="D613 levels schema / plans.article_char_limit not present on :5433 "
           "(LEAD applies migrations 012/014/039)",
)


def _make_text(length):
    """Generate text of ~length chars with sentence boundaries."""
    sentence = "The quick brown fox jumps over the lazy dog. "
    repeats = (length // len(sentence)) + 1
    return (sentence * repeats)[:length]


def _device_fixture(level):
    """Create a device_entitlement row at `level`; return (user_id, cleanup)."""
    user_id = f"test-local708-{level}-{uuid.uuid4().hex[:8]}"
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO device_entitlement (user_id, level, last_activity_at) "
        "VALUES (%s, %s, NOW()) "
        "ON CONFLICT (user_id) DO UPDATE SET level = EXCLUDED.level",
        (user_id, level),
    )
    conn.commit()
    cur.close()
    conn.close()

    def cleanup():
        c = _get_conn()
        cc = c.cursor()
        cc.execute("DELETE FROM device_entitlement WHERE user_id = %s", (user_id,))
        c.commit()
        cc.close()
        c.close()

    return user_id, cleanup


@pytest.fixture
def l1_user():
    uid, cleanup = _device_fixture('l1')
    yield uid
    cleanup()


@pytest.fixture
def l3_user():
    uid, cleanup = _device_fixture('l3')
    yield uid
    cleanup()


@pytest.fixture
def admin_user():
    uid, cleanup = _device_fixture('admin')
    yield uid
    cleanup()


_DOLLAR = re.compile(r'\$\d+')


class TestPerPlanTruncationEndToEnd:

    def test_l1_truncates_at_5000(self, l1_user):
        from article_truncation import truncate_for_user
        text = _make_text(8000)
        result, was_truncated, rule = truncate_for_user(text, l1_user)
        assert was_truncated is True
        assert len(result) <= 5000, f"L1 should truncate to <=5000, got {len(result)}"
        assert rule in ("sentence_boundary", "word_boundary")
        assert "5,000" in result
        assert "15,000" in result, "L1 (entry) notice should name the higher limit"
        assert not _DOLLAR.search(result), "D58: no dollar figure"

    def test_l3_truncates_at_10000(self, l3_user):
        from article_truncation import truncate_for_user
        text = _make_text(20000)
        result, was_truncated, rule = truncate_for_user(text, l3_user)
        assert was_truncated is True
        assert len(result) <= 10000, f"L3 should truncate to <=10000, got {len(result)}"
        # KEY: if level resolution failed it would fall back to 5,000.
        assert len(result) > 5000, (
            f"Result only {len(result)} chars — level likely fell back to default 5,000"
        )
        assert "10,000" in result
        assert not _DOLLAR.search(result), "D58: no dollar figure"

    def test_admin_truncates_at_15000(self, admin_user):
        from article_truncation import truncate_for_user
        text = _make_text(30000)
        result, was_truncated, rule = truncate_for_user(text, admin_user)
        assert was_truncated is True
        assert len(result) <= 15000, f"admin should truncate to <=15000, got {len(result)}"
        # KEY: admin must get MORE than L3's 10,000 — proves per-plan resolution.
        assert len(result) > 10000, (
            f"Result only {len(result)} chars — admin level did not resolve to 15,000"
        )
        assert "15,000" in result
        assert not _DOLLAR.search(result), "D58: no dollar figure"

    def test_admin_under_limit_not_truncated(self, admin_user):
        from article_truncation import truncate_for_user
        text = _make_text(12000)  # above L1/L3 limits, below admin's 15,000
        result, was_truncated, rule = truncate_for_user(text, admin_user)
        assert was_truncated is False, (
            "12,000-char article should NOT be truncated for admin (limit 15,000); "
            "truncation here means the level resolved too low"
        )
        assert rule == "none"
        assert result == text

    def test_level_resolution_from_db(self, admin_user):
        """Directly verify the entitlement lookup returns the admin limit."""
        from article_truncation import get_article_limit_for_user
        assert get_article_limit_for_user(admin_user) == 15000
