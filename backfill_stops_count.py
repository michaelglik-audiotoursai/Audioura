#!/usr/bin/env python3
"""LOCAL-190: Backfill stops_count from tour_content using parse_tour_stops.

Rules:
  - UPDATE only. No DELETE FROM audio_tours under any circumstances.
  - Only touch rows where stops_count is 0 or NULL AND parsed count > 0.
  - Never overwrite a non-zero count.
  - Report before/after for every row touched.
  - Row count must remain 117.
"""
import sys
sys.path.insert(0, 'tests')
from db_connection import get_connection
from stop_anchor_detector_v2 import parse_tour_stops


def main():
    conn = get_connection()
    cur = conn.cursor()

    # Record row count before
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    row_count_before = cur.fetchone()[0]
    print(f"Row count BEFORE: {row_count_before}")
    assert row_count_before == 117, f"Expected 117 rows, got {row_count_before}"

    # Find candidates: stops_count is 0 or NULL, has tour_content
    cur.execute("""
        SELECT id, tour_name, stops_count, tour_content
        FROM audio_tours
        WHERE (stops_count IS NULL OR stops_count = 0)
          AND tour_content IS NOT NULL
          AND length(tour_content) > 0
        ORDER BY id
    """)
    candidates = cur.fetchall()
    print(f"\nCandidates (stops_count=0/NULL with content): {len(candidates)} rows\n")

    updates = []
    for row_id, tour_name, old_count, tour_content in candidates:
        stops = parse_tour_stops(tour_content)
        parsed_count = len(stops)
        if parsed_count > 0:
            updates.append((row_id, tour_name, old_count, parsed_count))

    if not updates:
        print("No rows to update.")
        cur.close()
        conn.close()
        return

    # Print before/after table
    print(f"{'id':<6} {'old':<6} {'new':<6} {'tour_name'}")
    print("-" * 70)
    for row_id, tour_name, old_count, new_count in updates:
        old_display = str(old_count) if old_count is not None else "NULL"
        print(f"{row_id:<6} {old_display:<6} {new_count:<6} {tour_name[:50]}")

    print(f"\nApplying {len(updates)} UPDATEs...")

    for row_id, tour_name, old_count, new_count in updates:
        cur.execute(
            "UPDATE audio_tours SET stops_count = %s WHERE id = %s AND (stops_count IS NULL OR stops_count = 0)",
            (new_count, row_id)
        )
        if cur.rowcount != 1:
            print(f"  WARNING: UPDATE for id={row_id} affected {cur.rowcount} rows (expected 1)")

    conn.commit()
    print("Committed.")

    # Verify row count after
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    row_count_after = cur.fetchone()[0]
    print(f"\nRow count AFTER: {row_count_after}")
    assert row_count_after == 117, f"Expected 117 rows after, got {row_count_after}"

    # Verify the nice list is unchanged
    nice_ids = [1, 12, 14, 17, 21, 24, 27, 28, 29]
    cur.execute(
        "SELECT id, stops_count FROM audio_tours WHERE id = ANY(%s) ORDER BY id",
        (nice_ids,)
    )
    nice_rows = cur.fetchall()
    print(f"\nNice list verification (should all be non-zero, unchanged):")
    for nid, ncount in nice_rows:
        print(f"  id={nid}  stops_count={ncount}")
        assert ncount is not None and ncount > 0, f"Nice list id={nid} has stops_count={ncount}!"

    # Spot-check two backfilled tours
    if len(updates) >= 2:
        print(f"\n--- Spot-check: re-parse two backfilled tours ---")
        for row_id, tour_name, old_count, new_count in updates[:2]:
            cur.execute("SELECT tour_content, stops_count FROM audio_tours WHERE id = %s", (row_id,))
            content, db_count = cur.fetchone()
            re_parsed = len(parse_tour_stops(content))
            print(f"  id={row_id}: db stops_count={db_count}, re-parsed={re_parsed}, match={db_count == re_parsed}")
            assert db_count == re_parsed, f"Mismatch on id={row_id}!"

    cur.close()
    conn.close()
    print("\n✓ Backfill complete. Row count unchanged at 117.")


if __name__ == "__main__":
    main()
