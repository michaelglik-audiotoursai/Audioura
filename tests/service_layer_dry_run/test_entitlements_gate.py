"""
Test 3: Entitlements gate — free user at quota is refused with a limit, never a cost.

D58: "Users never see cost. They see limits."
  - Free tier refusal names the limit (e.g. "tours_per_day") and what lifts it.
  - No dollar figure in any user-facing string.

TIGHTENING (per LEAD bounce):
  Every assertion that could be satisfied by the fail-closed path (used=9999)
  now asserts the EXACT expected value. If the database is broken, used will
  be 9999 instead of the seeded count, and the test will fail — which is the
  point.
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


class TestEntitlementsGateFreeUser:
    """Free user at quota: refused with limit, never a cost."""

    def test_tour_quota_exceeded_free(self, test_user_id):
        """Free user who has used their 1 tour/day → refused, names limit not cost.

        TIGHT: asserts used==1 (not just allowed==False). If get_tours_used_today
        returns 9999 from fail-closed, this fails.
        """
        from entitlements import check_tour_quota

        # Seed a tour_request so the user appears to have used their quota
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tour_requests (secret_id, request_string, started_at, source)
            VALUES (%s, 'Test Tour', NOW(), 'orchestrator')
        """, (test_user_id,))
        conn.commit()
        cur.close()
        conn.close()

        try:
            result = check_tour_quota(test_user_id, requested_stops=5)
            print(f"  Tour quota check: {result}")

            # Verdict assertions
            assert result["allowed"] is False
            assert result["reason"] == "quota_exceeded"
            assert result["remedy"] == "upgrade"
            assert result["limit"] == "tours_per_day"

            # TIGHT VALUE ASSERTIONS — distinguishes healthy from fail-closed
            assert result["used"] == 1, (
                f"Expected used==1 (1 seeded tour), got used=={result['used']}. "
                f"If 9999, the DB query errored and returned fail-closed."
            )
            assert result["max"] == 1, (
                f"Expected max==1 (free tier tours_per_day), got max=={result['max']}"
            )

            # D58: NO dollar figure in any value shown to the user
            user_facing_fields = [
                str(result.get("message", "")),
                str(result.get("reason", "")),
                str(result.get("remedy", "")),
            ]
            for field in user_facing_fields:
                assert "$" not in field, f"D58 violation: dollar sign in '{field}'"
                money_pattern = re.compile(r'\$\d+\.\d{2}')
                assert not money_pattern.search(field), f"D58 violation: money in '{field}'"

            print(f"  ✓ Tour quota refused:")
            print(f"    reason={result['reason']}, used={result['used']}, max={result['max']}")
            print(f"    remedy={result['remedy']}")
            print(f"    No dollar figure in response ✓ (D58)")

        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_news_quota_exceeded_free(self, test_user_id):
        """Free user at news limit → refused, names limit not cost.

        TIGHT: asserts used==10 (exactly the number seeded). If the
        newsletters_article_link table is missing, get_news_used_period
        returns 9999 (fail-closed), and this assertion catches it.
        """
        from entitlements import check_news_quota

        # Seed 10 article_requests (free limit is 10/week)
        conn = _get_conn()
        cur = conn.cursor()
        for i in range(10):
            article_id = f"test-art-{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at)
                VALUES (%s, %s, 'Test Article', %s, 'completed', NOW())
            """, (article_id, test_user_id, b"some text"))
        conn.commit()
        cur.close()
        conn.close()

        try:
            result = check_news_quota(test_user_id)
            print(f"  News quota check: {result}")

            # Verdict assertions
            assert result["allowed"] is False
            assert result["reason"] == "quota_exceeded"
            assert result["remedy"] == "upgrade"

            # TIGHT VALUE ASSERTIONS — the key fix from the bounce
            assert result["used"] == 10, (
                f"Expected used==10 (10 seeded articles), got used=={result['used']}. "
                f"If 9999, newsletters_article_link is missing or query errored."
            )
            assert result["max"] == 10, (
                f"Expected max==10 (free tier news_per_period), got max=={result['max']}"
            )

            # D58: NO dollar figure in any value
            for key in ("message", "reason", "remedy"):
                val = str(result.get(key, ""))
                assert "$" not in val, f"D58 violation: dollar sign in {key}='{val}'"

            print(f"  ✓ News quota refused:")
            print(f"    reason={result['reason']}, used={result['used']}, max={result['max']}")
            print(f"    remedy={result['remedy']}")
            print(f"    No dollar figure in response ✓ (D58)")

        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_tour_quota_refusal_via_http(self, tour_orchestrator_client, test_user_id):
        """
        Exercise the entitlements gate through the actual HTTP route.
        Free user at quota gets 429 with correct used count, no cost.

        TIGHT: asserts used==1 in the JSON response body.

        NOTE: tour_orchestrator reads `user_id` from JSON (not `secret_id`
        like news_orchestrator). This is the real API contract.
        """
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tour_requests (secret_id, request_string, started_at, source)
            VALUES (%s, 'Test Tour HTTP', NOW(), 'orchestrator')
        """, (test_user_id,))
        conn.commit()
        cur.close()
        conn.close()

        try:
            import json
            resp = tour_orchestrator_client.post(
                "/generate-complete-tour",
                data=json.dumps({
                    "location": "Nice, France",
                    "tour_type": "walking",
                    "total_stops": 5,
                    "user_id": test_user_id,
                    "request_string": "Test tour for LOCAL-226",
                }),
                content_type="application/json",
            )
            print(f"  POST /generate-complete-tour → {resp.status_code}")
            body_text = resp.get_data(as_text=True)
            print(f"  Response: {body_text[:500]}")

            assert resp.status_code == 429, (
                f"Expected 429 (quota exceeded), got {resp.status_code}. "
                f"Body: {body_text[:200]}"
            )
            data = resp.get_json()
            assert data["allowed"] is False

            # TIGHT: assert the count from the response
            assert data["used"] == 1, (
                f"Expected used==1 in HTTP response, got {data.get('used')}. "
                f"9999 means fail-closed from DB error."
            )

            # D58 check: no dollar figures in user-facing refusal
            dollar_pattern = re.compile(r'\$\d+\.\d{2}')
            assert not dollar_pattern.search(body_text), \
                f"D58 violation: dollar amount in tour refusal: {body_text[:200]}"

            print(f"  ✓ Tour generation refused at quota via HTTP (429)")
            print(f"    used={data['used']}, max={data['max']}")
            print(f"    No cost in user-facing response ✓ (D58)")

        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_news_quota_refusal_via_http(self, news_orchestrator_client, test_user_id):
        """
        Exercise news quota gate through generate-news HTTP route.
        Free user at quota gets 429 with correct used count, no cost.

        TIGHT: asserts used==10 in the JSON response.
        """
        conn = _get_conn()
        cur = conn.cursor()
        for i in range(10):
            article_id = f"test-art-http-{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at)
                VALUES (%s, %s, 'Test Article HTTP', %s, 'completed', NOW())
            """, (article_id, test_user_id, b"some text"))
        conn.commit()
        cur.close()
        conn.close()

        try:
            import json
            resp = news_orchestrator_client.post(
                "/generate-news",
                data=json.dumps({
                    "article_text": "This is a test article for LOCAL-226.",
                    "request_string": "Test News",
                    "secret_id": test_user_id,
                    "major_points_count": 3,
                }),
                content_type="application/json",
            )
            print(f"  POST /generate-news → {resp.status_code}")
            body_text = resp.get_data(as_text=True)
            print(f"  Response: {body_text[:500]}")

            assert resp.status_code == 429, (
                f"Expected 429 (news quota exceeded), got {resp.status_code}. "
                f"Body: {body_text[:200]}"
            )
            data = resp.get_json()
            assert data["allowed"] is False

            # TIGHT: assert the EXACT count
            assert data["used"] == 10, (
                f"Expected used==10 in HTTP response, got {data.get('used')}. "
                f"9999 means newsletters_article_link table is missing or query errored."
            )

            # D58: no dollar figures in user-facing refusal
            dollar_pattern = re.compile(r'\$\d+\.\d{2}')
            assert not dollar_pattern.search(body_text), \
                f"D58 violation: dollar amount in news refusal: {body_text[:200]}"

            print(f"  ✓ News generation refused at quota via HTTP (429)")
            print(f"    used={data['used']}, max={data['max']}")
            print(f"    No cost in user-facing response ✓ (D58)")

        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_news_quota_healthy_returns_exact_count(self, test_user_id):
        """Verify get_news_used_period returns the exact seeded count, not 9999.

        This is the direct diagnostic: seed 3 articles, assert used==3.
        If newsletters_article_link is missing, returns 9999 → test fails.
        """
        from entitlements import get_news_used_period

        conn = _get_conn()
        cur = conn.cursor()
        for i in range(3):
            article_id = f"test-exact-{uuid.uuid4().hex[:8]}"
            cur.execute("""
                INSERT INTO article_requests (article_id, secret_id, request_string, article_text, status, created_at)
                VALUES (%s, %s, 'Test Exact Count', %s, 'completed', NOW())
            """, (article_id, test_user_id, b"count test"))
        conn.commit()
        cur.close()
        conn.close()

        try:
            used = get_news_used_period(test_user_id, 'week')
            print(f"  get_news_used_period returned: {used}")
            assert used == 3, (
                f"Expected used==3 (3 seeded articles), got {used}. "
                f"9999 = newsletters_article_link missing. Other = query bug."
            )
            print(f"  ✓ Exact count verified: seeded 3 articles, got used=={used}")
        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_tour_quota_healthy_returns_exact_count(self, test_user_id):
        """Verify get_tours_used_today returns the exact seeded count, not 9999.

        Seed 1 tour request, assert used==1.
        """
        from entitlements import get_tours_used_today

        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tour_requests (secret_id, request_string, started_at, source)
            VALUES (%s, 'Test Exact Tour', NOW(), 'orchestrator')
        """, (test_user_id,))
        conn.commit()
        cur.close()
        conn.close()

        try:
            used = get_tours_used_today(test_user_id)
            print(f"  get_tours_used_today returned: {used}")
            assert used == 1, (
                f"Expected used==1 (1 seeded tour), got {used}. "
                f"9999 = query error (fail-closed)."
            )
            print(f"  ✓ Exact count verified: seeded 1 tour, got used=={used}")
        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()
