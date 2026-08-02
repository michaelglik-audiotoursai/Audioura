#!/usr/bin/env python3
"""
LOCAL-139 Acceptance Test: Prove the TestTourFactory and guard work together.

Demonstrates:
1. A tour created through TestTourFactory has is_test=TRUE without the caller
   asking for it — there IS no parameter to ask.
2. A deliberately unflagged test-named row causes the guard to go RED.
3. Fixing the flag (is_test=TRUE) makes the guard go GREEN.
4. Row counts before/after — no DELETEs.

Usage:
    python3 tests/test_local139_acceptance.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection, check_db_available
from test_tour_factory import TestTourFactory
from test_no_unflagged_test_tours import GUARD_QUERY


def main():
    print("=" * 70)
    print("LOCAL-139 ACCEPTANCE TEST")
    print("=" * 70)

    if not check_db_available():
        print("ERROR: Database not available")
        sys.exit(7)

    # ─── Record initial state ─────────────────────────────────────────────────
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count_before = cur.fetchone()[0]
    print(f"\n  audio_tours count BEFORE: {count_before}")
    cur.close()
    conn.close()

    ts = int(time.time())
    rows_added = 0

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 1: Factory creates tour with is_test=TRUE — no opt-out possible
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("TEST 1: Factory creates tour with is_test=TRUE (no parameter for it)")
    print("─" * 70)

    factory = TestTourFactory(auto_cleanup=False)
    tour_id = factory.create(
        tour_name=f"LOCAL139 Acceptance Test {ts}",
        request_string=f"LOCAL139 Test {ts}, Seattle, WA",
        lat=47.6098,
        lng=-122.3423,
    )
    rows_added += 1
    print(f"  Created tour id={tour_id}")

    # Verify is_test=TRUE directly in DB
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, tour_name, is_test, lat, lng FROM audio_tours WHERE id = %s",
        (tour_id,),
    )
    row = cur.fetchone()
    tid, tname, is_test_val, lat_val, lng_val = row
    print(f"  DB row: id={tid}, is_test={is_test_val}, lat={lat_val}, lng={lng_val}")
    print(f"  tour_name: {tname}")
    assert is_test_val is True, f"FAIL: is_test should be True, got {is_test_val}"
    print("  ✅ PASS — is_test=TRUE without caller asking for it")
    cur.close()
    conn.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 2: Deliberately unflagged row makes the guard go RED
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("TEST 2: Unflagged test-named row → guard goes RED")
    print("─" * 70)

    # Insert a row with is_test=FALSE (simulating the bug)
    conn = get_connection()
    cur = conn.cursor()
    bad_name = f"LOCAL139 NoFlag Test {ts}"
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, number_requested, lat, lng, is_test)
        VALUES (%s, %s, 0, 47.6098, -122.3423, FALSE)
        RETURNING id
        """,
        (bad_name, f"Deliberately unflagged {ts}"),
    )
    bad_id = cur.fetchone()[0]
    conn.commit()
    rows_added += 1
    print(f"  Inserted deliberately unflagged row: id={bad_id}, is_test=FALSE")
    print(f"  tour_name: {bad_name}")

    # Run the guard query — should find the bad row
    cur.execute(GUARD_QUERY)
    unflagged = cur.fetchall()
    print(f"  Guard query result: {len(unflagged)} unflagged row(s)")
    found_bad = any(r[0] == bad_id for r in unflagged)
    assert found_bad, f"FAIL: Guard did not detect unflagged row id={bad_id}"
    for r in unflagged:
        if r[0] == bad_id:
            print(f"  → id={r[0]} is_test={r[2]} name={r[1][:50]}")
    print("  ✅ PASS — guard correctly detects unflagged test-named tour (RED)")
    cur.close()
    conn.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 3: Fix the flag → guard goes GREEN
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("TEST 3: Set is_test=TRUE → guard goes GREEN")
    print("─" * 70)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE audio_tours SET is_test = TRUE WHERE id = %s",
        (bad_id,),
    )
    update_count = cur.rowcount
    conn.commit()
    print(f"  UPDATE audio_tours SET is_test = TRUE WHERE id = {bad_id}")
    print(f"  Rows updated: {update_count}")

    # Re-run guard query — should be clean
    cur.execute(GUARD_QUERY)
    unflagged_after = cur.fetchall()
    print(f"  Guard query result after fix: {len(unflagged_after)} unflagged row(s)")
    assert len(unflagged_after) == 0, (
        f"FAIL: Guard still finds unflagged rows after fix: "
        f"{[r[0] for r in unflagged_after]}"
    )
    print("  ✅ PASS — guard is GREEN after setting is_test=TRUE")
    cur.close()
    conn.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 4: adopt_and_ensure_flagged works
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("TEST 4: adopt_and_ensure_flagged forces flag on externally-created tour")
    print("─" * 70)

    # Create a row without is_test (simulating orchestrator that dropped the flag)
    conn = get_connection()
    cur = conn.cursor()
    orphan_name = f"LOCAL139 Regression Test Orphan {ts}"
    cur.execute(
        """
        INSERT INTO audio_tours (tour_name, request_string, number_requested, lat, lng, is_test)
        VALUES (%s, %s, 0, 47.6098, -122.3423, FALSE)
        RETURNING id
        """,
        (orphan_name, f"Orphan test {ts}"),
    )
    orphan_id = cur.fetchone()[0]
    conn.commit()
    rows_added += 1
    print(f"  Created unflagged orphan: id={orphan_id}")

    cur.execute("SELECT is_test FROM audio_tours WHERE id = %s", (orphan_id,))
    print(f"  Before adopt: is_test={cur.fetchone()[0]}")
    cur.close()
    conn.close()

    # Adopt it through the factory
    updated = factory.adopt_and_ensure_flagged(orphan_id)
    print(f"  factory.adopt_and_ensure_flagged({orphan_id}) → updated={updated}")

    # Verify
    factory.verify_flagged(orphan_id)
    print("  ✅ PASS — adopted tour now has is_test=TRUE")

    # ═══════════════════════════════════════════════════════════════════════════
    # CLEANUP & FINAL STATE
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "─" * 70)
    print("CLEANUP")
    print("─" * 70)

    # Cleanup factory-created tours (nulls lat/lng, keeps row)
    factory.cleanup()

    # Also clean the bad_id we created manually (it's now flagged, just null coords)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE audio_tours SET lat = NULL, lng = NULL WHERE id = %s AND is_test = TRUE",
        (bad_id,),
    )
    conn.commit()
    print(f"  Cleaned bad_id={bad_id}: lat/lng nulled")
    cur.close()
    conn.close()

    # ─── Final row count ──────────────────────────────────────────────────────
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count_after = cur.fetchone()[0]
    cur.close()
    conn.close()

    print(f"\n  audio_tours count AFTER: {count_after}")
    print(f"  Delta: +{count_after - count_before} (added {rows_added} test rows)")
    assert count_after == count_before + rows_added, (
        f"Row count mismatch! Expected {count_before + rows_added}, got {count_after}"
    )

    # ─── Final guard check ────────────────────────────────────────────────────
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(GUARD_QUERY)
    final_unflagged = cur.fetchall()
    cur.close()
    conn.close()
    assert len(final_unflagged) == 0, (
        f"Final guard check failed! Unflagged: {[r[0] for r in final_unflagged]}"
    )

    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 70)
    print("ALL LOCAL-139 ACCEPTANCE TESTS PASSED")
    print("=" * 70)
    print(f"  Rows before: {count_before}")
    print(f"  Rows after:  {count_after}")
    print(f"  Rows added:  {rows_added} (all flagged is_test=TRUE)")
    print(f"  Guard:       GREEN (0 unflagged test-named tours)")
    print("=" * 70)
    return count_before, count_after, rows_added


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    sys.exit(0)
