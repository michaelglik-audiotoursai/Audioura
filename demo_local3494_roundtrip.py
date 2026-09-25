#!/usr/bin/env python3
"""
LOCAL-3494 before/after demonstration — real DB round-trip.

Proves the four acceptance criteria against the live Postgres cache
(development-postgres-2-1, db=audiotours):

  AC1  Two requests for the SAME venue at 6 and 4 stops produce ONE generation
       (one store row, one cache_key) and the 4-stop request is a HIT, not a
       second generation.
  AC2  The 4-stop delivery ends cleanly — its last hand-off names the delivered
       last stop, never a trimmed one (no "the Crypt awaits" dangling seam).
  AC3  tour_quality.score_tour on the trimmed tour reports stops_delivered == 4
       and no `truncated` defect.
  AC4  An exact-match request (6 stops, the cached count) is returned verbatim.

The demo writes ONE row under a clearly-synthetic venue name and removes it at
the end, so it never pollutes the production cache.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2
import tour_cache_layer1 as cache
import tour_quality

DB_URL = os.environ.get(
    "DEMO_DB_URL", "postgresql://admin:password123@localhost:5433/audiotours"
)

# A synthetic venue name that cannot collide with anything real, so the demo is
# isolated and trivially cleaned up.
VENUE = "ZZZ Demo Church LOCAL-3494"
TOUR_TYPE = "museum"

SIX_STOP_TOUR = """Step-by-Step Audio Guided Tour: ZZZ Demo Church LOCAL-3494, Boston, MA
Tour-Category: museum

Stop 1: The Steeple

Address: 193 Salem St, Boston, MA 02113

The steeple is where the lanterns were hung in 1775. Paul Revere arranged the signal here on the eve of the ride that warned the countryside.

Directions: Continue through ZZZ Demo Church LOCAL-3494 — next is The Bell Chamber.

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

Directions: Your final stop in ZZZ Demo Church LOCAL-3494: The Crypt.

Stop 6: The Crypt

Address: 193 Salem St, Boston, MA 02113

Beneath the church lie 37 tombs holding more than a thousand people, including Captain Samuel Nicholson.

From The Steeple to The Crypt, you have followed the thread of Signals and Silence. The church was built in 1723. That's 6 stops — The Steeple, where lanterns warned of the British, The Bell Chamber, home to America's oldest bells, and The Crypt, resting place of a thousand souls.

Sources: This tour draws on information from oldnorth.com and the Wikipedia article on the church.
"""


def _rule(label):
    print("\n" + "=" * 72)
    print(label)
    print("=" * 72)


def _row_count(conn, key):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT total_stops, hit_count FROM tour_cache WHERE cache_key = %s",
            (key,),
        )
        return cur.fetchone()


def _last_directions(text):
    dirs = re.findall(r'^Directions:.*$', text, re.M)
    return dirs[-1] if dirs else "(none)"


def main():
    key6 = cache._cache_key(VENUE, TOUR_TYPE, 6)
    key4 = cache._cache_key(VENUE, TOUR_TYPE, 4)

    _rule("SETUP — cache key is location|tour_type|BUCKET (total_stops removed)")
    print(f"  key for 6 stops : {key6}")
    print(f"  key for 4 stops : {key4}")
    print(f"  bucket(6) = {cache._stop_bucket(6)}   bucket(4) = {cache._stop_bucket(4)}")
    print(f"  SAME KEY for 4 and 6 stops? {key6 == key4}")

    conn = psycopg2.connect(DB_URL)
    cache._ensure_table(conn)
    # Clean any stale demo row first (idempotent re-runs).
    with conn.cursor() as cur:
        cur.execute("DELETE FROM tour_cache WHERE cache_key IN (%s, %s)", (key6, key4))
    conn.commit()

    try:
        # ---- BEFORE: first request (6 stops) is a MISS → generate + store. ----
        _rule("REQUEST #1 — venue at 6 stops (BEFORE: cache empty)")
        miss = cache.get_cached_tour(VENUE, TOUR_TYPE, 6, DB_URL)
        print(f"  get_cached_tour(6) -> {'MISS (None)' if miss is None else 'HIT'}")
        print("  ...generation happens here (the paid step)... storing result.")
        cache.store_tour(VENUE, TOUR_TYPE, 6, SIX_STOP_TOUR, DB_URL)
        row = _row_count(conn, key6)
        print(f"  stored row: total_stops={row[0]}, hit_count={row[1]}")

        # ---- AC1: second request (4 stops) is a HIT on the SAME key. ----
        _rule("REQUEST #2 — SAME venue at 4 stops (AFTER: served from cache)")
        served = cache.get_cached_tour(VENUE, TOUR_TYPE, 4, DB_URL)
        n_stops = len(re.findall(r'^Stop \d+:', served or '', re.M))
        row_after = _row_count(conn, key4)
        print(f"  get_cached_tour(4) -> {'HIT' if served else 'MISS'}, "
              f"delivered {n_stops} stops")
        print(f"  cache_key rows for this venue in DB: "
              f"{_distinct_keys(conn, key6, key4)} (AC1: must be 1)")
        print(f"  hit_count now = {row_after[1]} (incremented by the 4-stop HIT)")
        print(f"  AC1 — one generation, second request is a HIT: "
              f"{served is not None and _distinct_keys(conn, key6, key4) == 1}")

        # ---- AC2: the trimmed 4-stop delivery ends cleanly. ----
        _rule("AC2 — trimmed 4-stop delivery seam")
        print("  delivered stops:",
              re.findall(r'^Stop \d+:\s*(.+)$', served, re.M))
        print(f"  last Directions line: {_last_directions(served)!r}")
        print(f"  names a trimmed stop (Chandeliers/Crypt)? "
              f"{'The Chandeliers' in served or 'The Crypt' in served}")
        recap = re.search(r'From .+? you have followed the thread', served)
        print(f"  recap endpoint line : "
              f"{recap.group(0) if recap else '(none)'}")
        count_clause = re.search(r"That's \d+ stops?", served)
        print(f"  recap count clause  : "
              f"{count_clause.group(0) if count_clause else '(none)'}")
        ac2 = ("The Chandeliers" not in served and "The Crypt" not in served
               and _last_directions(served)
               == f"Directions: Your final stop in {VENUE}: The Organ.")
        print(f"  AC2 — clean seam, no dangling hand-off: {ac2}")

        # ---- AC3: quality score of the trimmed tour. ----
        _rule("AC3 — tour_quality.score_tour on the trimmed tour")
        result = tour_quality.score_tour(served, requested_stops=4)
        print(f"  stops_delivered = {result['metrics']['stops_delivered']} "
              f"(must be 4)")
        print(f"  defects         = {result['defects']}")
        ac3 = (result['metrics']['stops_delivered'] == 4
               and 'truncated' not in result['defects'])
        print(f"  AC3 — stops_delivered==4 and no `truncated` defect: {ac3}")

        # ---- AC4: exact-match request (6 stops) returned verbatim. ----
        _rule("AC4 — exact-match request (6 stops) unchanged")
        exact = cache.get_cached_tour(VENUE, TOUR_TYPE, 6, DB_URL)
        ac4 = exact == SIX_STOP_TOUR
        print(f"  6-stop delivery byte-identical to stored tour: {ac4}")
        exact_stops = len(re.findall(r'^Stop \d+:', exact or '', re.M))
        print(f"  delivered stops: {exact_stops} "
              f"(expected 6; exact-match not trimmed)")

        _rule("RESULT")
        all_ok = all([
            key6 == key4,
            served is not None,
            _distinct_keys(conn, key6, key4) == 1,
            ac2, ac3, ac4,
        ])
        print(f"  ALL ACCEPTANCE CRITERIA MET: {all_ok}")
        return 0 if all_ok else 1
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tour_cache WHERE cache_key IN (%s, %s)",
                        (key6, key4))
        conn.commit()
        conn.close()
        print("  (demo row removed — production cache untouched)")


def _distinct_keys(conn, *keys):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(DISTINCT cache_key) FROM tour_cache WHERE cache_key = ANY(%s)",
            (list(keys),),
        )
        return cur.fetchone()[0]


if __name__ == "__main__":
    sys.exit(main())
