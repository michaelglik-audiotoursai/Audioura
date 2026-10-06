#!/usr/bin/env python3
"""
l2_seat_job.py — LOCAL-596 hourly L2 seat-maintenance job.
==========================================================

Design of record: SUBSCRIPTION_LEVELS.md — "L2 seats and queue" (D613).

One idempotent cycle, in order:
  1. EVICT  — L2 devices idle >= inactivity_days (plans.l2, design 7) drop to
              L1 and free their seat. Any app-open / listen / download / article
              resets the clock via record_activity.
  2. EXPIRE — claim offers older than offer_expiry_hours (l2_settings, design
              72 h) are expired; the device goes back to the queue tail, or is
              dropped ('expired') after max_offer_misses offers.
  3. OFFER  — for each free seat under the 100 cap (plans.l2.seat_cap), offer the
              first waiting device a claim code.

The real work lives in l2_seats.run_seat_cycle(cur) — the SAME framework-free
core the install path and the user-api use. This file is only the runner: it
owns a DB connection, one transaction per cycle, and (for --daemon) the sleep
loop. Running it twice concurrently is safe: run_seat_cycle holds a Postgres
advisory lock for all seat decisions, and every step is written to be a no-op
when there is nothing to do.

SCHEDULING DECISION (see SUBMISSION_LOCAL-596.md):
  The task offered two homes — a line in launchd's `autonomy_tick.sh`, or an
  orchestrator background thread "if that is the existing pattern". There is no
  `autonomy_tick.sh` in this worktree (the launchd tick is a task-file
  DISPATCHER, not a general cron). The orchestrator already runs background work
  as daemon threads (GENERATION_MODE=thread). So the hourly schedule is wired as
  a GUARDED orchestrator background thread (see tour_orchestrator_service.py,
  env flag L2_SEAT_JOB_ENABLED). This file remains runnable standalone for
  manual use or a future launchd/cron entry — one authority, two ways to invoke.

Usage:
  python3 l2_seat_job.py              # run one cycle and exit
  python3 l2_seat_job.py --daemon     # loop every L2_SEAT_JOB_INTERVAL_SECONDS
  python3 l2_seat_job.py --quiet      # suppress the per-cycle summary line
"""

import os
import sys
import time
import json
import logging

import psycopg2

logger = logging.getLogger("l2_seat_job")

# Default hourly cadence (design: "runs as an hourly job"). Overridable by env;
# this is an operational knob, not a tier/plan constant.
_DEFAULT_INTERVAL_SECONDS = 3600


def _get_conn():
    """Connect using the same env contract as subscription_levels.py, with a
    DATABASE_URL fallback (the user-api/orchestrator style)."""
    url = os.getenv('DATABASE_URL')
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'postgres-2'),
        database=os.getenv('DB_NAME', 'audiotours'),
        user=os.getenv('DB_USER', 'admin'),
        password=os.getenv('DB_PASSWORD', 'password123'),
        port=os.getenv('DB_PORT', '5432'),
    )


def run_once(conn=None, quiet=False):
    """Run ONE seat-maintenance cycle in a single transaction. Returns the
    summary dict from l2_seats.run_seat_cycle. If `conn` is given it is used
    (caller owns its lifecycle); otherwise a short-lived connection is opened
    and closed here. Commits on success, rolls back on error (fail-safe: a
    failed cycle changes nothing)."""
    import l2_seats
    own_conn = conn is None
    if own_conn:
        conn = _get_conn()
    try:
        cur = conn.cursor()
        summary = l2_seats.run_seat_cycle(cur)
        conn.commit()
        cur.close()
        if not quiet:
            logger.info("[L2 SEAT JOB] cycle: %s", json.dumps(summary, default=str))
        return summary
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.error("[L2 SEAT JOB] cycle failed, rolled back: %s", e)
        raise
    finally:
        if own_conn:
            try:
                conn.close()
            except Exception:
                pass


def run_forever(interval_seconds=None, quiet=False, stop_event=None):
    """Loop run_once() every interval_seconds. A failed cycle is logged and the
    loop continues (one bad cycle must not kill the scheduler). `stop_event`, if
    given (threading.Event), ends the loop when set — used by the orchestrator
    thread for graceful shutdown."""
    interval = interval_seconds or int(
        os.getenv('L2_SEAT_JOB_INTERVAL_SECONDS', str(_DEFAULT_INTERVAL_SECONDS))
    )
    logger.info("[L2 SEAT JOB] daemon starting, interval=%ss", interval)
    while True:
        try:
            run_once(quiet=quiet)
        except Exception:
            pass  # already logged; keep looping
        if stop_event is not None:
            if stop_event.wait(interval):
                logger.info("[L2 SEAT JOB] stop requested, exiting daemon loop")
                return
        else:
            time.sleep(interval)


def main(argv=None):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    argv = argv if argv is not None else sys.argv[1:]
    daemon = '--daemon' in argv
    quiet = '--quiet' in argv
    if daemon:
        run_forever(quiet=quiet)
        return 0
    summary = run_once(quiet=quiet)
    if quiet:
        # Still emit a machine-readable line for manual/CLI/launchd use.
        print(json.dumps(summary, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
