#!/usr/bin/env python3
"""
reject_stops.py — LOCAL-792 / D726 (amended, Michael 2026-10-27).
=================================================================
Move INCORRECT-content stops of a tour OUT of ``stop_pool`` into
``stop_pool_rejected`` — "the pool holds only good material; the evidence lives
outside it for the failure analysis" (D723). This is the ONLY place a human moves
a ``stop_pool`` row, and it does so ONLY after a verified copy, in ONE transaction.
It never touches ``audio_tours``.

Usage
-----
    # Dry run (DEFAULT — shows what WOULD move, changes nothing):
    reject_stops.py --tour-id 463 --stop 2 --stop 4 \
        --reason "news headline / fabricated entry" --by GCloud_Storied

    # Apply (copy-then-remove in one transaction, verified):
    reject_stops.py --tour-id 463 --stop 2 --stop 4 \
        --reason "news headline / fabricated entry" --by GCloud_Storied --apply

    # Restore (move the rows back, stop_pool_rejected → stop_pool):
    reject_stops.py --tour-id 463 --stop 2 --stop 4 --restore --apply

``--stop K`` selects the K-th "Stop K:" of the tour's delivered content (1-based,
as the tour numbers them). Omit --stop to act on EVERY stop of the tour. The pool
identity (pool_key, title_norm) for each selected stop is computed EXACTLY as the
pool store keys it — under BOTH the QID key and the normalised-location key — so a
stop is found/moved whichever key it was stored under.

DATABASE_URL must be set (or pass --db-url). Dry run is the default: you must pass
``--apply`` for any write. Row counts of BOTH tables are printed before and after.
"""
import argparse
import os
import re
import sys
from typing import List, Optional, Tuple

import psycopg2


def _die(msg: str, code: int = 1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def _tour_type_from_tour(tour_name: str, tour_content: str) -> str:
    """Recover the tour_type the pool keyed on from the tour's own text — the
    category word before ' Tour' on the first line (store_audio_tour builds the
    name and the content header the same way). Mirrors
    stop_pool_sources._tour_type_from_tour so the key matches the pool row."""
    for text in (tour_content or "", tour_name or ""):
        first = (text or "").split("\n", 1)[0].strip()
        m = re.search(r"-\s*(.+?)\s+Tour\s*$", first)
        if m:
            return m.group(1).strip().lower()
    return ""


def _resolve_stops(
    conn,
    tour_id: int,
    stop_indices: Optional[List[int]],
) -> Tuple[List[Tuple[str, str, str]], str, str, str]:
    """Return ([(pool_key, title_norm, title)], location, tour_type, venue_identity)
    for the selected stops of ``tour_id``.

    The tour is read from ``audio_tours``; its content is parsed into the SAME stop
    units the pool stores, and each selected stop's (pool_key, title_norm) is
    computed under BOTH the QID and the location identity (so the move finds the
    row whichever key it lives under). ``stop_indices`` is 1-based; None selects
    every stop.
    """
    import stop_pool_store as pool

    with conn.cursor() as cur:
        cur.execute(
            "SELECT tour_name, request_string, tour_content "
            "FROM audio_tours WHERE id = %s",
            (int(tour_id),),
        )
        row = cur.fetchone()
    if not row:
        _die(f"tour {tour_id} not found in audio_tours")
    tour_name, request_string, tour_content = row
    if not tour_content:
        _die(f"tour {tour_id} has no tour_content to parse")

    location = request_string or tour_name or ""
    tour_type = _tour_type_from_tour(tour_name, tour_content)
    try:
        identity = pool.resolve_venue_identity(location)
    except Exception:
        identity = pool.venue_identity(location)
    qid = identity[4:] if identity.startswith("qid:") else None

    # Candidate pool keys: QID identity + plain location identity (D582 dual-key).
    keys = []
    if qid:
        keys.append(pool._pool_key(pool.venue_identity(location, qid), tour_type))
    loc_key = pool._pool_key(pool.venue_identity(location), tour_type)
    if loc_key not in keys:
        keys.append(loc_key)

    units = pool.parse_delivered_stops(tour_content)
    if not units:
        _die(f"tour {tour_id} parsed to 0 stops (nothing to select)")

    want = set(stop_indices) if stop_indices else None
    selected: List[Tuple[str, str, str]] = []
    for i, u in enumerate(units, start=1):
        if want is not None and i not in want:
            continue
        tnorm = pool._title_norm(u.get("title") or "")
        if not tnorm:
            continue
        for pk in keys:
            selected.append((pk, tnorm, u.get("title", "")))

    if want is not None:
        missing = want - set(range(1, len(units) + 1))
        if missing:
            print(f"  WARNING: stop index(es) {sorted(missing)} are beyond the "
                  f"{len(units)} stops in tour {tour_id}; ignored.")
    return selected, location, tour_type, identity


def _present_in(conn, table: str, keys: List[Tuple[str, str, str]]) -> List[Tuple[str, str, str]]:
    """Return the subset of ``keys`` whose (pool_key, title_norm) is present in
    ``table`` — used by the dry run to show exactly what would move."""
    import stop_pool_rejected as rej
    if not rej._table_exists(conn, table):
        return []
    present = []
    with conn.cursor() as cur:
        for pk, tn, title in keys:
            cur.execute(
                f"SELECT 1 FROM {table} WHERE pool_key = %s AND title_norm = %s",
                (pk, tn),
            )
            if cur.fetchone():
                present.append((pk, tn, title))
    return present


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="LOCAL-792: move incorrect stops out of stop_pool into "
                    "stop_pool_rejected (verified copy-then-remove), or restore.")
    ap.add_argument("--tour-id", type=int, required=True,
                    help="audio_tours.id whose reuse surfaced the bad stop(s).")
    ap.add_argument("--stop", type=int, action="append", dest="stops",
                    help="1-based stop index to act on (repeatable). Omit for ALL "
                         "stops of the tour.")
    ap.add_argument("--reason", default="",
                    help="Why the stop(s) are incorrect (stored in reject_reason). "
                         "Required for --apply unless --restore.")
    ap.add_argument("--by", dest="by", default="",
                    help="Who is moving the stop(s) (stored in rejected_by). "
                         "Required for --apply unless --restore.")
    ap.add_argument("--restore", action="store_true",
                    help="Move the selected stop(s) BACK (stop_pool_rejected → "
                         "stop_pool) instead of rejecting them.")
    ap.add_argument("--apply", action="store_true",
                    help="Actually perform the move. Without this it is a DRY RUN "
                         "(nothing is written).")
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"),
                    help="Postgres URL (default: $DATABASE_URL).")
    args = ap.parse_args(argv)

    if not args.db_url:
        _die("DATABASE_URL not set and --db-url not given")
    if args.apply and not args.restore:
        if not args.reason or not args.by:
            _die("--reason and --by are required with --apply (reject)")

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stop_pool_rejected as rej

    conn = psycopg2.connect(args.db_url)
    try:
        rej.ensure_table(conn)

        selected, location, tour_type, identity = _resolve_stops(
            conn, args.tour_id, args.stops)
        # Dedup (pool_key, title_norm) across the dual keys for the move call.
        move_keys = []
        _seen = set()
        for pk, tn, _title in selected:
            if (pk, tn) not in _seen:
                _seen.add((pk, tn))
                move_keys.append((pk, tn))

        mode = "RESTORE" if args.restore else "REJECT"
        print(f"=== reject_stops.py [{mode}] {'APPLY' if args.apply else 'DRY RUN'} ===")
        print(f"  tour_id={args.tour_id}  venue_identity={identity}  tour_type={tour_type!r}")
        print(f"  location={location!r}")
        print(f"  stops selected: {args.stops if args.stops else 'ALL'}")

        pool_before, rej_before = rej._counts(conn)
        print(f"  BEFORE: stop_pool={pool_before}  stop_pool_rejected={rej_before}")

        # Show exactly which selected stops are present in the source table.
        src_table = "stop_pool_rejected" if args.restore else "stop_pool"
        present = _present_in(conn, src_table, selected)
        print(f"  {len(present)} selected stop(s) present in {src_table}:")
        for _pk, _tn, title in present:
            print(f"    - {title!r}  (title_norm={_tn!r})")
        if not present:
            print(f"  Nothing to {'restore' if args.restore else 'reject'} "
                  f"(none of the selected stops are in {src_table}).")

        if not args.apply:
            print("  DRY RUN — no changes written. Re-run with --apply to perform "
                  "the move.")
            conn.rollback()
            return 0

        # Apply, in ONE transaction. The module's move/restore verifies the copy
        # count before any delete and raises on mismatch → we roll back.
        try:
            if args.restore:
                n = rej.restore_from_rejected(conn, move_keys)
            else:
                n = rej.move_to_rejected(
                    conn, move_keys, reason=args.reason, rejected_by=args.by,
                    source_tour_id=int(args.tour_id))
            conn.commit()
        except Exception as e:
            conn.rollback()
            _die(f"move aborted and rolled back (no change): {e}")

        pool_after, rej_after = rej._counts(conn)
        print(f"  MOVED {n} stop(s).")
        print(f"  AFTER:  stop_pool={pool_after}  stop_pool_rejected={rej_after}")
        # Sanity: the two tables' deltas must mirror each other.
        _d_pool = pool_after - pool_before
        _d_rej = rej_after - rej_before
        print(f"  delta: stop_pool={_d_pool:+d}  stop_pool_rejected={_d_rej:+d}")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
