#!/usr/bin/env python3
"""backfill_tour_coords.py — LOCAL-605 backfill (reversible, dry-run by default).

Lists ``audio_tours`` rows with NULL ``lat``/``lng`` whose ``tour_content`` has a
Stop 1 ``Coordinates:`` line, and the ``(lat, lng)`` it WOULD set from that line.

This is the clean-up for tours already delivered with NULL coordinates by the
pool/cache/overview/by-reference paths (LOCAL-605) — invisible in "tours near me"
with no map pin. The code fix stops NEW tours losing coordinates; this script
proposes repairing the ones already stored.

SAFETY (this script never writes unless you force it):
  * Default mode is ``--dry-run``: it only PRINTS what it would change.
  * It writes ONLY when ``--apply`` is passed explicitly. LEAD decides whether to
    run with ``--apply``; this script is delivered dry-run and MUST NOT be applied
    as part of LOCAL-605.
  * It EXCLUDES ``is_test = TRUE`` rows. These include tours deliberately hidden by
    the CLAUDE.md test-artifact rule, whose lat/lng were nulled ON PURPOSE
    (tests/test_tour_helper.py: cleanup sets lat=NULL, lng=NULL, is_test=TRUE —
    never DELETE). Backfilling them would make hidden artefacts reappear in
    tours-near. We never touch them.
  * It EXCLUDES rows created on or before 2026-10-04, listing ONLY rows created
    AFTER that date — so a pre-existing deliberately-nulled row (hidden before the
    LOCAL-605 window) is never resurrected.
  * The repair is reversible: the UPDATE only sets lat/lng on rows that are
    currently NULL, so re-running with the current NULLs recorded (printed below)
    is enough to revert. No other column is touched; no row is created or deleted.

Usage:
    python3 backfill_tour_coords.py                 # dry-run (default) — lists only
    python3 backfill_tour_coords.py --dry-run       # same, explicit
    python3 backfill_tour_coords.py --apply         # WRITES (LEAD only; not for LOCAL-605)
    python3 backfill_tour_coords.py --created-after 2026-10-04   # override the window

Connection: DATABASE_URL env var, else DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD,
else localhost:5433/audiotours (admin/password123) — the Mac Mini dev default.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tour_coordinates import parse_stop1_coordinates, coordinates_present

# The LOCAL-605 window: rows created strictly AFTER this date are eligible.
# Earlier NULL-coordinate rows may have been deliberately hidden and must not be
# resurrected (CLAUDE.md test-artifact rule).
DEFAULT_CREATED_AFTER = "2026-10-04"


def _connect():
    """Open a psycopg2 connection from DATABASE_URL or discrete env vars."""
    import psycopg2
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5433"),
        dbname=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"),
    )


def _fetch_candidates(cur, created_after: str):
    """Rows with NULL lat/lng, not is_test, created AFTER the window, with content.

    original_tour_id IS NULL keeps us to ORIGINAL tours (translations/derived rows
    inherit from their original and are not independently placed on the map).
    """
    cur.execute(
        """
        SELECT id, tour_name, created_at, tour_content
        FROM audio_tours
        WHERE (lat IS NULL OR lng IS NULL)
          AND (is_test IS NOT TRUE)
          AND original_tour_id IS NULL
          AND tour_content IS NOT NULL
          AND created_at > %s
        ORDER BY id
        """,
        (created_after,),
    )
    return cur.fetchall()


def main(argv=None):
    parser = argparse.ArgumentParser(description="LOCAL-605 tour-coordinate backfill (dry-run by default).")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", default=True,
                       help="List proposed changes only (default). Writes nothing.")
    group.add_argument("--apply", action="store_true", default=False,
                       help="ACTUALLY write lat/lng. LEAD only — not part of LOCAL-605.")
    parser.add_argument("--created-after", default=DEFAULT_CREATED_AFTER,
                        help=f"Only rows created strictly after this date (default {DEFAULT_CREATED_AFTER}).")
    args = parser.parse_args(argv)

    apply = bool(args.apply)
    mode = "APPLY (writing)" if apply else "DRY-RUN (no writes)"

    print("=" * 78)
    print(f"LOCAL-605 backfill_tour_coords — {mode}")
    print(f"  window: created_at > {args.created_after}")
    print(f"  excludes: is_test=TRUE (incl. deliberately-hidden), derived/translation rows")
    print("=" * 78)

    try:
        conn = _connect()
    except Exception as e:
        print(f"ERROR: could not connect to the database: {e}")
        return 2

    cur = conn.cursor()
    try:
        rows = _fetch_candidates(cur, args.created_after)
    except Exception as e:
        print(f"ERROR: query failed: {e}")
        cur.close()
        conn.close()
        return 2

    proposed = []   # (id, tour_name, created_at, lat, lng)
    skipped = []    # (id, tour_name, reason)
    for (tid, tour_name, created_at, tour_content) in rows:
        lat, lng = parse_stop1_coordinates(tour_content or "")
        if coordinates_present((lat, lng)):
            proposed.append((tid, tour_name, created_at, float(lat), float(lng)))
        else:
            skipped.append((tid, tour_name, "no parseable Stop 1 Coordinates line"))

    print(f"\nFound {len(rows)} NULL-coordinate candidate row(s) in the window.")
    print(f"  {len(proposed)} have a Stop 1 Coordinates line we could set.")
    print(f"  {len(skipped)} have NULL coordinates but no usable Stop 1 line (left untouched).\n")

    if proposed:
        print("WOULD SET (reversible — these rows are currently NULL):")
        print(f"  {'id':>6}  {'created_at':<20} {'lat':>12} {'lng':>12}  tour_name")
        for (tid, tour_name, created_at, lat, lng) in proposed:
            print(f"  {tid:>6}  {str(created_at):<20} {lat:>12.6f} {lng:>12.6f}  {tour_name}")

    if skipped:
        print("\nSKIPPED (NULL coords, no usable Stop 1 Coordinates line):")
        for (tid, tour_name, reason) in skipped:
            print(f"  {tid:>6}  {tour_name}  — {reason}")

    if not apply:
        print("\nDRY-RUN complete. No rows were modified. Re-run with --apply to write "
              "(LEAD decision — not part of LOCAL-605).")
        cur.close()
        conn.close()
        return 0

    # --apply path (guarded; only reached when LEAD explicitly asks for it).
    print("\n--apply given: writing lat/lng ONLY on rows that are currently NULL ...")
    written = 0
    try:
        for (tid, _tour_name, _created_at, lat, lng) in proposed:
            cur.execute(
                """
                UPDATE audio_tours
                SET lat = %s, lng = %s
                WHERE id = %s AND (lat IS NULL OR lng IS NULL) AND is_test IS NOT TRUE
                """,
                (lat, lng, tid),
            )
            written += cur.rowcount
        conn.commit()
        print(f"Wrote coordinates to {written} row(s).")
    except Exception as e:
        conn.rollback()
        print(f"ERROR during apply (rolled back, nothing written): {e}")
        cur.close()
        conn.close()
        return 2

    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
