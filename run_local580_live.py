#!/usr/bin/env python3
"""run_local580_live.py — LOCAL-580 acceptance (live, gpt-4o, $2 cap, D261).

Runs the two acceptance cases from the ticket through the REAL generation path:

  1. Griffin Museum of Photography, Winchester, MA — museum, 5 stops.
     Expect a real tour whose stops are CURRENT Griffin exhibitions (site-first),
     not the generic shows GPT used to invent.
  2. Palais Lascaris, Nice, France — museum, 4 stops.
     Expect 4/4 (LOCAL-577 regression stays green under the new code).

Mirrors run_local577_palais_live.py exactly: existence gate ON (DATABASE_URL,
D261), tour cache OFF (D262), gpt-4o, OpenAI hard cap $2.00.

Usage:  python3 run_local580_live.py griffin
        python3 run_local580_live.py palais
Writes: LOCAL580_<CASE>.txt and prints the stop list + sources.
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
os.environ['COST_HARD_LIMIT_USD'] = '2.00'

CASES = {
    'griffin': ('Griffin Museum of Photography, Winchester, MA', 5),
    'palais': ('Palais Lascaris, Nice, France', 4),
}

case = (sys.argv[1] if len(sys.argv) > 1 else 'griffin').lower()
if case not in CASES:
    print(f"unknown case {case!r}; choose: {', '.join(CASES)}")
    sys.exit(2)

LOCATION, STOPS = CASES[case]
OUT = os.path.join(HERE, f'LOCAL580_{case.upper()}.txt')

print(f"=== LOCAL-580 live: {case} ===")
print(f"location : {LOCATION}")
print(f"stops    : {STOPS} (requested)")
print(f"model    : {os.environ['TOUR_LLM_MODEL']}   cap: ${os.environ['COST_HARD_LIMIT_USD']}")
print(f"cache    : OFF   existence-gate DB: {'set' if os.environ.get('DATABASE_URL') else 'UNSET'}\n")

from generate_tour_text import generate_tour_text  # noqa: E402

t0 = time.time()
text, out_file, _coords = generate_tour_text(LOCATION, 'museum', OUT, STOPS)
elapsed = time.time() - t0

if not text:
    # A clean fail is a legitimate outcome to inspect — print the structured evidence.
    try:
        from generate_tour_text import _LAST_CLEAN_FAIL_EVIDENCE
        print(f"\n{case}: CLEAN FAIL after {elapsed:.1f}s")
        print(f"  evidence: {_LAST_CLEAN_FAIL_EVIDENCE}")
    except Exception as e:
        print(f"\n{case}: no text, evidence unavailable ({e})")
    sys.exit(1)

delivered = len(re.findall(r'(?mi)^\s*Stop\s+\d+\s*[:\-]', text))
print(f"\n{case}: {len(text)} chars in {elapsed:.1f}s -> {os.path.basename(OUT)}")
print(f"{case}: delivered stops = {delivered} / requested {STOPS}")

# Print the stop headings so we can see WHICH stops shipped.
for m in re.finditer(r'(?mi)^\s*(Stop\s+\d+\s*[:\-].*)$', text):
    print(f"   {m.group(1).strip()[:100]}")
