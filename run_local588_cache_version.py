#!/usr/bin/env python3
"""run_local588_cache_version.py — LOCAL-588 live acceptance (ISOLATED).

Runs ONE cheap 3-stop walking request TWICE through the real generation path,
which calls tour_cache_layer1.get_cached_tour / store_tour. Expected:

    run 1  -> [S20] cache v2 MISS key=<12>   (generated + stored)
    run 2  -> [S20] cache v2 HIT  key=<12>   (served from cache, $0.00)

ISOLATION (CLAUDE.md 2026-10-05): DATABASE_URL points at my OWN throwaway
Postgres container `local588-pg` on :5544. No audioura-* container is touched.
OpenAI capped at $0.50. Nothing is ever DELETEd.
"""
import logging
import os
import sys
import time

# Isolated DB + storied cache ON, cheap model, hard cost cap.
os.environ["DATABASE_URL"] = "postgresql://admin:admin@localhost:5544/audiotours"
os.environ["STORIED_MODE"] = "true"
os.environ.pop("DISABLE_TOUR_CACHE", None)        # cache must be ON
os.environ.setdefault("TOUR_LLM_MODEL", "gpt-4o-mini")
os.environ["COST_HARD_LIMIT_USD"] = "0.50"        # OpenAI hard cap $0.50 (ticket)

# Surface the [S20] cache log lines on stdout.
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

LOCATION = "Boston Common, Boston, MA"
TOUR_TYPE = "walking"
STOPS = 3

from generate_tour_text import generate_tour_text  # noqa: E402

run_tag = sys.argv[1] if len(sys.argv) > 1 else "1"
out = f"/tmp/LOCAL588_RUN{run_tag}.txt"
print(f"=== LOCAL-588 run {run_tag}: {LOCATION} / {TOUR_TYPE} / {STOPS} stops ===")
t0 = time.time()
text, out_file, _ = generate_tour_text(LOCATION, TOUR_TYPE, out, STOPS)
print(f"run {run_tag}: {len(text or '')} chars in {time.time()-t0:.1f}s")
