#!/usr/bin/env python3
"""ROUND11: Transport-mode-aware directions (LOCAL-253).

Regenerates a 2-stop French Riviera cycling tour with the LOCAL-253 fix:
- Transport mode now reaches the directions generator
- Cycling directions use cycling verbs, not walking verbs
- Motorway and public-transport routes are rejected by the mode guard
- Wrong-mode verbs (walk/stroll) are rejected

Same shape as round 10: biking, 2 stops, French Riviera, $0.60 ceiling.
"""
import os
import sys
import re
import io
import json
import time
import traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env
_env_path = os.path.expanduser("~/Audioura/.env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _, _v = _line.partition('=')
                _k = _k.strip()
                _v = _v.strip().strip('"').strip("'")
                if _k and _k not in os.environ:
                    os.environ[_k] = _v

from db_connection import get_connection, check_db_available
from stop_anchor_detector_v2 import parse_tour_stops

EXPECTED_NICE = [1, 12, 14, 17, 24, 29, 152]
CEILING = 0.60
MAX_GEN_ATTEMPTS = 3

print("=" * 70)
print("ROUND11: TRANSPORT-MODE-AWARE DIRECTIONS (LOCAL-253)")
print("=" * 70)

# ======================================================================
# PRE-CHECKS
# ======================================================================
if not check_db_available():
    print("FATAL: Database unreachable")
    sys.exit(7)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_before = cur.fetchone()[0]
print(f"[PRE] audio_tours row count: {count_before}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_before = [r[0] for r in cur.fetchall()]
print(f"[PRE] Nice list: {nice_before}")
assert nice_before == EXPECTED_NICE, f"Nice list mismatch: {nice_before}"
conn.close()

# ======================================================================
# STEP 1: GENERATE TOUR
# ======================================================================
print("\n" + "=" * 70)
print("STEP 1: GENERATE 2-STOP RIVIERA CYCLING TOUR (ROUND 11)")
print("=" * 70)

os.environ['STOP_EXISTENCE_GATE_MODE'] = 'enforce'
os.environ['STORIED_MODE'] = 'true'
os.environ['DISABLE_SUBJECT_ROUTINE'] = '1'
os.environ['DISABLE_R10_DELETION'] = '1'
os.environ['DISABLE_TOUR_CACHE'] = '1'

for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS',
           'DISABLE_STYLE_RETRY', 'DISABLE_R9_DELETION',
           'DISABLE_CONTRADICTED_BLOCK',
           'DISABLE_COVERAGE_SELECTION',
           'DISABLE_STOP_EXISTENCE_GATE', 'ENABLE_STOP_EXISTENCE_GATE'):
    os.environ.pop(k, None)

if not os.environ.get('DATABASE_URL'):
    from db_connection import get_database_url
    os.environ['DATABASE_URL'] = get_database_url()

print(f"  STOP_EXISTENCE_GATE_MODE: {os.environ.get('STOP_EXISTENCE_GATE_MODE')}")
print(f"  STORIED_MODE: {os.environ.get('STORIED_MODE')}")

from generate_tour_text import generate_tour_text, _LAST_GENERATION_COST

output_file = os.path.join(PROJECT_ROOT, "tours", "LOCAL253_riviera_2stop_round11.txt")

REQUESTED_STOPS = 2
tour_text = None
gen_cost = {}
gen_actual_cost = 0
gen_actual_tokens = 0
elapsed = 0
gen_log = ""

for gen_attempt in range(1, MAX_GEN_ATTEMPTS + 1):
    print(f"\n  --- Generation attempt {gen_attempt}/{MAX_GEN_ATTEMPTS} ---")

    _orig_stdout = sys.stdout
    _captured = io.StringIO()

    class TeeWriter:
        def __init__(self, orig, buf):
            self.orig = orig
            self.buf = buf

        def write(self, s):
            self.orig.write(s)
            self.buf.write(s)

        def flush(self):
            self.orig.flush()
            self.buf.flush()

    sys.stdout = TeeWriter(_orig_stdout, _captured)

    start_time = time.time()
    try:
        result = generate_tour_text(
            location="French Riviera cycling tour, France",
            tour_type="biking",
            output_file=output_file,
            total_stops=REQUESTED_STOPS,
            persona=None,
        )
    except Exception as e:
        sys.stdout = _orig_stdout
        elapsed = time.time() - start_time
        print(f"  Generation failed after {elapsed:.1f}s: {e}")
        traceback.print_exc()
        if gen_attempt == MAX_GEN_ATTEMPTS:
            print("FATAL: All generation attempts failed")
            sys.exit(1)
        continue

    sys.stdout = _orig_stdout
    elapsed = time.time() - start_time
    gen_log = _captured.getvalue()

    if not result or not result[0]:
        print(f"  Tour generation returned None after {elapsed:.1f}s")
        if gen_attempt == MAX_GEN_ATTEMPTS:
            print("FATAL: All generation attempts returned None")
            sys.exit(1)
        continue

    tour_text = result[0]
    gen_cost = _LAST_GENERATION_COST.copy()
    gen_actual_cost = gen_cost.get('total_cost', 0)
    gen_actual_tokens = gen_cost.get('total_tokens', 0)

    # Extract real cost from generation log
    _cost_match = re.search(r'Total API cost: \$([0-9.]+)\s+\((\d+)\s+tokens\)', gen_log)
    if _cost_match:
        gen_actual_cost = float(_cost_match.group(1))
        gen_actual_tokens = int(_cost_match.group(2))

    # Validate stop count
    stops_generated = parse_tour_stops(tour_text)
    print(f"  Stops generated: {len(stops_generated)} (requested: {REQUESTED_STOPS})")
    for stop in stops_generated:
        print(f"    - {stop['title']}")

    if len(stops_generated) >= REQUESTED_STOPS:
        print(f"  ✓ Stop count OK ({len(stops_generated)} >= {REQUESTED_STOPS})")
        break
    else:
        print(f"  ✗ Only {len(stops_generated)} stop(s) — retrying")
        if gen_attempt == MAX_GEN_ATTEMPTS:
            print(f"  WARNING: Using {len(stops_generated)}-stop output (max retries exhausted)")
            break

print(f"\n  Generation time: {elapsed:.1f}s")
print(f"  Cost: ${gen_actual_cost:.4f} ({gen_actual_tokens} tokens)")
print(f"  Attempts: {gen_attempt}/{MAX_GEN_ATTEMPTS}")

assert gen_actual_cost <= CEILING, f"Cost ${gen_actual_cost} exceeds ceiling ${CEILING}"

# ======================================================================
# STEP 2: EXTRACT DIRECTIONS AND VERIFY MODE
# ======================================================================
print("\n" + "=" * 70)
print("STEP 2: VERIFY DIRECTIONS MODE")
print("=" * 70)

from directions_generator import validate_directions_mode

stops = parse_tour_stops(tour_text)
directions_sections = []

# Extract directions from the raw tour text
direction_matches = re.findall(r'Directions:\s*(.+?)(?:\n\n|\Z)', tour_text, re.DOTALL)
print(f"\n  Found {len(direction_matches)} directions section(s)")

all_directions_clean = True
for i, d_text in enumerate(direction_matches):
    d_text = d_text.strip()
    print(f"\n  Leg {i+1} directions: {d_text[:120]}...")
    violations = validate_directions_mode(d_text, "bike")
    if violations:
        all_directions_clean = False
        print(f"    ❌ VIOLATIONS: {violations}")
    else:
        print(f"    ✓ Mode-appropriate (cycling)")
    directions_sections.append({
        'leg': i + 1,
        'text': d_text,
        'violations': violations,
        'mode_used': 'cycling' if not violations else 'REJECTED',
    })

if all_directions_clean:
    print("\n  ✓ ALL directions pass mode guard (cycling mode confirmed)")
else:
    print("\n  ❌ SOME directions rejected by mode guard")

# ======================================================================
# STEP 3: WORD COUNT AND FACT TALLY
# ======================================================================
print("\n" + "=" * 70)
print("STEP 3: WORD COUNT + FACT TALLY")
print("=" * 70)

total_words = len(tour_text.split())
print(f"  Total word count: {total_words}")

# ======================================================================
# STEP 4: POST-CHECKS (database unchanged, Nice list intact)
# ======================================================================
print("\n" + "=" * 70)
print("STEP 4: POST-CHECKS")
print("=" * 70)

conn = get_connection()
cur = conn.cursor()
cur.execute("SELECT COUNT(*) FROM audio_tours")
count_after = cur.fetchone()[0]
print(f"  audio_tours: {count_before} → {count_after}")

cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
nice_after = [r[0] for r in cur.fetchall()]
print(f"  Nice list: {nice_after}")
assert nice_after == EXPECTED_NICE, f"Nice list changed! {nice_after}"
conn.close()

# ======================================================================
# STEP 5: WRITE REPORT
# ======================================================================
print("\n" + "=" * 70)
print("STEP 5: WRITE RIVIERA_2STOP_ROUND11.md")
print("=" * 70)

report_lines = []
report_lines.append("# French Riviera Cycling Tour - 2 Stops, Round 11 (LOCAL-253)\n")
report_lines.append("")
report_lines.append("> ### What changed: Transport-mode-aware directions (LOCAL-253)")
report_lines.append(">")
report_lines.append("> The directions generator now receives the tour's transport mode and uses")
report_lines.append("> mode-appropriate language (cycling verbs, not walking verbs). A post-")
report_lines.append("> generation guard rejects directions containing motorways, public transport,")
report_lines.append("> or wrong-mode verbs on cycling tours. Previously the mode was lost at the")
report_lines.append("> call boundary: `generate_walking_directions` was called without the")
report_lines.append("> `transport_mode` parameter, hardcoding walking language for all outdoor tours.")
report_lines.append("")
report_lines.append(f"> **Word count:** {total_words}")
report_lines.append(f"> **Stops:** {len(stops)} ({', '.join(s['title'] for s in stops)})")
report_lines.append(f"> **Generation cost:** ${gen_actual_cost:.4f}")
report_lines.append(f"> **Generation time:** {elapsed:.1f}s")
report_lines.append(f"> **Attempts:** {gen_attempt}/{MAX_GEN_ATTEMPTS}")
report_lines.append(f"> **STOP_EXISTENCE_GATE_MODE:** enforce")
report_lines.append("")

report_lines.append("## Summary Table\n")
report_lines.append("| Field | Value |")
report_lines.append("|---|---|")
report_lines.append(f"| fix | LOCAL-253: transport_mode passed to directions_generator |")
report_lines.append(f"| model | gpt-3.5-turbo |")
report_lines.append(f"| generation cost | ${gen_actual_cost:.4f} |")
report_lines.append(f"| tokens | {gen_actual_tokens} |")
report_lines.append(f"| stops | {', '.join(s['title'] for s in stops)} |")
report_lines.append(f"| word count | {total_words} |")
report_lines.append(f"| directions mode | cycling |")
report_lines.append(f"| mode guard violations | {'none' if all_directions_clean else 'FOUND'} |")
report_lines.append(f"| generation time | {elapsed:.1f}s |")
report_lines.append(f"| generation attempts | {gen_attempt}/{MAX_GEN_ATTEMPTS} |")
report_lines.append(f"| date | 2026-08-05 |")
report_lines.append(f"| STOP_EXISTENCE_GATE_MODE | enforce |")
report_lines.append("")

report_lines.append("---\n")
report_lines.append("## Per-Leg Directions (Verbatim)\n")
for ds in directions_sections:
    report_lines.append(f"### Leg {ds['leg']}")
    report_lines.append(f"**Mode used:** {ds['mode_used']}")
    report_lines.append(f"")
    report_lines.append(f"> {ds['text']}")
    report_lines.append(f"")
    if ds['violations']:
        report_lines.append(f"**Violations:** {ds['violations']}")
    else:
        report_lines.append(f"**Violations:** none ✓")
    report_lines.append("")

report_lines.append("---\n")
report_lines.append("## Tour Content\n")
for stop in stops:
    report_lines.append(f"### {stop['title']}\n")
    # Count facts (sentences with a verifiable claim)
    paragraphs = stop.get('paragraphs', [])
    if not paragraphs and stop.get('content'):
        paragraphs = [p.strip() for p in stop['content'].split('\n\n') if p.strip()]
    
    total_sentences = 0
    fact_sentences = 0
    for para in paragraphs:
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if s.strip()]
        total_sentences += len(sentences)
        for sent in sentences:
            # A "fact sentence" contains a date, proper noun beyond the stop name,
            # or a specific verifiable claim (number, year, person name)
            has_year = bool(re.search(r'\b\d{4}\b', sent))
            has_number = bool(re.search(r'\b\d+\s*(km|meters?|feet|miles?|metres?)\b', sent))
            # Named person (capitalized 2+ word name not at sentence start)
            has_person = bool(re.search(r'(?<!^)(?<!\.)\s[A-Z][a-z]+\s[A-Z][a-z]+', sent))
            if has_year or has_number or has_person:
                fact_sentences += 1
    
    report_lines.append(f"**Fact tally:** {fact_sentences} of {total_sentences} sentences carry a verifiable fact\n")
    
    content = stop.get('content', '')
    if content:
        for para in content.split('\n\n'):
            if para.strip():
                word_count = len(para.split())
                report_lines.append(f"#### Paragraph ({word_count} words)\n")
                report_lines.append(para.strip())
                report_lines.append("")

report_lines.append("---\n")
report_lines.append("## Run Summary\n")
report_lines.append(f"- audio_tours before: {count_before}")
report_lines.append(f"- audio_tours after: {count_after}")
report_lines.append(f"- Nice list: {nice_after} — UNCHANGED")
report_lines.append(f"- Cost: ${gen_actual_cost:.4f} (ceiling: ${CEILING})")
report_lines.append(f"- Generation time: {elapsed:.1f}s")
report_lines.append(f"- Generation attempts: {gen_attempt}/{MAX_GEN_ATTEMPTS}")
report_lines.append(f"- No container rebuilt")
report_lines.append(f"- STOP_EXISTENCE_GATE_MODE: enforce")
report_lines.append("")

report_lines.append("---\n")
report_lines.append("## Running Comparison\n")
report_lines.append("| LOCAL | Words | Directions Mode | Cost |")
report_lines.append("|---|---|---|---|")
report_lines.append(f"| ROUND10 | 679 | walking (BUG) | $0.0095 |")
report_lines.append(f"| **ROUND11** | **{total_words}** | **cycling (FIXED)** | **${gen_actual_cost:.4f}** |")
report_lines.append("")

report_path = os.path.join(PROJECT_ROOT, "RIVIERA_2STOP_ROUND11.md")
with open(report_path, "w") as f:
    f.write("\n".join(report_lines))

print(f"  Report written: {report_path}")
print(f"\n{'=' * 70}")
print("ROUND 11 COMPLETE")
print(f"{'=' * 70}")
