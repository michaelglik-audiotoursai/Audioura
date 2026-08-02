#!/usr/bin/env python3
"""
Tour Quota Integration Tests — fail-CLOSED + single-count + rollback
====================================================================
Companion to test_news_quota_integration.py, for the TOUR path. Verifies the fixes reviewed in:
  claude_review_double_count_final_fix_implementation_2026_06_10.md

Cases:
  T1  Missing/empty user_id            -> 401, and NO orchestrator usage row created
  T2  Over daily limit                 -> 429 (usage seeded via SQL; gate returns before generation)
  T2b Tester limit honored             -> 429 only at the tester's higher limit (proves limit value, cheap)
  T3  Under limit (gate passes)         -> 200 queued, AND exactly ONE orchestrator row added (no double-count)
        [OPTIONAL: --run-generate, triggers real generation]
  T4  Quota-check DB down               -> 503  [OPERATOR-ASSISTED: --test-db-down]
  T5  Failed tour rolls back usage row  -> MANUAL procedure (see bottom); --check-rollback <job_id> verifies

Design
------
* The fail-closed GATE (401/429/503) returns BEFORE generation, so T1/T2/T2b/T4 are cheap (no OpenAI/Polly).
* The quota counter counts ONLY rows with source='orchestrator' (the tracking service's rows default to
  'tracking' and are excluded), so seeded rows use source='orchestrator'.
* T3 proves single-count: one allowed tour must add exactly ONE orchestrator row (the v18/v19 double-count fix).

Usage
-----
  python test_tour_quota_integration.py                 # cloud gateway, cheap gate tests
  python test_tour_quota_integration.py --local         # local Docker (TOUR_LOCAL_URL)
  python test_tour_quota_integration.py --base-url https://api.audioura.com --api-key KEY
  python test_tour_quota_integration.py --run-generate  # include T3 (real generation)
  python test_tour_quota_integration.py --test-db-down  # T4 only (operator broke DB first)
  python test_tour_quota_integration.py --check-rollback <job_id>   # verify a forced-failure row is gone
  python test_tour_quota_integration.py --keep          # skip teardown

Env: DB_HOST DB_NAME DB_USER DB_PASSWORD DB_PORT  |  GATEWAY_API_KEY  |  TOUR_LOCAL_URL
Confirm the route if needed: TOUR_PATH (default /generate-complete-tour)
Requires: requests, psycopg2 (pip install requests psycopg2-binary)

LOCAL-141: Migrated to TestTourFactory.adopt_and_ensure_flagged() — the flag
is set structurally after HTTP creation, regardless of Docker env vars.
"""
import os
import sys
import uuid
import argparse
import requests
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
CLOUD_URL = "https://api.audioura.com"
LOCAL_URL = os.getenv("TOUR_LOCAL_URL", "http://localhost:5008")  # set to your tour-orchestrator local port
API_KEY = os.getenv("GATEWAY_API_KEY", "")
TOUR_PATH = os.getenv("TOUR_PATH", "/generate-complete-tour")     # confirm against gateway_routes.yaml if unsure

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_db_config as _db_cfg
from test_tour_factory import TestTourFactory

# Factory instance — adopt tours created via HTTP so is_test=TRUE is structural
_factory = TestTourFactory(auto_cleanup=True)

DB = _db_cfg()

TEST_USER = "ITEST-TOUR-QUOTA"     # dedicated id; never a real user
TEST_PLAN = "itest_tour"           # dedicated plan; torn down at the end

results = []


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


def setup_db(tours_per_day):
    """Create the test plan + user; clear any prior tour usage."""
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""
        INSERT INTO plans (plan_id, tours_per_day, tour_max_poi, tour_max_minutes,
                           news_per_period, news_period, news_max_minutes, downloads_unlimited)
        VALUES (%s, %s, 30, 120, 10, 'week', 10, true)
        ON CONFLICT (plan_id) DO UPDATE SET tours_per_day = EXCLUDED.tours_per_day
    """, (TEST_PLAN, tours_per_day))
    cur.execute("""
        INSERT INTO users (secret_id, plan) VALUES (%s, %s)
        ON CONFLICT (secret_id) DO UPDATE SET plan = EXCLUDED.plan
    """, (TEST_USER, TEST_PLAN))
    cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (TEST_USER,))
    conn.commit(); cur.close(); conn.close()


def seed_usage(n):
    """Insert n orchestrator-source tour_requests dated today (counted toward tours_per_day)."""
    conn = db_conn(); cur = conn.cursor()
    for _ in range(n):
        cur.execute("""
            INSERT INTO tour_requests (secret_id, tour_id, status, started_at, source)
            VALUES (%s, %s, 'started', NOW(), 'orchestrator')
        """, (TEST_USER, str(uuid.uuid4())))
    conn.commit(); cur.close(); conn.close()


def count_orchestrator_usage():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("""SELECT COUNT(*) FROM tour_requests
                   WHERE secret_id = %s AND started_at::date = CURRENT_DATE
                   AND source = 'orchestrator'""", (TEST_USER,))
    n = cur.fetchone()[0]; cur.close(); conn.close(); return n


def row_exists(tour_id):
    conn = db_conn(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tour_requests WHERE tour_id = %s AND source = 'orchestrator'", (tour_id,))
    n = cur.fetchone()[0]; cur.close(); conn.close(); return n > 0


def teardown_db():
    conn = db_conn(); cur = conn.cursor()
    cur.execute("DELETE FROM tour_requests WHERE secret_id = %s", (TEST_USER,))
    cur.execute("DELETE FROM users WHERE secret_id = %s", (TEST_USER,))
    cur.execute("DELETE FROM plans WHERE plan_id = %s", (TEST_PLAN,))
    conn.commit(); cur.close(); conn.close()


# --------------------------------------------------------------------------- #
# HTTP helper
# --------------------------------------------------------------------------- #
def post_tour(base_url, payload, timeout=30):
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    return requests.post(f"{base_url}{TOUR_PATH}", json=payload, headers=headers, timeout=timeout)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def t1_anonymous_401(base_url, have_db):
    print("\n--- T1: missing/empty user_id -> 401, no orchestrator row ---")
    before = count_orchestrator_usage() if have_db else None
    r1 = post_tour(base_url, {"location": "test", "tour_type": "walking"})           # no user_id
    r2 = post_tour(base_url, {"location": "test", "tour_type": "walking", "user_id": ""})  # empty
    record("T1a missing user_id -> 401", r1.status_code == 401, f"got {r1.status_code}")
    record("T1b empty user_id -> 401", r2.status_code == 401, f"got {r2.status_code}")
    if have_db:
        after = count_orchestrator_usage()
        record("T1c no orchestrator row created", after == before, f"before={before} after={after}")


def t2_over_quota_429(base_url, limit, label):
    print(f"\n--- T2 ({label}): over limit={limit} -> 429 (gate returns before generation) ---")
    setup_db(tours_per_day=limit)
    seed_usage(limit)             # used == limit  => used >= max
    r = post_tour(base_url, {"location": "test", "tour_type": "walking", "total_stops": 1, "user_id": TEST_USER})
    ok = r.status_code == 429
    detail = f"got {r.status_code}"
    try:
        b = r.json(); detail += f", error={b.get('error')}, used={b.get('used')}, max={b.get('max')}"
    except Exception:
        pass
    record(f"T2 over quota ({label}) -> 429", ok, detail)


def t3_allow_and_single_count(base_url):
    print("\n--- T3: under limit -> 200 queued + exactly ONE orchestrator row (no double-count) [OPTIONAL] ---")
    setup_db(tours_per_day=100)   # plenty of room; clears prior usage (count starts at 0)
    before = count_orchestrator_usage()
    r = post_tour(base_url, {"location": "test park Boston", "tour_type": "walking",
                             "total_stops": 1, "user_id": TEST_USER}, timeout=180)
    ok_gate = r.status_code not in (401, 429, 503)
    record("T3 under quota -> not blocked by gate", ok_gate,
           f"got {r.status_code} (expect 200 queued; never 401/429/503)")
    if not ok_gate:
        return
    # The orchestrator records usage synchronously when admitting the tour.
    after = count_orchestrator_usage()
    added = after - before
    record("T3 single-count: exactly ONE orchestrator row added", added == 1,
           f"before={before} after={after} added={added} (2 = double-count regression)")

    # LOCAL-141: Adopt the tour so is_test=TRUE is structural.
    # T3 generates a real tour in audio_tours — find and adopt it.
    try:
        job_data = r.json()
        job_id = job_data.get("job_id")
        if job_id:
            # Poll briefly for completion to get tour_id
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    sr = requests.get(f"{base_url}/status/{job_id}", timeout=10)
                    if sr.status_code == 200:
                        sd = sr.json()
                        tour_id = sd.get('final_tour_id')
                        if tour_id:
                            _factory.adopt_and_ensure_flagged(tour_id)
                            print(f"  ✅ Tour {tour_id} adopted and flagged is_test=TRUE")
                            break
                        if sd.get('status') in ('completed', 'error', 'failed'):
                            break
                except Exception:
                    pass
                time.sleep(3)
            else:
                # Fallback: find by name
                import psycopg2
                conn = db_conn()
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM audio_tours WHERE tour_name ILIKE %s ORDER BY id DESC LIMIT 1",
                    ('%test park Boston%',)
                )
                row = cur.fetchone()
                cur.close()
                conn.close()
                if row:
                    _factory.adopt_and_ensure_flagged(row[0])
                    print(f"  ✅ Tour {row[0]} found by name and flagged is_test=TRUE")
    except Exception as e:
        print(f"  ⚠️ Could not adopt tour (will be caught by guard): {e}")


def t4_db_down_503(base_url):
    print("\n--- T4: quota-check DB down -> 503 (OPERATOR-ASSISTED) ---")
    print("  Pre-req: tour-orchestrator's DB_HOST pointed at an unreachable value on a TEST revision.")
    r = post_tour(base_url, {"location": "test", "tour_type": "walking", "total_stops": 1, "user_id": TEST_USER})
    record("T4 DB down -> 503 (not 200)", r.status_code == 503, f"got {r.status_code}")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="Test against local Docker (TOUR_LOCAL_URL)")
    ap.add_argument("--base-url", default=None, help="Explicit base url (overrides --local/cloud)")
    ap.add_argument("--api-key", default=None, help="X-API-Key (overrides GATEWAY_API_KEY env)")
    ap.add_argument("--run-generate", action="store_true", help="Include T3 (runs real generation)")
    ap.add_argument("--test-db-down", action="store_true", help="Run only T4 (operator must break DB first)")
    ap.add_argument("--check-rollback", metavar="JOB_ID", default=None,
                    help="Verify a forced-failure tour's orchestrator row was rolled back (T5 manual)")
    ap.add_argument("--keep", action="store_true", help="Skip DB teardown")
    args = ap.parse_args()

    global API_KEY
    if args.api_key:
        API_KEY = args.api_key
    base_url = args.base_url or (LOCAL_URL if args.local else CLOUD_URL)

    print("=" * 70)
    print(f"Tour quota integration tests  |  base_url={base_url}{TOUR_PATH}")
    print(f"DB={DB['host']}:{DB['port']}/{DB['dbname']}  user={DB['user']}")
    print(f"API key: {'set' if API_KEY else 'MISSING (gateway may 401/503)'}")
    print("=" * 70)

    have_db = db_available()
    if not have_db:
        print("  WARNING: DB not reachable — T2/T2b/T3/rollback (SQL-dependent) will be skipped.")

    # T5 manual rollback verification mode
    if args.check_rollback:
        if not have_db:
            print("  Cannot verify rollback without DB."); sys.exit(1)
        gone = not row_exists(args.check_rollback)
        record(f"T5 rollback: orchestrator row for job {args.check_rollback} is gone", gone)
        sys.exit(0 if gone else 1)

    try:
        if args.test_db_down:
            t4_db_down_503(base_url)
        else:
            t1_anonymous_401(base_url, have_db)
            if have_db:
                t2_over_quota_429(base_url, limit=1, label="free")
                t2_over_quota_429(base_url, limit=100, label="tester")   # proves higher limit blocks correctly
                if args.run_generate:
                    t3_allow_and_single_count(base_url)
            else:
                record("T2 over quota -> 429", False, "skipped: no DB")
    finally:
        if have_db and not args.keep and not args.test_db_down:
            try:
                teardown_db(); print("\n  (teardown complete)")
            except Exception as e:
                print(f"\n  (teardown failed: {e})")

    print("\n" + "=" * 70)
    passed = sum(1 for _, p, _ in results if p)
    total = len(results)
    for name, p, _ in results:
        print(f"  {'PASS' if p else 'FAIL'}  {name}")
    print(f"\n  {passed}/{total} checks passed")
    print("=" * 70)
    sys.exit(0 if passed == total else 1)


# --------------------------------------------------------------------------- #
# T5 — Failed-tour rollback (MANUAL procedure, cloud_tasks path)
# --------------------------------------------------------------------------- #
# Automated forcing of a generation failure is not reliable from outside, so verify it like this:
#   1. Ensure GENERATION_MODE='cloud_tasks'. Set a TEST tour-generator/worker to fail
#      (e.g. point TOUR_GENERATOR_URL at an unreachable host, or inject a failure).
#   2. As the test user (on a plan with tours_per_day=1), POST one tour -> note the returned job_id.
#   3. Let Cloud Tasks exhaust retries (MAX_TASK_ATTEMPTS). Confirm job_status='error'.
#   4. Run:  python test_tour_quota_integration.py --check-rollback <job_id>
#      Expect PASS (the orchestrator row was deleted by the worker's final-attempt rollback).
#   5. POST another tour the same day as the test user -> expect 200 (slot was freed, not 429).
#   Also confirm queue maxAttempts == MAX_TASK_ATTEMPTS env (rollback fires on the true final attempt).

if __name__ == "__main__":
    main()
