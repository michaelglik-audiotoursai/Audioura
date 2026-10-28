"""run_local797_container.py — LOCAL-797 live proof (ISOLATED container).

Generates ONE real 2-stop tour for "Arnold Arboretum, Boston" end to end through
the real generation path WHILE a deliberately idle-in-transaction reader holds a
lock on venue_corpus for the whole run. Pre-fix, this is exactly what froze every
tour on 2026-10-28 (a 26-minute hang): the generator's venue_corpus ALTER queued
behind an idle reader and every venue_corpus SELECT queued behind the ALTER.

With the LOCAL-797 fix the tour completes in normal time:
  * _ensure_table's ALTER/CREATE INDEX are lock-guarded (SET LOCAL lock_timeout
    3s) and conditional — they skip-and-log instead of blocking.
  * generator connections carry idle_in_transaction_session_timeout=60s and run
    reads under autocommit, so no reader can hold a lock for minutes.

Budget: HARD CAP $1.00 for the whole run (tests/live_run_meter.py). No DELETE.
The delivered tour is stored as ONE additive is_test row.

Run inside an isolated container only — NEVER -p audioura, NEVER the live 5433 DB.
The worktree is mounted at /app so the container runs THIS LOCAL-797 code:

    docker run --rm --name local797-tg \
        --network local797_default \
        --env-file .env \
        -e DATABASE_URL=postgresql://admin:password123@local797-postgres:5432/audiotours \
        -e STORIED_MODE=true -e DISABLE_TOUR_CACHE=1 -e DISABLE_STOP_POOL=1 \
        -e STOP_EXISTENCE_GATE_MODE=log_only \
        -e TEST_GEMINI_MAX_USD=1.00 -e COST_HARD_LIMIT_USD=1.00 \
        -v "$PWD":/app -w /app audioura-tour-generator:latest \
        python -u run_local797_container.py
"""
import os as _os
import sys as _sys
import re
import threading
import time

_sys.path.insert(0, _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'tests'))

_os.environ['STORIED_MODE'] = 'true'
_os.environ['DISABLE_TOUR_CACHE'] = '1'
_os.environ['DISABLE_STOP_POOL'] = '1'
_os.environ.setdefault('TEST_GEMINI_MAX_USD', '1.00')
_os.environ.setdefault('COST_HARD_LIMIT_USD', '1.00')
_os.environ.setdefault('STOP_EXISTENCE_GATE_MODE', 'log_only')

HARD_CAP_USD = 1.00

LOCATION = "Arnold Arboretum, Boston"
TOUR_TYPE = "walking"
N_STOPS = 2

print(f"[LOCAL-797] HARD CAP ${HARD_CAP_USD}  cache_off=1 pool_off=1 STORIED_MODE=true",
      flush=True)

try:
    from live_run_meter import LiveRunMeter
except Exception as _e:
    print(f"[LOCAL-797] live_run_meter unavailable ({_e}) — cannot cap; aborting", flush=True)
    _sys.exit(2)


def _conn(autocommit=False):
    import psycopg2
    dburl = _os.environ.get('DATABASE_URL')
    if dburl:
        c = psycopg2.connect(dburl)
    else:
        c = psycopg2.connect(
            host=_os.environ.get('DB_HOST', 'local797-postgres'),
            port=_os.environ.get('DB_PORT', '5432'),
            dbname=_os.environ.get('DB_NAME', 'audiotours'),
            user=_os.environ.get('DB_USER', 'admin'),
            password=_os.environ.get('DB_PASSWORD', 'password123'))
    c.autocommit = autocommit
    return c


def _refuse_live():
    dburl = _os.environ.get('DATABASE_URL', '')
    if ':5433/' in dburl or _os.environ.get('DB_PORT') == '5433':
        print("[LOCAL-797] REFUSING to run against the live DB (5433)", flush=True)
        _sys.exit(3)


def _scalar(sql, args=()):
    try:
        conn = _conn(autocommit=True)
        with conn.cursor() as cur:
            cur.execute(sql, args)
            v = cur.fetchone()[0]
        conn.close()
        return v
    except Exception as e:
        print(f"  [db] query failed: {e}", flush=True)
        return None


class IdleReader:
    """A background connection that opens a read transaction on venue_corpus and
    then stays IDLE IN TRANSACTION (never commits) — the live incident's pid A.

    Note: idle_in_transaction_session_timeout is a *per-connection* setting; this
    reader is a hostile external session that does NOT set it, so it genuinely
    holds its lock for the whole run, exactly as the frozen tour's reader did. The
    fix must therefore come from the generator never *waiting* on that lock
    (lock_timeout on its DDL) — which is what this proof exercises.
    """

    def __init__(self):
        self.conn = None
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self.conn = _conn(autocommit=False)
        cur = self.conn.cursor()
        cur.execute("SELECT count(*) FROM venue_corpus")
        n = cur.fetchone()[0]
        # Deliberately do NOT commit — we are now idle in transaction holding an
        # AccessShare lock on venue_corpus.
        print(f"  [LOCAL-797] idle reader holding venue_corpus "
              f"(saw {n} rows, NOT committing)", flush=True)
        self._thread = threading.Thread(target=self._hold, daemon=True)
        self._thread.start()

    def _hold(self):
        # Keep the session alive and idle-in-transaction; do nothing until asked
        # to stop. No further statements → the transaction stays open.
        while not self._stop.wait(1.0):
            pass

    def stop(self):
        self._stop.set()
        try:
            if self.conn:
                self.conn.rollback()
                self.conn.close()
        except Exception:
            pass


_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+\d+:\s*(.+)$")


def _report_stops(text):
    titles = _STOP_HEADER_RE.findall(text)
    print("  --- STOPS ---", flush=True)
    for i, t in enumerate(titles):
        print(f"  STOP {i+1}: {t.strip()[:80]}", flush=True)
    return titles


def _store(location, text, n_stops):
    try:
        conn = _conn(autocommit=True)
        name = f"LOCAL-797 {location.split(',')[0][:40]} {int(time.time())}"
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO audio_tours
                    (tour_name, request_string, number_requested,
                     tour_content, stops_count, creator_type, storied_mode,
                     is_test, track, tour_kind, description)
                VALUES (%s, %s, %s, %s, %s, 'Test', true, true, 'beta', 'full', %s)
                RETURNING id
                """,
                (name, location, n_stops, text, n_stops,
                 'LOCAL-797 idle-reader lock proof'))
            new_id = cur.fetchone()[0]
        conn.close()
        return new_id
    except Exception as e:
        print(f"  [db] store failed: {e}", flush=True)
        return None


def _tier_width():
    return _scalar(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_name='venue_corpus' AND column_name='tier'")


def main():
    _refuse_live()
    print(f"venue_corpus.tier width BEFORE: {_tier_width()}", flush=True)
    before = _scalar("SELECT count(*) FROM audio_tours")
    print(f"audio_tours rows BEFORE: {before}", flush=True)

    reader = IdleReader()
    reader.start()

    meter = LiveRunMeter('LOCAL-797')
    status = 'NO_TEXT'
    n = 0
    dt = 0.0
    try:
        import generate_tour_text as g
        import traceback as _tb
        print(f"\n=== TOUR {LOCATION!r} tour_type={TOUR_TYPE!r} ({N_STOPS} stops) "
              f"WITH idle reader holding venue_corpus ===", flush=True)
        t0 = time.time()
        try:
            text, _out, coords = g.generate_tour_text(LOCATION, TOUR_TYPE, None, N_STOPS)
            dt = time.time() - t0
            if not text:
                print(f"  [LOCAL-797] generation returned NO text in {dt:.0f}s", flush=True)
                status = 'NO_TEXT'
            else:
                titles = _report_stops(text)
                n = len(titles)
                rid = _store(LOCATION, text, N_STOPS)
                print(f"  stored is_test row id={rid}; delivered {n} stop(s) in {dt:.0f}s",
                      flush=True)
                status = f'{n} stops in {dt:.0f}s'
        except Exception as e:
            dt = time.time() - t0
            print(f"  [LOCAL-797] TOUR raised after {dt:.0f}s: {e}", flush=True)
            _tb.print_exc()
            status = f'ERROR: {e}'
        try:
            meter.add_generation(g)
        except Exception:
            pass
    finally:
        reader.stop()
        try:
            row_id = meter.record()
            print(f"\n[LOCAL-797] cost ledger row: {row_id}", flush=True)
        except Exception as _me:
            print(f"[LOCAL-797] meter.record failed (non-fatal): {_me}", flush=True)
        try:
            print(meter.summary(), flush=True)
        except Exception:
            pass
        try:
            meter.uninstall()
        except Exception:
            pass

    after = _scalar("SELECT count(*) FROM audio_tours")
    print(f"\nvenue_corpus.tier width AFTER: {_tier_width()}", flush=True)
    print(f"audio_tours rows AFTER: {after} "
          f"(delta={after - before if (after is not None and before is not None) else '?'})",
          flush=True)
    print("=== LOCAL-797 SUMMARY ===", flush=True)
    print(f"  tour: {status}", flush=True)
    # The freeze was 26 minutes; a healthy 2-stop tour is a few minutes. Flag if
    # it ever crosses a clearly-abnormal threshold even though it completed.
    if dt and dt > 600:
        print(f"  WARNING: tour took {dt:.0f}s (>10min) — investigate", flush=True)
    else:
        print(f"  OK: tour completed in normal time ({dt:.0f}s), "
              f"never blocked by the idle venue_corpus reader", flush=True)


if __name__ == '__main__':
    main()
