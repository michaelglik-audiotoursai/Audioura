#!/usr/bin/env python3
"""local811_pool_restore.py — [LOCAL-811B] restore the pooled rows that the
first LOCAL-811 audit (``rejected_by = 'local811_pool_audit'``) moved out of
``stop_pool`` WRONGLY, after the LEAD review of
``reports/local811_pool_audit_apply.txt``.

The LEAD found the audit over-rejected real artworks:
  1. a substring "shop" / a quoted title that merely reads like a sentence
     ("The Shop Girl"; '"I am half sick of shadows," said the Lady of Shalott');
  2. a MULTIPLE (cast/print/edition) rejected on one foreign P195 ("The Age of
     Bronze");
  3. two works WRONGLY called foreign to the Belvedere (a ticket error, not a
     pool defect — no pooled Belvedere row was actually moved for this, but the
     corrected guard keeps a museum's own work);
  4. ``room_or_space_title`` applied to WALKING / neighbourhood pools (every
     Salem row).

Rather than hand-pick rows, this tool is SELF-CONSISTENT with the fixed guards:
for every ``local811_pool_audit`` row still in ``stop_pool_rejected`` it rebuilds
the candidate (from the preserved ``stop_record_json`` / ``sources_json``),
classifies the group's ``contained`` flag exactly as the audit now does, fetches
the venue work set CACHE-FIRST (LOCAL-810, no paid API on a warm cache), and
re-runs ``pool_museum_checks.check_pooled_museum_stop``. A row the CORRECTED check
now KEEPS is restored to ``stop_pool`` via the verified LOCAL-792
``restore_from_rejected`` (copy-before-delete, one transaction); a row that still
fails (a real shop/CTA title, an exhibition-title pipe, an event, a unique foreign
work) stays quarantined. This is the ticket's "restore every row moved for reasons
1–3 and walking-pool rows under 4" expressed as: restore iff the fixed logic no
longer rejects it.

Modes mirror the audit (dry-run default; nothing moves without ``--apply``):

    python local811_pool_restore.py            # DRY RUN: list what WOULD restore
    python local811_pool_restore.py --apply     # RESTORE the now-kept rows

SAFETY: touches ONLY ``stop_pool`` / ``stop_pool_rejected`` on the ``--db-url`` /
``$DATABASE_URL`` Mac DB (same production-URL refusal as the audit). Never
``audio_tours``.
"""
from __future__ import annotations

import argparse
import json
import os
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
# Reuse the audit's venue-works + contained + art-museum helpers so a restore
# judges a row EXACTLY as the (fixed) audit would judge it fresh.
import local811_pool_audit as audit

_REJECTED_BY = "local811_pool_audit"

# Columns read from stop_pool_rejected for each candidate row (enough to rebuild
# the candidate the checks consume).
_READ_COLS = [
    "pool_key", "title_norm", "venue_identity", "tour_type", "title",
    "artist", "year", "narration", "raw_block", "sources_json",
    "stop_record_json", "reject_reason",
]


def _connect(db_url: str):
    return psycopg2.connect(db_url)


def _row_count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT count(*) FROM {table}")
        return cur.fetchone()[0]


def _read_rejected_rows(conn) -> List[Dict]:
    cols = ", ".join(_READ_COLS)
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {cols} FROM stop_pool_rejected WHERE rejected_by = %s",
            (_REJECTED_BY,))
        fetched = cur.fetchall()
    rows = []
    for r in fetched:
        d = dict(zip(_READ_COLS, r))
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


def select_restorable(conn, only_qid: Optional[str] = None
                      ) -> Tuple[List[Dict], List[Tuple[Dict, str]]]:
    """Return ``(restorable_rows, still_rejected)``. A row is restorable when the
    LEAD-corrected ``check_pooled_museum_stop`` now KEEPS it. Grouped by
    (venue_identity, tour_type) so the venue work set + contained flag are computed
    once per group, exactly as the audit does."""
    rows = _read_rejected_rows(conn)
    print(f"stop_pool_rejected rows by {_REJECTED_BY}: {len(rows)}")

    by_venue: Dict[Tuple[str, str], List[Dict]] = defaultdict(list)
    for r in rows:
        by_venue[(r.get("venue_identity") or "", r.get("tour_type") or "")].append(r)

    restorable: List[Dict] = []
    still_rejected: List[Tuple[Dict, str]] = []
    for (identity, tour_type), group in sorted(by_venue.items()):
        qid = audit._qid_from_identity(identity)
        if only_qid and qid != only_qid:
            continue
        venue_name = audit._venue_name_from_identity(identity)
        works, parents = audit._venue_works(qid)
        is_art = audit._is_art_museum(venue_name, works)
        contained = audit._is_contained(identity, venue_name, tour_type, qid)
        kept, rejected = pmc.split_pooled_museum_stops(
            group, venue_name=venue_name, venue_qid=(qid or ""),
            parent_qids=parents, sparql_works=works, is_art_museum=is_art,
            contained=contained)
        print(f"\n== venue {identity or '(no identity)'} | tour_type={tour_type!r} "
              f"| qid={qid or '-'} | contained={contained} | rows={len(group)} "
              f"| now_kept={len(kept)} | still_rejected={len(rejected)} ==")
        for r in kept:
            print(f"   RESTORE  {r.get('title','')!r:60}  (was: {r.get('reject_reason','')})")
            restorable.append(r)
        for r, reason in rejected:
            print(f"   KEEP-REJECTED  {r.get('title','')!r:60}  {reason}")
            still_rejected.append((r, reason))
    return restorable, still_rejected


def apply_restores(conn, restorable: List[Dict]) -> int:
    """Restore each now-kept row to stop_pool via the verified restore_from_rejected
    (copy-before-delete, one transaction per row). Returns the number restored."""
    if not restorable:
        return 0
    restored_total = 0
    for r in restorable:
        pk = r.get("pool_key")
        tn = r.get("title_norm")
        if not pk or not tn:
            continue
        try:
            n = rej.restore_from_rejected(conn, [(pk, tn)])
            conn.commit()
            restored_total += n
            if n:
                print(f"   RESTORED {r.get('title','')!r} back to the pool")
        except Exception as e:
            conn.rollback()
            print(f"   SKIP  {r.get('title','')!r} — restore failed ({e}); pool unchanged")
    return restored_total


def main(argv=None):
    ap = argparse.ArgumentParser(description="LOCAL-811B stop_pool restore")
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"),
                    help="Postgres URL (defaults to $DATABASE_URL)")
    ap.add_argument("--apply", action="store_true",
                    help="RESTORE the now-kept rows (default: dry run)")
    ap.add_argument("--qid", default=None,
                    help="restrict the restore to one venue QID")
    ap.add_argument("--force", action="store_true",
                    help="run even if the DB URL looks like a production service DB")
    args = ap.parse_args(argv)

    if not args.db_url:
        print("no --db-url / $DATABASE_URL", file=sys.stderr)
        return 2

    mode = "APPLY (restore now-kept rows)" if args.apply else "DRY RUN (report only)"
    print(f"=== LOCAL-811B stop_pool restore — {mode} ===")
    print(f"db: {args.db_url.rsplit('@', 1)[-1]}")

    _looks_prod = any(tok in args.db_url.lower()
                      for tok in ("audioura", "prod", "amazonaws.com"))
    if _looks_prod and not args.force:
        print("REFUSING: the DB URL looks like a production service DB. "
              "This tool is for the Mac dev/pool DB only. Pass --force to override.",
              file=sys.stderr)
        return 2

    conn = _connect(args.db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('stop_pool'), to_regclass('stop_pool_rejected')")
            sp, spr = cur.fetchone()
            if sp is None or spr is None:
                print("stop_pool / stop_pool_rejected not found — nothing to restore.")
                return 0

        pool_before = _row_count(conn, "stop_pool")
        rej_before = _row_count(conn, "stop_pool_rejected")
        print(f"stop_pool rows BEFORE:           {pool_before}")
        print(f"stop_pool_rejected rows BEFORE:  {rej_before}")

        restorable, still_rejected = select_restorable(conn, only_qid=args.qid)
        print(f"\n--- {len(restorable)} row(s) the corrected checks now KEEP "
              f"(restorable); {len(still_rejected)} stay rejected ---")

        if not args.apply:
            print("\nDRY RUN: no rows restored. Re-run with --apply to restore them.")
            return 0

        restored = apply_restores(conn, restorable)
        pool_after = _row_count(conn, "stop_pool")
        rej_after = _row_count(conn, "stop_pool_rejected")
        print(f"\nstop_pool rows AFTER:           {pool_after}  "
              f"(restored: {restored}, delta={pool_after - pool_before})")
        print(f"stop_pool_rejected rows AFTER:  {rej_after}  "
              f"(delta={rej_after - rej_before})")
        return 0
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
