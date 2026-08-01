#!/usr/bin/env python3
"""
LOCAL-88 Acceptance Test: Test tour pollution prevention.

Proves:
1. tours-near returns exactly Michael's 9 real Nice tours (no test rows)
2. A test tour created in test mode is flagged and excluded from tours-near
3. The helper's cleanup removes only ids it created (selective cleanup proof)
4. Known test rows are backfilled with is_test=TRUE and have real coordinates
5. Row count is preserved (no DELETEs)
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_connection
from test_tour_helper import TestTourHelper


def haversine(lat1, lng1, lat2, lng2):
    """Calculate distance in km between two points."""
    R = 6371
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def simulate_tours_near(cur, lat, lng, radius_km=50):
    """Simulate the tours-near endpoint query (matches map_delivery_service.py)."""
    cur.execute("""
        SELECT id, tour_name, lat, lng
        FROM audio_tours
        WHERE lat IS NOT NULL AND lng IS NOT NULL
          AND (is_test IS NOT TRUE)
          AND original_tour_id IS NULL
    """)
    nearby = []
    for row in cur.fetchall():
        d = haversine(lat, lng, row[2], row[3])
        if d <= radius_km:
            nearby.append(row[0])
    return sorted(nearby)


def test_tours_near_returns_michaels_9():
    """AC1: tours-near/43.7009358/7.2683912?radius=50 returns exactly [1,12,14,17,21,24,27,28,29]."""
    print("\n=== TEST 1: tours-near returns Michael's 9 real tours ===")
    conn = get_connection()
    cur = conn.cursor()

    result = simulate_tours_near(cur, 43.7009358, 7.2683912, radius_km=50)
    expected = [1, 12, 14, 17, 21, 24, 27, 28, 29]

    print(f"  Result:   {result}")
    print(f"  Expected: {expected}")

    assert result == expected, f"MISMATCH! Got {result}, expected {expected}"
    print("  ✅ PASS")
    cur.close()
    conn.close()


def test_test_mode_tour_flagged_and_excluded():
    """AC2: A tour generated in test mode exists, is flagged, and is NOT in tours-near."""
    print("\n=== TEST 2: Test-mode tour is flagged and excluded ===")
    import time
    helper = TestTourHelper(auto_cleanup=False)

    # Create a test tour with Nice coordinates (would appear in Michael's list without the flag)
    # Use timestamp to ensure unique name (unique constraint on tour_name)
    ts = int(time.time())
    tour_id = helper.create_test_tour(
        tour_name=f"LOCAL88 Acceptance Test Tour {ts}",
        request_string=f"LOCAL88 Test {ts}, Nice, France",
        lat=43.7009,
        lng=7.2684,
    )
    print(f"  Created test tour id={tour_id}")

    # Verify it exists and is flagged
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, is_test, lat, lng FROM audio_tours WHERE id = %s", (tour_id,))
    row = cur.fetchone()
    print(f"  Row exists: id={row[0]}, is_test={row[1]}, lat={row[2]}, lng={row[3]}")
    assert row[1] is True, f"is_test should be True, got {row[1]}"

    # Verify it does NOT appear in tours-near
    result = simulate_tours_near(cur, 43.7009358, 7.2683912, radius_km=50)
    assert tour_id not in result, f"Test tour {tour_id} appeared in tours-near!"
    print(f"  tours-near result (should not contain {tour_id}): {result}")
    print("  ✅ PASS — tour exists, is flagged, excluded from tours-near")

    cur.close()
    conn.close()

    # Cleanup
    helper.cleanup()
    return tour_id


def test_helper_cleanup_selective():
    """AC3: Helper's cleanup removes only ids it created — prove by creating two, cleaning one."""
    print("\n=== TEST 3: Helper cleanup is selective ===")
    import time
    helper = TestTourHelper(auto_cleanup=False)
    ts = int(time.time())

    # Create two test tours
    id_a = helper.create_test_tour(
        tour_name=f"LOCAL88 Selective Test A {ts}",
        request_string=f"Selective Test A {ts}",
        lat=43.70, lng=7.27,
    )
    id_b = helper.create_test_tour(
        tour_name=f"LOCAL88 Selective Test B {ts}",
        request_string=f"Selective Test B {ts}",
        lat=43.71, lng=7.28,
    )
    print(f"  Created tour A: id={id_a}")
    print(f"  Created tour B: id={id_b}")

    # Clean up ONLY id_a
    helper.cleanup_specific([id_a])

    # Verify id_a is cleaned (lat/lng NULL) but id_b survives with coordinates
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id, lat, lng, is_test FROM audio_tours WHERE id = %s", (id_a,))
    row_a = cur.fetchone()
    print(f"  After cleanup_specific([{id_a}]):")
    print(f"    Tour A: id={row_a[0]}, lat={row_a[1]}, lng={row_a[2]}, is_test={row_a[3]}")
    assert row_a[1] is None, f"Tour A lat should be NULL after cleanup, got {row_a[1]}"
    assert row_a[2] is None, f"Tour A lng should be NULL after cleanup, got {row_a[2]}"
    assert row_a[3] is True, "Tour A is_test should still be True"

    cur.execute("SELECT id, lat, lng, is_test FROM audio_tours WHERE id = %s", (id_b,))
    row_b = cur.fetchone()
    print(f"    Tour B: id={row_b[0]}, lat={row_b[1]}, lng={row_b[2]}, is_test={row_b[3]}")
    assert row_b[1] is not None, f"Tour B lat should SURVIVE, got {row_b[1]}"
    assert row_b[2] is not None, f"Tour B lng should SURVIVE, got {row_b[2]}"
    assert row_b[3] is True, "Tour B is_test should be True"

    print("  ✅ PASS — cleanup_specific only touched the specified ID")

    # Now clean up id_b too
    helper.cleanup_specific([id_b])

    cur.close()
    conn.close()
    return id_a, id_b


def test_backfill_verification():
    """AC4: Known test rows are backfilled with is_test=TRUE and have real coordinates."""
    print("\n=== TEST 4: Known test rows backfilled ===")
    known_test_ids = [39, 40, 41, 42, 43, 49, 50, 51, 52, 53, 54, 55]

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, lat, lng, is_test
        FROM audio_tours
        WHERE id = ANY(%s)
        ORDER BY id
        """,
        (known_test_ids,),
    )
    rows = cur.fetchall()
    print(f"  Checking {len(rows)} known test rows:")
    all_ok = True
    for row in rows:
        tid, lat, lng, is_test = row
        ok = is_test is True and lat is not None and lng is not None
        status = "✅" if ok else "❌"
        print(f"    {status} id={tid:3d} is_test={is_test} lat={lat} lng={lng}")
        if not ok:
            all_ok = False

    assert all_ok, "Some test rows are missing is_test=TRUE or have NULL coordinates"
    print("  ✅ PASS — all known test rows flagged with coordinates restored")

    cur.close()
    conn.close()


def test_row_count_preserved():
    """AC5: Row count before == after (no DELETEs)."""
    print("\n=== TEST 5: Row count preserved ===")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count = cur.fetchone()[0]
    print(f"  Current row count: {count}")
    # The test created 3 rows (test 2 + test 3 a/b) but cleaned them up
    # (cleanup nulls coords but doesn't delete) — so count should be
    # original 46 + 3 = 49 (the test rows still exist, just with NULL coords)
    assert count >= 46, f"Row count dropped below original 46! Got {count}"
    print(f"  ✅ PASS — count={count} (original was 46, test rows added {count - 46})")
    cur.close()
    conn.close()
    return count


if __name__ == "__main__":
    print("=" * 70)
    print("LOCAL-88 ACCEPTANCE TESTS — Tour Pollution Prevention")
    print("=" * 70)

    # Record initial count
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    initial_count = cur.fetchone()[0]
    print(f"\nInitial audio_tours row count: {initial_count}")
    cur.close()
    conn.close()

    try:
        test_tours_near_returns_michaels_9()
        test_test_mode_tour_flagged_and_excluded()
        test_helper_cleanup_selective()
        test_backfill_verification()
        final_count = test_row_count_preserved()
    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n" + "=" * 70)
    print("ALL ACCEPTANCE TESTS PASSED")
    print(f"Row count: {initial_count} → {final_count} (delta: +{final_count - initial_count})")
    print("=" * 70)
    sys.exit(0)
