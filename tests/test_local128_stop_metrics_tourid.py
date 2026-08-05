#!/usr/bin/env python3
"""
LOCAL-128: Guard test — stop_metrics.tour_id is populated via the production code path.

This test exercises the REAL function `link_stop_metrics_to_tour` from
tour_orchestrator_service.py — not a simulation of its SQL. If someone
removes or breaks the UPDATE in that function, this test fails.

Proves both directions:
  - WITH the function intact: tour_id is set, resolves to audio_tours → PASS
  - WITHOUT the function (returns 0 rows updated): tour_id stays NULL → FAIL

LEAD requirement: the test must import the orchestrator function and call it,
not reproduce its SQL. (Bounce 2026-08-02: previous test passed with UPDATE
commented out because it contained its own copy of the SQL.)
"""
import sys
import os
import uuid

# Add parent dir so we can import tour_orchestrator_service
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Override DB env vars BEFORE importing the orchestrator, so
# link_stop_metrics_to_tour connects to the host-side port (5433)
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_PORT', '5433')
os.environ.setdefault('DB_NAME', 'audiotours')
os.environ.setdefault('DB_USER', 'admin')
os.environ.setdefault('DB_PASSWORD', 'password123')

# Import the production function under test
from tour_orchestrator_service import link_stop_metrics_to_tour

# Import the test DB helper for setup/teardown
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from db_connection import get_connection


def main():
    conn = get_connection()
    cur = conn.cursor()

    # Use a unique job_id to avoid colliding with real data
    test_job_id = f"LOCAL128_TEST_{uuid.uuid4().hex[:12]}"
    test_tour_name = f"LOCAL-128 Guard Test {test_job_id}"
    test_request_string = f"test_request_{test_job_id}"

    print("=" * 70)
    print("LOCAL-128 GUARD TEST: link_stop_metrics_to_tour (production path)")
    print("=" * 70)

    try:
        # ─── Step 1: Record counts BEFORE ─────────────────────────────────────
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        tours_before = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM stop_metrics")
        sm_before = cur.fetchone()[0]
        print(f"\n  BEFORE: audio_tours={tours_before}, stop_metrics={sm_before}")

        # ─── Step 2: Simulate store_audio_tour (insert test tour row) ─────────
        cur.execute("""
            INSERT INTO audio_tours (tour_name, request_string, number_requested, lat, lng, is_test)
            VALUES (%s, %s, 1, 43.7009, 7.2684, true)
            RETURNING id
        """, (test_tour_name, test_request_string))
        test_tour_id = cur.fetchone()[0]
        conn.commit()
        print(f"\n  Step 2: Created test tour id={test_tour_id}")

        # ─── Step 3: Simulate _persist_icon_metrics (insert stop_metrics, no tour_id)
        cur.execute("""
            INSERT INTO stop_metrics (job_id, tour_id, stop_index, stop_title, i_con,
                                      class_details, class_historic, class_social,
                                      paragraphs, evaluator_version)
            VALUES (%s, NULL, 1, 'Test Stop', 3.50, 0.400, 0.350, 0.250,
                    '[{"text":"Test paragraph","i_con":3.5}]'::jsonb, '1.0.0')
        """, (test_job_id,))
        conn.commit()
        print(f"  Step 3: Inserted stop_metrics row with job_id={test_job_id}, tour_id=NULL")

        # ─── Step 4: Verify tour_id is NULL before calling production function ─
        cur.execute(
            "SELECT tour_id FROM stop_metrics WHERE job_id = %s",
            (test_job_id,)
        )
        row = cur.fetchone()
        assert row is not None, "stop_metrics row not found"
        assert row[0] is None, f"Expected tour_id=NULL before fix, got {row[0]}"
        print(f"  Step 4: Confirmed tour_id=NULL (pre-fix state)")

        # ─── Step 5: Call the PRODUCTION function from tour_orchestrator_service ─
        # This is the critical difference from the bounced test: we call the real
        # function, not a copy of its SQL. If the UPDATE inside it is removed,
        # this returns 0 and step 6 fails.
        updated = link_stop_metrics_to_tour(test_tour_id, test_job_id)
        print(f"  Step 5: link_stop_metrics_to_tour returned: {updated}")
        assert updated == 1, (
            f"FAIL: link_stop_metrics_to_tour updated {updated} rows, expected 1. "
            f"The UPDATE in the production function may be missing or broken."
        )

        # ─── Step 6: THE GUARD — tour_id is non-null and resolves to audio_tours ─
        cur.execute("""
            SELECT sm.tour_id, at.id, at.tour_name
            FROM stop_metrics sm
            JOIN audio_tours at ON sm.tour_id = at.id
            WHERE sm.job_id = %s
        """, (test_job_id,))
        result = cur.fetchone()
        assert result is not None, (
            "FAIL: JOIN returned no rows — tour_id does not resolve to audio_tours"
        )
        assert result[0] == test_tour_id, f"FAIL: tour_id={result[0]}, expected {test_tour_id}"
        assert result[1] == test_tour_id, f"FAIL: audio_tours.id mismatch"
        print(f"  Step 6: ✓ GUARD PASSED — tour_id={result[0]} resolves to audio_tours.id={result[1]}")
        print(f"           tour_name: {result[2]}")

        # ─── Step 7: Verify FK integrity (no orphan references) ───────────────
        cur.execute("""
            SELECT COUNT(*) FROM stop_metrics sm
            WHERE sm.job_id = %s
              AND sm.tour_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM audio_tours WHERE id = sm.tour_id)
        """, (test_job_id,))
        orphans = cur.fetchone()[0]
        assert orphans == 0, f"FAIL: {orphans} orphan stop_metrics rows"
        print(f"  Step 7: ✓ FK integrity verified — no orphan references")

        # ─── Step 8: Verify idempotency (re-running doesn't double-update) ────
        updated2 = link_stop_metrics_to_tour(test_tour_id, test_job_id)
        assert updated2 == 0, (
            f"FAIL: Second call updated {updated2} rows — the AND tour_id IS NULL "
            f"guard is missing or broken."
        )
        print(f"  Step 8: ✓ Idempotency verified — second call updated 0 rows")

        # ─── Step 9: Record counts AFTER and clean up ─────────────────────────
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        tours_after = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM stop_metrics")
        sm_after = cur.fetchone()[0]
        print(f"\n  AFTER (before cleanup): audio_tours={tours_after}, stop_metrics={sm_after}")

        # Clean up test data
        cur.execute("DELETE FROM stop_metrics WHERE job_id = %s", (test_job_id,))
        cur.execute("DELETE FROM audio_tours WHERE id = %s", (test_tour_id,))
        conn.commit()

        # Verify cleanup
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        tours_final = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM stop_metrics")
        sm_final = cur.fetchone()[0]
        print(f"  AFTER (cleanup): audio_tours={tours_final}, stop_metrics={sm_final}")
        assert tours_final == tours_before, f"Leak: audio_tours was {tours_before}, now {tours_final}"
        assert sm_final == sm_before, f"Leak: stop_metrics was {sm_before}, now {sm_final}"
        print(f"  ✓ No data leaked — counts restored to original")

        print("\n" + "=" * 70)
        print("LOCAL-128 GUARD TEST: ALL PASSED")
        print("=" * 70)

    except AssertionError as e:
        # Clean up on failure too
        try:
            cur.execute("DELETE FROM stop_metrics WHERE job_id = %s", (test_job_id,))
            cur.execute("DELETE FROM audio_tours WHERE id = %s AND tour_name = %s",
                        (test_tour_id, test_tour_name))
            conn.commit()
        except Exception:
            pass
        print(f"\n  ✗ ASSERTION FAILED: {e}")
        cur.close()
        conn.close()
        return 1
    except Exception as e:
        # Clean up on unexpected error
        try:
            cur.execute("DELETE FROM stop_metrics WHERE job_id = %s", (test_job_id,))
            conn.commit()
        except Exception:
            pass
        print(f"\n  ✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        cur.close()
        conn.close()
        return 1

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
