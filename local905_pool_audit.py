#!/usr/bin/env python3
"""[LOCAL-905] READ-ONLY audit of the stop_pool table: per venue key, list the rows the LOCAL-905 reuse guards
would reject. Issues SELECT only (the connection is opened read-only); never writes, never deletes.

Offline by default: empty/failed bodies, and a pin more than --outlier-km (default 100) from the median pin of
its own venue key. With --geo the venue's scope centre is resolved (network, area_resolver) and the full
pin_reject scope test is applied as well.

    DATABASE_URL=postgres://... python3 local905_pool_audit.py [--geo] [--outlier-km 100] [--limit 5000]
"""
import argparse
import os
import statistics
import sys
from collections import defaultdict

import pool_guards_905 as pg


def audit(rows, outlier_km=100.0, ctx_for=None):
    """rows: dicts with pool_key, venue_identity, title, narration, coordinates. Returns {key: [(title, reason)]}."""
    by_key = defaultdict(list)
    for r in rows:
        by_key[r.get("pool_key")].append(r)
    report = {}
    for key, rs in by_key.items():
        pins = [pg._coord(r.get("coordinates")) for r in rs]
        pins = [p for p in pins if p]
        med = (statistics.median(p[0] for p in pins), statistics.median(p[1] for p in pins)) if len(pins) >= 3 else None
        ctx = (ctx_for(rs[0]) if ctx_for else {}) or {}
        bad = []
        for r in rs:
            why = pg.body_reject(r) or pg.pin_reject(r, ctx)
            if not why and med is not None:
                p = pg._coord(r.get("coordinates"))
                if p and pg._km(p, med) > outlier_km:
                    why = f"pin {pg._km(p, med):.0f} km from the venue key's median pin > {outlier_km:.0f} km"
            if why:
                bad.append((r.get("title", ""), why))
        if bad:
            report[key] = bad
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--geo", action="store_true")
    ap.add_argument("--outlier-km", type=float, default=100.0)
    ap.add_argument("--limit", type=int, default=5000)
    a = ap.parse_args(argv)
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    import psycopg2
    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    with conn.cursor() as cur:
        cur.execute("SELECT pool_key, venue_identity, title, narration, coordinates FROM stop_pool "
                    "ORDER BY pool_key, order_seq LIMIT %s", (a.limit,))
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    ctx_for = None
    if a.geo:
        cache = {}

        def ctx_for(r):
            ident = str(r.get("venue_identity") or "")
            loc = ident[4:] if ident.startswith("loc:") else ""
            if not loc:
                return {}
            if loc not in cache:
                cache[loc] = pg.build_context(loc)
            return cache[loc]
    rep = audit(rows, a.outlier_km, ctx_for)
    total = sum(len(v) for v in rep.values())
    for key, bad in sorted(rep.items()):
        print(f"{key}")
        for t, why in bad:
            print(f"    '{t}': {why}")
    print(f"-- {total} row(s) in {len(rep)} venue key(s) of {len(rows)} would be rejected on reuse (nothing changed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
