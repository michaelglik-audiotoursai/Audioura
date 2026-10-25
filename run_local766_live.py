#!/usr/bin/env python3
"""run_local766_live.py — LOCAL-766 live proof (ISOLATED copy DB, $0).

Runs the REAL delivery rule (stop_pool_sources.filter_protected_titles, as called
by stop_pool_orchestrator.maybe_generate_with_pool) against REAL pooled rows copied
into our own local766 database (never the shared stop_pool). Proves on real data:

  * A COMMUNITY tour's pooled stops are SKIPPED for a non-creator — each emits
    `[LOCAL-766] POOL SKIP protected source tour=<id> reason=community`.
  * The tour's CREATOR still reuses every pooled stop (zero skips).

No generation, no paid API call: the rule is a pure DB read over provenance we
already backfilled. DATABASE_URL must point at the local766 copy (port 5466).
"""
import os
import sys

DB = os.environ["DATABASE_URL"]  # local766 copy DB only
import psycopg2
import stop_pool_store as pool
import stop_pool_sources as provenance

TOUR_ID = int(os.environ.get("LOCAL766_TOUR_ID", "716"))


def _tour_facts(tour_id):
    conn = psycopg2.connect(DB)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT request_string, tour_name, community_id, price_tier, "
            "creator_user_id FROM audio_tours WHERE id=%s", (tour_id,))
        row = cur.fetchone()
    conn.close()
    return row


def _pooled_titles_for_tour(tour_id):
    """The (pool_key, title_norm) rows this tour's provenance links, intersected
    with what the pool actually holds (so we reconstruct the venue's pooled rows)."""
    conn = psycopg2.connect(DB)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT sps.pool_key, sps.title_norm "
            "FROM stop_pool_sources sps JOIN stop_pool sp "
            "ON sp.pool_key=sps.pool_key AND sp.title_norm=sps.title_norm "
            "WHERE sps.audio_tour_id=%s", (tour_id,))
        keys = cur.fetchall()
    conn.close()
    return keys


def main():
    req, name, community_id, price_tier, creator = _tour_facts(TOUR_ID)
    reason = "community" if community_id is not None else (
        "paid" if (price_tier or 0) > 0 else "FREE(not protected!)")
    print(f"[LOCAL-766 LIVE] source tour id={TOUR_ID} name={name!r}")
    print(f"[LOCAL-766 LIVE]   community_id={community_id} price_tier={price_tier} "
          f"creator={creator!r} → protection reason={reason}")

    links = _pooled_titles_for_tour(TOUR_ID)
    print(f"[LOCAL-766 LIVE]   {len(links)} pooled stop(s) provenance-linked to this tour")
    if not links:
        print("[LOCAL-766 LIVE] no pooled stops linked — nothing to prove"); return 1

    # Reconstruct the venue identity + tour_type this tour pooled under, from the
    # pool_key of its linked rows: v<ver>|<identity>|<tour_type>.
    pk = links[0][0]
    _ver, identity, tour_type = pk.split("|", 2)
    # location that resolves to this identity: the tour's request_string.
    location = req or name or ""
    qid = identity[4:] if identity.startswith("qid:") else None

    pooled_rows = pool.get_pool_stops(location, tour_type, DB, qid=qid)
    print(f"[LOCAL-766 LIVE]   get_pool_stops → {len(pooled_rows)} row(s) under "
          f"identity={identity} type={tour_type}")

    print("\n--- Requester = ANOTHER USER (USER-OTHER-766) ---")
    allowed_o, skipped_o = provenance.partition_pool_rows(
        pooled_rows, location, tour_type, DB, qid=qid, user_id="USER-OTHER-766")
    for _r, tid, rsn in skipped_o:
        print(f"  [LOCAL-766] POOL SKIP protected source tour={tid} reason={rsn}")
    print(f"  → allowed(reuse)={len(allowed_o)}  skipped(fresh)={len(skipped_o)}")

    print(f"\n--- Requester = CREATOR ({creator}) ---")
    allowed_c, skipped_c = provenance.partition_pool_rows(
        pooled_rows, location, tour_type, DB, qid=qid, user_id=creator)
    print(f"  → allowed(reuse)={len(allowed_c)}  skipped(fresh)={len(skipped_c)}")

    ok = (len(skipped_o) >= len(links) and len(skipped_c) == 0
          and all(r == reason for _x, _t, r in skipped_o))
    print(f"\n[LOCAL-766 LIVE] RESULT: "
          f"{'PASS' if ok else 'FAIL'} — non-creator skipped {len(skipped_o)} "
          f"({reason}); creator skipped {len(skipped_c)}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
