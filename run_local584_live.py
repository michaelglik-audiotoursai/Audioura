#!/usr/bin/env python3
"""run_local584_live.py — LOCAL-584 live acceptance (Griffin Museum, $1 cap).

Drives the REAL museum generation path for the Griffin Museum of Photography
(Winchester, MA) — the venue whose tour 391 shipped the defect:
    "[LOCAL-91] Corpus fallback Museum Information: 08:00–20:00. €12"
from griffinmuseum.org, a $-priced, AM/PM page that has NO € and NO 08:00.

This harness exercises the fixed path end-to-end: the LOCAL-35 extractor
(currency-from-page, source-aware hours) feeding the LOCAL-91 corpus fallback,
which now routes format_en() through the ONE shared literal gate
(practical_facts_gate.gate_formatted_facts) before writing Museum Information.

Prints the Museum Information line (poi 1 operational_details) and every
"[LOCAL-91]"/"[LOCAL-584]"/"[LOCAL-39]" log line, so the fix is observable.

OpenAI hard cap $1.00. audio_tours is only COUNTED (never DELETE):
generate_tour_text does not insert tour rows (only the orchestrator does).

Usage: python3 run_local584_live.py ["Venue, Locality"] [stops]
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_envf = os.path.join(HERE, '.env')
if os.path.exists(_envf):
    for line in open(_envf):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

os.environ.setdefault('DATABASE_URL',
                      'postgresql://admin:password123@localhost:5433/audiotours')
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_TOUR_CACHE'] = '1'
os.environ['TOUR_LLM_MODEL'] = os.environ.get('TOUR_LLM_MODEL', 'gpt-4o')
os.environ['COST_HARD_LIMIT_USD'] = '1.00'

DEFAULT_VENUE = 'Griffin Museum of Photography, Winchester, MA'
LOCATION = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VENUE
STOPS = int(sys.argv[2]) if len(sys.argv) > 2 else 5
OUT = os.path.join(HERE, 'LOCAL584_LIVE.txt')


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


print("=== LOCAL-584 live (Griffin Museum practical facts: currency + hours + one gate) ===")
print(f"location : {LOCATION}")
print(f"stops    : {STOPS} (requested)")
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}")

_before = _audio_tours_count()
print(f"audio_tours BEFORE: {_before}\n")

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

_after = _audio_tours_count()

# Pull the Museum Information line straight out of the delivered tour text.
_museum_info = ''
if text:
    m = re.search(r'^Museum Information:\s*(.+)$', text, re.MULTILINE)
    if m:
        _museum_info = m.group(1).strip()

print(f"\n{'=' * 72}")
print(f"RESULT after {elapsed:.1f}s")
print(f"audio_tours BEFORE/AFTER: {_before} / {_after}   (never DELETE)")
print(f"{'=' * 72}")
print("MUSEUM INFORMATION LINE (poi 1):")
print(f"  {_museum_info!r}" if _museum_info else "  (no Museum Information line emitted)")

# LOCAL-584 acceptance assertions on the live output.
if _museum_info:
    assert '€' not in _museum_info, f"FAIL: euro leaked into Museum Information: {_museum_info!r}"
    assert '08:00' not in _museum_info and '20:00' not in _museum_info, \
        f"FAIL: synthetic 24h hours in Museum Information: {_museum_info!r}"
    print("  ✓ no € ; ✓ no 08:00/20:00")
print(f"{'=' * 72}")
if not text:
    print("NO TEXT — venue did not deliver a tour under the cap.")
    sys.exit(1)
