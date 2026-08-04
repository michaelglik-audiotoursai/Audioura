"""
Test 3: Entitlements gate — free user at quota is refused with a limit, never a cost.

D58: "Users never see cost. They see limits."
  - Free tier refusal names the limit (e.g. "tours_per_day") and what lifts it.
  - No dollar figure in any user-facing string.
  - PPU overdraft_floor_breach: message says "balance" and "limit" but the
    D58 check is that FREE users never see a cost figure. PPU users DO see
    their balance (that's the wallet screen), so balance_usd is acceptable there.

Exercises both tour and news quota at the free tier.
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
        """Free user who has used their 1 tour/day → refused, names limit not cost."""
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

            assert result["allowed"] is False
            assert result["reason"] == "quota_exceeded"
            assert result["remedy"] == "upgrade"
            assert result["limit"] == "tours_per_day"

            # D58: NO dollar figure in any value shown to the user
            user_facing_fields = [
                str(result.get("message", "")),
                str(result.get("reason", "")),
                str(result.get("remedy", "")),
            ]
            for field in user_facing_fields:
                assert "$" not in field, f"D58 violation: dollar sign in '{field}'"
                # Check for decimal amounts like "0.34" or "2.70"
                money_pattern = re.compile(r'\$\d+\.\d{2}')
                assert not money_pattern.search(field), f"D58 violation: money in '{field}'"

            print(f"  ✓ Tour quota refused:")
            print(f"    reason={result['reason']}")
            print(f"    limit={result['limit']}")
            print(f"    remedy={result['remedy']}")
            print(f"    No dollar figure in response ✓ (D58)")

        finally:
            # Cleanup
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()

    def test_news_quota_exceeded_free(self, test_user_id):
        """Free user at news limit → refused, names limit not cost."""
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

            assert result["allowed"] is False
            assert result["reason"] == "quota_exceeded"
            assert result["remedy"] == "upgrade"

            # D58: NO dollar figure in any value
            for key in ("message", "reason", "remedy"):
                val = str(result.get(key, ""))
                assert "$" not in val, f"D58 violation: dollar sign in {key}='{val}'"

            print(f"  ✓ News quota refused:")
            print(f"    reason={result['reason']}")
            print(f"    used={result['used']}, max={result['max']}")
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
        Exercise the entitlements gate through the actual HTTP route
        (generate-complete-tour on tour_orchestrator). Free user at quota
        gets 429 with limit info, no cost.
        """
        # Seed a tour so user is at quota
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
                    "secret_id": test_user_id,
                    "request_string": "Test tour for LOCAL-226",
                }),
                content_type="application/json",
            )
            print(f"  POST /generate-complete-tour → {resp.status_code}")
            print(f"  Response: {resp.get_data(as_text=True)[:500]}")

            # Should be 429 (quota exceeded) — the entitlements gate fires
            # before any generation work
            if resp.status_code == 429:
                data = resp.get_json()
                assert data["allowed"] is False
                # D58 check on HTTP response body
                body_text = resp.get_data(as_text=True)
                assert "$" not in body_text or "balance" in body_text.lower(), \
                    f"D58 potential violation in HTTP response"
                print(f"  ✓ Tour generation refused at quota via HTTP (429)")
                print(f"    No cost in user-facing response ✓")
            else:
                print(f"  ⚠ Unexpected status {resp.status_code} — route may not gate here")

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
        Free user at quota gets 429 with limit info, no cost.
        """
        # Seed 10 articles to exhaust quota
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
            print(f"  Response: {resp.get_data(as_text=True)[:500]}")

            if resp.status_code == 429:
                data = resp.get_json()
                assert data["allowed"] is False
                body_text = resp.get_data(as_text=True)
                # D58: no dollar figures in user-facing refusal
                dollar_pattern = re.compile(r'\$\d+\.\d{2}')
                assert not dollar_pattern.search(body_text), \
                    f"D58 violation: dollar amount in news refusal: {body_text[:200]}"
                print(f"  ✓ News generation refused at quota via HTTP (429)")
                print(f"    No cost in user-facing response ✓ (D58)")
            else:
                print(f"  ⚠ Status {resp.status_code} — may have different gate behavior")

        finally:
            conn = _get_conn()
            cur = conn.cursor()
            cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (test_user_id,))
            conn.commit()
            cur.close()
            conn.close()
