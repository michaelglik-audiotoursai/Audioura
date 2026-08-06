#!/usr/bin/env python3
"""
LOCAL-170: Verify the charge-vs-delivery fix on storied.

Tests that store_audio_tour:
1. Uses case-insensitive check matching the unique index
2. Returns structured dict with action='already_exists' when tour name collides
3. Returns action='error' on genuine failures (not 'completed')
4. Does NOT import wallet_ledger or entitlements (storied has neither)

Run: python3 tests/test_local170_charge_delivery_fix.py
"""
import os
import sys

# Add parent directory so we can import the service module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tests'))

from db_connection import get_connection, check_db_available

PASS = 0
FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL += 1
        print(f"  ❌ {label}")


def main():
    global PASS, FAIL

    if not check_db_available():
        print("DATABASE UNREACHABLE — cannot run tests")
        sys.exit(7)

    conn = get_connection()
    cur = conn.cursor()

    print("\n─── TEST 1: store_audio_tour detects existing tour (case-insensitive) ───")
    # Tour id=1 is "Palais Lascaris, Nice, France" — the collision target
    cur.execute("SELECT id, tour_name FROM audio_tours WHERE id = 1")
    row = cur.fetchone()
    if not row:
        print("  SKIP: tour id=1 not found — cannot test collision")
        sys.exit(1)
    tour_1_name = row[1]
    print(f"  Tour 1 name: '{tour_1_name}'")

    # Count before
    cur.execute("SELECT count(*) FROM audio_tours")
    count_before = cur.fetchone()[0]
    print(f"  audio_tours count before: {count_before}")

    # Get number_requested before
    cur.execute("SELECT number_requested FROM audio_tours WHERE id = 1")
    nr_before = cur.fetchone()[0]
    print(f"  number_requested before: {nr_before}")

    # Call store_audio_tour with a colliding name (different case)
    # We need a zip file — create a minimal one
    import tempfile, zipfile
    with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
        tmp_path = tmp.name
        with zipfile.ZipFile(tmp_path, 'w') as zf:
            zf.writestr("test.txt", "LOCAL-170 test file")

    # Set env vars for the function to connect to the right DB
    os.environ['DB_HOST'] = 'localhost'
    os.environ['DB_PORT'] = '5433'
    os.environ['DB_NAME'] = 'audiotours'
    os.environ['DB_USER'] = 'admin'
    os.environ['DB_PASSWORD'] = 'password123'

    # Import and call store_audio_tour
    from tour_orchestrator_service import store_audio_tour
    result = store_audio_tour(
        tour_name=tour_1_name,  # exact same name — should detect existing
        request_string="test LOCAL-170 collision",
        zip_path=tmp_path,
        lat=43.6961,
        lng=7.2760,
        tour_content="Test content for LOCAL-170",
        stops_count=2,
        is_test=True
    )

    print(f"  store_audio_tour result: {result}")
    check("Returns a dict", isinstance(result, dict))
    check("success=True", result.get("success") is True)
    check("action='already_exists'", result.get("action") == "already_exists")
    check("existing_tour_id=1", result.get("existing_tour_id") == 1)

    # Count after — should be unchanged
    cur.execute("SELECT count(*) FROM audio_tours")
    count_after = cur.fetchone()[0]
    print(f"  audio_tours count after: {count_after}")
    check("No new row created", count_after == count_before)

    # number_requested should have incremented
    cur.execute("SELECT number_requested FROM audio_tours WHERE id = 1")
    nr_after = cur.fetchone()[0]
    print(f"  number_requested after: {nr_after}")
    check("number_requested incremented", nr_after == nr_before + 1)

    # Reset number_requested to avoid accumulating test increments
    cur.execute("UPDATE audio_tours SET number_requested = %s WHERE id = 1", (nr_before,))
    conn.commit()
    print(f"  (reset number_requested back to {nr_before})")

    print("\n─── TEST 2: Case-insensitive collision detection ───")
    # Try with different casing
    mixed_case_name = tour_1_name.upper() if tour_1_name[0].islower() else tour_1_name.lower()
    print(f"  Testing with name: '{mixed_case_name}' (vs original '{tour_1_name}')")

    result2 = store_audio_tour(
        tour_name=mixed_case_name,
        request_string="test LOCAL-170 case mismatch",
        zip_path=tmp_path,
        lat=43.6961,
        lng=7.2760,
        tour_content="Test content for case mismatch",
        stops_count=2,
        is_test=True
    )
    print(f"  store_audio_tour result: {result2}")
    check("Case-insensitive match returns already_exists", result2.get("action") == "already_exists")
    check("Returns correct existing_tour_id", result2.get("existing_tour_id") == 1)

    # Reset number_requested again
    cur.execute("UPDATE audio_tours SET number_requested = %s WHERE id = 1", (nr_before,))
    conn.commit()

    # Count unchanged
    cur.execute("SELECT count(*) FROM audio_tours")
    count_after2 = cur.fetchone()[0]
    check("Still no new row", count_after2 == count_before)

    print("\n─── TEST 3: Error returns action='error' (not silently swallowed) ───")
    # Try with a non-existent zip path to trigger an error
    result3 = store_audio_tour(
        tour_name="Completely Unique Tour Name That Does Not Exist 170 " + str(os.getpid()),
        request_string="test error path",
        zip_path="/nonexistent/path/fake.zip",
        lat=0.0,
        lng=0.0,
        tour_content="test",
        stops_count=1,
        is_test=True
    )
    print(f"  store_audio_tour result: {result3}")
    check("Error: success=False", result3.get("success") is False)
    check("Error: action='error'", result3.get("action") == "error")
    check("Error: error message present", result3.get("error") is not None and len(result3.get("error", "")) > 0)

    print("\n─── TEST 4: No wallet code imported (storied has no wallet) ───")
    # Read the source and check for wallet imports in the LOCAL-156 orchestrator section
    import inspect
    source = inspect.getsource(store_audio_tour)
    check("store_audio_tour has no wallet_ledger import", "wallet_ledger" not in source)
    check("store_audio_tour has no service_credit", "service_credit" not in source)

    print("\n─── TEST 5: Nice tour list unchanged ───")
    # The expected Nice-area list includes tours found by coordinates, not just name.
    # Verify all expected IDs still exist as non-test originals.
    expected = [1, 12, 14, 17, 21, 24, 27, 28, 29]
    cur.execute("""
        SELECT array_agg(id ORDER BY id) 
        FROM audio_tours 
        WHERE id IN (1,12,14,17,21,24,27,28,29)
        AND original_tour_id IS NULL 
        AND (is_test IS NULL OR is_test = false)
    """)
    nice_ids = cur.fetchone()[0]
    print(f"  Nice tour IDs: {nice_ids}")
    check(f"Nice list = {expected}", nice_ids == expected)

    # Clean up
    os.unlink(tmp_path)
    cur.close()
    conn.close()

    print(f"\n{'='*60}")
    print(f"SUMMARY: {PASS}/{PASS+FAIL} PASS, {FAIL} FAIL")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
