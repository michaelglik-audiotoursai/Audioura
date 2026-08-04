"""
Test 5: Falsification — prove these tests detect a schema break.

This test renames newsletters_article_link away, asserts that
get_news_used_period returns 9999 (the broken-state signature),
and restores the table. If a future change makes the suite pass
despite a missing table, this test will catch it.

The guard logic ensures the table is ALWAYS restored, even on crash.
"""
import pytest
import psycopg2


def _get_conn():
    return psycopg2.connect(
        host="localhost", port="5433",
        dbname="audiotours_subscribed",
        user="admin", password="password123",
    )


class TestFalsificationGuard:
    """Prove the tests CAN detect a schema break."""

    def test_missing_table_produces_9999_not_correct_count(self, test_user_id):
        """
        Rename newsletters_article_link → _tmp_falsify.
        Seed 3 articles. Call get_news_used_period.
        Assert it returns 9999 (the fail-closed sentinel), NOT 3.
        Restore the table.

        This proves that our tight assertion (used==3) would FAIL
        if the table were missing — which is the entire purpose.
        """
        import uuid
        from entitlements import get_news_used_period

        conn = _get_conn()
        cur = conn.cursor()

        # Seed 3 articles
        for i in range(3):
            article_id = f"test-falsify-{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at)
                VALUES (%s, %s, 'Falsification Test', %s, 'completed', NOW())
            """, (article_id, test_user_id, b"falsify"))
        conn.commit()
        cur.close()
        conn.close()

        # Break the schema
        conn = _get_conn()
        cur = conn.cursor()
        try:
            cur.execute("ALTER TABLE newsletters_article_link RENAME TO _tmp_falsify_226")
            conn.commit()

            # The broken query should return 9999 (fail-closed)
            result = get_news_used_period(test_user_id, 'week')
            print(f"  With table missing: get_news_used_period returned {result}")
            assert result == 9999, (
                f"Expected 9999 (fail-closed) with table missing, got {result}. "
                f"If this passes with the correct count, the NOT EXISTS subquery "
                f"is no longer depending on newsletters_article_link."
            )
            print(f"  ✓ Confirmed: missing table → returns 9999 (detectable)")

        finally:
            # ALWAYS restore — even on assertion failure
            try:
                cur.execute("ALTER TABLE _tmp_falsify_226 RENAME TO newsletters_article_link")
                conn.commit()
                print(f"  ✓ Table restored: newsletters_article_link")
            except Exception as restore_err:
                # Table might not exist if rename failed — try direct create
                conn.rollback()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS newsletters_article_link (
                        id SERIAL PRIMARY KEY,
                        newsletters_id INTEGER,
                        article_requests_id VARCHAR(500),
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_nal_article_requests_id
                        ON newsletters_article_link(article_requests_id)
                """)
                conn.commit()
                print(f"  ⚠ Restore via rename failed ({restore_err}); recreated table")
            cur.close()
            conn.close()

            # Cleanup seeded articles
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_restored_table_returns_correct_count(self, test_user_id):
        """After falsification, confirm the table is healthy and returns exact count."""
        import uuid
        from entitlements import get_news_used_period

        conn = _get_conn()
        cur = conn.cursor()
        # Verify table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'newsletters_article_link'
            )
        """)
        exists = cur.fetchone()[0]
        assert exists, "newsletters_article_link does not exist after falsification test!"

        # Seed 2 articles and check
        for i in range(2):
            article_id = f"test-restore-{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at)
                VALUES (%s, %s, 'Restore Check', %s, 'completed', NOW())
            """, (article_id, test_user_id, b"restore"))
        conn.commit()
        cur.close()
        conn.close()

        try:
            result = get_news_used_period(test_user_id, 'week')
            print(f"  After restore: get_news_used_period returned {result}")
            assert result == 2, (
                f"Expected 2 after table restore, got {result}. "
                f"Table may not have been properly restored."
            )
            print(f"  ✓ Table healthy after falsification: used=={result}")
        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()
