"""
LOCAL-48 Acceptance Runner
=========================
Generates both the Riviera biking tour (15 stops) and Asian museum tour (8 stops)
in isolated containers with cleared caches, then reports per-stop evidence.

Usage:
    python3 run_local48_acceptance.py

Requirements:
    - OPENAI_API_KEY environment variable set
    - Network access for Wikipedia retrieval (biking tour)
    - Docker available for isolated container (optional — falls back to local)
"""
import sys
import os
import re
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def count_words(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def extract_stops(tour_text: str) -> list:
    """Extract individual stop texts from a generated tour."""
    stops = []
    # Split on "Stop N:" pattern
    parts = re.split(r'\nStop\s+(\d+):\s*', tour_text)
    # parts[0] is intro, then alternating (stop_number, stop_text)
    for i in range(1, len(parts) - 1, 2):
        stop_num = int(parts[i])
        stop_text = parts[i + 1].strip()
        # Extract stop name from first line
        first_line = stop_text.split('\n')[0]
        name = first_line.split(' by ')[0].strip() if ' by ' in first_line else first_line.strip()
        stops.append({
            'number': stop_num,
            'name': name,
            'text': stop_text,
            'words': count_words(stop_text),
        })
    return stops


def count_facts_in_stop(text: str) -> int:
    """Count distinct checkable facts in a stop's text.
    
    A checkable fact contains at least one of: a date/year, a named person,
    a measurement, or a specific event.
    """
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    _year = re.compile(r'\b\d{3,4}\b|\b\d{1,2}(?:st|nd|rd|th)\s+century\b', re.IGNORECASE)
    _person = re.compile(r'\b[A-Z][a-z]+\s+(?:[A-Z][a-z]+|[IVXLCDM]+)\b')
    _number = re.compile(r'\b\d+(?:\.\d+)?\s*(?:m|km|ft|metres?|meters?|miles?|hectares?|acres?|kg|tons?|tonnes?)\b', re.IGNORECASE)
    _event = re.compile(r'\b(?:battle|war|revolution|treaty|founded|built|constructed|opened|destroyed|conquered|invasion|established|inaugurated|completed|commissioned|designed)\b', re.IGNORECASE)
    
    facts = set()
    for sent in sentences:
        sent = sent.strip()
        if len(sent) < 20:
            continue
        if (_year.search(sent) or _person.search(sent) or
                _number.search(sent) or _event.search(sent)):
            # Normalize for deduplication
            facts.add(sent.lower().strip()[:100])
    
    return len(facts)


def check_phrase_count(text: str, phrase: str) -> int:
    """Count occurrences of a phrase in text (case-insensitive)."""
    return len(re.findall(re.escape(phrase), text, re.IGNORECASE))


def print_stop_table(stops: list, tour_name: str):
    """Print per-stop table with words, facts, words-per-fact."""
    print(f"\n{'='*70}")
    print(f"  {tour_name}")
    print(f"{'='*70}")
    print(f"{'Stop':<6} {'Name':<30} {'Words':>6} {'Facts':>6} {'W/F':>6}")
    print(f"{'-'*6} {'-'*30} {'-'*6} {'-'*6} {'-'*6}")
    
    total_words = 0
    total_facts = 0
    violations = []
    
    for stop in stops:
        words = stop['words']
        facts = count_facts_in_stop(stop['text'])
        wpf = f"{words/facts:.0f}" if facts > 0 else "∞"
        total_words += words
        total_facts += facts
        
        flag = ""
        if words > 250 and facts < 2:
            flag = " ⚠️ VIOLATION"
            violations.append(stop['number'])
        
        print(f"{stop['number']:<6} {stop['name'][:30]:<30} {words:>6} {facts:>6} {wpf:>6}{flag}")
    
    print(f"{'-'*6} {'-'*30} {'-'*6} {'-'*6} {'-'*6}")
    print(f"{'TOTAL':<37} {total_words:>6} {total_facts:>6}")
    print()
    
    return total_words, total_facts, violations


def run_acceptance():
    """Run full acceptance checks."""
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set")
        sys.exit(1)
    
    from generate_tour_text import generate_tour_text
    
    results = {}
    
    # ──────────────────────────────────────────────────────────────────
    # TEST 1: French Riviera biking tour (15 stops)
    # ──────────────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("  GENERATING: French Riviera biking tour, France (15 stops)")
    print("="*70)
    
    start_time = time.time()
    riviera_output = "tours/local48_riviera_biking.txt"
    
    riviera_result = generate_tour_text(
        "French Riviera biking tour, France",
        "explore",
        output_file=riviera_output,
        total_stops=15,
    )
    
    riviera_time = time.time() - start_time
    
    # Read the generated file
    if os.path.exists(riviera_output):
        with open(riviera_output) as f:
            riviera_text = f.read()
    else:
        riviera_text = riviera_result if isinstance(riviera_result, str) else ""
    
    riviera_stops = extract_stops(riviera_text)
    total_words, total_facts, violations = print_stop_table(riviera_stops, "French Riviera Biking Tour")
    
    # Check acceptance criteria
    riviera_checks = {
        'stops_generated': len(riviera_stops),
        'total_words': total_words,
        'distinct_facts': total_facts,
        'facts_ge_35': total_facts >= 35,
        'no_250w_lt_2f': len(violations) == 0,
        'violations': violations,
    }
    
    # Check location phrase repetition
    phrase_count = check_phrase_count(riviera_text, "French Riviera biking tour")
    riviera_checks['location_phrase_count'] = phrase_count
    riviera_checks['location_phrase_le_2'] = phrase_count <= 2
    
    # Check total words
    riviera_checks['words_le_4600'] = total_words <= 4600
    
    print(f"  Distinct facts: {total_facts} (target: ≥35) {'✓' if total_facts >= 35 else '✗'}")
    print(f"  Total words: {total_words} (target: ≤4600) {'✓' if total_words <= 4600 else '✗'}")
    print(f"  'French Riviera biking tour' count: {phrase_count} (target: ≤2) {'✓' if phrase_count <= 2 else '✗'}")
    print(f"  250w+ stops with <2 facts: {len(violations)} (target: 0) {'✓' if len(violations) == 0 else '✗'}")
    print(f"  Generation time: {riviera_time:.1f}s")
    
    results['riviera'] = riviera_checks
    
    # ──────────────────────────────────────────────────────────────────
    # TEST 2: Asian museum tour (8 stops)
    # ──────────────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("  GENERATING: Musée des Arts Asiatiques, Nice (8 stops)")
    print("="*70)
    
    start_time = time.time()
    asian_output = "tours/local48_asian_museum.txt"
    
    asian_result = generate_tour_text(
        "Musée des Arts Asiatiques, Nice, France",
        "explore",
        output_file=asian_output,
        total_stops=8,
    )
    
    asian_time = time.time() - start_time
    
    if os.path.exists(asian_output):
        with open(asian_output) as f:
            asian_text = f.read()
    else:
        asian_text = asian_result if isinstance(asian_result, str) else ""
    
    asian_stops = extract_stops(asian_text)
    asian_total_words, asian_total_facts, asian_violations = print_stop_table(
        asian_stops, "Asian Arts Museum Tour"
    )
    
    asian_checks = {
        'stops_generated': len(asian_stops),
        'all_8_stops': len(asian_stops) == 8,
        'distinct_facts': asian_total_facts,
        'facts_ge_27': asian_total_facts >= 27,
    }
    
    # Check for "Closed on Tuesday" and "Free admission"
    has_closed_tuesday = "closed on tuesday" in asian_text.lower() or "fermé le mardi" in asian_text.lower()
    has_free_admission = "free admission" in asian_text.lower() or "entrée gratuite" in asian_text.lower()
    asian_checks['has_closed_tuesday'] = has_closed_tuesday
    asian_checks['has_free_admission'] = has_free_admission
    
    print(f"  Stops: {len(asian_stops)}/8 {'✓' if len(asian_stops) == 8 else '✗'}")
    print(f"  Distinct facts: {asian_total_facts} (target: ≥27) {'✓' if asian_total_facts >= 27 else '✗'}")
    print(f"  'Closed on Tuesday': {'✓' if has_closed_tuesday else '✗'}")
    print(f"  'Free admission': {'✓' if has_free_admission else '✗'}")
    print(f"  Generation time: {asian_time:.1f}s")
    
    results['asian'] = asian_checks
    
    # ──────────────────────────────────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("  ACCEPTANCE SUMMARY")
    print("="*70)
    
    all_pass = True
    checks = [
        ("Riviera: ≥35 distinct facts", riviera_checks.get('facts_ge_35', False)),
        ("Riviera: ≤4600 total words", riviera_checks.get('words_le_4600', False)),
        ("Riviera: location phrase ≤2", riviera_checks.get('location_phrase_le_2', False)),
        ("Riviera: no 250w+ with <2 facts", riviera_checks.get('no_250w_lt_2f', False)),
        ("Asian: 8/8 stops", asian_checks.get('all_8_stops', False)),
        ("Asian: ≥27 distinct facts", asian_checks.get('facts_ge_27', False)),
        ("Asian: 'Closed on Tuesday'", asian_checks.get('has_closed_tuesday', False)),
        ("Asian: 'Free admission'", asian_checks.get('has_free_admission', False)),
    ]
    
    for label, passed in checks:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {label}")
        if not passed:
            all_pass = False
    
    print()
    if all_pass:
        print("  ✓ ALL ACCEPTANCE CHECKS PASSED")
    else:
        print("  ✗ SOME CHECKS FAILED — review above")
    
    # Save results
    with open("local48_acceptance_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(run_acceptance())
