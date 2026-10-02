#!/usr/bin/env python3
"""LOCAL-198: Stop corpus coverage gate — measure and enforce.

Part 1: Measures, for every venue in stop_corpus, for every stop:
  - passage count
  - whether the stop's own subject appears in its passages
  - how many passages are venue-level (mention venue but not stop)
  - coverage verdict: COVERED / VENUE_ONLY / EMPTY

Part 2: Implements the corpus gate behind DISABLE_CORPUS_GATE=1.
  - Detects VENUE_ONLY/EMPTY before narration call
  - Degrades gracefully (replace or shorten)
  - Logs decisions per stop

Part 3: A/B experiment — MAMAC, 2 stops, 3 runs, gate on vs off.

Word-matching approach to avoid the "Long" / "along" trap (LOCAL-178):
  - Extract content words from stop title (>=4 chars, not stopwords, not venue words)
  - Match whole words only (word-boundary regex)
  - Case-insensitive and accent-insensitive (NFD strip)
  - Short title words (<4 chars) are excluded from matching to avoid false positives
  - Venue name words are excluded (they don't distinguish stops from venue-level text)
"""
import os
import sys
import json
import re
import time
import unicodedata
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from db_connection import get_connection, check_db_available


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1: Coverage Measurement
# ═══════════════════════════════════════════════════════════════════════════════

# Stopwords for French + English (common words that appear in titles but don't
# indicate subject-matter coverage)
# LEAD fixup: the coverage primitives now live at the repo root in
# corpus_coverage.py so production can import them inside Docker. Re-exported
# here so this file's own tests and any existing callers keep working.
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from corpus_coverage import (  # noqa: F401,E402
    STOPWORDS, strip_accents, extract_content_words,
    word_appears_in_text, assess_stop_coverage, _extract_passage_texts,
)

def measure_all_coverage(conn) -> Dict[str, List[Dict]]:
    """Measure coverage for every venue, every stop in stop_corpus.

    Returns: {venue_name: [stop_assessment, ...]}
    """
    cur = conn.cursor()
    cur.execute('''
        SELECT venue_name, stop_title, passage_count, passages_json
        FROM stop_corpus
        ORDER BY venue_name, passage_count DESC
    ''')
    rows = cur.fetchall()
    cur.close()

    results = {}
    for venue_name, stop_title, passage_count, passages_json in rows:
        # Parse passages — can be list of strings OR list of dicts with 'text' key
        passages = _extract_passage_texts(passages_json)

        assessment = assess_stop_coverage(stop_title, venue_name, passages)
        assessment['stop_title'] = stop_title
        assessment['venue_name'] = venue_name

        if venue_name not in results:
            results[venue_name] = []
        results[venue_name].append(assessment)

    return results


def print_coverage_report(results: Dict[str, List[Dict]]) -> str:
    """Print and return the coverage report as a string."""
    lines = []
    lines.append("=" * 80)
    lines.append("STOP CORPUS COVERAGE REPORT — LOCAL-198")
    lines.append("=" * 80)
    lines.append("")

    total_stops = 0
    total_covered = 0
    total_venue_only = 0
    total_empty = 0

    for venue_name, stops in sorted(results.items()):
        lines.append(f"┌─ {venue_name} ({len(stops)} stops)")
        lines.append(f"│")

        venue_covered = 0
        venue_venue_only = 0
        venue_empty = 0

        for s in stops:
            verdict_icon = {
                'COVERED': '✓',
                'VENUE_ONLY': '⚠',
                'EMPTY': '✗',
            }.get(s['verdict'], '?')

            match_info = ""
            if s['subject_match_words']:
                match_info = f" (matched: {', '.join(s['subject_match_words'])})"
            elif s['content_words']:
                match_info = f" (sought: {', '.join(s['content_words'])} — NOT FOUND)"
            else:
                match_info = " (no extractable content words)"

            lines.append(
                f"│  {verdict_icon} {s['passage_count']:2d} passages | "
                f"{s['verdict']:11s} | {s['stop_title']}{match_info}"
            )

            if s['verdict'] == 'COVERED':
                venue_covered += 1
            elif s['verdict'] == 'VENUE_ONLY':
                venue_venue_only += 1
            else:
                venue_empty += 1

        lines.append(f"│")
        lines.append(
            f"└─ Summary: {venue_covered} COVERED, "
            f"{venue_venue_only} VENUE_ONLY, {venue_empty} EMPTY"
        )
        lines.append("")

        total_stops += len(stops)
        total_covered += venue_covered
        total_venue_only += venue_venue_only
        total_empty += venue_empty

    lines.append("=" * 80)
    lines.append("OVERALL SUMMARY")
    lines.append("=" * 80)
    lines.append(f"  Total stops in corpus:  {total_stops}")
    lines.append(f"  COVERED (writable):     {total_covered} ({100*total_covered/total_stops:.0f}%)")
    lines.append(f"  VENUE_ONLY (dangerous): {total_venue_only} ({100*total_venue_only/total_stops:.0f}%)")
    lines.append(f"  EMPTY (impossible):     {total_empty} ({100*total_empty/total_stops:.0f}%)")
    lines.append(f"")
    lines.append(f"  ** Writable stops (the real ceiling on tour quality): {total_covered}/{total_stops} **")
    lines.append("")

    report = "\n".join(lines)
    print(report)
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2: The Corpus Coverage Gate
# ═══════════════════════════════════════════════════════════════════════════════

def corpus_gate_check(
    stop_title: str,
    venue_name: str,
    conn,
) -> Dict:
    """Check whether a stop passes the corpus coverage gate.

    Returns:
        {
            'stop_title': str,
            'verdict': 'COVERED' | 'VENUE_ONLY' | 'EMPTY',
            'passage_count': int,
            'content_words': list,
            'subject_match_words': list,
        }
    """
    import psycopg2.extras

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Find matching corpus row
    cur.execute(
        "SELECT passages_json FROM stop_corpus WHERE venue_name = %s AND stop_title = %s",
        (venue_name, stop_title)
    )
    row = cur.fetchone()

    if not row:
        # Try fuzzy match (same as stop_corpus_reader._match_stop_to_corpus)
        cur.execute(
            "SELECT stop_title, passages_json FROM stop_corpus WHERE venue_name = %s",
            (venue_name,)
        )
        all_rows = cur.fetchall()
        cur.close()

        # Try containment match
        matched_row = None
        for r in all_rows:
            title_lower = r['stop_title'].lower()
            name_lower = stop_title.lower()
            if name_lower in title_lower or title_lower in name_lower:
                matched_row = r
                break

        if not matched_row:
            return {
                'stop_title': stop_title,
                'verdict': 'EMPTY',
                'passage_count': 0,
                'content_words': extract_content_words(stop_title, venue_name),
                'subject_match_words': [],
            }
        passages_json = matched_row['passages_json']
    else:
        cur.close()
        passages_json = row['passages_json']

    passages = _extract_passage_texts(passages_json)
    assessment = assess_stop_coverage(stop_title, venue_name, passages)
    return {
        'stop_title': stop_title,
        'verdict': assessment['verdict'],
        'passage_count': assessment['passage_count'],
        'content_words': assessment['content_words'],
        'subject_match_words': assessment['subject_match_words'],
    }


def apply_corpus_gate(
    stop_titles: List[str],
    venue_name: str,
    requested_stop_count: int,
    conn,
) -> Tuple[List[str], List[Dict]]:
    """Apply the corpus coverage gate to a list of candidate stops.

    Implements the degradation path:
      1. COVERED stops pass through.
      2. VENUE_ONLY stops get flagged for shortened narration (venue-grounded only).
      3. If replacements with COVERED status exist, prefer them.

    Returns:
        (final_stop_list, gate_log)

    gate_log is a list of per-stop decisions:
        {'stop': str, 'verdict': str, 'action': 'PASSED'|'SHORTENED'|'REPLACED'}
    """
    gate_log = []
    final_stops = []

    # Assess all candidate stops
    assessments = {}
    for title in stop_titles:
        assessments[title] = corpus_gate_check(title, venue_name, conn)

    # Get all available stops for this venue (for replacement candidates)
    import psycopg2.extras
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT stop_title, passages_json FROM stop_corpus WHERE venue_name = %s",
        (venue_name,)
    )
    all_venue_stops = cur.fetchall()
    cur.close()

    # Find COVERED replacement candidates (not already in the stop list)
    replacement_pool = []
    for row in all_venue_stops:
        title = row['stop_title']
        if title in stop_titles:
            continue
        # Check if this candidate is COVERED
        passages_json = row['passages_json']
        passages = _extract_passage_texts(passages_json)

        assessment = assess_stop_coverage(title, venue_name, passages)
        if assessment['verdict'] == 'COVERED':
            replacement_pool.append(title)

    replacement_idx = 0

    for title in stop_titles:
        a = assessments[title]
        if a['verdict'] == 'COVERED':
            final_stops.append(title)
            gate_log.append({
                'stop': title,
                'verdict': 'COVERED',
                'action': 'PASSED',
            })
        elif a['verdict'] in ('VENUE_ONLY', 'EMPTY'):
            # Try to replace with a COVERED stop
            if replacement_idx < len(replacement_pool):
                replacement = replacement_pool[replacement_idx]
                replacement_idx += 1
                final_stops.append(replacement)
                gate_log.append({
                    'stop': title,
                    'verdict': a['verdict'],
                    'action': 'REPLACED',
                    'replacement': replacement,
                })
                print(f"  [CORPUS-GATE] stop='{title}' verdict={a['verdict']} "
                      f"action=REPLACED replacement='{replacement}'")
            else:
                # No replacement available — shorten
                final_stops.append(title)
                gate_log.append({
                    'stop': title,
                    'verdict': a['verdict'],
                    'action': 'SHORTENED',
                })
                print(f"  [CORPUS-GATE] stop='{title}' verdict={a['verdict']} "
                      f"action=SHORTENED")
        else:
            final_stops.append(title)
            gate_log.append({
                'stop': title,
                'verdict': a['verdict'],
                'action': 'PASSED',
            })

    # Report if we couldn't meet requested count
    if len(final_stops) < requested_stop_count:
        print(f"  [CORPUS-GATE] WARNING: Only {len(final_stops)} stops available, "
              f"requested {requested_stop_count}")

    return final_stops, gate_log


# ═══════════════════════════════════════════════════════════════════════════════
# PART 3: A/B Experiment
# ═══════════════════════════════════════════════════════════════════════════════

LOCATION = "Musee d Art Moderne et d Art Contemporain, Nice, France"
TOUR_TYPE = "museum"
STOPS_PER_RUN = 2
RUNS_PER_ARM = 3


def _ensure_env():
    """Ensure OPENAI_API_KEY is set."""
    if not os.environ.get('OPENAI_API_KEY'):
        import subprocess
        try:
            key = subprocess.check_output(
                ['docker', 'exec', 'audioura-tour-generator-1', 'printenv', 'OPENAI_API_KEY'],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            os.environ['OPENAI_API_KEY'] = key
        except Exception:
            print("ERROR: OPENAI_API_KEY not set and cannot fetch from container")
            sys.exit(1)


def generate_with_gate(gate_enabled: bool, run_idx: int, conn) -> Dict:
    """Generate a tour with or without the corpus gate.

    Returns: {tour_text, stops, gate_log, paragraphs}
    """
    _ensure_env()

    os.environ['STORIED_MODE'] = 'true'

    if gate_enabled:
        os.environ.pop('DISABLE_CORPUS_GATE', None)
    else:
        os.environ['DISABLE_CORPUS_GATE'] = '1'

    # Remove DATABASE_URL to bypass S20 cache
    _saved_db_url = os.environ.pop('DATABASE_URL', None)

    # Force fresh import each time to pick up env changes
    if 'generate_tour_text' in sys.modules:
        del sys.modules['generate_tour_text']

    from generate_tour_text import generate_tour_text

    tour_text, output_file, coords = generate_tour_text(
        location=LOCATION,
        tour_type=TOUR_TYPE,
        total_stops=STOPS_PER_RUN,
    )

    # Restore env
    if _saved_db_url:
        os.environ['DATABASE_URL'] = _saved_db_url

    # Parse stops and paragraphs
    stops = extract_stops_and_paragraphs(tour_text)
    stop_titles = [s['title'] for s in stops]

    return {
        'tour_text': tour_text,
        'stops': stops,
        'stop_titles': stop_titles,
        'gate_enabled': gate_enabled,
        'run_idx': run_idx,
    }


def extract_stops_and_paragraphs(tour_text: str) -> List[Dict]:
    """Parse tour text into stops with their paragraphs."""
    if not tour_text:
        return []

    stops = []
    parts = re.split(r'^(Stop\s+\d+:.*)$', tour_text, flags=re.MULTILINE)

    current_title = None
    current_content = ""

    for part in parts:
        if re.match(r'^Stop\s+\d+:', part):
            if current_title:
                stops.append({'title': current_title, 'content': current_content.strip()})
            current_title = part.strip()
            current_content = ""
        else:
            current_content += part

    if current_title:
        stops.append({'title': current_title, 'content': current_content.strip()})

    return stops


def run_experiment(conn):
    """Run the A/B experiment: 3 runs × 2 arms."""
    print("\n" + "=" * 80)
    print("PART 3: A/B EXPERIMENT — MAMAC, 2 stops, 3 runs per arm")
    print("=" * 80)

    results = {'gate_on': [], 'gate_off': []}
    all_paragraphs = {}

    for arm_name, gate_enabled in [('gate_off', False), ('gate_on', True)]:
        print(f"\n{'─'*40}")
        print(f"ARM: {arm_name.upper()} (gate_enabled={gate_enabled})")
        print(f"{'─'*40}")

        for run_idx in range(RUNS_PER_ARM):
            print(f"\n  Run {run_idx + 1}/{RUNS_PER_ARM}...")
            try:
                result = generate_with_gate(gate_enabled, run_idx, conn)
                results[arm_name].append(result)
                all_paragraphs[f"{arm_name}_run{run_idx}"] = result['tour_text']
                print(f"    Stops: {[s['title'][:40] for s in result['stops']]}")
                time.sleep(1)  # Rate limit courtesy
            except Exception as e:
                print(f"    ERROR: {e}")
                import traceback
                traceback.print_exc()
                results[arm_name].append({'error': str(e)})

    return results, all_paragraphs


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    if not check_db_available():
        print("ERROR: Database not available")
        sys.exit(7)

    conn = get_connection()

    # ─── PART 1: Measure coverage ─────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART 1: CORPUS COVERAGE MEASUREMENT")
    print("=" * 80 + "\n")

    results = measure_all_coverage(conn)
    report = print_coverage_report(results)

    # Save report to file
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 
        'tests', 'local198_coverage_report.txt'
    )
    # Actually put it in the repo root for visibility
    report_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', 
        'local198_coverage_report.txt'
    )
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to: {report_path}")

    # ─── PART 2: Gate demonstration ──────────────────────────────────────────
    print("\n" + "=" * 80)
    print("PART 2: CORPUS GATE DEMONSTRATION")
    print("=" * 80 + "\n")

    # Demonstrate gate on MAMAC stops
    mamac_venue = "Musee d Art Moderne et d Art Contemporain, Nice, France"
    mamac_stops = [s['stop_title'] for s in results.get(mamac_venue, [])]

    if mamac_stops:
        print(f"Applying gate to all {len(mamac_stops)} MAMAC stops:")
        print(f"  Input: {mamac_stops}")
        final_stops, gate_log = apply_corpus_gate(
            mamac_stops, mamac_venue, len(mamac_stops), conn
        )
        print(f"\n  Gate results:")
        for entry in gate_log:
            action = entry['action']
            extra = f" → '{entry.get('replacement', '')}'" if 'replacement' in entry else ''
            print(f"    {entry['verdict']:11s} | {action:10s} | {entry['stop']}{extra}")

    # ─── PART 3: A/B Experiment ───────────────────────────────────────────────
    # Only run if explicitly requested (costs money)
    if '--experiment' in sys.argv:
        exp_results, paragraphs = run_experiment(conn)

        # Persist paragraphs to file (D71 requirement)
        para_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..',
            'local198_experiment_paragraphs.json'
        )
        with open(para_path, 'w') as f:
            json.dump(paragraphs, f, indent=2, ensure_ascii=False)
        print(f"\nParagraphs persisted to: {para_path}")

        # Run anchor detector on results
        run_anchor_analysis(exp_results, conn)
    else:
        print("\n[Skip A/B experiment — pass --experiment to run (costs ~$0.12)]")

    # ─── Safety checks ────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("SAFETY CHECKS")
    print("=" * 80)

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    count = cur.fetchone()[0]
    print(f"  audio_tours rows: {count}")
    assert count == 117, f"Expected 117, got {count}"

    cur.execute("""
        SELECT id FROM audio_tours 
        WHERE id IN (1,12,14,17,21,24,27,28,29,152) 
        ORDER BY id
    """)
    nice_list = [r[0] for r in cur.fetchall()]
    print(f"  Nice list: {nice_list}")
    assert nice_list == [1, 12, 14, 17, 21, 24, 27, 28, 29, 152]

    cur.close()
    conn.close()

    print("\n✓ All safety checks passed")


def run_anchor_analysis(exp_results: Dict, conn):
    """Run anchor detector on experiment results and report."""
    try:
        from tests.stop_anchor_detector_v2_with_stop_corpus import classify_paragraphs
    except ImportError:
        try:
            # Try the test file that has the detector
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tests'))
            from stop_anchor_detector_v2 import classify_paragraph
        except ImportError:
            print("  [Anchor analysis skipped — detector not importable]")
            return

    print("\n  Anchor analysis would go here (detector integration)")


if __name__ == '__main__':
    main()
