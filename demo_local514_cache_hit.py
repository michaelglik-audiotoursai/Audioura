#!/usr/bin/env python3
"""LOCAL-514 — real before/after demonstration of the bucketed cache (D581 step one).

Runs the FULL cache path against a live Postgres (not the pure functions):

  Request A:  Old North Church / museum / 6 stops  -> MISS -> store_tour  (the paid generation)
  Request B:  Old North Church / museum / 4 stops  -> HIT  (same bucket) -> trimmed 6->4

Proves acceptance criteria against real DB reads/writes:
  AC1  the 6-stop store and the 4-stop request share ONE key/row: one generation, one hit.
  AC2  the 4-stop delivery ends cleanly — no hand-off or recap naming a trimmed stop.
  AC3  tour_quality.score_tour(trimmed, 4) -> stops_delivered == 4, no 'truncated'.
  AC4  an exact-match 6-stop request returns the stored content verbatim.

Usage:  DB_URL=... python3 demo_local514_cache_hit.py
Default DB_URL targets the docker-compose postgres-2 container on host port 5433.
"""
import os
import re
import sys

import tour_cache_layer1 as cache
import tour_quality

DB_URL = os.environ.get(
    "DB_URL",
    "postgresql://admin:password123@localhost:5433/audiotours",
)

LOCATION = "Old North Church, Boston, MA"
TOUR_TYPE = "museum"

SIX_STOP_TOUR = """Step-by-Step Audio Guided Tour: Old North Church, Boston, MA
Tour-Category: museum

Stop 1: The Steeple

Address: 193 Salem St, Boston, MA 02113

The steeple is where the lanterns were hung in 1775. Paul Revere arranged the signal here on the eve of the ride that warned the countryside.

Directions: Continue through Old North Church — next is The Bell Chamber.

Stop 2: The Bell Chamber

Address: 193 Salem St, Boston, MA 02113

The eight bells were cast in 1744 by Abel Rudhall of Gloucester, the oldest change-ringing bells in North America.

Directions: Next: The Box Pews.

Stop 3: The Box Pews

Address: 193 Salem St, Boston, MA 02113

The high box pews were owned by families who paid for their upkeep. Robert Newman's family pew sits near the front.

Directions: Proceed to The Organ.

Stop 4: The Organ

Address: 193 Salem St, Boston, MA 02113

The organ loft overlooks the nave. The instrument accompanied worship for generations of the congregation.

Directions: Continue to The Chandeliers.

Stop 5: The Chandeliers

Address: 193 Salem St, Boston, MA 02113

The brass chandeliers were donated in 1724 and are lit only on special occasions.

Directions: Your final stop in Old North Church: The Crypt.

Stop 6: The Crypt

Address: 193 Salem St, Boston, MA 02113

Beneath the church lie 37 tombs holding more than a thousand people, including Captain Samuel Nicholson.

From The Steeple to The Crypt, you have followed the thread of Signals and Silence. The church was built in 1723. That's 6 stops — The Steeple, where lanterns warned of the British, The Bell Chamber, home to America's oldest bells, and The Crypt, resting place of a thousand souls.

Sources: This tour draws on information from oldnorth.com and the Wikipedia article on the church.
"""


def _rows_for_bucket(db_url, location, tour_type, total_stops):
    """Return the cache rows under THIS venue's bucket key only.

    The live cache holds many unrelated venues; scoping to the exact bucket key
    is what proves 'one generation, one row' for the venue under test.
    """
    import psycopg2
    key = cache._cache_key(location, tour_type, total_stops)
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cache_key, total_stops, hit_count FROM tour_cache "
            "WHERE cache_key = %s",
            (key,),
        )
        rows = cur.fetchall()
    conn.close()
    return rows


def _clean_slate(db_url, tour_type):
    """Remove any rows this demo would touch, so before/after is unambiguous."""
    import psycopg2
    conn = psycopg2.connect(db_url)
    cache._ensure_table(conn)
    with conn.cursor() as cur:
        for n in (3, 4, 6, 10):
            cur.execute("DELETE FROM tour_cache WHERE cache_key = %s",
                        (cache._cache_key(LOCATION, tour_type, n),))
    conn.commit()
    conn.close()


def _last_directions(text):
    dirs = re.findall(r'^Directions:.*$', text, re.M)
    return dirs[-1] if dirs else "(none)"


def _stop_names(text):
    return re.findall(r'^Stop \d+:\s*(.+)$', text, re.M)


def main():
    print("=" * 72)
    print("LOCAL-514 bucketed-cache demonstration (live Postgres)")
    print("DB_URL:", re.sub(r':[^:@/]+@', ':***@', DB_URL))
    print("=" * 72)

    _clean_slate(DB_URL, TOUR_TYPE)

    k6 = cache._cache_key(LOCATION, TOUR_TYPE, 6)
    k4 = cache._cache_key(LOCATION, TOUR_TYPE, 4)
    print(f"\n[keys] 6-stop key = {k6[:16]}…")
    print(f"[keys] 4-stop key = {k4[:16]}…")
    print(f"[keys] SAME KEY (AC1 bucketing): {k6 == k4}")
    assert k6 == k4, "AC1 FAILED: 4 and 6 stops must share a key"

    # -- Request A: 6 stops. Cold cache -> MISS -> generate + store. --
    print("\n" + "-" * 72)
    print("REQUEST A — Old North Church / museum / 6 stops")
    print("-" * 72)
    miss = cache.get_cached_tour(LOCATION, TOUR_TYPE, 6, DB_URL)
    print("get_cached_tour(6) ->", "MISS (None)" if miss is None else "HIT")
    assert miss is None, "expected a cold MISS on first request"
    print("=> paying for ONE generation, storing it under the bucket key")
    stored = cache.store_tour(LOCATION, TOUR_TYPE, 6, SIX_STOP_TOUR, DB_URL)
    print("store_tour(6) ->", stored)

    rows = _rows_for_bucket(DB_URL, LOCATION, TOUR_TYPE, 6)
    print(f"rows under THIS venue's bucket key: {len(rows)}  (total_stops, hit_count) = "
          f"{[(r[1], r[2]) for r in rows]}")

    # -- Request B: 4 stops. Same bucket -> HIT -> trim 6->4 on delivery. --
    print("\n" + "-" * 72)
    print("REQUEST B — Old North Church / museum / 4 stops  (the SECOND request)")
    print("-" * 72)
    delivered = cache.get_cached_tour(LOCATION, TOUR_TYPE, 4, DB_URL)
    served = delivered is not None
    print("get_cached_tour(4) ->", "HIT (served from cache, trimmed)" if served else "MISS")
    assert served, "AC1 FAILED: second request must be a cache HIT, not a generation"

    rows = _rows_for_bucket(DB_URL, LOCATION, TOUR_TYPE, 4)
    print(f"rows under THIS venue's bucket key after request B: {len(rows)}  "
          f"(still ONE row = one generation)")
    print(f"hit_count on the row: {rows[0][2]}  (incremented by the HIT)")
    assert len(rows) == 1, "AC1 FAILED: a second row would mean a second generation"

    # -- AC2: the delivered 4-stop tour ends cleanly. --
    print("\n[AC2] delivered stops:", _stop_names(delivered))
    print("[AC2] last Directions line:", _last_directions(delivered))
    print("[AC2] names 'The Chandeliers' (stop 5)?:", "The Chandeliers" in delivered)
    print("[AC2] names 'The Crypt' (stop 6)?:      ", "The Crypt" in delivered)
    assert "The Chandeliers" not in delivered and "The Crypt" not in delivered, \
        "AC2 FAILED: delivery names a trimmed stop"
    assert _last_directions(delivered) == \
        "Directions: Your final stop in Old North Church: The Organ.", \
        "AC2 FAILED: trailing seam not repaired to the final-stop form"
    assert "From The Steeple to The Organ" in delivered and "That's 4 stops" in delivered, \
        "AC2 FAILED: recap does not name only delivered stops"

    # -- AC3: quality scorer on the trimmed tour. --
    score = tour_quality.score_tour(delivered, requested_stops=4)
    print("\n[AC3] score_tour(delivered, 4):")
    print("      stops_delivered =", score['metrics']['stops_delivered'])
    print("      defects         =", dict(score['defects']))
    assert score['metrics']['stops_delivered'] == 4, "AC3 FAILED: stops_delivered != 4"
    assert 'truncated' not in score['defects'], "AC3 FAILED: 'truncated' defect present"
    assert 'thin' not in score['defects'], "AC3 FAILED: 'thin' defect present"

    # -- AC4: an exact-match (6-stop) request is unchanged. --
    exact = cache.get_cached_tour(LOCATION, TOUR_TYPE, 6, DB_URL)
    print("\n[AC4] exact 6-stop request returns stored content verbatim:",
          exact == SIX_STOP_TOUR)
    assert exact == SIX_STOP_TOUR, "AC4 FAILED: exact-match delivery was altered"

    print("\n" + "=" * 72)
    print("ALL ACCEPTANCE CRITERIA PASSED")
    print("  AC1  one generation + one hit for 6 then 4 stops (single cache row)")
    print("  AC2  4-stop delivery ends cleanly, no trimmed stop named")
    print("  AC3  score_tour: stops_delivered==4, no 'truncated'")
    print("  AC4  exact 6-stop request unchanged")
    print("=" * 72)

    print("\n----- FULL 4-STOP DELIVERY (trimmed from the 6-stop generation) -----\n")
    print(delivered)


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print("\nFAILED:", e)
        sys.exit(1)
