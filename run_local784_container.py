"""run_local784_container.py — LOCAL-784 / D722 live acceptance (ISOLATED).

Exercises the escalation ladder through the REAL code path against the live
Serper Places provider and the shared DB, proving the D722 contract end-to-end:

  1. "middle eastern restaurants near me, west Roxbury, MA" — the cheap tier is
     FORCED to miss (D722_FORCE_CHEAP_MISS=1), the ladder escalates to Serper
     Places (tier b), DELIVERS the real West Roxbury Middle-Eastern places, and
     writes ONE lookup_escalations row (tier_found='b'). A SECOND identical run is
     served from the LOCAL-783 24 h places cache (no new /places call).
  2. "yak-wool cafes in West Roxbury, MA" — a nonsense category. Every tier comes
     up empty, the ladder refuses honestly, and writes a lookup_escalations row
     with tier_found='none' (the real-absence record).

Prints the escalation rows written, the Serper /places call + $ deltas, and the
BEFORE/AFTER counts of lookup_escalations, lookup_routing and audio_tours.

HARD BUDGET: ≤ $1.00 for the whole run (tier b is $0.002/query; this run makes a
handful). Runs the ladder directly (replenish_with_escalation) rather than a full
~$0.5 tour generation, so it is both cheap and a direct proof of the new code.

Run inside an isolated container only (never -p audioura; never touch audioura-*):
    docker run --rm --name local784-tg \
        --network development_default \
        --env-file /Users/micha/Audioura/.env \
        -e DB_HOST=postgres-2 -e DB_NAME=audiotours -e DB_USER=admin \
        -e DB_PASSWORD=password123 -e DB_PORT=5432 \
        -e SERP_PROVIDER=serper -e STORIED_MODE=true \
        -e D722_FORCE_CHEAP_MISS=1 \
        -v "$PWD":/app -w /app audioura-tour-generator \
        python -u run_local784_container.py
"""
import os
import sys
import time

os.environ.setdefault("SERP_PROVIDER", "serper")
os.environ.setdefault("STORIED_MODE", "true")

HARD_CAP_USD = 1.00


def _conn():
    import psycopg2
    dburl = os.environ.get("DATABASE_URL")
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "postgres-2"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"))


def _scalar(sql, args=()):
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(sql, args)
            v = cur.fetchone()[0]
        conn.close(); return v
    except Exception as e:
        print(f"  [db] query failed: {e}", flush=True); return None


def _count(table):
    return _scalar(f"SELECT count(*) FROM {table}")


def _places_calls():
    return _scalar("SELECT count(*) FROM paid_api_calls WHERE url LIKE %s", ("%/places%",))


def _places_usd():
    return _scalar("SELECT COALESCE(SUM(usd),0) FROM paid_api_calls WHERE url LIKE %s",
                   ("%/places%",))


def _recent_escalations(since_ts):
    try:
        conn = _conn(); conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, kind, category, scope, tier_found, results_by_tier, "
                "cost_usd FROM lookup_escalations WHERE ts >= to_timestamp(%s) "
                "ORDER BY id", (since_ts,))
            rows = cur.fetchall()
        conn.close(); return rows
    except Exception as e:
        print(f"  [db] escalations query failed: {e}", flush=True); return []


def main():
    print("=== LOCAL-784 / D722 isolated live run (escalation ladder) ===", flush=True)
    print(f"host: {os.uname().nodename}  SERP_PROVIDER={os.environ.get('SERP_PROVIDER')}  "
          f"FORCE_CHEAP_MISS={os.environ.get('D722_FORCE_CHEAP_MISS')}", flush=True)
    print(f"serper key present: "
          f"{bool(os.environ.get('SERP_API_KEY') or os.environ.get('SERPER_API_KEY'))}  "
          f"HARD CAP ${HARD_CAP_USD:.2f}", flush=True)

    esc_before = _count("lookup_escalations")
    route_before = _count("lookup_routing")
    tours_before = _count("audio_tours")
    places_before = _places_calls()
    usd_before = float(_places_usd() or 0.0)
    start_ts = time.time() - 1
    print(f"\nBEFORE: lookup_escalations={esc_before}  lookup_routing={route_before}  "
          f"audio_tours={tours_before}  places_calls={places_before}  "
          f"places_$={usd_before:.4f}", flush=True)

    import stop_existence_gate as gate

    # ── Case 1: forced cheap miss → tier b rescue (West Roxbury Middle Eastern) ─
    print("\n--- CASE 1: 'middle eastern restaurants near me, west Roxbury, MA' ---",
          flush=True)
    os.environ["D722_FORCE_CHEAP_MISS"] = "1"   # force tier a empty (test-only)
    t0 = time.time()
    out1 = gate.replenish_with_escalation(
        "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
        cuisine="middle eastern",
        request_text="middle eastern restaurants near me, west Roxbury, MA")
    print(f"  tier b delivered {len(out1)} place(s) in {time.time()-t0:.1f}s:", flush=True)
    for c in out1:
        print(f"    · {c.get('name')}  [{c.get('coordinates')}]  {c.get('address','')[:60]}",
              flush=True)

    pc_after_1 = _places_calls()
    print(f"  serper /places calls so far: {pc_after_1} "
          f"(delta {pc_after_1 - places_before if (pc_after_1 is not None and places_before is not None) else '?'})",
          flush=True)

    # ── Case 1b: repeat → served from the LOCAL-783 places cache (no new call) ─
    print("\n--- CASE 1b: repeat the SAME request → cache hit (no new /places) ---",
          flush=True)
    pc_before_rep = _places_calls()
    out1b = gate.replenish_with_escalation(
        "dining", "middle eastern restaurants", "West Roxbury, MA", 2,
        cuisine="middle eastern",
        request_text="middle eastern restaurants near me, west Roxbury, MA")
    pc_after_rep = _places_calls()
    print(f"  repeat delivered {len(out1b)} place(s); serper /places calls "
          f"{pc_before_rep} -> {pc_after_rep} "
          f"(delta {pc_after_rep - pc_before_rep if (pc_after_rep is not None and pc_before_rep is not None) else '?'} "
          f"— 0 means served from cache)", flush=True)

    # ── Case 2: nonsense category → all tiers none → honest refusal + 'none' row
    print("\n--- CASE 2: 'yak-wool cafes in West Roxbury, MA' → all none ---", flush=True)
    t0 = time.time()
    out2 = gate.replenish_with_escalation(
        "dining", "yak-wool cafes", "West Roxbury, MA", 2,
        cuisine="yak-wool",
        request_text="yak-wool cafes in West Roxbury, MA")
    print(f"  delivered {len(out2)} place(s) in {time.time()-t0:.1f}s "
          f"(expected 0 — honest refusal)", flush=True)

    # ── Report ─────────────────────────────────────────────────────────────────
    esc_after = _count("lookup_escalations")
    route_after = _count("lookup_routing")
    tours_after = _count("audio_tours")
    places_after = _places_calls()
    usd_after = float(_places_usd() or 0.0)

    print("\n=== ESCALATION ROWS WRITTEN THIS RUN ===", flush=True)
    for (rid, kind, category, scope, tier, rbt, cost) in _recent_escalations(start_ts):
        print(f"  id={rid} kind={kind} category={category!r} scope={scope!r} "
              f"tier_found={tier} cost=${float(cost or 0):.4f}", flush=True)
        print(f"      results_by_tier={rbt}", flush=True)

    print("\n=== ROW COUNTS ===", flush=True)
    def _d(a, b):
        return (a - b) if (a is not None and b is not None) else "?"
    print(f"  lookup_escalations: {esc_before} -> {esc_after}  (delta {_d(esc_after, esc_before)})",
          flush=True)
    print(f"  lookup_routing:     {route_before} -> {route_after}  (delta {_d(route_after, route_before)})",
          flush=True)
    print(f"  audio_tours:        {tours_before} -> {tours_after}  (delta {_d(tours_after, tours_before)})",
          flush=True)
    print(f"  serper /places calls: {places_before} -> {places_after}  "
          f"(delta {_d(places_after, places_before)})", flush=True)
    spend = usd_after - usd_before
    print(f"  serper /places $ this run: ${spend:.4f}  (cumulative ledger ${usd_after:.4f})",
          flush=True)
    print(f"\n  BUDGET: this run spent ~${spend:.4f} on Serper /places "
          f"(HARD CAP ${HARD_CAP_USD:.2f}) — {'OK' if spend <= HARD_CAP_USD else 'OVER'}",
          flush=True)
    print("=== LOCAL-784 LIVE RUN COMPLETE ===", flush=True)


if __name__ == "__main__":
    main()
