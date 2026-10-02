#!/usr/bin/env python3
"""
News Quota Integration Tests — fail-CLOSED + news_max_minutes
=============================================================
Verifies the behavior reviewed in:
  claude_review_news_quota_failclosed_implementation_2026_06_10.md

Cases:
  T1  Missing/anonymous secret_id      -> 401, and NO article_requests row created
  T2  Over quota                       -> 429 (usage seeded via SQL; gate returns before generation)
  T3  Under quota (gate passes)         -> not 401/429/503  [OPTIONAL: triggers full generation]
  T4  Quota-check DB down               -> 503             [OPERATOR-ASSISTED: see notes]
  T5  Long article truncated to budget  -> stored narration <= budget words  [OPTIONAL: heavy]

Design notes
------------
* The fail-closed GATE (401/429/503) returns BEFORE generation, so T1/T2/T4 are cheap — they do not
  run the (slow, cost-bearing) news pipeline.
* T2 seeds rows directly into `article_requests` so we hit the cap without generating real articles.
* T3 and T5 DO run the real generator/processor, so they are opt-in (--run-generate / --test-truncation).
* T4 cannot flip a deployed service's env from here; the operator points the news services' DB_HOST at an
  unreachable value first, then runs with --test-db-down. The script only asserts the 503.

Usage
-----
  # Cloud gateway (default). Needs GATEWAY_API_KEY and DB access (Cloud SQL proxy or in-cluster):
  python test_news_quota_integration.py

  # Local Docker:
  python test_news_quota_integration.py --local

  # Explicit base url and api key:
  python test_news_quota_integration.py --base-url https://api.audioura.com --api-key KEY

  # Include the heavy / opt-in cases:
  python test_news_quota_integration.py --run-generate --test-truncation

  # 503 case (after you have pointed the news services at an unreachable DB):
  python test_news_quota_integration.py --test-db-down

  # Keep seeded rows for inspection (skip teardown):
  python test_news_quota_integration.py --keep

DB config comes from the same env vars the services use (with safe local defaults):
  DB_HOST DB_NAME DB_USER DB_PASSWORD DB_PORT
Override the narration column if your schema stores generated text elsewhere:
  NARRATION_COLUMN (default: article_text)

Requires: requests, psycopg2 (pip install requests psycopg2-binary)
"""
import os
import sys
import json
import time
import uuid
import argparse
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
CLOUD_URL = "https://api.audioura.com"
LOCAL_URL = os.getenv("NEWS_LOCAL_URL", "http://localhost:5009")  # set to your news-orchestrator local port

API_KEY = os.getenv("GATEWAY_API_KEY", "")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_db_config as _db_cfg

DB = _db_cfg()

TEST_USER = "ITEST-NEWS-QUOTA"          # dedicated id; never a real user
TEST_PLAN = "itest"                     # dedicated plan; torn down at the end
NARRATION_COLUMN = os.getenv("NARRATION_COLUMN", "article_text")  # confirm w/ schema if generator stores elsewhere
WPM = int(os.getenv("NEWS_WPM", "150"))
GENERATE_PATH = "/generate-news"

# A long article (~6000 words) for the truncation case
LONG_ARTICLE = " ".join(
    "This is sentence number %d about the city and its long and storied history of notable events." % i
    for i in range(450)
)

results = []  # (name, passed, detail)


def record(name, passed, detail=""):
    results.append((name, passed, detail))
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# DB helpers (graceful skip if psycopg2 / DB unavailable)
# --------------------------------------------------------------------------- #
def db_conn():
    import psycopg2
    return psycopg2.connect(**DB)


def db_available():
    try:
        c = db_conn(); c.close(); return True
    except Exception as e:
        print(f"  (DB unavailable: {e})")
        return False


def setup_db(news_per_period, news_max_minutes=10):
    """Create the test plan + user; clear any prior usage."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
                           news_per_period, news_period, news_max_minutes, downloads_unlimited)
        VALUES (%s, 1, 30, 120, %s, 'week', %s, true)
        ON CONFLICT (plan_id) DO UPDATE SET
            news_per_period = EXCLUDED.news_per_period,
            news_max_minutes = EXCLUDED.news_max_minutes
    """, (TEST_PLAN, news_per_period, news_max_minutes))
    cur.execute("""
        INSERT INTO users (secret_id, plan) VALUES (%s, %s)
        ON CONFLICT (secret_id) DO UPDATE SET plan = EXCLUDED.plan
    """, (TEST_USER, TEST_PLAN))
    cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (TEST_USER,))
    conn.commit(); cur.close(); conn.close()


def seed_usage(n):
    """Insert n completed article_requests dated now (counts toward this week's news quota)."""
    import psycopg2
    conn = db_conn(); cur = conn.cursor()
    for _ in range(n):
        cur.execute("""
            INSERT INTO article_requests
                (article_id, secret_id, request_string, article_text, status, created_at, started_at)
            VALUES (%s, %s, %s, %s, 'completed', NOW(), NOW())
        """, (str(uuid.uuid4()), TEST_USER, "itest-seed", psycopg2.Binary(b"seed")))
    conn.commit(); cur.close(); conn.close()


def count_usage():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) FROM article_requests
                   WHERE secret_id = %s AND created_at >= date_trunc('week', CURRENT_DATE)""", (TEST_USER,))
    n = cur.fetchone()[0]; cur.close(); conn.close(); return n


def latest_narration_words():
    """Word count of the most recent generated narration for the test user."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute(f"""SELECT {NARRATION_COLUMN} FROM article_requests
                    WHERE secret_id = %s ORDER BY created_at DESC LIMIT 1""", (TEST_USER,))
    row = cur.fetchone(); cur.close(); conn.close()
    if not row or row[0] is None:
        return None
    val = row[0]
    if hasattr(val, "tobytes"):
        val = val.tobytes()
    if isinstance(val, (bytes, bytearray)):
        val = bytes(val).decode("utf-8", "ignore")
    return len(val.split())


def teardown_db():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM article_requests WHERE secret_id = %s", (TEST_USER,))
    cur.execute("DELETE FROM users WHERE secret_id = %s", (TEST_USER,))
    cur.execute("DELETE FROM plans WHERE plan_id = %s", (TEST_PLAN,))
    conn.commit(); cur.close(); conn.close()


# --------------------------------------------------------------------------- #
# HTTP helper
# --------------------------------------------------------------------------- #
def post_news(base_url, payload, timeout=30):
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    return requests.post(f"{base_url}{GENERATE_PATH}", json=payload, headers=headers, timeout=timeout)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def t1_anonymous_401(base_url, have_db):
    print("\n--- T1: anonymous/missing secret_id -> 401, no row created ---")
    before = count_usage() if have_db else None
    # (a) no secret_id key at all
    r1 = post_news(base_url, {"article_text": "hello world"})
    # (b) explicit 'anonymous'
    r2 = post_news(base_url, {"article_text": "hello world", "secret_id": "anonymous"})
    ok = r1.status_code == 401 and r2.status_code == 401
    record("T1a missing secret_id -> 401", r1.status_code == 401, f"got {r1.status_code}")
    record("T1b secret_id='anonymous' -> 401", r2.status_code == 401, f"got {r2.status_code}")
    if have_db:
        after = count_usage()
        record("T1c no article_requests row created", after == before, f"before={before} after={after}")
    return ok


def t2_over_quota_429(base_url):
    print("\n--- T2: over quota -> 429 (gate returns before generation) ---")
    setup_db(news_per_period=1)     # limit = 1
    seed_usage(1)                   # used = 1  => used >= max
    r = post_news(base_url, {"article_text": "hello world", "secret_id": TEST_USER})
    ok = r.status_code == 429
    detail = f"got {r.status_code}"
    try:
        body = r.json()
        detail += f", error={body.get('error')}, used={body.get('used')}, max={body.get('max')}"
    except Exception:
        pass
    record("T2 over quota -> 429", ok, detail)
    return ok


def t3_under_quota_passes(base_url):
    print("\n--- T3: under quota -> gate passes (OPTIONAL, runs full generation) ---")
    setup_db(news_per_period=10)    # plenty of room
    # clear usage already done in setup; used = 0 < 10
    r = post_news(base_url, {"article_text": "The museum opened in 1899. It holds many works.",
                             "secret_id": TEST_USER, "major_points_count": 0}, timeout=180)
    ok = r.status_code not in (401, 429, 503)
    record("T3 under quota -> not blocked by gate", ok, f"got {r.status_code} (expect 200, or a 5xx from generation, but NOT 401/429/503)")
    return ok


def t4_db_down_503(base_url):
    print("\n--- T4: quota-check DB down -> 503 (OPERATOR-ASSISTED) ---")
    print("  Pre-req: news services' DB_HOST must be pointed at an unreachable value, then redeployed.")
    r = post_news(base_url, {"article_text": "hello world", "secret_id": TEST_USER})
    ok = r.status_code == 503
    record("T4 DB down -> 503 (not 200)", ok, f"got {r.status_code}")
    return ok


def t5_truncation(base_url):
    print("\n--- T5: long article truncated to news_max_minutes budget (OPTIONAL, heavy) ---")
    setup_db(news_per_period=10, news_max_minutes=10)   # budget = 10 * WPM words
    budget = 10 * WPM
    word_count = len(LONG_ARTICLE.split())
    r = post_news(base_url, {"article_text": LONG_ARTICLE, "secret_id": TEST_USER,
                             "major_points_count": 0}, timeout=300)
    if r.status_code != 200:
        record("T5 generation completed", False, f"got {r.status_code}; cannot check truncation")
        return False
    # allow async pipeline a moment to store the processed narration
    time.sleep(3)
    stored = latest_narration_words()
    if stored is None:
        record("T5 narration readable", False, f"could not read column '{NARRATION_COLUMN}' — set NARRATION_COLUMN")
        return False
    # generous tolerance: budget plus a small margin for the sentence-boundary backoff
    ok = stored <= budget + 50
    record("T5 narration <= budget", ok,
           f"input={word_count}w, budget={budget}w, stored={stored}w (col={NARRATION_COLUMN})")
    return ok


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="Test against local Docker (NEWS_LOCAL_URL)")
    ap.add_argument("--base-url", default=None, help="Explicit base url (overrides --local/cloud)")
    ap.add_argument("--api-key", default=None, help="X-API-Key (overrides GATEWAY_API_KEY env)")
    ap.add_argument("--run-generate", action="store_true", help="Include T3 (runs full generation)")
    ap.add_argument("--test-truncation", action="store_true", help="Include T5 (heavy; runs full generation)")
    ap.add_argument("--test-db-down", action="store_true", help="Run only T4 (operator must break DB first)")
    ap.add_argument("--keep", action="store_true", help="Skip DB teardown (leave seeded rows)")
    args = ap.parse_args()

    global API_KEY
    if args.api_key:
        API_KEY = args.api_key
    base_url = args.base_url or (LOCAL_URL if args.local else CLOUD_URL)

    print("=" * 70)
    print(f"News quota integration tests  |  base_url={base_url}")
    print(f"DB={DB['host']}:{DB['port']}/{DB['dbname']}  user={DB['user']}  WPM={WPM}")
    print(f"API key: {'set' if API_KEY else 'MISSING (cloud cost-bearing endpoints may 401/503)'}")
    print("=" * 70)

    have_db = db_available()
    if not have_db:
        print("  WARNING: DB not reachable — T2/T5 (SQL-dependent) will be skipped.")

    try:
        if args.test_db_down:
            t4_db_down_503(base_url)
        else:
            t1_anonymous_401(base_url, have_db)
            if have_db:
                t2_over_quota_429(base_url)
            else:
                record("T2 over quota -> 429", False, "skipped: no DB")
            if args.run_generate and have_db:
                t3_under_quota_passes(base_url)
            if args.test_truncation and have_db:
                t5_truncation(base_url)
    finally:
        if have_db and not args.keep and not args.test_db_down:
            try:
                teardown_db()
                print("\n  (teardown complete)")
            except Exception as e:
                print(f"\n  (teardown failed: {e})")

    # Summary
    print("\n" + "=" * 70)
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    for name, p, detail in results:
        print(f"  {'PASS' if p else 'FAIL'}  {name}")
    print(f"\n  {passed}/{total} checks passed")
    print("=" * 70)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
