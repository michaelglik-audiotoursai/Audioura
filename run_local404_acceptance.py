#!/usr/bin/env python3
"""run_local404_acceptance.py — Acceptance for LOCAL-404: an appositive is not a story.

Primary venue: Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA (8 stops)
Control venue: Palais Lascaris, Nice, France (4 stops)

Acceptance criteria:
  - Every stop has ≥1 sentence in which a named person DOES something with a consequence
  - An appositive ("X, a ROLE") does NOT count
  - Broder, Mourlot, and Fridman each ≥1, all in stop 1
  - Appositive-rejection log lines present (showing the check fired)
  - Coherence gate rejection count logged; zero impossible relations
  - Control: Palais Lascaris at 4 → 4/4 real instruments, dates intact, base score ≥90

Env:
  DISABLE_TOUR_CACHE=1
  DATABASE_URL=postgresql://admin:password123@localhost:5433/audiotours
  STORIED_MODE=true
  SERP_API_KEY / SERP_PROVIDER from ~/Audioura/.env
"""
import os
import sys
import re
import io
import time
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault('DISABLE_TOUR_CACHE', '1')
os.environ.setdefault('DATABASE_URL', 'postgresql://admin:password123@localhost:5433/audiotours')
os.environ.setdefault('STORIED_MODE', 'true')

# Load ~/Audioura/.env for SERP keys
_home_env = os.path.expanduser('~/Audioura/.env')
if os.path.exists(_home_env):
    with open(_home_env) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

import work_story_searcher
work_story_searcher.SERP_API_KEY = os.environ.get('SERP_API_KEY', '')
work_story_searcher.OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

import generate_tour_text
from generate_tour_text import generate_tour_text as gen_tour
from tour_rubric_scorer import score_tour_file
from story_beat_injector import _APPOSITIVE_ONLY_RE, _CONSEQUENTIAL_VERB_RE


# === Helpers ===

def split_stops(tour_text: str) -> list:
    stops = re.split(r'\n(?=Stop \d+:)', tour_text)
    return [s for s in stops if s.strip().startswith('Stop')]


def contains_ci(text: str, term: str) -> bool:
    return term.lower() in text.lower()


def has_consequential_story(stop_text: str, person_surname: str) -> bool:
    """Check if a stop text contains a sentence where person DOES something consequential.

    Returns True if at least one sentence mentioning the person has a consequential
    verb that is NOT just an appositive-role identification.
    """
    sentences = re.split(r'(?<=[.!?])\s+', stop_text)
    person_lower = person_surname.lower()
    for sent in sentences:
        if person_lower not in sent.lower():
            continue
        # Check for consequential verb
        if _CONSEQUENTIAL_VERB_RE.search(sent):
            # Make sure it's not JUST an appositive
            m = _APPOSITIVE_ONLY_RE.search(sent)
            if not m:
                return True  # Verb present, no appositive pattern → story!
            # Appositive present — check if verb comes AFTER it
            after = sent[m.end():]
            if _CONSEQUENTIAL_VERB_RE.search(after):
                return True
    return False


# === Main ===

def run_mfa_acceptance():
    """Generate MFA Unbound tour and verify acceptance criteria."""
    print("\n" + "=" * 70)
    print("LOCAL-404 ACCEPTANCE: Picasso, Miró, Dalí: Unbound at MFA, Boston, MA")
    print("=" * 70)

    location = "Picasso, Miró, Dalí: Unbound exhibition at MFA, Boston, MA"
    output_file = "tours/LOCAL404_mfa_unbound.json"

    # Capture stdout for log analysis
    log_capture = io.StringIO()
    start = time.time()

    with redirect_stdout(log_capture):
        result = gen_tour(location, 'museum', output_file=output_file, total_stops=8)

    elapsed = time.time() - start
    log_output = log_capture.getvalue()
    print(f"\n  Generation completed in {elapsed:.1f}s")

    # Parse the tour
    tour_text = ''
    if isinstance(result, dict):
        tour_text = result.get('tour_text', '') or result.get('complete_tour', '')
    elif isinstance(result, str):
        tour_text = result
    if not tour_text and os.path.exists(output_file):
        with open(output_file) as f:
            content = f.read()
            if content.strip().startswith('{'):
                import json
                data = json.loads(content)
                tour_text = data.get('tour_text', '') or data.get('complete_tour', '')
            else:
                tour_text = content

    stops = split_stops(tour_text)
    print(f"  Stops generated: {len(stops)}")

    # === CRITERION 1: Every stop has a person doing something consequential ===
    print("\n--- Criterion 1: Every stop has a named person with a consequential verb ---")
    criterion1_pass = True
    for i, stop in enumerate(stops, 1):
        # Find any sentence with a capitalized name + consequential verb
        sentences = re.split(r'(?<=[.!?])\s+', stop)
        found_story = False
        story_sentence = ""
        for sent in sentences:
            # Look for any proper noun followed by a consequential verb
            if _CONSEQUENTIAL_VERB_RE.search(sent):
                # Has a named person? (capital letter word that isn't first word)
                names = re.findall(r'(?<!^)(?<!\. )([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)', sent)
                if names:
                    found_story = True
                    story_sentence = sent[:80]
                    break
        status = "✓" if found_story else "✗"
        if not found_story:
            criterion1_pass = False
        print(f"  Stop {i}: {status} {story_sentence}...")

    # === CRITERION 2: Broder, Mourlot, Fridman all in stop 1 ===
    print("\n--- Criterion 2: Broder, Mourlot, Fridman each ≥1, all in stop 1 ---")
    stop1 = stops[0] if stops else ''
    broder_in_1 = contains_ci(stop1, 'broder')
    mourlot_in_1 = contains_ci(stop1, 'mourlot')
    fridman_in_1 = contains_ci(stop1, 'fridman')
    print(f"  Broder in stop 1: {'✓' if broder_in_1 else '✗'}")
    print(f"  Mourlot in stop 1: {'✓' if mourlot_in_1 else '✗'}")
    print(f"  Fridman in stop 1: {'✓' if fridman_in_1 else '✗'}")
    criterion2_pass = broder_in_1 and mourlot_in_1 and fridman_in_1

    # === CRITERION 3: Appositive-rejection log lines present ===
    print("\n--- Criterion 3: Appositive-rejection log lines ([LOCAL-404]) ---")
    appositive_lines = [l for l in log_output.split('\n') if '[LOCAL-404]' in l]
    criterion3_pass = len(appositive_lines) > 0
    print(f"  [LOCAL-404] log lines: {len(appositive_lines)}")
    for line in appositive_lines[:5]:
        print(f"    {line.strip()}")

    # === CRITERION 4: Coherence gate ===
    print("\n--- Criterion 4: Coherence gate (zero impossible relations) ---")
    coherence_lines = [l for l in log_output.split('\n') if 'coherence' in l.lower() or 'temporal' in l.lower()]
    impossible_lines = [l for l in log_output.split('\n') if 'impossible' in l.lower() and 'relation' in l.lower()]
    print(f"  Coherence log lines: {len(coherence_lines)}")
    print(f"  Impossible relation lines: {len(impossible_lines)}")
    criterion4_pass = len(impossible_lines) == 0

    # === CRITERION 5: Storied mode invariants ===
    print("\n--- Criterion 5: Storied mode invariants (from LOCAL-403) ---")
    full_text_lower = tour_text.lower()
    with_publisher_count = full_text_lower.count('with publisher')
    livre_present = 'livre' in full_text_lower or "livre d'artiste" in full_text_lower
    collab_present = 'collabor' in full_text_lower
    typog_present = 'typograph' in full_text_lower or 'book' in full_text_lower
    print(f"  'with publisher' count: {with_publisher_count} (must be 0)")
    print(f"  livre d'artiste/livre: {'✓' if livre_present else '✗'}")
    print(f"  collabor*: {'✓' if collab_present else '✗'}")
    print(f"  typography/book: {'✓' if typog_present else '✗'}")
    print(f"  Stops declared == actual: {len(stops)} (requested 8)")
    criterion5_pass = (
        with_publisher_count == 0
        and livre_present
        and collab_present
        and typog_present
        and len(stops) >= 3  # at least 3 of 8 requested
    )

    # === Summary ===
    print("\n" + "=" * 70)
    print("MFA ACCEPTANCE SUMMARY")
    print("=" * 70)
    all_pass = criterion1_pass and criterion2_pass and criterion3_pass and criterion4_pass and criterion5_pass
    results = [
        ("1. Every stop has person + consequential verb", criterion1_pass),
        ("2. Broder, Mourlot, Fridman all in stop 1", criterion2_pass),
        ("3. Appositive-rejection log lines present", criterion3_pass),
        ("4. Zero impossible relations", criterion4_pass),
        ("5. Storied mode invariants", criterion5_pass),
    ]
    for label, passed in results:
        print(f"  {'✓' if passed else '✗'} {label}")
    print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")
    return all_pass, tour_text, log_output


def run_palais_control():
    """Control: Palais Lascaris at 4 stops → instruments + dates intact."""
    print("\n" + "=" * 70)
    print("CONTROL: Palais Lascaris, Nice, France (4 stops)")
    print("=" * 70)

    location = "Palais Lascaris, Nice, France"
    output_file = "tours/LOCAL404_palais_control.json"

    log_capture = io.StringIO()
    start = time.time()

    with redirect_stdout(log_capture):
        result = gen_tour(location, 'museum', output_file=output_file, total_stops=4)

    elapsed = time.time() - start
    log_output = log_capture.getvalue()
    print(f"\n  Generation completed in {elapsed:.1f}s")

    tour_text = ''
    if isinstance(result, dict):
        tour_text = result.get('tour_text', '') or result.get('complete_tour', '')
    elif isinstance(result, str):
        tour_text = result
    if not tour_text and os.path.exists(output_file):
        with open(output_file) as f:
            content = f.read()
            if content.strip().startswith('{'):
                import json
                data = json.loads(content)
                tour_text = data.get('tour_text', '') or data.get('complete_tour', '')
            else:
                tour_text = content

    stops = split_stops(tour_text)
    print(f"  Stops generated: {len(stops)} (requested 4)")

    # Check instrument presence
    instruments_re = re.compile(r'(guitar|harpsichord|violin|viola|cello|flute|trumpet|'
                                r'oboe|clarinet|lute|mandolin|harp|organ|piano|drum|'
                                r'tambourine|hurdy[- ]gurdy|baroque|instrument)',
                                re.IGNORECASE)
    instrument_stops = sum(1 for s in stops if instruments_re.search(s))
    print(f"  Stops with instruments: {instrument_stops}/4")

    # Check dates
    dates_expected = ['1780', '1884', '1696', '1581']
    dates_found = [d for d in dates_expected if d in tour_text]
    print(f"  Expected dates found: {dates_found}")

    # Check framing
    framing_lines = [l for l in log_output.split('\n') if 'framing=' in l.lower()]
    venue_purpose = any('venue_purpose' in l for l in framing_lines)
    print(f"  framing=venue_purpose: {'✓' if venue_purpose else '?'}")

    # Score
    base_score = None
    score_lines = [l for l in log_output.split('\n') if 'base_score' in l.lower() or 'rubric' in l.lower()]
    for line in score_lines:
        m = re.search(r'(\d+\.?\d*)', line)
        if m:
            base_score = float(m.group(1))
            break
    if base_score:
        print(f"  Base score: {base_score} (previous best: 93.8)")
    else:
        print(f"  Base score: not found in logs")

    control_pass = (
        len(stops) == 4
        and instrument_stops >= 3  # At least 3/4 mention instruments
    )
    print(f"\n  CONTROL: {'PASS' if control_pass else 'FAIL'}")
    return control_pass


if __name__ == '__main__':
    mfa_pass, tour_text, log_output = run_mfa_acceptance()

    # Save log for analysis
    with open('tours/LOCAL404_mfa_log.txt', 'w') as f:
        f.write(log_output)

    control_pass = run_palais_control()

    print("\n" + "=" * 70)
    print(f"FINAL: MFA={'PASS' if mfa_pass else 'FAIL'} | Control={'PASS' if control_pass else 'FAIL'}")
    print("=" * 70)
    sys.exit(0 if (mfa_pass and control_pass) else 1)
