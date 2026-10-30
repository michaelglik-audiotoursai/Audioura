"""run_local830_container.py — LOCAL-830 live proof (ISOLATED container).

Proves the category-scoped pool-reuse fix against the REAL generation path, with
POOL ON and a seeded pooled "Sandals Restaurant" row for Mui Ne — the exact
GCloud_Storied tour-502 condition (a kite-school tour that reused an
off-category restaurant from the stop pool).

Fixture seeded into THIS run's throwaway stop_pool (never the live DB):
    6 on-category kite schools  +  1 off-category "Sandals Restaurant"
under the pool key for ("Kitesurfing schools in Mui Ne, Vietnam", tour_type="").
With N=5 requested and K=7 pooled (>= N even after the restaurant is skipped),
the delivery is served ENTIRELY from the pool — the stop-pool reuse path, zero
new generation — so the cost is ~$0 and trivially under the $0.60 task cap.

PASS when the delivered 5-stop tour contains NO restaurant (Sandals skipped by
the LOCAL-830 reuse guard) and the stop pool STILL holds the Sandals row (the
guard skips, never deletes — category-scoped reuse).

Run inside an isolated container only (OWN `-p local830` postgres; never
audioura-*, never the live DB):
    docker run --rm --name local830-tg \
        --network local830_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local830-postgres:5432/audiotours \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 \
        -e TEST_GEMINI_MAX_USD=0.60 -e COST_HARD_LIMIT_USD=0.60 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local830_container.py
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tests"))

os.environ.setdefault("STORIED_MODE", "true")
os.environ.setdefault("DISABLE_TOUR_CACHE", "1")
# POOL ON — do NOT set DISABLE_STOP_POOL.
os.environ.pop("DISABLE_STOP_POOL", None)
os.environ.setdefault("TEST_GEMINI_MAX_USD", "0.60")
os.environ.setdefault("COST_HARD_LIMIT_USD", "0.60")

LOCATION = "Kitesurfing schools in Mui Ne, Vietnam"
TOUR_TYPE = ""           # the app sends an empty type for a business request
STOPS = 5

KITE_SCHOOLS = [
    ("Jibe's Beach Club", "Kitesurfing school"),
    ("Muine Kitesurf School (MKS)", "Water sports center"),
    ("C2Sky KiteSurfing", "Kitesurfing school"),
    ("Palm Kite Club Mui Ne", "Kiteboarding school"),
    ("Mui Ne Kite School", "Water sports center"),
    ("Vietnam Kiteboarding School", "Kitesurfing school"),
]
RESTAURANT = ("Sandals Restaurant", "Restaurant")


def _conn():
    import psycopg2
    dburl = os.environ.get("DATABASE_URL")
    if dburl:
        return psycopg2.connect(dburl)
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "local830-postgres"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "audiotours"),
        user=os.environ.get("DB_USER", "admin"),
        password=os.environ.get("DB_PASSWORD", "password123"))


def _seed_pool():
    """Seed 6 kite schools + Sandals Restaurant into stop_pool under the Mui Ne
    kite-school key. Additive INSERTs only — no DELETE, never the live DB."""
    import stop_pool_store as pool
    conn = _conn()
    # _ensure_table uses SAVEPOINTs → needs an explicit transaction (not
    # autocommit). Run it first, commit, then seed with autocommit.
    conn.autocommit = False
    pool._ensure_table(conn)
    conn.commit()
    conn.autocommit = True
    ident = pool.venue_identity(LOCATION)
    pk = pool._pool_key(ident, TOUR_TYPE)
    rows = [(t, c) for (t, c) in KITE_SCHOOLS] + [RESTAURANT]
    with conn.cursor() as cur:
        for seq, (title, cat) in enumerate(rows):
            tn = pool._title_norm(title)
            narration = (f"{title} is a well-known spot along the Mui Ne strip. "
                         f"This stop was pre-seeded for the LOCAL-830 pool proof.")
            cur.execute(
                """
                INSERT INTO stop_pool (
                    pool_key, title_norm, venue_identity, tour_type, pool_version,
                    title, narration, raw_block, type_specialty, order_seq,
                    address, coordinates)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (pool_key, title_norm) DO NOTHING
                """,
                (pk, tn, ident, TOUR_TYPE, pool.POOL_VERSION, title, narration,
                 "", cat, seq, "Mui Ne, Vietnam", ""))
    print(f"[LOCAL-830] seeded {len(rows)} pool rows under key {pk!r} "
          f"(6 kite schools + Sandals Restaurant)", flush=True)
    conn.close()


def _pool_titles():
    import stop_pool_store as pool
    stops = pool.get_pool_stops(LOCATION, TOUR_TYPE, os.environ["DATABASE_URL"])
    return [s["title"] for s in stops]


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")
_RESTAURANT_RE = re.compile(r"\brestaurant\b", re.I)


def main():
    print("=" * 74)
    print(f"LOCAL-830 live pool-reuse category guard: {LOCATION} / {STOPS} stops")
    print("=" * 74, flush=True)

    _seed_pool()
    before = _pool_titles()
    print(f"[LOCAL-830] pool BEFORE delivery ({len(before)}): {before}", flush=True)
    assert "Sandals Restaurant" in before, "fixture not seeded"

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-830] live_run_meter unavailable ({e}); aborting", flush=True)
        sys.exit(2)

    meter = LiveRunMeter("LOCAL-830")
    text = None
    try:
        import generate_tour_text as g
        t0 = time.time()
        text, _out, _coords = g.generate_tour_text(LOCATION, TOUR_TYPE, None, STOPS)
        wall = time.time() - t0
        try:
            meter.add_generation(g)
        except Exception:
            pass
        path = getattr(g, "_LAST_DELIVERY_PATH", "?")
        cost = dict(getattr(g, "_LAST_GENERATION_COST", {}) or {})
    finally:
        try:
            print(f"\n[LOCAL-830] cost ledger row: {meter.record()}", flush=True)
            print(meter.summary(), flush=True)
            meter.uninstall()
        except Exception as _me:
            print(f"[LOCAL-830] meter finalise non-fatal: {_me}", flush=True)

    if not text:
        print("FAIL: generation returned no text.", flush=True)
        sys.exit(1)

    titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
    after = _pool_titles()

    print("\n" + "=" * 74)
    print("LOCAL-830 RESULT")
    print("=" * 74)
    print(f"  delivery_path        : {path}")
    print(f"  pool_reuse           : {cost.get('pool_reuse', False)}")
    print(f"  delivered stops      : {len(titles)}")
    for i, t in enumerate(titles, 1):
        print(f"    Stop {i}: {t[:70]}")
    print(f"  new_cost (LLM)       : ${cost.get('total_cost', 0.0):.4f}")
    print(f"  wall                 : {wall:.0f}s")
    print(f"  pool AFTER ({len(after)}) : {after}")
    print("=" * 74, flush=True)

    restaurant_stops = [t for t in titles if _RESTAURANT_RE.search(t)]
    sandals_present = any("sandals" in t.lower() for t in titles)
    pool_kept_sandals = "Sandals Restaurant" in after

    ok = True
    if restaurant_stops or sandals_present:
        print(f"FAIL: off-category restaurant delivered: {restaurant_stops}", flush=True)
        ok = False
    else:
        print("OK: no restaurant in the delivered kite-school tour.", flush=True)
    if not pool_kept_sandals:
        print("FAIL: Sandals row was DELETED from the pool (must be skip-only).",
              flush=True)
        ok = False
    else:
        print("OK: Sandals row still in the pool (category-scoped reuse — skip, "
              "not delete).", flush=True)
    if len(titles) != STOPS:
        print(f"WARN: delivered {len(titles)} stops, expected {STOPS}.", flush=True)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
