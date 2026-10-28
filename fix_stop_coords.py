#!/usr/bin/env python3
"""
fix_stop_coords.py — LOCAL-792 / D726 (amended, Michael 2026-10-27).
====================================================================
The WRONG-PIN case: a real place with good research but the WRONG coordinates
(461 Opera House, ~0.7 km off). The stop is CORRECT content — it must stay in the
pool — so instead of rejecting it, re-geocode the place and UPDATE its coordinates
IN PLACE: in the pooled row (``stop_pool.coordinates``) AND in the tour's stored
stop (the ``Coordinates:`` line of ``audio_tours.tour_content``). Prints the old
and new coordinates and the distance moved.

Usage
-----
    # Dry run (DEFAULT — shows old/new/distance, changes nothing):
    fix_stop_coords.py --tour-id 461 --stop 3

    # Apply the coordinate correction in place:
    fix_stop_coords.py --tour-id 461 --stop 3 --apply

``--stop K`` is the 1-based "Stop K:" of the tour's delivered content. The new
coordinates are found by geocoding the stop's own name/address (``geocode_stops``,
Nominatim with the LOCAL fallback variants). Nothing is invented: if the place
cannot be geocoded, the stop is left exactly as it was.

This tool only ever UPDATEs a coordinate string — it never INSERTs, DELETEs, moves
a row, or touches any column other than ``coordinates`` (pool) and the stop's
``Coordinates:`` line (tour content). It never removes a stop from the pool
(that is reject_stops.py) and never touches audio_tours rows other than the named
tour's content.

DATABASE_URL must be set (or pass --db-url). Dry run is the default: pass
``--apply`` to write.
"""
import argparse
import math
import os
import re
import sys
from typing import Optional, Tuple

import psycopg2


def _die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


_COORD_RE = re.compile(r"\s*(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*")


def _parse_coords(s: str) -> Optional[Tuple[float, float]]:
    """Parse a 'lat, lng' string to (lat, lng) floats, or None."""
    if not s:
        return None
    m = _COORD_RE.fullmatch(s.strip()) or _COORD_RE.match(s.strip())
    if not m:
        return None
    try:
        return float(m.group(1)), float(m.group(2))
    except (TypeError, ValueError):
        return None


def _haversine_km(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance in km between (lat, lng) a and b."""
    R = 6371.0088
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _tour_type_from_tour(tour_name: str, tour_content: str) -> str:
    for text in (tour_content or "", tour_name or ""):
        first = (text or "").split("\n", 1)[0].strip()
        m = re.search(r"-\s*(.+?)\s+Tour\s*$", first)
        if m:
            return m.group(1).strip().lower()
    return ""


def _geocode_query(title: str, address: str, location: str) -> str:
    """Build the best geocoder query for a stop: prefer a full address, else the
    stop title with the tour's locality tail appended."""
    if address and address.strip():
        return address.strip()
    tail = ""
    if "," in (location or ""):
        tail = ", " + ", ".join(p.strip() for p in location.split(",")[1:3] if p.strip())
    return f"{(title or '').strip()}{tail}".strip(", ").strip()


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="LOCAL-792: re-geocode a wrong-pin stop and correct its "
                    "coordinates in place (pool row + tour content).")
    ap.add_argument("--tour-id", type=int, required=True,
                    help="audio_tours.id whose stop has the wrong pin.")
    ap.add_argument("--stop", type=int, required=True,
                    help="1-based stop index to re-geocode.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually write the corrected coordinates. Without this "
                         "it is a DRY RUN (nothing written).")
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"),
                    help="Postgres URL (default: $DATABASE_URL).")
    args = ap.parse_args(argv)
    if not args.db_url:
        _die("DATABASE_URL not set and --db-url not given")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stop_pool_store as pool
    try:
        from geocode_stops import geocode
    except Exception as e:
        _die(f"geocoder (geocode_stops) unavailable: {e}")

    conn = psycopg2.connect(args.db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tour_name, request_string, tour_content "
                "FROM audio_tours WHERE id = %s",
                (int(args.tour_id),),
            )
            row = cur.fetchone()
        if not row:
            _die(f"tour {args.tour_id} not found in audio_tours")
        tour_name, request_string, tour_content = row
        if not tour_content:
            _die(f"tour {args.tour_id} has no tour_content")

        location = request_string or tour_name or ""
        tour_type = _tour_type_from_tour(tour_name, tour_content)
        units = pool.parse_delivered_stops(tour_content)
        if not (1 <= args.stop <= len(units)):
            _die(f"stop {args.stop} is out of range (tour {args.tour_id} has "
                 f"{len(units)} stops)")
        unit = units[args.stop - 1]
        title = unit.get("title", "")
        address = unit.get("address", "")
        old_coords_str = unit.get("coordinates", "") or ""
        old_coords = _parse_coords(old_coords_str)

        query = _geocode_query(title, address, location)
        print(f"=== fix_stop_coords.py [{'APPLY' if args.apply else 'DRY RUN'}] ===")
        print(f"  tour_id={args.tour_id}  stop={args.stop}  title={title!r}")
        print(f"  geocode query: {query!r}")

        hit = geocode(query)
        if not hit:
            print(f"  Could not geocode {query!r}; leaving the stop unchanged "
                  f"(nothing is invented).")
            conn.rollback()
            return 0
        new_coords = (float(hit[0]), float(hit[1]))
        new_coords_str = f"{new_coords[0]:.6f}, {new_coords[1]:.6f}"

        dist_txt = "n/a (no parseable old coordinates)"
        if old_coords:
            dist_txt = f"{_haversine_km(old_coords, new_coords):.3f} km"
        print(f"  OLD coordinates: {old_coords_str!r}")
        print(f"  NEW coordinates: {new_coords_str!r}")
        print(f"  distance moved:  {dist_txt}")

        # Build the pool identity keys (QID + location) and the content rewrite.
        try:
            identity = pool.resolve_venue_identity(location)
        except Exception:
            identity = pool.venue_identity(location)
        qid = identity[4:] if identity.startswith("qid:") else None
        keys = []
        if qid:
            keys.append(pool._pool_key(pool.venue_identity(location, qid), tour_type))
        loc_key = pool._pool_key(pool.venue_identity(location), tour_type)
        if loc_key not in keys:
            keys.append(loc_key)
        tnorm = pool._title_norm(title)

        # Rewrite ONLY this stop's Coordinates: line in the tour content. Scope the
        # replacement to the stop's own block so a repeated coordinate elsewhere is
        # untouched.
        new_content, n_content = _rewrite_stop_coord_line(
            tour_content, args.stop, new_coords_str)

        if not args.apply:
            # Report what WOULD change.
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM stop_pool "
                    "WHERE pool_key = ANY(%s) AND title_norm = %s",
                    (keys, tnorm),
                )
                pool_hits = cur.fetchone()[0]
            print(f"  WOULD update {pool_hits} pool row(s) and "
                  f"{n_content} tour-content Coordinates line(s).")
            print("  DRY RUN — no changes written. Re-run with --apply to correct.")
            conn.rollback()
            return 0

        # Apply: UPDATE the pool row(s) coordinates, and the tour content, in one
        # transaction. UPDATE only — never a DELETE or INSERT.
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE stop_pool SET coordinates = %s "
                "WHERE pool_key = ANY(%s) AND title_norm = %s",
                (new_coords_str, keys, tnorm),
            )
            pool_updated = cur.rowcount
            content_updated = 0
            if n_content:
                cur.execute(
                    "UPDATE audio_tours SET tour_content = %s WHERE id = %s",
                    (new_content, int(args.tour_id)),
                )
                content_updated = cur.rowcount
        conn.commit()
        print(f"  UPDATED {pool_updated} pool row(s); tour-content rows updated: "
              f"{content_updated} ({n_content} Coordinates line(s) rewritten).")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _rewrite_stop_coord_line(tour_content: str, stop_index: int,
                             new_coords_str: str) -> Tuple[str, int]:
    """Replace the ``Coordinates:`` line inside the ``Stop <stop_index>:`` block of
    ``tour_content`` with ``new_coords_str``. Returns (new_content, lines_changed).

    The replacement is scoped to the block between this stop's header and the next
    ``Stop N:`` header (or end of text), so only this stop's coordinate is touched.
    If the stop has no ``Coordinates:`` line, nothing changes (returns 0)."""
    headers = list(re.finditer(r'^Stop (\d+):', tour_content or "", re.M))
    if not headers or stop_index < 1 or stop_index > len(headers):
        return tour_content, 0
    start = headers[stop_index - 1].start()
    end = headers[stop_index].start() if stop_index < len(headers) else len(tour_content)
    block = tour_content[start:end]
    new_block, n = re.subn(
        r'(?m)^(Coordinates:\s*).+?\s*$',
        lambda m: m.group(1) + new_coords_str,
        block, count=1)
    if not n:
        return tour_content, 0
    return tour_content[:start] + new_block + tour_content[end:], n


if __name__ == "__main__":
    sys.exit(main())
