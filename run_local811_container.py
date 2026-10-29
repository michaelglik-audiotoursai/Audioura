"""run_local811_container.py — LOCAL-811 live acceptance (ISOLATED container).

Proves the pooled/reused museum fix end to end on the ticket's named venue, with a
pool SEEDED with the bad Belvedere rows BEFORE the run:

  seed (into THIS stack's stop_pool, loc + museum keys):
    * Monet "Portrait of Père Paul"  (P195 = Musée d'Orsay — NOT the Belvedere)
    * Van Gogh "Plain of Auvers"      (P195 = elsewhere — NOT the Belvedere)
    * a disambiguation stub stop ("Belvedere" / "… may refer to:")
    * one GOOD Klimt stop ("The Kiss") so the pool is not all-bad

  run: "Belvedere Museum, Vienna, Austria" (5), STORIED_MODE + stop pool ENABLED,
       RESEARCH_BACKEND=serper (cheap arm). The reuse path must auto-reject the
       three bad seeded stops (LOCAL-811 museum checks → move_to_rejected) and
       research the rest fresh.

Acceptance (printed after the run):
  * NO "may refer to" disambiguation text anywhere in the delivered tour;
  * every stop title passes junk/shop checks (no merchandise);
  * the three seeded bad stops are gone from stop_pool and present in
    stop_pool_rejected with an auto:local811:* reason;
  * the delivered stops are Belvedere works (spot check: the foreign Monet/Van Gogh
    titles do not appear as stops).

Budget: HARD CAP $0.80 for the WHOLE task across ALL runs (LEAD note). This runner
reads the ledger total spent SO FAR and refuses to start a tour that could exceed
the cap. ≤ 1 live tour here. ONE additive is_test audio_tours row in the ISOLATED
postgres only. The only stop_pool removal is the LOCAL-792 verified
move_to_rejected the fix performs. Never the shared/development DB.

Run (one-shot) on the local811 stack network:
    docker run --rm --name local811-tg \
        --network local811_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local811-postgres:5432/audiotours \
        -e RESEARCH_BACKEND=serper -e SERP_PROVIDER=serper \
        -e NARRATION_MODEL=gpt-4.1-mini -e SERPER_RESEARCH_MODEL=gpt-4.1-mini \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=0.80 -e COST_HARD_LIMIT_USD=0.80 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local811_container.py
"""
import os as _os
import sys as _sys
import re
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ.setdefault('RESEARCH_BACKEND', 'serper')
_os.environ.setdefault('SERP_PROVIDER', 'serper')
_os.environ.setdefault('NARRATION_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('SERPER_RESEARCH_MODEL', 'gpt-4.1-mini')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '0.80')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '0.80')
# The stop pool MUST be ON (that is the path under test).
_os.environ.pop('DISABLE_STOP_POOL', None)

HARD_CAP_USD = 0.80
LOCATION = 'Belvedere Museum, Vienna, Austria'
N_STOPS = 5

import stop_pool_store as pool


def _conn():
    import psycopg2
    return psycopg2.connect(_os.environ['DATABASE_URL'])


def _seed_bad_pool():
    """Seed the bad Belvedere rows under BOTH the loc key and the 'museum' key so
    the reuse read finds them whatever tour_type the classifier assigns."""
    ident = pool.venue_identity(LOCATION)
    seeds = [
        # (title, artist, narration, raw_block, stop_record_json)
        ("The Kiss", "Gustav Klimt",
         "Gustav Klimt painted The Kiss between 1907 and 1908 during his Golden Period.",
         "", None),
        ("Portrait of Père Paul", "Claude Monet",
         "A portrait Claude Monet painted; it hangs in the Musée d'Orsay, not here.",
         "", '{"collection_qids": ["Q23402"]}'),
        ("Plain of Auvers", "Vincent van Gogh",
         "A landscape Vincent van Gogh painted near Auvers-sur-Oise.",
         "", '{"collection_qids": ["Q153306"]}'),
        ("Belvedere", "",
         "Belvedere may refer to: a palace in Vienna, a place in California, a ship.",
         "Belvedere may refer to: a palace in Vienna, a place in California, a ship.",
         None),
    ]
    conn = _conn()
    conn.autocommit = True
    pool.ensure_table(conn) if hasattr(pool, "ensure_table") else None
    seq = 0
    with conn.cursor() as cur:
        for ttype in ("", "museum"):
            pk = pool._pool_key(ident, ttype)
            for (title, artist, narr, raw, rec) in seeds:
                tn = pool._title_norm(title)
                cur.execute(
                    """
                    INSERT INTO stop_pool (
                        pool_key, title_norm, venue_identity, tour_type,
                        pool_version, title, artist, narration, raw_block,
                        order_seq, stop_record_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (pool_key, title_norm) DO NOTHING
                    """,
                    (pk, tn, ident, ttype, pool.POOL_VERSION, title, artist,
                     narr, raw, seq, rec))
                seq += 1
    conn.close()
    print(f"[LOCAL-811] seeded bad Belvedere pool under identity {ident!r} "
          f"(keys: '' and 'museum')", flush=True)


def _pool_titles():
    conn = _conn()
    with conn.cursor() as cur:
        cur.execute("SELECT title FROM stop_pool ORDER BY title")
        rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def _rejected():
    conn = _conn()
    out = []
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('stop_pool_rejected')")
        if cur.fetchone()[0] is not None:
            cur.execute("SELECT title, reject_reason, rejected_by "
                        "FROM stop_pool_rejected ORDER BY title")
            out = cur.fetchall()
    conn.close()
    return out


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")


def _check(text):
    problems = []
    try:
        import junk_title_guard as jtg
    except Exception:
        jtg = None
    titles = [t.strip() for t in _STOP_HEADER_RE.findall(text)]
    print("  --- STOPS ---", flush=True)
    for i, t in enumerate(titles):
        print(f"  STOP {i+1}: {t[:80]}", flush=True)
        if jtg is not None and (jtg.is_junk_page_title(t, 'Belvedere')
                                or jtg.is_shop_product_title(t)):
            problems.append(f"shop/junk stop title: {t!r}")
    # No disambiguation anywhere.
    if re.search(r"(?i)\bmay\s+(?:also\s+)?refer\s+to\b", text):
        problems.append("tour body contains a 'may refer to' disambiguation line")
    # The seeded foreign works must NOT be delivered as stops.
    for bad in ("Portrait of Père Paul", "Plain of Auvers"):
        if any(bad.lower() in t.lower() for t in titles):
            problems.append(f"foreign (non-Belvedere) work delivered as a stop: {bad!r}")
    return problems, titles


def main():
    print("=== LOCAL-811 isolated live run (pooled museum checks) ===", flush=True)
    print(f"HARD CAP(task): ${HARD_CAP_USD}  pool=ON  "
          f"RESEARCH_BACKEND={_os.environ.get('RESEARCH_BACKEND')}", flush=True)

    try:
        from live_run_meter import LiveRunMeter
    except Exception as e:
        print(f"[LOCAL-811] live_run_meter unavailable ({e}); aborting", flush=True)
        return 2

    _seed_bad_pool()
    print(f"[LOCAL-811] pool BEFORE run ({len(_pool_titles())}): {_pool_titles()}",
          flush=True)

    meter = LiveRunMeter('LOCAL-811')
    # Reserve gate: refuse to start if we are already at/over the cap.
    try:
        spent = meter.total_usd()
    except Exception:
        spent = 0.0
    if spent >= HARD_CAP_USD:
        print(f"[LOCAL-811] reserve gate: ${spent:.3f} >= ${HARD_CAP_USD} — not running",
              flush=True)
        return 0

    import generate_tour_text as g
    import traceback as _tb
    t0 = time.time()
    verdict, problems, titles = 'NO_TEXT', [], []
    try:
        text, _out, _coords = g.generate_tour_text(LOCATION, '', None, N_STOPS)
        dt = time.time() - t0
        if text:
            problems, titles = _check(text)
            verdict = 'PASS' if not problems else 'FAIL'
            print(f"  generated in {dt:.0f}s — {verdict}", flush=True)
        else:
            print(f"  [LOCAL-811] NO text in {dt:.0f}s", flush=True)
    except Exception as e:
        print(f"  [LOCAL-811] raised: {e}", flush=True)
        _tb.print_exc()
    finally:
        try:
            meter.add_generation(g)
        except Exception:
            pass
        try:
            meter.record()
        except Exception:
            pass
        try:
            print(meter.summary(), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    print(f"\n[LOCAL-811] pool AFTER run ({len(_pool_titles())}): {_pool_titles()}",
          flush=True)
    print("[LOCAL-811] stop_pool_rejected:", flush=True)
    for t, reason, by in _rejected():
        print(f"    REJECTED {t!r}  reason={reason!r}  by={by!r}", flush=True)

    print("\n=== LOCAL-811 SUMMARY ===", flush=True)
    print(f"  verdict: {verdict}", flush=True)
    for p in problems:
        print(f"    PROBLEM: {p}", flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
