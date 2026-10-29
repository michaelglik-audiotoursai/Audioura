#!/usr/bin/env python3
"""local811_pool_audit.py — [LOCAL-811] one-off audit of the current Mac
``stop_pool`` MUSEUM rows against the LOCAL-809 checks.

The LOCAL-811 wiring stops a BAD pooled stop being re-served from now on, but the
rows already in the pool (delivered and saved before the fix) are still there. This
one-off tool runs the SAME ``pool_museum_checks`` over every pooled MUSEUM row and
reports the ones that fail — merchandise/shop titles, works NOT in the venue's
collection, and disambiguation stubs.

Two modes (dry-run is the default; nothing is ever deleted without ``--apply``):

    python local811_pool_audit.py            # DRY RUN: print the report only
    python local811_pool_audit.py --apply    # MOVE failing rows out of the pool

``--apply`` moves each failing row out of ``stop_pool`` into ``stop_pool_rejected``
via the verified ``stop_pool_rejected.move_to_rejected`` (copy-before-delete, one
transaction) — the ONLY allowed removal, exactly as LOCAL-792 does it. It prints
the before/after ``stop_pool`` row counts.

SAFETY. This tool touches ONLY ``stop_pool`` / ``stop_pool_rejected`` on the Mac
database given by ``--db-url`` / ``$DATABASE_URL``. It NEVER touches
``audio_tours`` or any other table. It refuses to run against a URL that looks like
the production ``audio_tours`` service DB unless ``--force`` is given. The venue
work set for the collection check is read CACHE-FIRST (LOCAL-810
venue_works_cache) so the audit adds no paid-API cost on a warm cache; a cache miss
runs one bounded, free WDQS query per venue (never the fallback chain).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

try:
    import psycopg2
except Exception as _e:  # pragma: no cover
    print(f"psycopg2 unavailable: {_e}", file=sys.stderr)
    sys.exit(2)

import pool_museum_checks as pmc
import stop_pool_rejected as rej


# Columns read from stop_pool for each candidate row (enough to run every check
# and to rebuild the reuse-candidate dict pool_museum_checks consumes).
_READ_COLS = [
    "pool_key", "title_norm", "venue_identity", "tour_type", "title",
    "artist", "year", "narration", "raw_block", "sources_json",
    "stop_record_json",
]


def _connect(db_url: str):
    return psycopg2.connect(db_url)


def _row_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM stop_pool")
        return cur.fetchone()[0]


def _read_rows(conn) -> List[Dict]:
    cols = ", ".join(_READ_COLS)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {cols} FROM stop_pool")
        fetched = cur.fetchall()
    rows = []
    for r in fetched:
        d = dict(zip(_READ_COLS, r))
        # Normalise JSON columns to the shapes pool_museum_checks expects.
        try:
            d["sources"] = json.loads(d.get("sources_json") or "[]")
        except Exception:
            d["sources"] = []
        try:
            d["stop_record"] = json.loads(d["stop_record_json"]) if d.get("stop_record_json") else None
        except Exception:
            d["stop_record"] = None
        rows.append(d)
    return rows


def _qid_from_identity(identity: str) -> Optional[str]:
    """The venue QID a stop was keyed under, or None for a location-only identity."""
    if identity and identity.startswith("qid:"):
        return identity[4:]
    return None


def _venue_name_from_identity(identity: str) -> str:
    """A readable venue name for the title/shop checks. The identity is either
    ``qid:<Q…>`` (no name) or a normalised location string; the latter is the best
    name we have for the title-level guards."""
    if not identity:
        return ""
    if identity.startswith("qid:"):
        return ""
    return identity


def _venue_works(qid: Optional[str]):
    """Cache-first venue work set + derived parent/sibling collection QIDs for the
    membership check. Returns ([], ()) when no QID — the membership arm is then a
    no-op and only the title/body arms judge the row (never a wrong rejection)."""
    if not qid:
        return [], ()
    works = []
    try:
        import venue_resolver as vr
        works = vr.venue_works_cache_get(qid) or []
        if not works:
            try:
                works = vr.fetch_venue_works(qid) or []
            except Exception as e:
                print(f"    [audit] venue-works fetch skipped for {qid} ({e}); "
                      f"membership arm disabled for this venue")
                works = []
    except Exception as e:
        print(f"    [audit] venue_resolver unavailable ({e}); membership disabled")
        return [], ()

    parents = set()
    try:
        from collections import Counter
        p195 = Counter(q for w in (works or [])
                       for q in set((w or {}).get("collection_qids") or []))
        thr = max(3, int(0.10 * max(1, len(works or []))))
        for q, c in p195.items():
            if c >= thr and q != qid:
                parents.add(q)
    except Exception:
        pass
    try:
        import venue_resolver as vr2
        for rq in (vr2.fetch_collection_holder_qids(qid) or ()):
            if rq:
                parents.add(rq)
    except Exception:
        pass
    return works, tuple(parents)


def _is_art_museum(venue_name: str, works) -> bool:
    try:
        from generate_tour_text import _is_art_museum as _iam
        return bool(_iam(venue_name, works))
    except Exception:
        return True


def _is_contained(identity: str, venue_name: str, tour_type: str,
                  qid: Optional[str]) -> bool:
    """[LOCAL-811B] True when a pooled venue group is a CONTAINED (museum/facility)
    tour, False for a walking / neighbourhood pool.

    The LEAD rule (item 4): the room/space-title reject must apply ONLY to
    contained tours, never to walking/neighbourhood pools (Salem Witch Trials
    Memorial, Salem Common, Salem Maritime NHS, Salem Willows Park …). The audit
    groups the whole pool by (venue_identity, tour_type); here we reuse the
    orchestrator's own classification so the audit judges a group exactly as the
    live reuse path would.

    A QID-keyed identity is a resolved single venue → treated as contained (the
    pool keys a museum/facility under its QID; a walking pool is keyed by the
    location string, not a QID). A location-string identity is classified by the
    generator's own ``_classify_tour_category`` against the location + tour_type;
    'museum'/'facility' → contained, everything else (walking/restaurant/
    specialized) → not contained. Any failure defaults to contained=True so the
    museum checks are never silently disabled on a real museum pool."""
    try:
        from stop_pool_orchestrator import _is_contained as _orch_is_contained
        from generate_tour_text import _classify_tour_category
    except Exception:
        # Without the classifier, a QID identity is a resolved venue (contained);
        # a bare location string is treated as not contained only when it is
        # obviously a walking request, else default contained.
        loc = identity if (identity and not identity.startswith("qid:")) else venue_name
        return not bool(re.search(r"(?i)\bwalk(?:ing)?\b", loc or "")) if loc else True

    # Best location text we have for the classifier: the location-string identity,
    # else the venue name.
    loc = identity if (identity and not identity.startswith("qid:")) else venue_name
    try:
        cat = _classify_tour_category(loc or venue_name or "", tour_type or "")
    except Exception:
        cat = (tour_type or "").strip().lower()
    # A QID-keyed pool is a resolved museum/facility venue; keep it contained even
    # if the (often empty) location text would not classify as museum.
    if qid:
        return True
    return bool(_orch_is_contained(cat))


def audit(conn, only_qid: Optional[str] = None) -> List[Tuple[Dict, str]]:
    """Run the LOCAL-809 checks over every pooled museum row. Returns the list of
    ``(row, reason)`` failures. Groups rows by (venue_identity, tour_type) so the
    venue work set is fetched ONCE per venue."""
    rows = _read_rows(conn)
    print(f"stop_pool rows read: {len(rows)}")

    by_venue: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for r in rows:
        by_venue[(r.get("venue_identity") or "", r.get("tour_type") or "")].append(r)

    failures: List[Tuple[Dict, str]] = []
    for (identity, tour_type), group in sorted(by_venue.items()):
        qid = _qid_from_identity(identity)
        if only_qid and qid != only_qid:
            continue
        venue_name = _venue_name_from_identity(identity)
        works, parents = _venue_works(qid)
        is_art = _is_art_museum(venue_name, works)
        contained = _is_contained(identity, venue_name, tour_type, qid)
        kept, rejected = pmc.split_pooled_museum_stops(
            group, venue_name=venue_name, venue_qid=(qid or ""),
            parent_qids=parents, sparql_works=works, is_art_museum=is_art,
            contained=contained)
        label = identity or "(no identity)"
        _mem = "n" if not works else f"{len(works)} works"
        print(f"\n== venue {label} | tour_type={tour_type!r} | qid={qid or '-'} "
              f"| contained={contained} | membership-set={_mem} | rows={len(group)} | "
              f"fail={len(rejected)} ==")
        for r, reason in rejected:
            print(f"   FAIL  {r.get('title','')!r:60}  {reason}")
            failures.append((r, reason))
    return failures


def apply_moves(conn, failures: List[Tuple[Dict, str]]) -> int:
    """Move each failing row out of stop_pool via the verified move_to_rejected
    (copy-before-delete, one transaction). Returns the number moved."""
    if not failures:
        return 0
    moved_total = 0
    for r, reason in failures:
        pk = r.get("pool_key")
        tn = r.get("title_norm")
        if not pk or not tn:
            continue
        try:
            moved = rej.move_to_rejected(
                conn, [(pk, tn)],
                reason=f"auto:local811:{reason}",
                rejected_by="local811_pool_audit",
                source_tour_id=None)
            conn.commit()
            moved_total += moved
            if moved:
                print(f"   MOVED {r.get('title','')!r} out of the pool ({reason})")
        except Exception as e:
            conn.rollback()
            print(f"   SKIP  {r.get('title','')!r} — move failed ({e}); pool unchanged")
    return moved_total


def main(argv=None):
    ap = argparse.ArgumentParser(description="LOCAL-811 stop_pool museum audit")
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"),
                    help="Postgres URL (defaults to $DATABASE_URL)")
    ap.add_argument("--apply", action="store_true",
                    help="MOVE failing rows out of the pool (default: dry run)")
    ap.add_argument("--qid", default=None,
                    help="restrict the audit to one venue QID (e.g. Q303139)")
    ap.add_argument("--force", action="store_true",
                    help="run even if the DB URL looks like a production service DB")
    args = ap.parse_args(argv)

    if not args.db_url:
        print("no --db-url / $DATABASE_URL", file=sys.stderr)
        return 2

    mode = "APPLY (move failing rows)" if args.apply else "DRY RUN (report only)"
    print(f"=== LOCAL-811 stop_pool museum audit — {mode} ===")
    print(f"db: {args.db_url.rsplit('@', 1)[-1]}")

    # Refuse a URL that looks like a production service database unless --force.
    # This tool only ever touches stop_pool / stop_pool_rejected, but the guard
    # keeps it from pointing at the wrong host by accident.
    _looks_prod = any(tok in args.db_url.lower()
                      for tok in ("audioura", "prod", "amazonaws.com"))
    if _looks_prod and not args.force:
        print("REFUSING: the DB URL looks like a production service DB. "
              "This tool is for the Mac dev/pool DB only. Pass --force to override.",
              file=sys.stderr)
        return 2

    conn = _connect(args.db_url)
    try:
        # Confirm the table exists; refuse gracefully if not.
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('stop_pool')")
            if cur.fetchone()[0] is None:
                print("stop_pool table not found — nothing to audit.")
                return 0

        before = _row_count(conn)
        print(f"stop_pool rows BEFORE: {before}")

        failures = audit(conn, only_qid=args.qid)
        print(f"\n--- {len(failures)} pooled museum stop(s) FAIL the LOCAL-809 checks ---")

        if not args.apply:
            print("\nDRY RUN: no rows moved. Re-run with --apply to quarantine them.")
            return 0

        moved = apply_moves(conn, failures)
        after = _row_count(conn)
        print(f"\nstop_pool rows AFTER:  {after}  (moved out: {moved}, "
              f"delta={before - after})")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
