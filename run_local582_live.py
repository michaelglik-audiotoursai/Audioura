#!/usr/bin/env python3
"""run_local582_live.py — LOCAL-582 acceptance (live, gpt-4o, $1 cap).

Drives the REAL generation path for a venue that should hit RUNG 3 of the ladder
(D607): a museum that resolves on Wikidata, whose own site is reachable, but for
which no works/exhibitions can be verified — so instead of clean-failing, the
engine delivers ONE sourced MUSEUM OVERVIEW from the venue's own pages.

Mirrors run_local580_live.py: existence gate ON (DATABASE_URL, D261), tour cache
OFF (D262), gpt-4o, OpenAI hard cap $1.00 (lower than LOCAL-580's $2 — the
overview composer makes NO OpenAI calls, so cost is only upstream intent +
verification).

The overview path itself is deterministic (no LLM); any OpenAI spend here is the
intent-analysis + verification that runs BEFORE rung 3 is reached.

Usage:  python3 run_local582_live.py "<venue, locality>" [stops]
Writes: LOCAL582_LIVE.txt and prints tour_kind, the narration, and its sources.

audio_tours is NEVER modified by this harness: generate_tour_text does not insert
tour rows (only the orchestrator does), and we only COUNT rows, before and after.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

for line in open(os.path.join(HERE, '.env')):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['TOUR_LLM_MODEL'] = 'gpt-4o'
os.environ['COST_HARD_LIMIT_USD'] = '1.00'

DEFAULT_VENUE = 'Nave Gallery, Somerville, MA'
LOCATION = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VENUE
STOPS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
OUT = os.path.join(HERE, 'LOCAL582_LIVE.txt')


def _audio_tours_count():
    try:
        import psycopg2
        c = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM audio_tours")
        n = cur.fetchone()[0]
        cur.close(); c.close()
        return n
    except Exception as e:
        return f"(count unavailable: {type(e).__name__}: {e})"


print(f"=== LOCAL-582 live (rung-3 museum overview) ===")
print(f"location : {LOCATION}")
print(f"stops    : {STOPS} (requested)")
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}")
print(f"cache    : OFF   existence-gate DB: {'set' if os.environ.get('DATABASE_URL') else 'UNSET'}")

_before = _audio_tours_count()
print(f"audio_tours BEFORE: {_before}\n")

from generate_tour_text import generate_tour_text  # noqa: E402
import generate_tour_text as _g  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

_after = _audio_tours_count()

print(f"\n{'=' * 70}")
print(f"RESULT after {elapsed:.1f}s")
print(f"tour_kind         : {getattr(_g, '_LAST_TOUR_KIND', '?')}")
print(f"overview sources  : {getattr(_g, '_LAST_OVERVIEW_SOURCES', [])}")
print(f"suggestion        : {getattr(_g, '_LAST_TOUR_SUGGESTION', {})}")
print(f"stop-count notice : {getattr(_g, '_LAST_STOP_COUNT_NOTICE', {})}")
print(f"generation cost   : {getattr(_g, '_LAST_GENERATION_COST', {})}")
print(f"clean-fail evid.  : {getattr(_g, '_LAST_CLEAN_FAIL_EVIDENCE', {})}")
print(f"audio_tours BEFORE/AFTER: {_before} / {_after}  (never DELETE)")
print(f"{'=' * 70}")

if not text:
    print(f"\nNO TEXT — this venue did NOT reach rung 3 (clean fail / rung 4).")
    print(f"Try a different exhibition-only venue.")
    sys.exit(1)

print(f"\n--- NARRATION ({len(text.split())} words in file; stop body is the overview) ---\n")
print(text)
