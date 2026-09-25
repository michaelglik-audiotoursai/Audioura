#!/usr/bin/env python3
"""
LOCAL-494 before/after demonstration — bucketed cache serving two stop counts
from ONE generation.

Runs the REAL cache functions (store_tour / get_cached_tour / _cache_key /
trim_tour_to_stops) against a throwaway Postgres database so the hit/miss log
lines are the ones the orchestrator would actually emit. No paid generation is
involved — a real corpus tour stands in for the "generated" 6-stop content.

Scenario (acceptance criterion 1):
  Request A: 6 stops for a venue  -> MISS, generate once, store (bucket 6).
  Request B: 4 stops, same venue  -> HIT on the same bucket key, trimmed to 4.

One generation, one hit. The 4-stop delivery is checked to end cleanly and to
score with stops_delivered == 4 and no `truncated` defect.
"""
import logging
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tour_cache_layer1 as cache
import tour_quality

logging.basicConfig(level=logging.INFO, format="LOG %(levelname)s: %(message)s")

DB_URL = os.environ.get(
    "LOCAL494_DEMO_DB_URL",
    "postgresql://admin:password123@localhost:5433/local494_demo",
)

LOCATION = "Musee des Arts Asiatiques, Nice, France"
TOUR_TYPE = "museum"

# Stand-in for a freshly generated 6-stop tour: take the real 8-stop corpus tour
# and trim it to 6 with the same production trimmer, so the "generated" content
# is itself a clean, well-formed 6-stop tour.
_CORPUS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "tours", "LOCAL262_asian_arts_8stop_restored.txt")


def _rule(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    six_stop_tour = cache.trim_tour_to_stops(open(_CORPUS, encoding="utf-8").read(), 6)

    _rule("KEY EQUALITY — 4-stop and 6-stop requests resolve to ONE cache key")
    k4 = cache._cache_key(LOCATION, TOUR_TYPE, 4)
    k6 = cache._cache_key(LOCATION, TOUR_TYPE, 6)
    print(f"  bucket(4) = {cache._stop_bucket(4)}   bucket(6) = {cache._stop_bucket(6)}")
    print(f"  key(4 stops) = {k4[:16]}…")
    print(f"  key(6 stops) = {k6[:16]}…")
    print(f"  SAME KEY: {k4 == k6}")
    assert k4 == k6

    _rule("REQUEST A — 6 stops (cold cache): expect MISS, then generate + store")
    before = cache.get_cached_tour(LOCATION, TOUR_TYPE, 6, DB_URL)
    print(f"  get_cached_tour(6) -> {'HIT' if before else 'MISS (None)'}")
    assert before is None, "expected a cold MISS"
    print("  [generate 6-stop tour once — this is the ONE paid generation]")
    cache.store_tour(LOCATION, TOUR_TYPE, 6, six_stop_tour, DB_URL)

    _rule("REQUEST B — 4 stops, same venue: expect HIT (trimmed), NO generation")
    delivered = cache.get_cached_tour(LOCATION, TOUR_TYPE, 4, DB_URL)
    print(f"  get_cached_tour(4) -> {'HIT' if delivered else 'MISS'}")
    assert delivered is not None, "expected a bucket HIT for the 4-stop request"

    names = re.findall(r"^Stop \d+:\s*(.+)$", delivered, re.M)
    last_dir = [ln for ln in delivered.splitlines() if ln.startswith("Directions:")][-1]
    _rule("4-STOP DELIVERY — seam + recap check")
    print(f"  stops delivered: {len(names)} -> {names}")
    print(f"  last Directions line: {last_dir}")
    recap = [ln for ln in delivered.splitlines() if ln.startswith("From ")]
    if recap:
        print(f"  closing recap: {recap[0]}")

    result = tour_quality.score_tour(delivered, requested_stops=4)
    _rule("SCORE — tour_quality.score_tour on the trimmed 4-stop delivery")
    print(f"  stops_delivered : {result['metrics']['stops_delivered']}")
    print(f"  truncated defect: {'truncated' in result['defects']}")
    print(f"  thin defect     : {'thin' in result['defects']}")
    print(f"  defects         : {result['defects']}")

    assert len(names) == 4
    # The trimmed STOP 5 ("Kannon à mille bras") must not be named by any
    # navigation/recap line. (Its name may still appear inside earlier stops'
    # prose — that is original body content, not a dangling hand-off.)
    nav_lines = [ln for ln in delivered.splitlines()
                 if ln.startswith("Directions:") or ln.startswith("From ")]
    assert not any("Kannon" in ln for ln in nav_lines), \
        "seam/recap must not name a trimmed stop"
    assert result["metrics"]["stops_delivered"] == 4
    assert "truncated" not in result["defects"]

    _rule("VERIFY DB — one row (one generation) served both requests")
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    with conn.cursor() as cur:
        cur.execute("SELECT total_stops, hit_count FROM tour_cache WHERE cache_key = %s", (k6,))
        row = cur.fetchone()
    conn.close()
    print(f"  cached total_stops = {row[0]} (bucket max)   hit_count = {row[1]}")
    print("\nRESULT: 1 generation, 1 stored row, 1 cache hit serving the 4-stop request.")


if __name__ == "__main__":
    main()
