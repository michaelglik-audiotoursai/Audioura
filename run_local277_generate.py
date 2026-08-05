#!/usr/bin/env python3
"""LOCAL-277: Generate 2-stop and 8-stop Riviera tours to measure corpus depth effect.

Measures against baselines:
  2-stop: Cap d'Antibes + Eze = 7.0 and 6.5 facts/stop
  2-stop: Cap d'Antibes + Port de Nice = 1.5 facts/stop
  8-stop: 3.1 facts/stop, 25 total, all 8 delivered

Copies output to ~/Audioura/tours/ (gitignored).
"""
import os
import sys
import time
import json
import shutil

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'tests'))

# Load .env for API keys
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

os.environ['STORIED_MODE'] = 'true'
for k in ('TOUR_LLM_MODEL', 'DISABLE_CORPUS_GATE', 'DISABLE_STOP_CORPUS', 'DISABLE_STYLE_RETRY'):
    if k in os.environ:
        del os.environ[k]

# Force production DB for corpus reads
os.environ.pop('PYTEST_CURRENT_TEST', None)
os.environ.pop('_AUDIOURA_PYTEST_SESSION', None)

from db_connection import get_connection, check_db_available
from generate_tour_text import generate_tour_text

TOURS_DIR = os.path.join(PROJECT_ROOT, "tours")
DEST_DIR = os.path.expanduser("~/Audioura/tours")
os.makedirs(TOURS_DIR, exist_ok=True)
os.makedirs(DEST_DIR, exist_ok=True)


def count_facts(tour_text):
    """Simple fact counter: sentences with dates, named persons, or measurements."""
    import re
    facts = 0
    sentences = re.split(r'[.!?]+', tour_text)
    for s in sentences:
        s = s.strip()
        if not s or len(s) < 20:
            continue
        # Has a year (4 digits)?
        if re.search(r'\b\d{4}\b', s):
            facts += 1
            continue
        # Has a measurement?
        if re.search(r'\b\d+[\s-]*(km|metres?|meters?|miles?|hectares?|feet|years?)\b', s, re.I):
            facts += 1
            continue
        # Has a named person (capitalized word followed by another)?
        if re.search(r'[A-Z][a-z]+ [A-Z][a-z]+', s):
            facts += 1
            continue
    return facts


def parse_stops_from_text(text):
    """Parse stop names from generated tour text."""
    import re
    stops = []
    # Look for "Stop N:" or "## Stop N:" patterns
    patterns = [
        r'(?:^|\n)\s*(?:##?\s*)?Stop\s+\d+[:\s]+([^\n]+)',
        r'(?:^|\n)\s*\*\*Stop\s+\d+[:\s]+([^\n*]+)',
    ]
    for pat in patterns:
        matches = re.findall(pat, text)
        if matches:
            stops = [m.strip().rstrip('*').strip() for m in matches]
            break
    return stops


def generate_and_measure(n_stops, label):
    """Generate a tour and measure facts per stop."""
    print(f"\n{'─' * 70}")
    print(f"GENERATING: {n_stops}-stop Riviera tour ({label})")
    print(f"{'─' * 70}")

    output_file = os.path.join(TOURS_DIR, f"LOCAL277_riviera_{n_stops}stop_{label}.txt")

    start_time = time.time()
    result = generate_tour_text(
        location="French Riviera cycling tour, France",
        tour_type="biking",
        output_file=output_file,
        total_stops=n_stops,
        persona=None,
    )
    elapsed = time.time() - start_time

    if not result or not result[0]:
        print(f"  FATAL: Generation failed after {elapsed:.1f}s")
        return None

    tour_text = result[0]
    cost = 0.0
    if len(result) > 1 and result[1]:
        try:
            cost = float(result[1])
        except (TypeError, ValueError):
            cost = 0.0

    print(f"  ✓ Generated: {len(tour_text)} chars, {len(tour_text.split())} words")
    print(f"  ✓ Time: {elapsed:.1f}s")
    print(f"  ✓ Cost: ${cost:.4f}")
    print(f"  ✓ File: {output_file}")

    # Parse stops
    stops = parse_stops_from_text(tour_text)
    print(f"  ✓ Stops found: {len(stops)}: {stops}")

    # Count facts per stop
    # Split text by stop headers
    import re
    stop_sections = re.split(r'(?:^|\n)\s*(?:##?\s*)?Stop\s+\d+[:\s]', tour_text)
    if len(stop_sections) > 1:
        stop_sections = stop_sections[1:]  # skip preamble

    total_facts = 0
    facts_per_stop = []
    for i, section in enumerate(stop_sections):
        f = count_facts(section)
        stop_name = stops[i] if i < len(stops) else f"Stop {i+1}"
        facts_per_stop.append((stop_name, f))
        total_facts += f
        print(f"    {stop_name}: {f} facts")

    avg_facts = total_facts / max(len(stops), 1)
    print(f"  ✓ Total facts: {total_facts}, avg: {avg_facts:.1f} facts/stop")

    # Check corpus resolution for these stops
    from stop_corpus_reader import get_stop_corpus_for_tour
    conn = get_connection()
    corpus_data = get_stop_corpus_for_tour("French Riviera", stops, conn)
    conn.close()

    print(f"  Corpus resolution:")
    for s in stops:
        cd = corpus_data.get(s)
        pcount = len(cd['passages']) if cd and cd.get('passages') else 0
        print(f"    {s}: {pcount} passages available")

    # Copy to ~/Audioura/tours/
    dest_file = os.path.join(DEST_DIR, os.path.basename(output_file))
    shutil.copy2(output_file, dest_file)
    print(f"  ✓ Copied to: {dest_file}")

    return {
        'stops': stops,
        'facts_per_stop': facts_per_stop,
        'total_facts': total_facts,
        'avg_facts': avg_facts,
        'elapsed': elapsed,
        'cost': cost,
        'chars': len(tour_text),
        'words': len(tour_text.split()),
        'file': output_file,
    }


def main():
    print("=" * 70)
    print("LOCAL-277: GENERATE TOURS — MEASURE CORPUS DEPTH EFFECT")
    print("=" * 70)

    if not check_db_available():
        print("FATAL: Database unreachable")
        sys.exit(7)

    # Check OPENAI_API_KEY is available
    if not os.environ.get('OPENAI_API_KEY'):
        print("FATAL: OPENAI_API_KEY not set")
        sys.exit(1)

    # Pre-check audio_tours
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_before = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_before = [r[0] for r in cur.fetchall()]
    conn.close()
    print(f"  audio_tours: {at_before} rows")
    print(f"  Nice list: {nice_before}")

    # Generate 2-stop tour
    result_2 = generate_and_measure(2, "post_corpus")

    # Generate 8-stop tour
    result_8 = generate_and_measure(8, "post_corpus")

    # Summary
    print(f"\n{'=' * 70}")
    print("SUMMARY — LOCAL-277 corpus depth measurement")
    print(f"{'=' * 70}")

    if result_2:
        print(f"\n  2-STOP TOUR:")
        print(f"    Stops: {result_2['stops']}")
        print(f"    Facts/stop: {result_2['avg_facts']:.1f}")
        print(f"    Cost: ${result_2['cost']:.4f}")
        print(f"    Time: {result_2['elapsed']:.1f}s")
        print(f"    Baseline: Cap d'Antibes + Eze = 7.0 and 6.5 facts/stop")
        print(f"              Cap d'Antibes + Port de Nice = 1.5 facts/stop")

    if result_8:
        print(f"\n  8-STOP TOUR:")
        print(f"    Stops: {result_8['stops']}")
        print(f"    Facts/stop: {result_8['avg_facts']:.1f}")
        print(f"    Total facts: {result_8['total_facts']}")
        print(f"    Cost: ${result_8['cost']:.4f}")
        print(f"    Time: {result_8['elapsed']:.1f}s")
        print(f"    Baseline: 3.1 facts/stop, 25 total")

    # Post-check audio_tours
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    at_after = cur.fetchone()[0]
    cur.execute("SELECT id FROM audio_tours WHERE id IN (1,12,14,17,24,29,152) ORDER BY id")
    nice_after = [r[0] for r in cur.fetchall()]
    conn.close()
    print(f"\n  audio_tours: {at_after} (was {at_before})")
    print(f"  Nice list: {nice_after}")

    # D141: cleanup any test rows we created
    if at_after > at_before:
        new_count = at_after - at_before
        print(f"\n  D141 cleanup: {new_count} new rows to check...")
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT id, is_test FROM audio_tours
            WHERE id > (SELECT MAX(id) - %s FROM audio_tours)
            ORDER BY id DESC LIMIT %s
        """, (new_count + 5, new_count + 5))
        recent = cur.fetchall()
        for rid, is_test in recent:
            if is_test and rid not in nice_before:
                cur.execute("DELETE FROM audio_tours WHERE id = %s AND is_test = true", (rid,))
                print(f"    Deleted test row id={rid}")
        conn.commit()
        conn.close()

    print(f"\n  Output files copied to: {DEST_DIR}")
    print("=" * 70)


if __name__ == '__main__':
    main()
