#!/usr/bin/env python3
"""
LOCAL-139 Guard Test: No unflagged test-named tour may exist in audio_tours.

This test enforces the invariant from D38: any row whose name matches a test
marker pattern MUST have is_test=TRUE. If it doesn't, the tour is visible to
users through tours-near — which is exactly what happened with tour 132.

The pattern matches:
  - LOCAL followed by digits (e.g. "LOCAL49 Regression Test ...")
  - "Regression Test"
  - "Acceptance Test"
  - "Selective Test"
  - "NoFlag Test"

This runs as part of the normal test suite so it fires without anyone
remembering to invoke it. It is the structural counterpart to the
TestTourFactory — the factory prevents the problem, this test detects it
if anything bypasses the factory.

Usage:
    python3 tests/test_no_unflagged_test_tours.py
    # or via pytest:
    pytest tests/test_no_unflagged_test_tours.py -v
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection, check_db_available


# The canonical guard query from D38
GUARD_QUERY = """
    SELECT id, tour_name, is_test, lat, lng
    FROM audio_tours
    WHERE tour_name ~ '(LOCAL[0-9]+|Regression Test|Acceptance Test|Selective Test|NoFlag Test)'
      AND is_test IS NOT TRUE
    ORDER BY id
"""


def test_no_unflagged_test_tours():
    """
    GUARD: No test-named tour may exist with is_test != TRUE.

    If this fails, a test suite created a user-visible tour. The fix is to
    set is_test=TRUE on the offending row(s) — NEVER delete them.
    """
    if not check_db_available():
        print("SKIP: Database not available")
        return

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(GUARD_QUERY)
        unflagged = cur.fetchall()

        if unflagged:
            print("\n" + "=" * 70)
            print("❌ GUARD FAILURE: Unflagged test-named tours found!")
            print("=" * 70)
            print("\nThese tours are VISIBLE TO USERS through tours-near:")
            for row in unflagged:
                tid, name, is_test, lat, lng = row
                print(f"  id={tid:3d} is_test={is_test} lat={lat} lng={lng}")
                print(f"         name: {name}")
            print(f"\nTotal unflagged: {len(unflagged)}")
            print("\nFix: UPDATE audio_tours SET is_test = TRUE WHERE id IN (...)")
            print("Do NOT delete rows from audio_tours.")
            print("=" * 70)

        assert len(unflagged) == 0, (
            f"Found {len(unflagged)} test-named tour(s) with is_test != TRUE. "
            f"IDs: {[r[0] for r in unflagged]}. "
            f"These are VISIBLE TO USERS. Set is_test=TRUE to fix."
        )

        # Also report the count of correctly-flagged test tours for context
        cur.execute("""
            SELECT COUNT(*)
            FROM audio_tours
            WHERE tour_name ~ '(LOCAL[0-9]+|Regression Test|Acceptance Test|Selective Test|NoFlag Test)'
              AND is_test IS TRUE
        """)
        flagged_count = cur.fetchone()[0]
        print(f"✅ GUARD PASS: 0 unflagged test-named tours "
              f"({flagged_count} correctly flagged)")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    print("=" * 70)
    print("LOCAL-139 GUARD: No unflagged test-named tours")
    print("=" * 70)
    try:
        test_no_unflagged_test_tours()
    except AssertionError as e:
        print(f"\n❌ FAILED: {e}")
        sys.exit(1)
    sys.exit(0)
